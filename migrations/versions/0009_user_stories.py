"""Persist SIH user stories independently of optional search indexing."""

import sqlalchemy as sa
from alembic import op

revision = "0009_user_stories"
down_revision = "0008_media"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_story",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("user_story")
