"""Private bounded image quarantine and stripped derivative storage."""

import sqlalchemy as sa
from alembic import op

revision = "0008_media"
down_revision = "0007_route_comparisons"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_object",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "field_report_id", sa.String(36), sa.ForeignKey("field_report.id"), nullable=False
        ),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("upload_state", sa.String(16), nullable=False),
        sa.Column("scan_state", sa.String(16), nullable=False),
        sa.Column("scan_reason", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.Column("raw", sa.LargeBinary()),
        sa.Column("derivative", sa.LargeBinary()),
        sa.Column("upload_response", sa.JSON()),
        sa.UniqueConstraint("field_report_id", "slot", name="uq_report_media_slot"),
        sa.CheckConstraint("slot >= 0 AND slot < 4", name="ck_media_slot"),
        sa.CheckConstraint(
            "content_length > 0 AND content_length <= 8388608", name="ck_media_length"
        ),
        sa.CheckConstraint(
            "upload_state IN ('uploading','incomplete','received')", name="ck_media_upload_state"
        ),
        sa.CheckConstraint(
            "scan_state IN ('pending','clean','rejected','error')", name="ck_media_scan_state"
        ),
    )
    op.create_index("ix_media_object_field_report_id", "media_object", ["field_report_id"])


def downgrade():
    op.drop_table("media_object")
