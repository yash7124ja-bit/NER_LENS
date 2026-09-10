"""Alembic environment for the A-owned foundation migration chain."""

from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from ner_lens.corridor.models import Base
from ner_lens.identity import models as _identity_models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://ner_lens@localhost/ner_lens")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = config.get_section(config.config_ini_section) or {}
    settings["sqlalchemy.url"] = os.getenv(
        "DATABASE_URL", settings.get("sqlalchemy.url", "postgresql+psycopg://ner_lens@localhost/ner_lens")
    )
    connectable = engine_from_config(settings, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
