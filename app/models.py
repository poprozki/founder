from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="free")

    contacts_used: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    sender_name: Mapped[str] = mapped_column(String(120), default="")
    sender_offer: Mapped[str] = mapped_column(
        String(255), default="сайты и WhatsApp-воронки")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    runs: Mapped[list["Run"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    templates: Mapped[list["Template"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    city_slug: Mapped[str] = mapped_column(String(64))
    city_name: Mapped[str] = mapped_column(String(120))
    niche: Mapped[str] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(String(24), default="pending")
    stage: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(Text, default="")

    requested: Mapped[int] = mapped_column(Integer, default=10)
    hot_only: Mapped[bool] = mapped_column(Boolean, default=False)

    total_in_city: Mapped[int] = mapped_column(Integer, default=0)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    hot_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="runs")
    leads: Mapped[list["Lead"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Lead.id")

class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("run_id", "org_id", name="uq_run_org"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)

    org_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(300))
    extension: Mapped[str] = mapped_column(String(300), default="")
    rubric: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(300), default="")

    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    phones_json: Mapped[str] = mapped_column(Text, default="[]")
    email: Mapped[str] = mapped_column(String(255), default="")
    website: Mapped[str] = mapped_column(String(500), default="")
    instagram: Mapped[str] = mapped_column(String(500), default="")
    whatsapp: Mapped[str] = mapped_column(String(500), default="")
    telegram: Mapped[str] = mapped_column(String(500), default="")

    has_site: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False)
    card_scraped: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="leads")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan")

    @property
    def phones(self) -> list[str]:
        try:
            return json.loads(self.phones_json or "[]")
        except Exception:
            return []

    @phones.setter
    def phones(self, value: list[str]) -> None:
        self.phones_json = json.dumps(list(dict.fromkeys(value)), ensure_ascii=False)

    @property
    def primary_phone(self) -> str:
        ph = self.phones
        return ph[0] if ph else ""

    @property
    def wa_number(self) -> str:
        import re
        if self.whatsapp:
            m = re.search(r"(\d{10,15})", self.whatsapp)
            if m:
                return m.group(1)
        p = self.primary_phone
        return "".join(ch for ch in p if ch.isdigit())

    @property
    def display_title(self) -> str:
        return f"{self.name}, {self.extension}" if self.extension else self.name

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)

    angle: Mapped[str] = mapped_column(String(32), default="auto")
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="local")
    sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="messages")

class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="templates")

class SavedList(Base):
    __tablename__ = "saved_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("runs.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
