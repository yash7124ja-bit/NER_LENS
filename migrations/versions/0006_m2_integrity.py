"""A-M2 corrective integrity: append-only association and SQLite guards."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_m2_integrity"
down_revision = "0005_review_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_snapshot") as batch:
        batch.create_unique_constraint("uq_snapshot_source_sha256", ["source", "content_sha256"])
    op.create_table(
        "evidence_association",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["road_segment.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_association_evidence_id", "evidence_association", ["evidence_id"])
    op.create_index("ix_evidence_association_segment_id", "evidence_association", ["segment_id"])
    if op.get_bind().dialect.name == "sqlite":
        for table in ("source_snapshot", "evidence", "audit_event"):
            op.execute(
                f"CREATE TRIGGER guard_{table}_update BEFORE UPDATE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'append_only_record'); END"
            )
            op.execute(
                f"CREATE TRIGGER guard_{table}_delete BEFORE DELETE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'append_only_record'); END"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in ("source_snapshot", "evidence", "audit_event"):
            op.execute(f"DROP TRIGGER IF EXISTS guard_{table}_delete")
            op.execute(f"DROP TRIGGER IF EXISTS guard_{table}_update")
    op.drop_index("ix_evidence_association_segment_id", table_name="evidence_association")
    op.drop_index("ix_evidence_association_evidence_id", table_name="evidence_association")
    op.drop_table("evidence_association")
    with op.batch_alter_table("source_snapshot") as batch:
        batch.drop_constraint("uq_snapshot_source_sha256", type_="unique")
