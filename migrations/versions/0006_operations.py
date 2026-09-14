"""Persist operational workflow and explicitly scoped status authority."""

import sqlalchemy as sa
from alembic import op

revision = "0006_operations"
down_revision = "0005_source_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    def ident():
        return sa.Column("id", sa.String(36), primary_key=True)

    def ref(name, target, primary=False):
        return sa.Column(
            name, sa.String(36), sa.ForeignKey(target), nullable=False, primary_key=primary
        )

    def stamp(name, nullable=False):
        return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)

    def payload(name="payload"):
        return sa.Column(name, sa.JSON(), nullable=False)

    op.create_table(
        "status_authority",
        ref("actor_id", "actor.id", True),
        ref("jurisdiction_id", "jurisdiction.id", True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "field_report",
        ident(),
        sa.Column("client_report_id", sa.String(128), unique=True, nullable=False),
        ref("actor_id", "actor.id"),
        ref("segment_id", "road_segment.id"),
        ref("jurisdiction_id", "jurisdiction.id"),
        stamp("received_at"),
        payload(),
        payload("response"),
    )
    op.create_table(
        "evidence_review",
        ident(),
        ref("evidence_id", "field_report.id"),
        ref("actor_id", "actor.id"),
        stamp("created_at"),
        payload(),
    )
    op.create_table(
        "status_decision",
        ident(),
        ref("segment_id", "road_segment.id"),
        ref("jurisdiction_id", "jurisdiction.id"),
        ref("actor_id", "actor.id"),
        stamp("created_at"),
        stamp("effective_at"),
        stamp("valid_until"),
        payload(),
        sa.CheckConstraint("valid_until > effective_at", name="ck_status_interval"),
    )
    op.create_table(
        "mission",
        ident(),
        ref("actor_id", "actor.id"),
        ref("corridor_id", "corridor_version.id"),
        ref("jurisdiction_id", "jurisdiction.id"),
        sa.Column("graph_version_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        stamp("created_at"),
        stamp("started_at", True),
        stamp("completed_at", True),
        payload(),
        sa.CheckConstraint("state IN ('planned','active','completed')", name="ck_mission_state"),
    )
    op.create_table(
        "mission_assignment",
        ref("actor_id", "actor.id", True),
        ref("mission_id", "mission.id", True),
    )
    op.create_table(
        "gps_observation",
        ident(),
        ref("mission_id", "mission.id"),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        stamp("captured_at"),
        stamp("received_at"),
        payload(),
        payload("flags"),
        sa.UniqueConstraint("mission_id", "device_id", "sequence", name="uq_gps_sequence"),
        sa.CheckConstraint("sequence >= 0", name="ck_gps_sequence"),
    )
    op.create_table("mutation_response", ref("id", "idempotency_record.id", True), payload("body"))
    for table, columns in {
        "field_report": ["segment_id", "jurisdiction_id"],
        "evidence_review": ["evidence_id"],
        "status_decision": ["segment_id", "jurisdiction_id"],
        "mission": ["jurisdiction_id"],
        "gps_observation": ["mission_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in (
        "mutation_response",
        "gps_observation",
        "mission_assignment",
        "mission",
        "status_decision",
        "evidence_review",
        "field_report",
        "status_authority",
    ):
        op.drop_table(table)
