from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from ner_lens.app import create_app
from ner_lens.config import Settings
from ner_lens.contracts import CorridorState, ErrorResponse
from ner_lens.corridor.models import CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.identity.models import Actor, AuditEvent, RoleAssignment, SessionRecord
from ner_lens.identity.replay import VIEWER, session_key
from ner_lens.replay import initialize


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.sqlite'}")
    token = initialize(settings)
    factory = build_session_factory(settings)
    with TestClient(create_app(settings, factory)) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, factory, token
    factory.kw["bind"].dispose()


def test_clean_bootstrap_and_paginated_truthful_corridor(api):
    client, _, _ = api
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").status_code == 200
    catalog = client.get("/v1/corridors")
    assert catalog.status_code == 200
    assert catalog.headers["Cache-Control"] == "no-store"
    UUID_request = catalog.headers["X-Request-ID"]
    assert len(UUID_request) == 36
    entry = catalog.json()["corridors"][0]
    path = f"/v1/corridors/{entry['corridor_id']}/state"
    ids = []
    cursor = None
    while True:
        response = client.get(path, params={"limit": 2, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200
        body = response.json()
        CorridorState.model_validate(body)
        assert body["data_mode"] == "replay"
        assert (
            body["provenance"]["fixture_sha256"] == catalog.json()["provenance"]["fixture_sha256"]
        )
        assert body["provenance"]["observed_at"] is None
        assert body["provenance"]["policy_version"] == "replay_unapproved_v1"
        for segment in body["segments"]:
            assert segment["operational_status"]["value"] == "unknown"
            assert segment["operational_status"]["valid_until"] is None
            assert segment["risk"]["probability"] is None
            assert segment["risk"]["state"] == "insufficient_evidence"
            assert segment["source_health"] == "failed"
            assert segment["evidence_age_seconds"] is None
            assert segment["external_refs"][0]["source"] != "osm"
            assert "evidence" not in segment
            ids.append(segment["segment_id"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(ids) == len(set(ids)) == 6
    imported_at = catalog.json()["provenance"]["retrieved_at"]
    offset_time = datetime.fromisoformat(imported_at).astimezone(timezone(timedelta(hours=5.5)))
    state = client.get(
        path,
        params={
            "include_evidence": "true",
            "at": offset_time.isoformat(),
            "vehicle_profile": "rigid_truck",
        },
    ).json()
    assert state["as_of"] == imported_at
    assert all(segment["evidence"] == [] for segment in state["segments"])
    assert CorridorState.model_validate(state).model_dump(mode="json") == state


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 201},
        {"limit": 0},
        {"vehicle_profile": "aircraft"},
        {"at": "2026-09-10T12:00:00"},
        {"at": "2020-09-10T12:00:00Z"},
        {"at": "2099-09-10T12:00:00Z"},
        {"unexpected": "secret-value"},
        {"cursor": "not-a-uuid"},
        {"cursor": str(uuid4())},
    ],
)
def test_bad_queries_use_safe_error_envelope(api, query):
    client, _, _ = api
    corridor = client.get("/v1/corridors").json()["corridors"][0]["corridor_id"]
    response = client.get(f"/v1/corridors/{corridor}/state", params=query)
    assert response.status_code == 400
    ErrorResponse.model_validate(response.json())
    assert "secret-value" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_authentication_and_revocation(api):
    client, factory, token = api
    for authorization in ("", "Bearer wrong-token", "Basic bogus"):
        response = client.get("/v1/corridors", headers={"Authorization": authorization})
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        ErrorResponse.model_validate(response.json())
    with factory.begin() as session:
        record = session.get(SessionRecord, session_key(token))
        assert record.id != token
        record.revoked_at = datetime.now(timezone.utc)
    assert client.get("/v1/corridors").status_code == 401


def test_bearer_logout_revokes_presented_session(api):
    client, _, _ = api
    assert client.post("/v1/auth/logout").status_code == 204
    assert client.get("/v1/corridors").status_code == 401


@pytest.mark.parametrize(
    "change, expected",
    [
        ("expired", 401),
        ("future", 401),
        ("inactive", 401),
        ("jurisdiction", 403),
        ("role", 403),
    ],
)
def test_persisted_session_and_object_scope(api, change, expected):
    client, factory, token = api
    with factory.begin() as session:
        record = session.get(SessionRecord, session_key(token))
        if change == "expired":
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif change == "future":
            record.token_issued_at = datetime.now(timezone.utc) + timedelta(hours=1)
        elif change == "inactive":
            session.get(Actor, VIEWER).active = False
        else:
            assignment = session.scalar(
                select(RoleAssignment).where(RoleAssignment.actor_id == VIEWER)
            )
            if change == "jurisdiction":
                assignment.jurisdiction_id = None
            else:
                assignment.role = "system_admin"
    assert client.get("/v1/corridors").status_code == expected


def test_unknown_paths_and_method_and_host(api):
    client, _, _ = api
    for path, code in (("/missing", 404), (f"/v1/corridors/{uuid4()}/state", 404)):
        response = client.get(path)
        assert response.status_code == code
        ErrorResponse.model_validate(response.json())
    response = client.post("/v1/corridors", json={"actor_id": "forged"})
    assert response.status_code == 405
    ErrorResponse.model_validate(response.json())
    response = client.get("/health/live", headers={"Host": "attacker.invalid"})
    assert response.status_code == 400
    ErrorResponse.model_validate(response.json())


def test_readiness_requires_migrations_and_current_head(api):
    client, factory, _ = api
    with factory.begin() as session:
        session.execute(text("UPDATE alembic_version SET version_num='future_schema'"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True
    assert client.get("/health/live").status_code == 200
    assert client.get("/v1/corridors").status_code == 503
    settings = Settings()
    with TestClient(create_app(settings)) as empty:
        assert empty.get("/health/ready").status_code == 503


def test_openapi_contains_only_implemented_routes_and_matches_snapshot(api):
    client, _, _ = api
    document = client.get("/openapi.json").json()
    assert set(document["paths"]) == {
        "/v1/models/current",
        "/v1/missions/{mission_id}/start",
        "/v1/auth/session",
        "/v1/auth/logout",
        "/v1/auth/login",
        "/v1/corridors/{corridor_id}/state",
        "/v1/status-decisions",
        "/v1/field-reports/{report_id}/media",
        "/health/sources",
        "/v1/reviews/{evidence_id}",
        "/v1/routes/compare",
        "/v1/missions",
        "/v1/field-reports/{report_id}/media/{slot}",
        "/health/live",
        "/v1/missions/{mission_id}/complete",
        "/v1/missions/{mission_id}/positions",
        "/v1/field-reports",
        "/v1/missions/{mission_id}",
        "/v1/corridors",
        "/health/ready",
    }
    assert document["paths"]["/v1/corridors"]["get"]["security"] == [
        {"HTTPBearer": []},
        {"APIKeyCookie": []},
    ]
    import json

    snapshot = Path(__file__).resolve().parents[2] / "docs/openapi/v1.json"
    assert document == json.loads(snapshot.read_text(encoding="utf-8"))


def test_production_mode_is_rejected():
    with pytest.raises(ValueError, match="replay only"):
        create_app(Settings(environment="production"))


def test_authenticated_authorization_is_audited_with_request_id(api):
    client, factory, token = api
    response = client.get("/v1/corridors")
    with factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.request_id == response.headers["X-Request-ID"])
        )
        assert event.outcome == "allowed"
        assert token not in str(event.__dict__)
    with factory.begin() as session:
        assignment = session.scalar(select(RoleAssignment).where(RoleAssignment.actor_id == VIEWER))
        assignment.role = "system_admin"
    response = client.get("/v1/corridors")
    assert response.status_code == 403
    with factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.request_id == response.headers["X-Request-ID"])
        )
        assert event.outcome == "denied"


def test_reinitialization_preserves_import_and_prior_session(api):
    client, factory, original_token = api
    next_token = initialize(Settings(database_url=str(factory.kw["bind"].url)))
    assert next_token != original_token
    assert client.get("/v1/corridors").status_code == 200
    assert (
        client.get("/v1/corridors", headers={"Authorization": f"Bearer {next_token}"}).status_code
        == 200
    )
    with factory() as session:
        assert len(session.scalars(select(CorridorVersion)).all()) == 1
        assert len(session.scalars(select(RoadSegment)).all()) == 6
        assert len(session.scalars(select(RoleAssignment)).all()) == 1


def test_internal_errors_do_not_expose_exception_text(api, monkeypatch):
    client, _, _ = api

    def broken(_factory, _actor, _request_id):
        raise RuntimeError("private-exception-value")

    monkeypatch.setattr("ner_lens.app.list_corridors", broken)
    response = client.get("/v1/corridors")
    assert response.status_code == 500
    ErrorResponse.model_validate(response.json())
    assert "private-exception-value" not in response.text
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]
