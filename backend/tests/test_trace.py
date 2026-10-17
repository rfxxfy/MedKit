import json

from app import main
from app.db import Base, Inspection, Organization, Template, TemplateVersion, User
from conftest import fill, login
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def test_trace_100_survives_engine_restart(client, monkeypatch, tmp_path):
    """TRACE-01: persist 100 API-created snapshots, reopen storage and read each."""
    db_path = tmp_path / "trace.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(Organization(id=1, name="TRACE", timezone="Europe/Moscow"))
        db.flush()
        db.add(
            User(
                id=1,
                org_id=1,
                email="admin@test.ru",
                display_name="TRACE inspector",
                password_hash=main.hasher.hash("TestPassword2026!"),
                role="ADMIN",
                active=True,
            )
        )
        db.add(Template(id=1, org_id=1, name="TRACE template", version=1))
        db.flush()
        db.add(
            TemplateVersion(
                template_id=1,
                version=1,
                items=[
                    {"id": 1, "name": "Бинт", "unit": "шт.", "required_qty": 4, "requires_expiry": True},
                    {"id": 2, "name": "Ножницы", "unit": "шт.", "required_qty": 1, "requires_expiry": False},
                ],
            )
        )
        db.commit()
    monkeypatch.setattr(main, "SessionLocal", factory)
    login(client)
    kit = client.post("/api/v1/kits", json={"name": "TRACE kit", "location": "Lab", "template_id": 1, "interval_days": 30}).json()
    originals = {}
    for index in range(100):
        draft = client.post(f"/api/v1/kits/{kit['id']}/inspections").json()
        saved = fill(client, draft, 4 if index % 2 else 0)
        response = client.post(f"/api/v1/inspections/{draft['id']}/complete", json={"expected_revision": saved["revision"]})
        assert response.status_code == 200
        result = response.json()
        assert all(
            result.get(key) is not None
            for key in ["owner_id", "started_at", "completed_at", "inspection_date", "result", "snapshot", "items"]
        )
        assert all(item["checked_at"] and "reasons" in item and "replenish_qty" in item for item in result["items"])
        originals[result["id"]] = result
    engine.dispose()
    reopened = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(reopened, expire_on_commit=False))
    for inspection_id, original in originals.items():
        assert client.get(f"/api/v1/inspections/{inspection_id}").json() == original
    assert len(client.get(f"/api/v1/kits/{kit['id']}/inspections").json()["items"]) == 20
    assert client.get(f"/api/v1/kits/{kit['id']}/inspections?page=5").json()["has_next"] is False
    assert client.get(f"/api/v1/kits/{kit['id']}/inspections?page=0").status_code == 422
    with reopened.connect() as conn:
        assert len(conn.execute(select(Inspection.id)).all()) == 100
    (tmp_path / "trace-results.json").write_text(json.dumps({"count": 100, "equal_after_reopen": 100}))
    reopened.dispose()
