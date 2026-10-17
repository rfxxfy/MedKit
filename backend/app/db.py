"""Small relational core; inspection facts are immutable JSON snapshots."""

import os
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./medkit.db")
engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_setup(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(100))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class Kit(Base):
    __tablename__ = "kits"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    public_code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    interval_days: Mapped[int] = mapped_column(default=30)
    archived: Mapped[bool] = mapped_column(default=False)


class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    kit_id: Mapped[int] = mapped_column(ForeignKey("kits.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    lifecycle: Mapped[str] = mapped_column(String(20), default="DRAFT")
    revision: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inspection_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    cancellation_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    __table_args__ = (
        Index(
            "one_draft_per_kit",
            "kit_id",
            unique=True,
            sqlite_where=text("lifecycle = 'DRAFT'"),
            postgresql_where=text("lifecycle = 'DRAFT'"),
        ),
        Index("inspection_history", "org_id", "kit_id", "completed_at"),
    )


def init_db() -> None:
    Base.metadata.create_all(engine)
