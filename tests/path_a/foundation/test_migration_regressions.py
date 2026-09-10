from __future__ import annotations

import importlib
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]


def test_migration_cycle_does_not_create_later_revision_tables_early():
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    revisions = [
        importlib.import_module("migrations.versions.0001_foundation"),
        importlib.import_module("migrations.versions.0002_session_record"),
        importlib.import_module("migrations.versions.0003_corridor_import"),
    ]

    def run(function):
        with Operations.context(MigrationContext.configure(connection)):
            function()

    run(revisions[0].upgrade)
    assert "corridor_version" in inspect(connection).get_table_names()
    assert "session_record" not in inspect(connection).get_table_names()
    for revision in revisions[1:]:
        run(revision.upgrade)
    for revision in reversed(revisions):
        run(revision.downgrade)
    for revision in revisions:
        run(revision.upgrade)
    assert "session_record" in inspect(connection).get_table_names()
    connection.close()
    engine.dispose()
