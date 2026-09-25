"""Store owner replies to reviewer clarification requests."""

import sqlalchemy as sa
from alembic import op

revision = "0013_field_clarifications"
down_revision = "0012_driver_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "field_clarification",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("field_report.id"), nullable=False),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("evidence_review.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(4000), nullable=False),
        sa.UniqueConstraint("review_id", name="uq_clarification_review"),
    )
    op.create_index("ix_field_clarification_evidence_id", "field_clarification", ["evidence_id"])


def downgrade():
    op.drop_index("ix_field_clarification_evidence_id", "field_clarification")
    op.drop_table("field_clarification")
