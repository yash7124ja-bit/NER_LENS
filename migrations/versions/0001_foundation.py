"""A-M1-01 foundation tables.

Revision ID: 0001_foundation
Revises:
"""

from __future__ import annotations

from alembic import op

from ner_lens.corridor.models import Base
from ner_lens.identity import models as _identity_models  # noqa: F401


revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
