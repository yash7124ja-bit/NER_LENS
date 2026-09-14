"""A-M1-01 identity, jurisdiction, audit, and idempotency tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.corridor.models import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Jurisdiction(Base):
    __tablename__ = "jurisdiction"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Actor(Base):
    __tablename__ = "actor"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_subject: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    active: Mapped[bool] = mapped_column(nullable=False, default=True)


class SessionRecord(Base):
    __tablename__ = "session_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), nullable=False, index=True)
    token_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def is_valid(self, now: datetime) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return self.active and self.revoked_at is None and now < expires_at


class LocalAccount(Base):
    __tablename__ = "local_account"

    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)


class LoginThrottle(Base):
    __tablename__ = "login_throttle"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class RoleAssignment(Base):
    __tablename__ = "role_assignment"
    __table_args__ = (
        UniqueConstraint("actor_id", "role", "jurisdiction_id", name="uq_actor_role_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdiction.id"))


class AuditEvent(Base):
    __tablename__ = "audit_event"
    immutable: ClassVar[bool] = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("actor.id"))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdiction.id"))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "method", "path", "idempotency_key", name="uq_idempotency_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
