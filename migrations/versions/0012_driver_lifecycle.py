"""Permit audited driver and dispatcher mission lifecycle states."""

import sqlalchemy as sa
from alembic import op

revision = "0012_driver_lifecycle"
down_revision = "0011_route_selections"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mission") as batch:
        batch.drop_constraint("ck_mission_state", type_="check")
        batch.create_check_constraint(
            "ck_mission_state",
            "state IN ('planned','accepted','active','delivered',"
            "'completed','rejected','cancelled')",
        )


def downgrade():
    connection = op.get_bind()
    states = connection.execute(sa.text(
        "SELECT COUNT(*) FROM mission WHERE state NOT IN ('planned','active','completed')"
    )).scalar_one()
    if states:
        raise RuntimeError("Cannot downgrade while extended mission states exist")
    with op.batch_alter_table("mission") as batch:
        batch.drop_constraint("ck_mission_state", type_="check")
        batch.create_check_constraint(
            "ck_mission_state", "state IN ('planned','active','completed')"
        )
