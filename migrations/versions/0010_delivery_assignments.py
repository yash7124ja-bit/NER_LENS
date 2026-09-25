"""Add scoped fleet records and private mission assignment details."""

import sqlalchemy as sa
from alembic import op

revision = "0010_delivery_assignments"
down_revision = "0009_user_stories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vehicle",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "jurisdiction_id", sa.String(36), sa.ForeignKey("jurisdiction.id"), nullable=False
        ),
        sa.Column("alias", sa.String(64), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("jurisdiction_id", "alias", name="uq_vehicle_jurisdiction_alias"),
        sa.CheckConstraint(
            "profile IN ('light_goods','rigid_truck','emergency')", name="ck_vehicle_profile"
        ),
    )
    op.create_index("ix_vehicle_jurisdiction_id", "vehicle", ["jurisdiction_id"])
    with op.batch_alter_table("mission") as batch:
        batch.add_column(sa.Column("vehicle_id", sa.String(36)))
        batch.add_column(sa.Column("driver_actor_id", sa.String(36)))
        batch.add_column(sa.Column("receiving_facility", sa.String(255)))
        batch.add_column(sa.Column("receiving_contact", sa.String(255)))
        batch.create_foreign_key("fk_mission_vehicle", "vehicle", ["vehicle_id"], ["id"])
        batch.create_foreign_key("fk_mission_driver", "actor", ["driver_actor_id"], ["id"])


def downgrade():
    with op.batch_alter_table("mission") as batch:
        batch.drop_constraint("fk_mission_driver", type_="foreignkey")
        batch.drop_constraint("fk_mission_vehicle", type_="foreignkey")
        batch.drop_column("receiving_contact")
        batch.drop_column("receiving_facility")
        batch.drop_column("driver_actor_id")
        batch.drop_column("vehicle_id")
    op.drop_index("ix_vehicle_jurisdiction_id", "vehicle")
    op.drop_table("vehicle")
