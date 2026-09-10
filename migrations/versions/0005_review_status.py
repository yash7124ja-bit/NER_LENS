"""A-M2-02 evidence review and operational status workflow."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_review_status"
down_revision = "0004_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_review",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=False),
        sa.Column("merge_into_evidence_id", sa.String(length=36), nullable=True),
        sa.Column("resulting_state", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=False),
        sa.Column("after_hash", sa.String(length=64), nullable=False),
        sa.Column("audit_event_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["merge_into_evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_review_evidence_id", "evidence_review", ["evidence_id"])
    op.create_table(
        "review_idempotency",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["evidence_review.id"]),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_review_idempotency_actor_key"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "status_decision",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("vehicle_scope", sa.JSON(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_event_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["road_segment.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_decision_segment_id", "status_decision", ["segment_id"])
    op.create_table(
        "status_idempotency",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_decision_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["status_decision_id"], ["status_decision.id"]),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_status_idempotency_actor_key"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "status_conflict",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("existing_decision_id", sa.String(length=36), nullable=False),
        sa.Column("incoming_decision_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["road_segment.id"]),
        sa.ForeignKeyConstraint(["existing_decision_id"], ["status_decision.id"]),
        sa.ForeignKeyConstraint(["incoming_decision_id"], ["status_decision.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_conflict_segment_id", "status_conflict", ["segment_id"])


def downgrade() -> None:
    op.drop_index("ix_status_conflict_segment_id", table_name="status_conflict")
    op.drop_table("status_conflict")
    op.drop_table("status_idempotency")
    op.drop_index("ix_status_decision_segment_id", table_name="status_decision")
    op.drop_table("status_decision")
    op.drop_table("review_idempotency")
    op.drop_index("ix_evidence_review_evidence_id", table_name="evidence_review")
    op.drop_table("evidence_review")
