from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from scripts.backup_restore import backup, decrypt_dump, encrypt_dump, restore


def test_authenticated_encryption_and_wrong_keys():
    key = Fernet.generate_key()
    token = encrypt_dump(b"PGDMP TEST ONLY", "source_db", key)
    assert b"PGDMP" not in token
    assert decrypt_dump(token, key)["dump"] == b"PGDMP TEST ONLY"
    for invalid, candidate_key in ((token[:-5] + b"xxxxx", key), (token, Fernet.generate_key())):
        with pytest.raises(ValueError, match="authentication"):
            decrypt_dump(invalid, candidate_key)


def test_failure_does_not_create_backup_or_leak_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.backup_restore.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"secret password"),
    )
    with pytest.raises(ValueError, match="command failed") as error:
        backup("source_db", tmp_path / "dump.fernet", Fernet.generate_key())
    assert "secret" not in str(error.value)
    assert not (tmp_path / "dump.fernet").exists()


def test_restore_distinct_target_and_transaction_arguments(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    archive = tmp_path / "dump.fernet"
    archive.write_bytes(encrypt_dump(b"PGDMP TEST ONLY", "source_db", key))
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=b"0\n" if args[0] == "psql" else b"",
            stderr=b"",
        )

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", run)
    with pytest.raises(ValueError, match="distinct"):
        restore(archive, "source_db", key)
    assert not calls
    restore(archive, "isolated_restore", key)
    assert calls[0][0][0] == "psql"
    assert "--single-transaction" in calls[1][0]
    assert "--clean" not in calls[1][0]
    assert calls[1][1]["input"] == b"PGDMP TEST ONLY"
    assert archive.exists()


def test_restore_refuses_populated_target(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    archive = tmp_path / "dump.fernet"
    archive.write_bytes(encrypt_dump(b"PGDMP TEST ONLY", "source_db", key))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=b"1\n", stderr=b"")

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", run)
    with pytest.raises(ValueError, match="no user relations"):
        restore(archive, "populated_restore", key)
    assert len(calls) == 1
    assert calls[0][0] == "psql"


def test_existing_backup_preserved(tmp_path):
    path = tmp_path / "existing"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError, match="overwrite"):
        backup("source_db", path, Fernet.generate_key())
    assert path.read_bytes() == b"keep"
