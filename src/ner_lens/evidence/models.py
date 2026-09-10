"""A-M2-01 source snapshots and normalized evidence records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DDL, JSON, DateTime, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.corridor.models import Base


class SourceSnapshot(Base):
    __tablename__ = "source_snapshot"
    __table_args__ = (
        UniqueConstraint("source", "content_sha256", name="uq_snapshot_source_sha256"),
    )
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


@event.listens_for(Evidence, "before_update")
def _reject_evidence_update(_mapper: Any, _connection: Any, _target: Evidence) -> None:
    raise ValueError("evidence facts are immutable; record a revision or association")


@event.listens_for(Evidence, "before_delete")
def _reject_evidence_delete(_mapper: Any, _connection: Any, _target: Evidence) -> None:
    raise ValueError("evidence facts are immutable and append-only")


for _table in (SourceSnapshot.__table__, Evidence.__table__):
    _table_name = _table.name
    event.listen(
        _table,
        "after_create",
        DDL(
            f"CREATE TRIGGER guard_{_table_name}_update BEFORE UPDATE ON {_table_name} "
            "BEGIN SELECT RAISE(ABORT, 'append_only_record'); END"
        ).execute_if(dialect="sqlite"),
    )
    event.listen(
        _table,
        "after_create",
        DDL(
            f"CREATE TRIGGER guard_{_table_name}_delete BEFORE DELETE ON {_table_name} "
            "BEGIN SELECT RAISE(ABORT, 'append_only_record'); END"
        ).execute_if(dialect="sqlite"),
    )


class EvidenceReview(Base):
    __tablename__ = "evidence_review"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(String(2000), nullable=False)
    merge_into_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))
    resulting_state: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    before_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    after_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(ForeignKey("audit_event.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(EvidenceReview, "before_update")
def _reject_review_update(_mapper: Any, _connection: Any, _target: EvidenceReview) -> None:
    raise ValueError("evidence reviews are immutable and append-only")


@event.listens_for(EvidenceReview, "before_delete")
def _reject_review_delete(_mapper: Any, _connection: Any, _target: EvidenceReview) -> None:
    raise ValueError("evidence reviews are immutable and append-only")


class EvidenceAssociation(Base):
    __tablename__ = "evidence_association"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("road_segment.id"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    distance_m: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(EvidenceAssociation, "before_update")
def _reject_association_update(
    _mapper: Any, _connection: Any, _target: EvidenceAssociation
) -> None:
    raise ValueError("evidence associations are immutable and append-only")


@event.listens_for(EvidenceAssociation, "before_delete")
def _reject_association_delete(
    _mapper: Any, _connection: Any, _target: EvidenceAssociation
) -> None:
    raise ValueError("evidence associations are immutable and append-only")


class ReviewIdempotency(Base):
    __tablename__ = "review_idempotency"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_review_idempotency_actor_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_id: Mapped[str] = mapped_column(ForeignKey("evidence_review.id"), nullable=False)
