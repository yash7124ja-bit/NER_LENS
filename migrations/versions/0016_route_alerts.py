"""Persist route alert delivery and assigned-driver acknowledgment separately."""

import sqlalchemy as sa
from alembic import op

revision = "0016_route_alerts"
down_revision = "0015_route_change_approvals"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("route_change_approval") as batch:
        batch.drop_constraint("uq_route_change_impact", type_="unique")
    op.create_table(
        "route_alert",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "approval_id", sa.String(36), sa.ForeignKey("route_change_approval.id"), nullable=False
        ),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("mission.id"), nullable=False),
        sa.Column("recipient_actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("approval_id", name="uq_route_alert_approval"),
    )
    op.create_index("ix_route_alert_mission_id", "route_alert", ["mission_id"])
    op.create_index("ix_route_alert_recipient_actor_id", "route_alert", ["recipient_actor_id"])
    op.create_table(
        "alert_delivery_attempt",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("route_alert.id"), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("alert_id", "channel", name="uq_alert_delivery_channel"),
    )
    op.create_index("ix_alert_delivery_attempt_alert_id", "alert_delivery_attempt", ["alert_id"])
    op.create_table(
        "alert_acknowledgment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("route_alert.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selection_id", sa.String(36), sa.ForeignKey("route_selection.id")),
        sa.UniqueConstraint("alert_id", name="uq_alert_acknowledgment"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_alert_ack_actor_key"),
    )


def downgrade():
    duplicate = op.get_bind().execute(sa.text(
        "SELECT impact_id FROM route_change_approval GROUP BY impact_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Cannot restore the one-approval schema while renewed approvals exist; "
            "restore the prior database backup instead"
        )
    op.drop_table("alert_acknowledgment")
    op.drop_index("ix_alert_delivery_attempt_alert_id", "alert_delivery_attempt")
    op.drop_table("alert_delivery_attempt")
    op.drop_index("ix_route_alert_recipient_actor_id", "route_alert")
    op.drop_index("ix_route_alert_mission_id", "route_alert")
    op.drop_table("route_alert")
    with op.batch_alter_table("route_change_approval") as batch:
        batch.create_unique_constraint("uq_route_change_impact", ["impact_id"])
