from datetime import datetime, timedelta, timezone

import pytest
from app.db import Inspection, Session, User
from conftest import fill, login
from sqlalchemy import select


def test_auth_and_csrf(client):
    assert client.get("/api/v1/kits").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "x", "password": "x"}).status_code == 403
    login(client)
    client.headers.pop("x-csrf-token")
    assert client.post("/api/v1/kits", json={"name": "X", "location": "X", "template_id": 1, "interval_days": 1}).status_code == 403


def test_logout_revokes_session(auth):
    cookie = auth.cookies.get("medkit_session")
    assert auth.post("/api/v1/auth/logout").status_code == 204
    auth.cookies.set("medkit_session", cookie)
    assert auth.get("/api/v1/auth/session").status_code == 401
    auth.cookies.clear()
    assert auth.post("/api/v1/auth/logout").status_code == 204


def test_rate_limit(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/v1/auth/login", headers={"origin": "http://testserver"}, json={"email": "nobody@test.ru", "password": "x"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login", headers={"origin": "http://testserver"}, json={"email": "nobody@test.ru", "password": "x"}
        ).status_code
        == 429
    )


def test_roles_and_isolation(auth, kit, draft):
    login(auth, "inspector@test.ru")
    assert auth.post("/api/v1/kits", json={"name": "X", "location": "X", "template_id": 1, "interval_days": 1}).status_code == 403
    assert auth.get(f"/api/v1/inspections/{draft['id']}").status_code == 403
    assert auth.post(f"/api/v1/kits/{kit['id']}/inspections").status_code == 409
    login(auth, "other@test.ru")
    for path in [
        f"/kits/{kit['id']}",
        f"/kits/{kit['id']}/qr",
        f"/kits/by-code/{kit['public_code']}",
        f"/inspections/{draft['id']}",
        f"/inspections/{draft['id']}/report.pdf",
    ]:
        assert auth.get("/api/v1" + path).status_code == 404
    assert auth.post("/api/v1/kits", json={"name": "X", "location": "X", "template_id": 1, "interval_days": 1}).status_code == 404


def test_revision_and_single_draft(auth, kit, draft):
    assert auth.post(f"/api/v1/kits/{kit['id']}/inspections").json()["id"] == draft["id"]
    saved = fill(auth, draft)
    response = auth.put(
        f"/api/v1/inspections/{draft['id']}/items/2", json={"expected_revision": draft["revision"], "actual_qty": 9, "confirmed": True}
    )
    assert response.status_code == 409
    assert auth.get(f"/api/v1/inspections/{draft['id']}").json() == saved


def test_incomplete_cannot_complete(auth, draft):
    assert auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": draft["revision"]}).status_code == 422
    assert auth.get(f"/api/v1/inspections/{draft['id']}/report.pdf").status_code == 409


@pytest.mark.parametrize(
    "actual,groups,expected",
    [
        (4, None, "OK"),
        (0, [], "PROBLEM"),
        (
            3,
            [
                {"qty": 1, "expiry_state": "KNOWN", "input_value": "2000-01-01", "confirmed": True},
                {"qty": 1, "expiry_state": "UNKNOWN", "unknown_reason": "NO_MARK"},
                {"qty": 1, "expiry_state": "KNOWN", "input_value": "2099-01-01", "confirmed": True},
            ],
            "PROBLEM",
        ),
    ],
)
def test_completion_idempotent_and_immutable(auth, draft, actual, groups, expected):
    saved = fill(auth, draft, actual, groups)
    response = auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": saved["revision"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["result"] == expected
    assert auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": 1}).json() == result
    assert (
        auth.put(
            f"/api/v1/inspections/{draft['id']}/items/2", json={"expected_revision": result["revision"], "actual_qty": 9, "confirmed": True}
        ).status_code
        == 409
    )
    if actual == 3:
        assert result["items"][0]["replenish_qty"] == 3
        assert result["items"][0]["reasons"] == ["SHORTAGE", "EXPIRED", "EXPIRY_UNKNOWN"]


def test_snapshot_survives_renaming_new_template_archive_and_pdf(auth, kit, draft, setup_db):
    saved = fill(auth, draft)
    result = auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": saved["revision"]}).json()
    version = auth.post(
        "/api/v1/templates/1/versions",
        json={"name": "Новый шаблон", "items": [{"name": "Другая позиция", "unit": "шт.", "required_qty": 9, "requires_expiry": False}]},
    )
    assert version.status_code == 201
    assert (
        auth.patch(
            f"/api/v1/kits/{kit['id']}", json={"name": "Переименовано", "location": "2 этаж", "interval_days": 20, "template_id": 1}
        ).status_code
        == 200
    )
    assert auth.get(f"/api/v1/kits/{kit['id']}").json()["warnings"] == ["CONFIG_CHANGED"]
    assert auth.post(f"/api/v1/kits/{kit['id']}/archive").status_code == 200
    assert auth.get(f"/api/v1/inspections/{draft['id']}").json() == result
    pdf = auth.get(f"/api/v1/inspections/{draft['id']}/report.pdf")
    assert pdf.status_code == 200, pdf.text[:100] if pdf.status_code != 200 else ""
    assert pdf.content.startswith(b"%PDF-")
    assert len(pdf.content) > 5000
    assert auth.post(f"/api/v1/kits/{kit['id']}/inspections").status_code == 409
    with setup_db() as db:
        stored = db.get(Inspection, draft["id"])
        assert stored.snapshot["kit_name"] == "Корпус А"
        assert stored.snapshot["template_version"] == 1


def test_cancel_ownership_reason_and_reopen(auth, kit, draft):
    assert auth.post(f"/api/v1/kits/{kit['id']}/archive").status_code == 409
    login(auth, "inspector@test.ru")
    assert auth.post(f"/api/v1/inspections/{draft['id']}/cancel", json={"expected_revision": 1, "reason": "test"}).status_code == 403
    login(auth)
    assert auth.post(f"/api/v1/inspections/{draft['id']}/cancel", json={"expected_revision": 1, "reason": " "}).status_code == 422
    assert (
        auth.post(f"/api/v1/inspections/{draft['id']}/cancel", json={"expected_revision": 1, "reason": "Ошибочный старт"}).status_code
        == 200
    )
    assert auth.get(f"/api/v1/kits/{kit['id']}/inspections?cancelled=true").json()["items"][0]["lifecycle"] == "CANCELLED"
    assert auth.get(f"/api/v1/kits/{kit['id']}").json()["last_result"] == "NEVER_CHECKED"
    new = auth.post(f"/api/v1/kits/{kit['id']}/inspections")
    assert new.status_code == 200
    assert new.json()["id"] != draft["id"]


def test_date_based_on_completion_timezone(auth, draft, monkeypatch, setup_db):
    import app.main as main

    saved = fill(auth, draft, 4, [{"qty": 4, "expiry_state": "KNOWN", "input_value": "2026-10-17", "confirmed": True}])
    with setup_db() as db:
        session = db.scalar(select(Session))
        session.created_at = datetime(2026, 10, 17, 20, 0)
        session.last_seen_at = datetime(2026, 10, 17, 21, 0)
        session.expires_at = datetime(2026, 10, 18, 4, 0)
        db.commit()
    monkeypatch.setattr(main, "now", lambda: datetime(2026, 10, 17, 21, 5, tzinfo=timezone.utc))
    response = auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": saved["revision"]})
    # Existing test session is time bound to real execution date. Move its window for this controlled clock.
    if response.status_code == 401:
        pytest.fail("Test clock must remain within the fixture session; update the session fixture clock")
    assert response.json()["inspection_date"] == "2026-10-18"
    assert response.json()["items"][0]["expired_qty"] == 4


def test_invalid_nested_item_and_upload(auth, draft):
    path = f"/api/v1/inspections/{draft['id']}/items/999"
    assert auth.put(path, json={"expected_revision": 1, "actual_qty": 1, "confirmed": True}).status_code == 404
    assert auth.post(path + "/ocr", files={"file": ("x.png", b"bad", "image/png")}).status_code == 404
    path = f"/api/v1/inspections/{draft['id']}/items/1/ocr"
    assert auth.post(path, files={"file": ("x.png", b"<svg/>", "image/png")}).status_code == 415
    assert auth.post(path, files={"file": ("x.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")}).status_code == 413


def test_invalid_quantity_and_unconfirmed_month(auth, draft):
    path = f"/api/v1/inspections/{draft['id']}/items/1"
    for qty in [None, -1, 10000, 1.5, True]:
        assert auth.put(path, json={"expected_revision": 1, "actual_qty": qty, "confirmed": True}).status_code == 422
    assert (
        auth.put(
            path,
            json={
                "expected_revision": 1,
                "actual_qty": 1,
                "confirmed": True,
                "groups": [{"qty": 1, "expiry_state": "KNOWN", "input_value": "10/2026", "confirmed": True}],
            },
        ).status_code
        == 422
    )


def test_session_expiry_and_disabled_user(auth, setup_db):
    with setup_db() as db:
        session = db.scalar(select(Session))
        session.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=31)
        db.commit()
    assert auth.get("/api/v1/kits").status_code == 401
    login(auth)
    with setup_db() as db:
        db.scalar(select(User).where(User.email == "admin@test.ru")).active = False
        db.commit()
    assert auth.get("/api/v1/kits").status_code == 401


def test_health_and_error_contract(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    error = client.get("/api/v1/nope")
    assert error.status_code == 404
    assert set(error.json()) == {"code", "message", "field_errors", "request_id"}
    assert error.headers["x-request-id"] == error.json()["request_id"]
    assert "default-src" in error.headers["content-security-policy"]


def test_failed_commit_rolls_back_completion(auth, draft, monkeypatch, setup_db):
    import app.main as main
    from sqlalchemy import event

    saved = fill(auth, draft)
    original = main.atomic_change

    def failing_change(db, inspection, revision, **values):
        db.info["fail_completion_commit"] = True
        return original(db, inspection, revision, **values)

    def fail_commit(db):
        if db.info.get("fail_completion_commit"):
            raise RuntimeError("Synthetic commit failure")

    event.listen(setup_db.class_, "before_commit", fail_commit)
    monkeypatch.setattr(main, "atomic_change", failing_change)
    try:
        response = auth.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": saved["revision"]})
        assert response.status_code == 500
    finally:
        event.remove(setup_db.class_, "before_commit", fail_commit)
    restored = auth.get(f"/api/v1/inspections/{draft['id']}").json()
    assert restored == saved
    assert restored["completed_at"] is None


def test_logout_expired_session_is_safe(auth, setup_db):
    with setup_db() as db:
        db.scalar(select(Session)).expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert auth.post("/api/v1/auth/logout").status_code == 204
