"""A-M2-02 review/status persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.corridor.models import Base


class StatusDecision(Base):
    __tablename__ = "status_decision"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("road_segment.id"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    jurisdiction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    vehicle_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(2000), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(String(36), nullable=False)


class StatusIdempotency(Base):
    __tablename__ = "status_idempotency"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_decision_id: Mapped[str] = mapped_column(
        ForeignKey("status_decision.id"), nullable=False
    )


class StatusConflict(Base):
    __tablename__ = "status_conflict"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("road_segment.id"), nullable=False, index=True
    )
    existing_decision_id: Mapped[str] = mapped_column(
        ForeignKey("status_decision.id"), nullable=False
    )
    incoming_decision_id: Mapped[str] = mapped_column(
        ForeignKey("status_decision.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
