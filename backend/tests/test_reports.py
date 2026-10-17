from types import SimpleNamespace

from app.reports import render_report


def test_pdf_large_expiry_groups_split_across_pages():
    groups = [
        {
            "qty": 1,
            "expiry_state": "KNOWN",
            "input_value": "12/2099",
            "normalized_date": "2099-12-31",
            "precision": "MONTH",
            "source": "MANUAL",
            "confirmed_by": 1,
            "confirmed_at": "2026-10-17T12:00:00+00:00",
        }
        for _ in range(20)
    ]
    item = {
        "name": "Бинт " * 20,
        "unit": "шт.",
        "groups": groups,
        "required_qty": 20,
        "actual_qty": 20,
        "shortage_qty": 0,
        "expired_qty": 0,
        "unknown_qty": 0,
        "replenish_qty": 0,
        "reasons": [],
    }
    inspection = SimpleNamespace(
        id=1,
        inspection_date="2026-10-17",
        started_at="2026-10-17T12:00:00Z",
        completed_at="2026-10-17T12:05:00Z",
        result="OK",
        items=[item] * 50,
        snapshot={
            "organization_name": "Организация",
            "kit_name": "Аптечка",
            "location": "Корпус",
            "inspector_name": "Инспектор",
            "timezone": "Europe/Moscow",
            "template_name": "Шаблон",
            "template_version": 1,
            "interval_days": 30,
        },
    )
    pdf = render_report(inspection)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 30_000
