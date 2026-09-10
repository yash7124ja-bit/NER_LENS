"""A-M1-01 foundation tables.

Revision ID: 0001_foundation
Revises:

This revision is intentionally explicit. It must not materialize tables from
the current ORM metadata because later revisions may add models.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from ner_lens.corridor.models import Geometry4326

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "corridor_version",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("corridor_key", sa.String(length=128), nullable=False),
        sa.Column("graph_version", sa.String(length=128), nullable=False),
        sa.Column("graph_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded')", name="ck_corridor_version_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "jurisdiction",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "actor",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_subject"),
    )
    op.create_table(
        "road_segment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("corridor_version_id", sa.String(length=36), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column("segment_type", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("geometry", Geometry4326(), nullable=False),
        sa.Column("vehicle_constraints", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["corridor_version_id"], ["corridor_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "corridor_version_id",
            "external_ref",
            "direction",
            name="uq_segment_external_ref_direction",
        ),
        sa.CheckConstraint(
            "segment_type IN ('road', 'bridge', 'tunnel', 'approach')",
            name="ck_road_segment_type",
        ),
        sa.CheckConstraint(
            "direction IN ('both', 'forward', 'backward', 'forward_only', 'backward_only')",
            name="ck_road_segment_direction",
        ),
    )
    op.create_index("ix_road_segment_corridor_version_id", "road_segment", ["corridor_version_id"])
    op.create_table(
        "role_assignment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"]),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdiction.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "role", "jurisdiction_id", name="uq_actor_role_scope"),
    )
    op.create_index("ix_role_assignment_actor_id", "role_assignment", ["actor_id"])
    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jurisdiction_id", sa.String(length=36), nullable=True),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"]),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdiction.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "idempotency_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_id", "method", "path", "idempotency_key", name="uq_idempotency_scope"
        ),
    )
    op.create_index("ix_idempotency_record_actor_id", "idempotency_record", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_record_actor_id", table_name="idempotency_record")
    op.drop_table("idempotency_record")
    op.drop_table("audit_event")
    op.drop_index("ix_role_assignment_actor_id", table_name="role_assignment")
    op.drop_table("role_assignment")
    op.drop_index("ix_road_segment_corridor_version_id", table_name="road_segment")
    op.drop_table("road_segment")
    op.drop_table("actor")
    op.drop_table("jurisdiction")
    op.drop_table("corridor_version")
