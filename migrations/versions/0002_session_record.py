"""A-M1-02 session expiry/revocation record.

Revision ID: 0002_session_record
Revises: 0001_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_session_record"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("token_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_record_actor_id", "session_record", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_session_record_actor_id", table_name="session_record")
    op.drop_table("session_record")
