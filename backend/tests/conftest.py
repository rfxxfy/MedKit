import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"
os.environ["BASE_URL"] = "http://testserver"

import pytest
from app import db as database
from app import main
from app.db import Base, Organization, Template, TemplateVersion, User
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def setup_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = database.sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "init_db", lambda: None)
    main.login_failures.clear()
    main.ocr_requests.clear()
    with factory() as db:
        org = Organization(name="Учебная организация", timezone="Europe/Moscow")
        other = Organization(name="Чужая организация", timezone="UTC")
        db.add_all([org, other])
        db.flush()
        password_hash = main.hasher.hash("TestPassword2026!")
        db.add_all(
            [
                User(org_id=org.id, email="admin@test.ru", display_name="Админ", role="ADMIN", active=True, password_hash=password_hash),
                User(
                    org_id=org.id,
                    email="inspector@test.ru",
                    display_name="Инспектор",
                    role="INSPECTOR",
                    active=True,
                    password_hash=password_hash,
                ),
                User(org_id=other.id, email="other@test.ru", display_name="Чужой", role="ADMIN", active=True, password_hash=password_hash),
            ]
        )
        for o in [org, other]:
            template = Template(org_id=o.id, name="Учебный шаблон", version=1)
            db.add(template)
            db.flush()
            db.add(
                TemplateVersion(
                    template_id=template.id,
                    version=1,
                    items=[
                        {"id": 1, "name": "Бинт", "unit": "шт.", "required_qty": 4, "requires_expiry": True},
                        {"id": 2, "name": "Ножницы", "unit": "шт.", "required_qty": 1, "requires_expiry": False},
                    ],
                )
            )
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(setup_db):
    with TestClient(main.app) as client:
        yield client


def login(client, email="admin@test.ru"):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "TestPassword2026!"}, headers={"origin": "http://testserver"}
    )
    assert response.status_code == 200, response.text
    client.headers.update({"origin": "http://testserver", "x-csrf-token": response.json()["csrf_token"]})
    return response.json()


@pytest.fixture()
def auth(client):
    login(client)
    return client


@pytest.fixture()
def kit(auth):
    response = auth.post("/api/v1/kits", json={"name": "Корпус А", "location": "1 этаж", "template_id": 1, "interval_days": 30})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def draft(auth, kit):
    return auth.post(f"/api/v1/kits/{kit['id']}/inspections").json()


def fill(auth, draft, actual=4, groups=None):
    if groups is None:
        groups = [{"qty": actual, "expiry_state": "KNOWN", "input_value": "2099-12-31", "confirmed": True}] if actual else []
    response = auth.put(
        f"/api/v1/inspections/{draft['id']}/items/1",
        json={"expected_revision": draft["revision"], "actual_qty": actual, "confirmed": True, "groups": groups},
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    response = auth.put(
        f"/api/v1/inspections/{draft['id']}/items/2",
        json={"expected_revision": draft["revision"], "actual_qty": 1, "confirmed": True, "groups": []},
    )
    assert response.status_code == 200, response.text
    return response.json()
