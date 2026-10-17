import asyncio
import hashlib
import io
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from starlette.exceptions import HTTPException

from .db import Inspection, Kit, Organization, Session, SessionLocal, Template, TemplateVersion, User, init_db
from .ocr import UploadError, recognize
from .reports import render_report
from .rules import RuleError, finalize, kit_status, validate_item
from .schemas import Cancel, ItemInput, KitInput, Login, Revision, TemplateInput

logger = logging.getLogger("medkit")
logging.basicConfig(level=logging.INFO, format="%(message)s")
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8010").rstrip("/")
ALLOWED_ORIGINS = set(
    os.getenv("ALLOWED_ORIGINS", "http://localhost:8010,http://127.0.0.1:8010,http://localhost:5173,http://127.0.0.1:5173").split(",")
)
SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
login_failures: dict[str, deque[float]] = defaultdict(deque)
ocr_requests: dict[int, deque[float]] = defaultdict(deque)
ocr_slots = asyncio.Semaphore(1)
ocr_pending = 0


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return now().isoformat()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="MedKit Inspector", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next: Any) -> Response:
    request.state.request_id = secrets.token_hex(8)
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        # No request bodies, user names, OCR text or secrets in logs.
        response = error_response(request, 500, "INTERNAL_ERROR", "Ошибка сервера. Сохранённые данные не потеряны; повторите запрос.")
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
    )
    if request.url.path in {"/docs", "/redoc"}:
        # FastAPI's documentation UI loads its assets from this HTTPS CDN.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
        )
    logger.info(
        json.dumps(
            {
                "request_id": request.state.request_id,
                "code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )
    )
    return response


def error_response(request: Request, status: int, code: str, message: str, fields: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "field_errors": fields or [], "request_id": getattr(request.state, "request_id", "")},
    )


@app.exception_handler(APIError)
async def api_error(request: Request, exc: APIError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message)


@app.exception_handler(RuleError)
async def rule_error(request: Request, exc: RuleError) -> JSONResponse:
    return error_response(request, 422, "INVALID_FACTS", str(exc))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return error_response(request, 422, "VALIDATION_ERROR", "Проверьте заполнение полей.", fields)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))


def db_session():
    with SessionLocal() as db:
        yield db


DB = Annotated[DBSession, Depends(db_session)]


def check_origin(request: Request) -> None:
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise APIError(403, "ORIGIN_REJECTED", "Недопустимый адрес сайта. Откройте приложение по настроенному адресу.")


def current_user(request: Request, db: DB) -> User:
    token = request.cookies.get("medkit_session", "")
    session = db.get(Session, digest(token))
    current = now().replace(tzinfo=None)
    if not session or current > session.expires_at or current - session.last_seen_at > timedelta(minutes=30):
        raise APIError(401, "UNAUTHENTICATED", "Войдите в систему.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise APIError(401, "UNAUTHENTICATED", "Войдите в систему.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise APIError(403, "CSRF_FAILED", "Обновите страницу и повторите действие.")
    session.last_seen_at = current
    db.commit()
    request.state.csrf = session.csrf
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def admin(user: User) -> None:
    if user.role != "ADMIN":
        raise APIError(403, "FORBIDDEN", "Действие доступно администратору.")


def scoped(db: DBSession, model: Any, object_id: int, user: User, lock: bool = False) -> Any:
    query = select(model).where(model.id == object_id, model.org_id == user.org_id)
    if lock:
        query = query.with_for_update()
    obj = db.scalar(query)
    if obj is None:
        raise APIError(404, "NOT_FOUND", "Объект не найден.")
    return obj


def editable(inspection: Inspection, user: User, revision: int) -> None:
    if inspection.owner_id != user.id:
        raise APIError(403, "NOT_OWNER", "Можно изменять только свой черновик.")
    if inspection.lifecycle != "DRAFT":
        raise APIError(409, "IMMUTABLE", "Проверка закрыта. Начните новую проверку.")
    if inspection.revision != revision:
        raise APIError(409, "REVISION_CONFLICT", "Черновик изменён в другой вкладке. Обновите данные и повторите ввод.")


def serialize(inspection: Inspection) -> dict[str, Any]:
    return {
        k: getattr(inspection, k)
        for k in [
            "id",
            "kit_id",
            "owner_id",
            "lifecycle",
            "revision",
            "started_at",
            "completed_at",
            "inspection_date",
            "result",
            "snapshot",
            "items",
            "cancellation_reason",
        ]
    }


def atomic_change(db: DBSession, inspection: Inspection, revision: int, **values: Any) -> Inspection:
    changed = db.execute(
        update(Inspection)
        .where(Inspection.id == inspection.id, Inspection.revision == revision, Inspection.lifecycle == "DRAFT")
        .values(**values, revision=revision + 1),
        execution_options={"synchronize_session": False},
    )
    if cast(CursorResult, changed).rowcount != 1:
        db.rollback()
        db.refresh(inspection)
        if values.get("lifecycle") == "COMPLETED" and inspection.lifecycle == "COMPLETED":
            return inspection
        raise APIError(409, "REVISION_CONFLICT", "Данные изменились. Обновите страницу.")
    db.commit()
    db.refresh(inspection)
    return inspection


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: DB) -> Response:
    try:
        db.execute(text("SELECT id FROM organizations LIMIT 1"))
        return JSONResponse({"status": "ready", "schema": 1})
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


@app.post("/api/v1/auth/login")
def login(body: Login, request: Request, response: Response, db: DB) -> dict[str, Any]:
    check_origin(request)
    key = digest(f"{request.client.host if request.client else ''}:{body.email.lower()}")
    attempts = login_failures[key]
    timestamp = time.monotonic()
    while attempts and attempts[0] < timestamp - 900:
        attempts.popleft()
    if len(attempts) >= 10:
        raise APIError(429, "LOGIN_RATE_LIMIT", "Слишком много попыток. Повторите через 15 минут.")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    verified: bool
    try:
        verified = hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except VerificationError:
        verified = False
    if not verified or not user or not user.active:
        attempts.append(timestamp)
        raise APIError(401, "LOGIN_FAILED", "Неверная почта или пароль.")
    login_failures.pop(key, None)
    old = request.cookies.get("medkit_session")
    if old:
        db.execute(delete(Session).where(Session.token_hash == digest(old)))
    secret = secrets.token_urlsafe(32)
    current = now().replace(tzinfo=None)
    session = Session(
        token_hash=digest(secret),
        user_id=user.id,
        csrf=secrets.token_urlsafe(32),
        created_at=current,
        last_seen_at=current,
        expires_at=current + timedelta(hours=8),
    )
    db.add(session)
    db.commit()
    response.set_cookie("medkit_session", secret, httponly=True, secure=SECURE, samesite="lax", max_age=8 * 3600, path="/")
    return user_payload(user, db, session.csrf)


def user_payload(user: User, db: DBSession, csrf: str) -> dict[str, Any]:
    org = db.get(Organization, user.org_id)
    assert org is not None, "User organization is enforced by foreign key"
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "organization": {"name": org.name, "timezone": org.timezone},
        "csrf_token": csrf,
    }


@app.get("/api/v1/auth/session")
def session_info(request: Request, db: DB, user: CurrentUser) -> dict[str, Any]:
    return user_payload(user, db, request.state.csrf)


@app.post("/api/v1/auth/logout", status_code=204)
def logout(request: Request, db: DB) -> Response:
    token = request.cookies.get("medkit_session", "")
    session = db.get(Session, digest(token))
    if session:
        current = now().replace(tzinfo=None)
        active = current <= session.expires_at and current - session.last_seen_at <= timedelta(minutes=30)
        if active:
            check_origin(request)
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
                raise APIError(403, "CSRF_FAILED", "Обновите страницу и повторите действие.")
        db.execute(delete(Session).where(Session.token_hash == digest(token)))
        db.commit()
    response = Response(status_code=204)
    response.delete_cookie("medkit_session", path="/", httponly=True, samesite="lax", secure=SECURE)
    return response


@app.get("/api/v1/templates")
def list_templates(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return [template_payload(t, db) for t in db.scalars(select(Template).where(Template.org_id == user.org_id).order_by(Template.id))]


def template_payload(template: Template, db: DBSession) -> dict[str, Any]:
    version = db.get(TemplateVersion, (template.id, template.version))
    assert version is not None, "Template version is created atomically"
    return {"id": template.id, "name": template.name, "version": template.version, "items": version.items}


@app.post("/api/v1/templates", status_code=201)
def create_template(body: TemplateInput, db: DB, user: CurrentUser) -> dict[str, Any]:
    admin(user)
    template = Template(org_id=user.org_id, name=body.name, version=1)
    db.add(template)
    db.flush()
    db.add(TemplateVersion(template_id=template.id, version=1, items=[{**i.model_dump(), "id": n + 1} for n, i in enumerate(body.items)]))
    db.commit()
    return template_payload(template, db)


@app.post("/api/v1/templates/{template_id}/versions", status_code=201)
def new_template_version(template_id: int, body: TemplateInput, db: DB, user: CurrentUser) -> dict[str, Any]:
    admin(user)
    template = scoped(db, Template, template_id, user, lock=True)
    template.version += 1
    template.name = body.name
    db.add(
        TemplateVersion(
            template_id=template.id, version=template.version, items=[{**i.model_dump(), "id": n + 1} for n, i in enumerate(body.items)]
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise APIError(409, "VERSION_CONFLICT", "Шаблон уже обновлён. Загрузите актуальную версию.") from None
    return template_payload(template, db)


def kit_payload(kit: Kit, db: DBSession) -> dict[str, Any]:
    template = db.get(Template, kit.template_id)
    org = db.get(Organization, kit.org_id)
    assert template is not None and org is not None, "Kit references are enforced by foreign keys"
    last = db.scalar(
        select(Inspection)
        .where(Inspection.kit_id == kit.id, Inspection.lifecycle == "COMPLETED")
        .order_by(Inspection.completed_at.desc(), Inspection.id.desc())
        .limit(1)
    )
    draft = db.scalar(select(Inspection).where(Inspection.kit_id == kit.id, Inspection.lifecycle == "DRAFT"))
    return {
        "id": kit.id,
        "name": kit.name,
        "location": kit.location,
        "public_code": kit.public_code,
        "interval_days": kit.interval_days,
        "archived": kit.archived,
        "template_id": kit.template_id,
        "template_name": template.name,
        "template_version": template.version,
        "draft_id": draft.id if draft else None,
        "draft_owner_id": draft.owner_id if draft else None,
        "draft_revision": draft.revision if draft else None,
        **kit_status(last, kit, template, org.timezone, now()),
    }


@app.get("/api/v1/kits")
def list_kits(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return [kit_payload(k, db) for k in db.scalars(select(Kit).where(Kit.org_id == user.org_id).order_by(Kit.id))]


@app.get("/api/v1/kits/by-code/{code}")
def kit_by_code(code: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    kit = db.scalar(select(Kit).where(Kit.public_code == code, Kit.org_id == user.org_id))
    if not kit:
        raise APIError(404, "NOT_FOUND", "Аптечка не найдена.")
    return kit_payload(kit, db)


@app.get("/api/v1/kits/{kit_id}")
def get_kit(kit_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    return kit_payload(scoped(db, Kit, kit_id, user), db)


@app.post("/api/v1/kits", status_code=201)
def create_kit(body: KitInput, db: DB, user: CurrentUser) -> dict[str, Any]:
    admin(user)
    scoped(db, Template, body.template_id, user)
    kit = Kit(org_id=user.org_id, public_code=secrets.token_urlsafe(18), **body.model_dump())
    db.add(kit)
    db.commit()
    return kit_payload(kit, db)


@app.patch("/api/v1/kits/{kit_id}")
def edit_kit(kit_id: int, body: KitInput, db: DB, user: CurrentUser) -> dict[str, Any]:
    admin(user)
    kit = scoped(db, Kit, kit_id, user, lock=True)
    if kit.archived:
        raise APIError(409, "ARCHIVED", "Аптечка в архиве.")
    scoped(db, Template, body.template_id, user)
    for key, value in body.model_dump().items():
        setattr(kit, key, value)
    db.commit()
    return kit_payload(kit, db)


@app.post("/api/v1/kits/{kit_id}/archive")
def archive_kit(kit_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    admin(user)
    kit = scoped(db, Kit, kit_id, user, lock=True)
    if db.scalar(select(Inspection).where(Inspection.kit_id == kit.id, Inspection.lifecycle == "DRAFT")):
        raise APIError(409, "ACTIVE_INSPECTION", "Сначала завершите или отмените черновик.")
    kit.archived = True
    db.commit()
    return kit_payload(kit, db)


@app.get("/api/v1/kits/{kit_id}/qr")
def qr(kit_id: int, db: DB, user: CurrentUser) -> Response:
    kit = scoped(db, Kit, kit_id, user)
    output = io.BytesIO()
    qrcode.make(f"{BASE_URL}/q/{kit.public_code}").save(output, format="PNG")
    return Response(
        output.getvalue(), media_type="image/png", headers={"Content-Disposition": f'inline; filename="medkit-{kit.id}-qr.png"'}
    )


@app.post("/api/v1/kits/{kit_id}/inspections")
def start_inspection(kit_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    kit = scoped(db, Kit, kit_id, user, lock=True)
    if kit.archived:
        raise APIError(409, "ARCHIVED", "Аптечка в архиве; доступна только история.")
    existing = db.scalar(select(Inspection).where(Inspection.kit_id == kit.id, Inspection.lifecycle == "DRAFT"))
    if existing:
        if existing.owner_id != user.id:
            raise APIError(409, "ACTIVE_INSPECTION", "Аптечку уже проверяет другой сотрудник.")
        return serialize(existing)
    template = db.get(Template, kit.template_id)
    assert template is not None, "Kit template is enforced by foreign key"
    version = db.get(TemplateVersion, (template.id, template.version))
    org = db.get(Organization, user.org_id)
    assert org is not None and version is not None, "Snapshot references must exist"
    inspection = Inspection(
        org_id=user.org_id,
        kit_id=kit.id,
        owner_id=user.id,
        started_at=stamp(),
        snapshot={
            "organization_name": org.name,
            "kit_name": kit.name,
            "location": kit.location,
            "inspector_name": user.display_name,
            "timezone": org.timezone,
            "interval_days": kit.interval_days,
            "template_id": template.id,
            "template_name": template.name,
            "template_version": template.version,
        },
        items=[{**i, "source_item_id": i["id"], "actual_qty": None, "checked_at": None, "groups": []} for i in version.items],
    )
    db.add(inspection)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise APIError(409, "ACTIVE_INSPECTION", "Проверка уже начата. Обновите страницу.") from None
    return serialize(inspection)


@app.get("/api/v1/inspections/{inspection_id}")
def get_inspection(inspection_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    inspection = scoped(db, Inspection, inspection_id, user)
    if inspection.lifecycle == "DRAFT" and inspection.owner_id != user.id:
        raise APIError(403, "NOT_OWNER", "Доступен только собственный черновик.")
    return serialize(inspection)


@app.put("/api/v1/inspections/{inspection_id}/items/{item_id}")
def save_item(inspection_id: int, item_id: int, body: ItemInput, db: DB, user: CurrentUser) -> dict[str, Any]:
    inspection = scoped(db, Inspection, inspection_id, user, lock=True)
    editable(inspection, user, body.expected_revision)
    item = next((i for i in inspection.items if i["id"] == item_id), None)
    if item is None:
        raise APIError(404, "NOT_FOUND", "Позиция не найдена.")
    saved = validate_item(item, body.actual_qty, [g.model_dump() for g in body.groups], user.id, stamp())
    items = [saved if i["id"] == item_id else i for i in inspection.items]
    return serialize(atomic_change(db, inspection, body.expected_revision, items=items))


@app.post("/api/v1/inspections/{inspection_id}/complete")
def complete(inspection_id: int, body: Revision, db: DB, user: CurrentUser) -> dict[str, Any]:
    inspection = scoped(db, Inspection, inspection_id, user, lock=True)
    if inspection.owner_id != user.id:
        raise APIError(403, "NOT_OWNER", "Завершить проверку может только её владелец.")
    if inspection.lifecycle == "COMPLETED":
        return serialize(inspection)
    editable(inspection, user, body.expected_revision)
    completed = now()
    date_string = completed.astimezone(ZoneInfo(inspection.snapshot["timezone"])).date().isoformat()
    items, result = finalize(inspection.items, date_string)
    return serialize(
        atomic_change(
            db,
            inspection,
            body.expected_revision,
            items=items,
            result=result,
            inspection_date=date_string,
            completed_at=completed.isoformat(),
            lifecycle="COMPLETED",
        )
    )


@app.post("/api/v1/inspections/{inspection_id}/cancel")
def cancel(inspection_id: int, body: Cancel, db: DB, user: CurrentUser) -> dict[str, Any]:
    inspection = scoped(db, Inspection, inspection_id, user, lock=True)
    if inspection.owner_id != user.id and user.role != "ADMIN":
        raise APIError(403, "NOT_OWNER", "Отменить проверку может владелец или администратор.")
    if inspection.lifecycle != "DRAFT" or inspection.revision != body.expected_revision:
        raise APIError(409, "REVISION_CONFLICT", "Состояние проверки изменилось. Обновите данные.")
    return serialize(atomic_change(db, inspection, body.expected_revision, lifecycle="CANCELLED", cancellation_reason=body.reason))


@app.get("/api/v1/kits/{kit_id}/inspections")
def history(kit_id: int, db: DB, user: CurrentUser, page: int = 1, cancelled: bool = False) -> dict[str, Any]:
    scoped(db, Kit, kit_id, user)
    if page < 1:
        raise APIError(422, "INVALID_PAGE", "Номер страницы начинается с 1.")
    query = (
        select(Inspection)
        .where(Inspection.kit_id == kit_id, Inspection.lifecycle == ("CANCELLED" if cancelled else "COMPLETED"))
        .order_by(Inspection.completed_at.desc(), Inspection.id.desc())
        .offset((page - 1) * 20)
        .limit(21)
    )
    records = list(db.scalars(query))
    return {"page": page, "page_size": 20, "has_next": len(records) > 20, "items": [serialize(i) for i in records[:20]]}


@app.get("/api/v1/inspections/{inspection_id}/report.pdf")
def report(inspection_id: int, db: DB, user: CurrentUser) -> Response:
    inspection = scoped(db, Inspection, inspection_id, user)
    if inspection.lifecycle != "COMPLETED":
        raise APIError(409, "NOT_COMPLETED", "Отчёт доступен только после завершения проверки.")
    return Response(
        render_report(inspection),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="medkit-inspection-{inspection.id}.pdf"'},
    )


@app.post("/api/v1/inspections/{inspection_id}/items/{item_id}/ocr")
async def ocr(inspection_id: int, item_id: int, file: UploadFile, db: DB, user: CurrentUser) -> dict[str, Any]:
    global ocr_pending
    inspection = scoped(db, Inspection, inspection_id, user)
    editable(inspection, user, inspection.revision)
    if not any(i["id"] == item_id for i in inspection.items):
        raise APIError(404, "NOT_FOUND", "Позиция не найдена.")
    requests = ocr_requests[user.id]
    current = time.monotonic()
    while requests and requests[0] < current - 60:
        requests.popleft()
    if len(requests) >= 10 or ocr_pending >= 3:
        raise APIError(429, "OCR_BUSY", "Распознавание занято. Повторите позже или введите дату вручную.")
    requests.append(current)
    data = await file.read(5 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 5 * 1024 * 1024:
        raise APIError(413, "FILE_TOO_LARGE", "Максимальный размер — 5 MiB.")
    ocr_pending += 1
    try:
        async with ocr_slots:
            return await asyncio.to_thread(recognize, data)
    except UploadError as exc:
        raise APIError(exc.status, exc.code, str(exc)) from exc
    finally:
        ocr_pending -= 1
        del data


# Same origin in production; Vite proxies the API during development.
DIST = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")))
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> Response:
    if path.startswith("api/"):
        raise APIError(404, "NOT_FOUND", "Метод API не найден.")
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return JSONResponse({"message": "Run frontend build or open http://localhost:5173", "docs": "/docs"})
