"""Persist candidate impacts of road decisions on selected mission baselines."""

import sqlalchemy as sa
from alembic import op

revision = "0014_mission_impacts"
down_revision = "0013_field_clarifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mission_impact",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corridor_id", sa.String(36), sa.ForeignKey("corridor_version.id"), nullable=False
        ),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("mission.id"), nullable=False),
        sa.Column(
            "decision_id", sa.String(36), sa.ForeignKey("status_decision.id"), nullable=False
        ),
        sa.Column(
            "route_selection_id", sa.String(36), sa.ForeignKey("route_selection.id"), nullable=False
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "mission_id", "decision_id", "route_selection_id", name="uq_mission_impact_basis"
        ),
    )
    op.create_index("ix_mission_impact_corridor_id", "mission_impact", ["corridor_id"])
    op.create_index("ix_mission_impact_mission_id", "mission_impact", ["mission_id"])


def downgrade():
    op.drop_index("ix_mission_impact_mission_id", "mission_impact")
    op.drop_index("ix_mission_impact_corridor_id", "mission_impact")
    op.drop_table("mission_impact")
