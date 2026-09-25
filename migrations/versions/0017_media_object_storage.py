"""Track private object keys and derivative integrity for cleared media."""

import sqlalchemy as sa
from alembic import op

revision = "0017_media_object_storage"
down_revision = "0016_route_alerts"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("media_object") as batch:
        batch.add_column(sa.Column("storage_key", sa.String(96)))
        batch.add_column(sa.Column("derivative_sha256", sa.String(64)))


def downgrade():
    connection = op.get_bind()
    stored = connection.scalar(
        sa.text("SELECT COUNT(*) FROM media_object WHERE storage_key IS NOT NULL")
    )
    if stored:
        raise RuntimeError("Restore private media objects to database columns before downgrade")
    with op.batch_alter_table("media_object") as batch:
        batch.drop_column("derivative_sha256")
        batch.drop_column("storage_key")
