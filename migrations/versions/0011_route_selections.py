"""Persist dispatcher planning-baseline choices for missions."""

import sqlalchemy as sa
from alembic import op

revision = "0011_route_selections"
down_revision = "0010_delivery_assignments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "route_selection",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("mission.id"), nullable=False),
        sa.Column(
            "comparison_id", sa.String(36), sa.ForeignKey("route_comparison.id"), nullable=False
        ),
        sa.Column("route_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_route_selection_actor_key"),
    )
    op.create_index("ix_route_selection_mission_id", "route_selection", ["mission_id"])


def downgrade():
    op.drop_index("ix_route_selection_mission_id", "route_selection")
    op.drop_table("route_selection")
