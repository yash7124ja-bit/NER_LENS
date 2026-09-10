"""A-M2-01 source snapshots and normalized evidence records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, ForeignKey, String, event
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.corridor.models import Base


class SourceSnapshot(Base):
    __tablename__ = "source_snapshot"
    immutable: ClassVar[bool] = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    terms_label: Mapped[str] = mapped_column(String(255), nullable=False)
    data_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="replay")
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    supersedes_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshot.id")
    )


@event.listens_for(SourceSnapshot, "before_update")
def _reject_snapshot_update(_mapper: Any, _connection: Any, _target: SourceSnapshot) -> None:
    raise ValueError("source snapshots are immutable; record a superseding snapshot")


@event.listens_for(SourceSnapshot, "before_delete")
def _reject_snapshot_delete(_mapper: Any, _connection: Any, _target: SourceSnapshot) -> None:
    raise ValueError("source snapshots are immutable and append-only")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("source_snapshot.id"), nullable=False, index=True
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    units: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    review_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    confidence: Mapped[float | None] = mapped_column()
    segment_id: Mapped[str | None] = mapped_column(ForeignKey("road_segment.id"))
    association_method: Mapped[str | None] = mapped_column(String(32))
    association_distance_m: Mapped[float | None] = mapped_column()
    supersedes_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))
