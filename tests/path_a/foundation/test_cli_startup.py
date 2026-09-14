from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]


def test_alembic_cli_cycle_uses_replay_safe_repository_configuration():
    database = ROOT / f"cli-migration-{uuid4().hex}.sqlite"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database}"
    commands = (
        ("upgrade", "head"),
        ("downgrade", "base"),
        ("upgrade", "head"),
    )
    try:
        for command in commands:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *command],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
    finally:
        database.unlink(missing_ok=True)


def test_replay_environment_does_not_require_postgres_driver():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    active_database_lines = [
        line for line in env_example.splitlines() if line.startswith("DATABASE_URL=")
    ]
    assert active_database_lines == ["DATABASE_URL="]
    assert all(not line.split("=", 1)[1] for line in env_example.splitlines()
               if line and not line.startswith("#"))
