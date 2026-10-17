"""BR-04..BR-14: pure calculations, independent of HTTP and persistence."""

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


class RuleError(ValueError):
    pass


def parse_expiry(value: str, month_confirmed: bool = False) -> dict[str, Any]:
    value = value.strip()
    try:
        if re.fullmatch(r"\d{2}/\d{4}", value):
            month, year = map(int, value.split("/"))
            if not month_confirmed:
                raise RuleError("Подтвердите правило последнего дня месяца отдельно.")
            expiry = date(year, month, calendar.monthrange(year, month)[1])
            precision, policy = "MONTH", "MONTH_END_V1"
        elif re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            expiry = datetime.strptime(value, "%d.%m.%Y").date()
            precision, policy = "DAY", None
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            expiry = date.fromisoformat(value)
            precision, policy = "DAY", None
        else:
            raise ValueError
        if not 1900 <= expiry.year <= 2199:
            raise ValueError
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, RuleError):
            raise
        raise RuleError("Введите реальную дату: ДД.ММ.ГГГГ, ГГГГ-ММ-ДД или ММ/ГГГГ (1900–2199).") from exc
    return {"input_value": value, "normalized_date": expiry.isoformat(), "precision": precision, "policy": policy}


def validate_item(item: dict[str, Any], actual: int, groups: list[dict[str, Any]], user_id: int, now: str) -> dict[str, Any]:
    if type(actual) is not int or not 0 <= actual <= 9999:
        raise RuleError("Количество должно быть целым числом от 0 до 9999.")
    if (not item["requires_expiry"] or actual == 0) and groups:
        raise RuleError("Для этой позиции группы сроков не нужны.")
    if item["requires_expiry"] and actual > 0:
        if not 1 <= len(groups) <= 20 or sum(g["qty"] for g in groups) != actual:
            raise RuleError("Сумма 1–20 групп сроков должна совпадать с фактическим количеством.")
    normalized = []
    for group in groups:
        if type(group["qty"]) is not int or not 1 <= group["qty"] <= 9999:
            raise RuleError("Количество группы должно быть положительным целым числом.")
        base = {"qty": group["qty"], "expiry_state": group["expiry_state"], "confirmed_by": user_id, "confirmed_at": now}
        if group["expiry_state"] == "UNKNOWN":
            if group.get("unknown_reason") not in {"UNREADABLE", "NO_MARK", "AMBIGUOUS"}:
                raise RuleError("Укажите причину неизвестного срока.")
            if group.get("input_value"):
                raise RuleError("У неизвестного срока не может быть даты.")
            base.update(unknown_reason=group["unknown_reason"])
        elif group["expiry_state"] == "KNOWN":
            if not group.get("confirmed"):
                raise RuleError("Подтвердите каждую дату.")
            if group.get("unknown_reason"):
                raise RuleError("Для известной даты причина неизвестного срока недопустима.")
            base.update(parse_expiry(group.get("input_value", ""), group.get("month_end_confirmed", False)))
            base["source"] = group.get("source", "MANUAL")
        else:
            raise RuleError("Неизвестное состояние срока.")
        normalized.append(base)
    return {**item, "actual_qty": actual, "groups": normalized, "checked_at": now}


def calculate(required: int, actual: int, expired: int, unknown: int) -> dict[str, Any]:
    shortage = max(required - actual, 0)
    eligible = actual - expired - unknown
    return {
        "shortage_qty": shortage,
        "expired_qty": expired,
        "unknown_qty": unknown,
        "eligible_qty": eligible,
        "replenish_qty": max(required - eligible, 0),
        "reasons": [reason for reason, qty in [("SHORTAGE", shortage), ("EXPIRED", expired), ("EXPIRY_UNKNOWN", unknown)] if qty > 0],
    }


def finalize(items: list[dict[str, Any]], inspection_date: str) -> tuple[list[dict[str, Any]], str]:
    result = []
    for item in items:
        if item.get("checked_at") is None or item.get("actual_qty") is None:
            raise RuleError("Подтвердите все позиции перед завершением.")
        expired = sum(g["qty"] for g in item["groups"] if g["expiry_state"] == "KNOWN" and g["normalized_date"] < inspection_date)
        unknown = sum(g["qty"] for g in item["groups"] if g["expiry_state"] == "UNKNOWN")
        result.append({**item, **calculate(item["required_qty"], item["actual_qty"], expired, unknown)})
    return result, "PROBLEM" if any(i["reasons"] for i in result) else "OK"


def kit_status(last: Any, kit: Any, template: Any, timezone: str, now: datetime) -> dict[str, Any]:
    if not last:
        return {"last_result": "NEVER_CHECKED", "freshness": "NEVER_CHECKED", "warnings": [], "due_date": None, "last_completed_at": None}
    today = now.astimezone(ZoneInfo(timezone)).date()
    due = date.fromisoformat(last.inspection_date) + timedelta(days=kit.interval_days)
    warnings = []
    if last.snapshot["template_id"] != kit.template_id or last.snapshot["template_version"] != template.version:
        warnings.append("CONFIG_CHANGED")
    if any(
        g["expiry_state"] == "KNOWN" and last.inspection_date <= g["normalized_date"] < today.isoformat()
        for i in last.items
        for g in i["groups"]
    ):
        warnings.append("EXPIRED_SINCE")
    return {
        "last_result": last.result,
        "freshness": "CURRENT" if today <= due else "OVERDUE",
        "warnings": warnings,
        "due_date": due.isoformat(),
        "last_completed_at": last.completed_at,
    }
