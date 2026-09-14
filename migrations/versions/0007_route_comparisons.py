"""Persist actor-scoped route comparisons and request replay keys."""

import sqlalchemy as sa
from alembic import op

revision = "0007_route_comparisons"
down_revision = "0006_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "route_comparison",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column(
            "corridor_id", sa.String(36), sa.ForeignKey("corridor_version.id"), nullable=False
        ),
        sa.Column("graph_version", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_route_actor_key"),
    )


def downgrade():
    op.drop_table("route_comparison")
