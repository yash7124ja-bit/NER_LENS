"""Store dispatcher approval without activating a route before driver acknowledgment."""

import sqlalchemy as sa
from alembic import op

revision = "0015_route_change_approvals"
down_revision = "0014_mission_impacts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "route_change_approval",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("impact_id", sa.String(36), sa.ForeignKey("mission_impact.id"), nullable=False),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("mission.id"), nullable=False),
        sa.Column(
            "comparison_id", sa.String(36), sa.ForeignKey("route_comparison.id"), nullable=False
        ),
        sa.Column("route_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("impact_id", name="uq_route_change_impact"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_route_change_actor_key"),
    )
    op.create_index("ix_route_change_approval_mission_id", "route_change_approval", ["mission_id"])


def downgrade():
    op.drop_index("ix_route_change_approval_mission_id", "route_change_approval")
    op.drop_table("route_change_approval")
