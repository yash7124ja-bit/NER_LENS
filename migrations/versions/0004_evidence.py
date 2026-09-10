"""A-M2-01 immutable source snapshots and evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_evidence"
down_revision = "0003_corridor_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_snapshot",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=128), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("terms_label", sa.String(length=255), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.Column("health", sa.String(length=16), nullable=False),
        sa.Column("supersedes_snapshot_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["supersedes_snapshot_id"], ["source_snapshot.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("raw_value", sa.JSON(), nullable=False),
        sa.Column("units", sa.JSON(), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("segment_id", sa.String(length=36), nullable=True),
        sa.Column("association_method", sa.String(length=32), nullable=True),
        sa.Column("association_distance_m", sa.Float(), nullable=True),
        sa.Column("supersedes_evidence_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshot.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["road_segment.id"]),
        sa.ForeignKeyConstraint(["supersedes_evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_snapshot_id", "evidence", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_snapshot_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("source_snapshot")
