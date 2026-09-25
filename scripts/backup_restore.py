"""Authenticated encrypted pg_dump backups; restore only into a distinct existing database."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _run(arguments: list[str], *, data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            arguments,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=os.environ.copy(),
        )
    except OSError as error:
        raise ValueError("PostgreSQL client executable unavailable") from error
    if result.returncode:
        # Client stderr may include connection details; never echo it or secret-bearing env.
        raise ValueError("PostgreSQL command failed; no successful backup/restore recorded")
    return result.stdout


def _database(value: str) -> str:
    if not value or not value.replace("_", "").isalnum() or not value.isascii():
        raise ValueError("database name must contain only ASCII letters, digits or underscore")
    return value


def encrypt_dump(dump: bytes, source_db: str, key: bytes) -> bytes:
    envelope = json.dumps(
        {
            "format": "ner-lens-pgdump-v1",
            "source_db": _database(source_db),
            "dump": base64.b64encode(dump).decode("ascii"),
        }
    ).encode()
    return Fernet(key).encrypt(envelope)


def decrypt_dump(token: bytes, key: bytes) -> dict:
    try:
        payload = json.loads(Fernet(key).decrypt(token))
        if payload["format"] != "ner-lens-pgdump-v1":
            raise ValueError("unsupported archive format")
        return {
            "source_db": _database(payload["source_db"]),
            "dump": base64.b64decode(payload["dump"], validate=True),
        }
    except (InvalidToken, ValueError, KeyError, TypeError) as error:
        raise ValueError("archive authentication or format validation failed") from error


def backup(source_db: str, output: Path, key: bytes) -> None:
    source_db = _database(source_db)
    if output.exists():
        raise ValueError("refusing to overwrite existing backup")
    Fernet(key)  # Validate key before accessing the database.
    dump = _run(["pg_dump", "--format=custom", "--no-password", "--dbname", source_db])
    encrypted = encrypt_dump(dump, source_db, key)
    # ponytail: whole archive in RAM; use streaming authenticated encryption for large databases.
    with output.open("xb") as stream:
        stream.write(encrypted)


def restore(archive: Path, target_db: str, key: bytes) -> None:
    payload = decrypt_dump(archive.read_bytes(), key)
    target_db = _database(target_db)
    if target_db == payload["source_db"]:
        raise ValueError("restore target must be distinct from source database")
    # Extension-owned tables (for example PostGIS spatial_ref_sys) are not user data.
    count = _run(
        [
            "psql",
            "--no-password",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--dbname",
            target_db,
            "--command",
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S') "
            "AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass "
            "AND d.objid = c.oid AND d.deptype = 'e')",
        ]
    )
    if count.strip() != b"0":
        raise ValueError("restore target must contain no user relations")
    # No --clean or --create: an existing empty target is required; any error rolls back.
    _run(
        [
            "pg_restore",
            "--no-password",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            target_db,
        ],
        data=payload["dump"],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    save = commands.add_parser("backup")
    save.add_argument("--source-db", required=True)
    save.add_argument("--output", type=Path, required=True)
    load = commands.add_parser("restore")
    load.add_argument("--archive", type=Path, required=True)
    load.add_argument("--target-db", required=True)
    args = parser.parse_args(argv)
    try:
        key = os.environ["BACKUP_FERNET_KEY"].encode("ascii")
        if args.action == "backup":
            backup(args.source_db, args.output, key)
        else:
            restore(args.archive, args.target_db, key)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Backup/restore blocked: {error}\n")
    print(f"{args.action} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
