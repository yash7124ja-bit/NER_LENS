"""A-M1-03 corridor provenance and authority fields.

Revision ID: 0003_corridor_import
Revises: 0002_session_record
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_corridor_import"
down_revision = "0002_session_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    corridor_columns = {column["name"] for column in inspector.get_columns("corridor_version")}
    segment_columns = {column["name"] for column in inspector.get_columns("road_segment")}
    if "source_url" not in corridor_columns:
        op.add_column(
            "corridor_version", sa.Column("source_url", sa.String(length=512), nullable=True)
        )
    if "provenance_label" not in corridor_columns:
        op.add_column(
            "corridor_version",
            sa.Column(
                "provenance_label", sa.String(length=32), nullable=False, server_default="replay"
            ),
        )
    if "route_buffer_km" not in corridor_columns:
        op.add_column(
            "corridor_version",
            sa.Column("route_buffer_km", sa.Float(), nullable=False, server_default="5"),
        )
    if "hazard_context_buffer_km" not in corridor_columns:
        op.add_column(
            "corridor_version",
            sa.Column("hazard_context_buffer_km", sa.Float(), nullable=False, server_default="20"),
        )
    if "authority_ref" not in segment_columns:
        op.add_column(
            "road_segment", sa.Column("authority_ref", sa.String(length=255), nullable=True)
        )
    if "source_url" in corridor_columns:
        op.alter_column("corridor_version", "source_url", nullable=False)
    if "provenance_label" in corridor_columns:
        op.alter_column("corridor_version", "provenance_label", server_default=None)
    if "route_buffer_km" in corridor_columns:
        op.alter_column("corridor_version", "route_buffer_km", server_default=None)
    if "hazard_context_buffer_km" in corridor_columns:
        op.alter_column("corridor_version", "hazard_context_buffer_km", server_default=None)


def downgrade() -> None:
    op.drop_column("road_segment", "authority_ref")
    op.drop_column("corridor_version", "hazard_context_buffer_km")
    op.drop_column("corridor_version", "route_buffer_km")
    op.drop_column("corridor_version", "provenance_label")
    op.drop_column("corridor_version", "source_url")
