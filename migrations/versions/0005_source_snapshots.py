"""Persist provider retrievals and source health without credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0005_source_snapshots"
down_revision = "0004_local_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("etag", sa.String(512)),
        sa.Column("license", sa.String(255)),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("raw", sa.LargeBinary()),
        sa.Column("records", sa.JSON(), nullable=False),
    )
    op.create_index("ix_source_snapshot_source", "source_snapshot", ["source"])
    op.create_index("ix_source_snapshot_retrieved_at", "source_snapshot", ["retrieved_at"])


def downgrade():
    op.drop_table("source_snapshot")
