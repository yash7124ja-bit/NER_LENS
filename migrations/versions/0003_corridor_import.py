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
    source_url_added = "source_url" not in corridor_columns
    provenance_label_added = "provenance_label" not in corridor_columns
    route_buffer_added = "route_buffer_km" not in corridor_columns
    hazard_buffer_added = "hazard_context_buffer_km" not in corridor_columns
    if source_url_added:
        op.add_column(
            "corridor_version", sa.Column("source_url", sa.String(length=512), nullable=True)
        )
    if provenance_label_added:
        op.add_column(
            "corridor_version",
            sa.Column(
                "provenance_label", sa.String(length=32), nullable=False, server_default="replay"
            ),
        )
    if route_buffer_added:
        op.add_column(
            "corridor_version",
            sa.Column("route_buffer_km", sa.Float(), nullable=False, server_default="5"),
        )
    if hazard_buffer_added:
        op.add_column(
            "corridor_version",
            sa.Column("hazard_context_buffer_km", sa.Float(), nullable=False, server_default="20"),
        )
    if "authority_ref" not in segment_columns:
        op.add_column(
            "road_segment", sa.Column("authority_ref", sa.String(length=255), nullable=True)
        )
    source_url_nullable = _column_is_nullable("corridor_version", "source_url")
    if source_url_added or source_url_nullable:
        op.execute(
            "UPDATE corridor_version SET source_url = 'replay://unspecified' "
            "WHERE source_url IS NULL"
        )
    if source_url_added or source_url_nullable:
        with op.batch_alter_table("corridor_version") as batch_op:
            batch_op.alter_column("source_url", nullable=False)


def _column_is_nullable(table: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return next(
        column["nullable"]
        for column in inspector.get_columns(table)
        if column["name"] == column_name
    )


def downgrade() -> None:
    op.drop_column("road_segment", "authority_ref")
    op.drop_column("corridor_version", "hazard_context_buffer_km")
    op.drop_column("corridor_version", "route_buffer_km")
    op.drop_column("corridor_version", "provenance_label")
    op.drop_column("corridor_version", "source_url")
