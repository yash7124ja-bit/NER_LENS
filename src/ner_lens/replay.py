"""Initialize the local replay store and issue a short-lived read-only session."""

import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from ner_lens.config import Settings, normalize_database_url
from ner_lens.corridor.importer import (
    PROJECT_ROOT,
    CorridorImportService,
    bind_corridor,
    load_import_manifest,
    load_primary_band_specs,
)
from ner_lens.corridor.models import CorridorVersion
from ner_lens.db import build_session_factory
from ner_lens.identity.replay import JURISDICTION, issue_viewer_session


def initialize(settings: Settings) -> str:
    if settings.environment != "replay" or not settings.database_url.startswith(
        ("sqlite", "postgresql")
    ):
        raise ValueError("Initialization requires a SQLite or PostgreSQL replay database")
    if ":memory:" in settings.database_url or settings.database_url.rstrip("/") == "sqlite:":
        raise ValueError("Initialization requires a persistent SQLite replay file")
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    if (
        normalize_database_url(os.getenv("DATABASE_URL", settings.database_url))
        != settings.database_url
    ):
        raise ValueError("DATABASE_URL must agree with the requested replay database")
    command.upgrade(config, "head")
    factory = build_session_factory(settings)
    try:
        manifest = load_import_manifest()
        token = issue_viewer_session(factory)
        result = CorridorImportService().import_primary(
            factory,
            graph_version=manifest["graph_version"],
            graph_sha256=manifest["graph_sha256"],
            source_url=manifest["source_url"],
            specs=load_primary_band_specs(PROJECT_ROOT / manifest["fixture_path"]),
        )
        with factory() as session:
            version = session.get(CorridorVersion, result.corridor_version_id)
            name = version.name or version.corridor_key.replace("_", " ").title()
            scope = version.jurisdiction_id or JURISDICTION
        bind_corridor(factory, result.corridor_version_id, name, scope)
        return token
    finally:
        factory.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", type=Path, default=Path(".replay-token"))
    parser.add_argument("--initialize-only", action="store_true")
    args = parser.parse_args()
    if args.initialize_only:
        initialize(Settings.from_env())
        print("Replay database migrated and initialized.")
        return
    # Exclusive creation avoids silently replacing another operator's session credential.
    descriptor = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
        try:
            token_file.write(initialize(Settings.from_env()) + "\n")
        except Exception:
            token_file.close()
            args.token_file.unlink(missing_ok=True)
            raise
    print(f"Replay database initialized. Eight-hour viewer token saved to {args.token_file}.")


if __name__ == "__main__":
    main()
