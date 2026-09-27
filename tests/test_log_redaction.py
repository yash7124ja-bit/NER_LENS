"""Regression check at the shared logging boundary: secrets and precise GPS
must never reach application logs, stdout, or error response bodies, even
when a request fails validation, authentication, or hits an unhandled
exception. Uses synthetic canary values only.
"""
import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ner_lens.app import create_app
from ner_lens.config import Settings
from ner_lens.corridor.importer import bind_corridor
from ner_lens.corridor.models import CorridorVersion
from ner_lens.db import build_session_factory
from ner_lens.identity.accounts import provision_account
from ner_lens.identity.models import Jurisdiction
from ner_lens.replay import initialize

CANARY_PASSWORD = "canary-secret-Tr0ub4dor&3-do-not-log"  # noqa: S105 synthetic test value
CANARY_LATITUDE = 26.123456789
CANARY_LONGITUDE = 91.987654321


@pytest.fixture
def redaction_api(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'redaction.sqlite'}")
    initialize(settings)
    factory = build_session_factory(settings)
    email, password = f"{uuid4().hex}@example.test", "Real-account-password-2026!"
    scope = str(uuid4())
    with factory.begin() as session:
        session.add(Jurisdiction(id=scope, code=scope, name=scope))
        corridor_id = session.scalar(select(CorridorVersion.id))
    bind_corridor(factory, corridor_id, scope, scope)
    provision_account(factory, email, password, "Redaction test account", ("dispatcher",), (scope,))
    with TestClient(create_app(settings, factory)) as client:
        yield client, email, password
    factory.kw["bind"].dispose()


def assert_canary_absent(*, response_text, log_text, captured_out):
    for canary in (CANARY_PASSWORD, str(CANARY_LATITUDE), str(CANARY_LONGITUDE)):
        assert canary not in response_text, f"canary leaked into response: {canary}"
        assert canary not in log_text, f"canary leaked into logging output: {canary}"
        assert canary not in captured_out, f"canary leaked into stdout/stderr: {canary}"


def test_failed_login_never_logs_or_echoes_the_password(redaction_api, caplog, capsys):
    client, email, _real_password = redaction_api
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/v1/auth/login", json={"email": email, "password": CANARY_PASSWORD}
        )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email or password is incorrect."
    captured = capsys.readouterr()
    assert_canary_absent(
        response_text=response.text, log_text=caplog.text,
        captured_out=captured.out + captured.err,
    )


def test_validation_failure_reports_field_and_reason_never_the_submitted_value(
    redaction_api, caplog, capsys
):
    client, email, password = redaction_api
    client.post("/v1/auth/login", json={"email": email, "password": password})
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/v1/missions",
            json={
                "cargo_class": "medicine",
                "priority": "high",
                "origin": {"type": "Point", "coordinates": [CANARY_LONGITUDE, CANARY_LATITUDE]},
                "destination": {"type": "Point", "coordinates": [999, 999]},
                "delivery_window": {"start": "not-a-date", "end": "also-not-a-date"},
                "vehicle_profile": "rigid_truck",
                "corridor_id": "does-not-matter",
                "gps_consent": {"basis": "mission_assignment", "recorded_at": "not-a-date"},
            },
        )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    for detail in body["error"]["details"]:
        assert set(detail) == {"field", "reason"}
    captured = capsys.readouterr()
    assert_canary_absent(
        response_text=response.text, log_text=caplog.text,
        captured_out=captured.out + captured.err,
    )


def test_unhandled_exception_is_swallowed_at_the_shared_boundary_without_logging(
    redaction_api, caplog, monkeypatch
):
    client, email, password = redaction_api
    client.post("/v1/auth/login", json={"email": email, "password": password})

    def leaking_failure(*_args, **_kwargs):
        raise RuntimeError(f"internal failure near secret={CANARY_PASSWORD}")

    monkeypatch.setattr("ner_lens.app.list_corridors", leaking_failure)
    with caplog.at_level(logging.DEBUG):
        response = client.get("/v1/corridors")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == "An unexpected server error occurred"
    assert not error["details"]
    assert CANARY_PASSWORD not in response.text
    assert CANARY_PASSWORD not in caplog.text
