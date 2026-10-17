import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.ocr import UploadError, candidate_from_text, recognize
from app.rules import RuleError, calculate, finalize, kit_status, parse_expiry, validate_item

DATA = json.loads(Path(__file__).with_name("ds_rules_1.json").read_text())


@pytest.mark.parametrize("r,a,e,u,shortage,replenish,reasons", DATA)
def test_ds_rules_1(r, a, e, u, shortage, replenish, reasons):
    result = calculate(r, a, e, u)
    assert result["shortage_qty"] == shortage
    assert result["replenish_qty"] == replenish
    assert result["reasons"] == reasons
    groups = []
    if e:
        groups.append({"qty": e, "expiry_state": "KNOWN", "input_value": "2026-10-16", "confirmed": True})
    if u:
        groups.append({"qty": u, "expiry_state": "UNKNOWN", "unknown_reason": "UNREADABLE"})
    if a - e - u:
        groups.append({"qty": a - e - u, "expiry_state": "KNOWN", "input_value": "2026-10-17", "confirmed": True})
    item = validate_item({"required_qty": r, "requires_expiry": True}, a, groups, 1, "2026-10-17T00:00:00Z")
    facts, status = finalize([item], "2026-10-17")
    assert facts[0]["reasons"] == reasons
    assert facts[0]["replenish_qty"] == replenish
    assert status == ("PROBLEM" if reasons else "OK")


@pytest.mark.parametrize(
    "value,expected,precision",
    [
        ("29.02.2024", "2024-02-29", "DAY"),
        ("2026-10-17", "2026-10-17", "DAY"),
        ("02/2024", "2024-02-29", "MONTH"),
        ("02/2100", "2100-02-28", "MONTH"),
    ],
)
def test_dates(value, expected, precision):
    result = parse_expiry(value, True)
    assert result["normalized_date"] == expected
    assert result["precision"] == precision


@pytest.mark.parametrize(
    "value", ["29.02.2025", "01.01.26", "2026-13-01", "13/2026", "2026-02-30", "1899-12-31", "2200-01-01", "", "2026-1-1"]
)
def test_invalid_dates(value):
    with pytest.raises(RuleError):
        parse_expiry(value, True)


def test_month_requires_separate_confirmation():
    with pytest.raises(RuleError, match="Подтвердите"):
        parse_expiry("10/2026")


@pytest.mark.parametrize(
    "actual,groups",
    [
        (-1, []),
        (1.5, []),
        (True, []),
        (10000, []),
        (2, []),
        (2, [{"qty": 1, "expiry_state": "UNKNOWN", "unknown_reason": "UNREADABLE"}]),
        (1, [{"qty": 1, "expiry_state": "KNOWN", "input_value": "2026-10-17", "confirmed": False}]),
        (1, [{"qty": 1, "expiry_state": "UNKNOWN"}]),
    ],
)
def test_invalid_facts(actual, groups):
    with pytest.raises(RuleError):
        validate_item({"requires_expiry": True}, actual, groups, 1, "now")


def test_unknown_is_problem_even_without_replenishment():
    assert calculate(1, 4, 0, 1)["reasons"] == ["EXPIRY_UNKNOWN"]
    assert calculate(1, 4, 0, 1)["replenish_qty"] == 0


def test_blank_not_zero():
    with pytest.raises(RuleError):
        finalize([{"actual_qty": None, "checked_at": None}], "2026-10-17")


def test_freshness_independent_from_historical_result():
    kit = SimpleNamespace(interval_days=30, template_id=1)
    template = SimpleNamespace(version=2)
    last = SimpleNamespace(
        inspection_date="2026-09-01",
        result="OK",
        completed_at="2026-09-01T12:00:00Z",
        snapshot={"template_id": 1, "template_version": 1},
        items=[{"groups": [{"expiry_state": "KNOWN", "normalized_date": "2026-09-30", "qty": 1}]}],
    )
    state = kit_status(last, kit, template, "Europe/Moscow", datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert state["last_result"] == "OK"
    assert state["freshness"] == "OVERDUE"
    assert state["warnings"] == ["CONFIG_CHANGED", "EXPIRED_SINCE"]


def test_due_date_boundary():
    kit = SimpleNamespace(interval_days=30, template_id=1)
    last = SimpleNamespace(
        inspection_date="2026-09-17",
        result="OK",
        completed_at="2026-09-17T12:00:00Z",
        snapshot={"template_id": 1, "template_version": 1},
        items=[],
    )
    state = kit_status(last, kit, SimpleNamespace(version=1), "UTC", datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert state["freshness"] == "CURRENT"


@pytest.mark.parametrize(
    "text,status,value",
    [
        ("EXP 31.12.2027", "CANDIDATE", "31.12.2027"),
        ("MFG 01.01.2025 EXP 01.01.2027", "CANDIDATE", "01.01.2027"),
        ("01.01.2025 01.01.2027", "AMBIGUOUS", None),
        ("EXP 31.02.2027", "AMBIGUOUS", None),
        ("MFG 01.01.2025", "AMBIGUOUS", None),
        ("EXP 01.01.27", "NOT_READ", None),
        ("Unreadable", "NOT_READ", None),
        ("EXP 02/2028", "CANDIDATE", "02/2028"),
    ],
)
def test_ocr_parser(text, status, value):
    result = candidate_from_text(text)
    assert result["status"] == status
    if value:
        assert result["candidate"]["input_value"] == value


@pytest.mark.parametrize(
    "data,code",
    [
        (b"<svg/>", "UNSUPPORTED_IMAGE"),
        (b"%PDF-1.0", "UNSUPPORTED_IMAGE"),
        (b"\x89PNG\r\n\x1a\ncorrupt", "INVALID_IMAGE"),
        (b"x" * (5 * 1024 * 1024 + 1), "FILE_TOO_LARGE"),
    ],
)
def test_upload_rejection(data, code):
    with pytest.raises(UploadError) as error:
        recognize(data)
    assert error.value.code == code
