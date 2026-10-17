"""Operator-only account management. Passwords never travel in command arguments."""

import argparse
import getpass
import secrets
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select

from .db import Inspection, Kit, Organization, Session, SessionLocal, Template, TemplateVersion, User, init_db
from .main import hasher, now
from .rules import finalize, validate_item

DEMO_PASSWORD = "MedkitDemo2026!"
DEMO_ITEMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Бинт марлевый стерильный", "unit": "шт.", "required_qty": 4, "requires_expiry": True},
    {"id": 2, "name": "Салфетки антисептические", "unit": "уп.", "required_qty": 4, "requires_expiry": True},
    {"id": 3, "name": "Перчатки медицинские", "unit": "пара", "required_qty": 2, "requires_expiry": True},
    {"id": 4, "name": "Лейкопластырь рулонный", "unit": "шт.", "required_qty": 2, "requires_expiry": True},
    {"id": 5, "name": "Ножницы для перевязок", "unit": "шт.", "required_qty": 1, "requires_expiry": False},
    {"id": 6, "name": "Маска медицинская", "unit": "шт.", "required_qty": 2, "requires_expiry": True},
]


def seed_demo() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "admin@medkit.demo")):
            print("Демонстрационные данные уже существуют.")
            return
        org = Organization(name="Кампус · демоорганизация", timezone="Europe/Moscow")
        db.add(org)
        db.flush()
        admin = User(
            org_id=org.id,
            email="admin@medkit.demo",
            display_name="Алина Хорст",
            role="ADMIN",
            active=True,
            password_hash=hasher.hash(DEMO_PASSWORD),
        )
        inspector = User(
            org_id=org.id,
            email="inspector@medkit.demo",
            display_name="Демо-инспектор",
            role="INSPECTOR",
            active=True,
            password_hash=hasher.hash(DEMO_PASSWORD),
        )
        db.add_all([admin, inspector])
        template = Template(org_id=org.id, name="Базовая аптечка · учебный состав", version=1)
        db.add(template)
        db.flush()
        db.add(TemplateVersion(template_id=template.id, version=1, items=DEMO_ITEMS))
        names = [
            ("Главный корпус", "1 этаж · рядом с ресепшен", "problem"),
            ("Лаборатория", "2 этаж · кабинет 204", "ok"),
            ("Спортивный зал", "1 этаж · тренерская", "overdue"),
            ("Библиотека", "3 этаж · стойка администратора", "never"),
        ]
        for name, location, scenario in names:
            kit = Kit(
                org_id=org.id,
                public_code=secrets.token_urlsafe(18),
                name=name,
                location=location,
                template_id=template.id,
                interval_days=30,
            )
            db.add(kit)
            db.flush()
            if scenario == "never":
                continue
            completed = now() - timedelta(days=40 if scenario == "overdue" else 2)
            day = completed.astimezone(ZoneInfo(org.timezone)).date()
            items = []
            for entry in DEMO_ITEMS:
                actual = entry["required_qty"]
                if scenario == "problem" and entry["id"] == 1:
                    actual = 2
                groups = []
                if entry["requires_expiry"]:
                    if scenario == "problem" and entry["id"] == 3:
                        groups = [{"qty": actual, "expiry_state": "UNKNOWN", "unknown_reason": "UNREADABLE"}]
                    else:
                        expiry = day + timedelta(days=-5 if scenario == "problem" and entry["id"] == 2 else 365)
                        groups = [{"qty": actual, "expiry_state": "KNOWN", "input_value": expiry.isoformat(), "confirmed": True}]
                items.append(validate_item(entry, actual, groups, admin.id, completed.isoformat()))
            facts, result = finalize(items, day.isoformat())
            snapshot = {
                "organization_name": org.name,
                "kit_name": name,
                "location": location,
                "inspector_name": admin.display_name,
                "timezone": org.timezone,
                "interval_days": 30,
                "template_id": template.id,
                "template_name": template.name,
                "template_version": 1,
            }
            db.add(
                Inspection(
                    org_id=org.id,
                    kit_id=kit.id,
                    owner_id=admin.id,
                    lifecycle="COMPLETED",
                    revision=8,
                    started_at=(completed - timedelta(minutes=4)).isoformat(),
                    completed_at=completed.isoformat(),
                    inspection_date=day.isoformat(),
                    result=result,
                    snapshot=snapshot,
                    items=facts,
                )
            )
        db.commit()
        print("Демо создано. Аккаунты: admin@medkit.demo / inspector@medkit.demo")
        print("Учебный пароль: " + DEMO_PASSWORD)


def main() -> None:
    parser = argparse.ArgumentParser(description="MedKit operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed-demo")
    org = sub.add_parser("create-org")
    org.add_argument("--name", required=True)
    org.add_argument("--timezone", required=True)
    user = sub.add_parser("create-user")
    user.add_argument("--org-id", type=int, required=True)
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--role", choices=["ADMIN", "INSPECTOR"], required=True)
    for command in ["reset-password", "disable-user"]:
        p = sub.add_parser(command)
        p.add_argument("--email", required=True)
    args = parser.parse_args()
    init_db()
    if args.command == "init-db":
        print("Схема v1 создана (идемпотентная начальная миграция).")
        return
    if args.command == "seed-demo":
        seed_demo()
        return
    with SessionLocal() as db:
        if args.command == "create-org":
            try:
                ZoneInfo(args.timezone)
            except ZoneInfoNotFoundError:
                parser.error("Неизвестный часовой пояс IANA")
            if not 1 <= len(args.name.strip()) <= 100:
                parser.error("Название должно содержать 1–100 символов")
            organization = Organization(name=args.name.strip(), timezone=args.timezone)
            db.add(organization)
            db.commit()
            print(f"Организация #{organization.id} создана.")
            return
        if args.command == "create-user":
            if not db.get(Organization, args.org_id):
                parser.error("Организация не найдена")
            if db.scalar(select(User).where(User.email == args.email.lower())):
                parser.error("Почта уже занята")
            if not 1 <= len(args.name.strip()) <= 100 or "@" not in args.email or len(args.email) > 254:
                parser.error("Некорректное имя или почта")
            account = User(org_id=args.org_id, email=args.email.lower(), display_name=args.name.strip(), role=args.role, active=True)
            db.add(account)
        else:
            existing_account = db.scalar(select(User).where(User.email == args.email.lower()))
            if not existing_account:
                parser.error("Аккаунт не найден")
            account = existing_account
        if args.command in {"create-user", "reset-password"}:
            password = getpass.getpass("Пароль (12–128 символов): ")
            if not 12 <= len(password) <= 128:
                parser.error("Неверная длина пароля")
            if password != getpass.getpass("Повторите пароль: "):
                parser.error("Пароли не совпадают")
            account.password_hash = hasher.hash(password)
        if args.command == "disable-user":
            account.active = False
        if account.id:
            db.execute(delete(Session).where(Session.user_id == account.id))
        db.commit()
        print("Готово. Прежние сессии отозваны.")


if __name__ == "__main__":
    main()
