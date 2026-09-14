"""Local password accounts, login throttling, and persisted corridor scope."""

import sqlalchemy as sa
from alembic import op

revision = "0004_local_accounts"
down_revision = "0003_corridor_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_account",
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actor.id"), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
    )
    op.create_table(
        "login_throttle",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    with op.batch_alter_table("corridor_version") as batch:
        batch.add_column(sa.Column("name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("jurisdiction_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_corridor_jurisdiction", "jurisdiction", ["jurisdiction_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("corridor_version") as batch:
        batch.drop_constraint("fk_corridor_jurisdiction", type_="foreignkey")
        batch.drop_column("jurisdiction_id")
        batch.drop_column("name")
    op.drop_table("login_throttle")
    op.drop_table("local_account")
