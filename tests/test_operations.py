from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ner_lens.config import Settings
from ner_lens.corridor.models import CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.identity.models import (
    Actor,
    AuditEvent,
    Jurisdiction,
    RoleAssignment,
    SessionRecord,
    StatusAuthority,
)
from ner_lens.identity.service import AuthContext
from ner_lens.operations import FieldReport, GPSObservation, Mission, build_router, effective_status


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("NER_LENS_ENV_FILE", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = f"sqlite:///{tmp_path / 'operations.sqlite'}"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.attributes["skip_env_file"] = True
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    factory = build_session_factory(Settings(database_url=url))
    now = datetime.now(timezone.utc)
    actors = {}
    with factory.begin() as session:
        for scope in ("north", "south"):
            session.add(Jurisdiction(id=scope, code=scope, name=scope))
            session.add(
                CorridorVersion(
                    id=scope,
                    corridor_key=scope,
                    jurisdiction_id=scope,
                    graph_version="test-v1",
                    graph_sha256="a" * 64,
                    status="active",
                    effective_from=now,
                )
            )
            session.add(
                RoadSegment(
                    id=scope,
                    corridor_version_id=scope,
                    external_ref=scope,
                    segment_type="road",
                    direction="both",
                    geometry={"type": "LineString", "coordinates": [[92, 25], [92.1, 25.1]]},
                )
            )
        for role in (
            "field_reporter",
            "reviewer",
            "dispatcher",
            "district_officer",
            "regional_viewer",
            "system_admin",
        ):
            for scope in ("north", "south"):
                aid = f"{role}-{scope}"
                session.add(Actor(id=aid, external_subject=aid, actor_type="user", active=True))
                session.add(
                    RoleAssignment(id=str(uuid4()), actor_id=aid, role=role, jurisdiction_id=scope)
                )
                session.add(
                    SessionRecord(
                        id=aid,
                        actor_id=aid,
                        token_issued_at=now - timedelta(minutes=1),
                        expires_at=now + timedelta(hours=1),
                    )
                )
                actors[aid] = AuthContext(
                    aid,
                    "user",
                    (role,),
                    (scope,),
                    (),
                    aid,
                    now - timedelta(minutes=1),
                    now + timedelta(hours=1),
                    status_authority_actor_id=aid if role == "district_officer" else None,
                )
        session.add(
            StatusAuthority(actor_id="district_officer-north", jurisdiction_id="north", active=True)
        )
    selected = [actors["field_reporter-north"]]
    app = FastAPI()
    app.include_router(build_router(factory, lambda: selected[0]))
    with TestClient(app) as client:
        yield client, factory, selected, actors
    factory.kw["bind"].dispose()
    command.downgrade(config, "0005_source_snapshots")


def report_body():
    return {
        "client_report_id": str(uuid4()),
        "client_sequence": 1,
        "segment_id": "north",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "geometry": {"type": "Point", "coordinates": [92, 25]},
        "accuracy_m": 10,
        "status_claim": "blocked",
        "condition_code": "landslide",
        "note": "Test report",
        "device_id": "test-device",
    }


def post(client, path, body, key=None, **headers):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid4()), **headers})


def test_report_review_status_expiry_and_audit(api):
    client, factory, selected, actors = api
    payload = report_body()
    response = post(client, "/v1/field-reports", payload, "one")
    assert response.status_code == 201, response.text
    assert post(client, "/v1/field-reports", payload, "one").json() == response.json()
    assert post(client, "/v1/field-reports", payload, "two").json() == response.json()
    assert (
        post(client, "/v1/field-reports", {**payload, "note": "changed"}, "one").status_code == 409
    )
    assert (
        post(
            client, "/v1/field-reports", payload, "three", **{"X-Ner-Lens-Actor": "other"}
        ).status_code
        == 403
    )
    eid = response.json()["field_report_id"]
    selected[0] = actors["district_officer-north"]
    now = datetime.now(timezone.utc)
    decision = {
        "segment_id": "north",
        "status": "closed",
        "vehicle_scope": ["all"],
        "direction": "both",
        "reason_code": "landslide",
        "evidence_ids": [eid],
        "effective_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "note": "Reviewed obstruction",
    }
    assert post(client, "/v1/status-decisions", decision).status_code == 422
    selected[0] = actors["reviewer-north"]
    assert (
        post(client, f"/v1/reviews/{eid}", {"action": "accept", "note": "Confirmed"}).status_code
        == 201
    )
    assert (
        client.get("/v1/field-reports?segment_id=north").json()["reports"][0]["review_state"]
        == "accept"
    )
    selected[0] = actors["district_officer-north"]
    assert post(client, "/v1/status-decisions", decision).status_code == 201
    assert client.get("/v1/status-decisions?segment_id=north").json()["status"] == "closed"
    with factory() as session:
        assert effective_status(session, "north", now + timedelta(hours=2))["status"] == "unknown"
        assert session.scalar(select(func.count()).select_from(FieldReport)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) >= 3
    with factory.begin() as session:
        session.get(StatusAuthority, ("district_officer-north", "north")).active = False
    assert post(client, "/v1/status-decisions", decision).status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        "field_reporter",
        "reviewer",
        "dispatcher",
        "district_officer",
        "regional_viewer",
        "system_admin",
    ],
)
def test_role_and_jurisdiction_matrix(api, role):
    client, _, selected, actors = api
    selected[0] = actors[f"{role}-south"]
    assert post(client, "/v1/field-reports", report_body()).status_code == 403
    selected[0] = actors[f"{role}-north"]
    result = post(client, "/v1/field-reports", report_body())
    assert result.status_code == (201 if role == "field_reporter" else 403)
    selected[0] = replace(selected[0], expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert post(client, "/v1/field-reports", report_body()).status_code == 403


def test_validation_and_mission_gps(api):
    client, factory, selected, actors = api
    assert (
        post(
            client,
            "/v1/field-reports",
            {**report_body(), "geometry": {"type": "Point", "coordinates": [25, 92]}},
        ).status_code
        == 422
    )
    assert (
        post(
            client,
            "/v1/field-reports",
            {**report_body(), "geometry": {"type": "Point", "coordinates": [0, 0]}},
        ).status_code
        == 422
    )
    assert (
        post(
            client, "/v1/field-reports", {**report_body(), "observed_at": "2026-01-01T12:00:00"}
        ).status_code
        == 422
    )
    selected[0] = actors["dispatcher-north"]
    now = datetime.now(timezone.utc)
    body = {
        "cargo_class": "medicine",
        "priority": "high",
        "origin": {"type": "Point", "coordinates": [92, 25]},
        "destination": {"type": "Point", "coordinates": [92.1, 25.1]},
        "delivery_window": {
            "start": now.isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
        },
        "vehicle_profile": "rigid_truck",
        "corridor_id": "north",
        "gps_consent": {"basis": "mission_assignment", "recorded_at": now.isoformat()},
        "assigned_actor_ids": ["field_reporter-north"],
    }
    created = post(client, "/v1/missions", body)
    assert created.status_code == 201, created.text
    mid = created.json()["mission_id"]
    assert created.json()["state"] == "planned"
    assert created.json()["graph_version_id"] == "test-v1"
    assert post(client, f"/v1/missions/{mid}/start", None, "start").status_code == 201
    assert post(client, f"/v1/missions/{mid}/start", None, "start").status_code == 201
    selected[0] = actors["field_reporter-north"]
    point = {
        "sequence": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "geometry": {"type": "Point", "coordinates": [92, 25]},
        "accuracy_m": 5,
    }
    batch = {"device_id": "gps-test", "sequence_start": 1, "points": [point]}
    first = post(client, f"/v1/missions/{mid}/positions", batch, "gps")
    assert first.status_code == 201, first.text
    assert first.json()["accepted"] == [1]
    assert post(client, f"/v1/missions/{mid}/positions", batch, "gps").json() == first.json()
    assert post(client, f"/v1/missions/{mid}/positions", batch).json()["duplicate"] == [1]
    conflict = {**batch, "points": [{**point, "accuracy_m": 7}]}
    assert post(client, f"/v1/missions/{mid}/positions", conflict).status_code == 409
    jumped = {
        **point,
        "sequence": 2,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "geometry": {"type": "Point", "coordinates": [92.1, 25.1]},
    }
    assert post(
        client, f"/v1/missions/{mid}/positions", {**batch, "sequence_start": 2, "points": [jumped]}
    ).json()["flagged"] == [2]
    assert client.get(f"/v1/missions/{mid}").json()["delay_estimate"] is None
    assert client.get("/v1/missions?corridor_id=north").json()["missions"][0]["mission_id"] == mid
    assert (
        post(client, f"/v1/missions/{mid}/complete", None, "complete").json()["state"]
        == "completed"
    )
    assert post(client, f"/v1/missions/{mid}/complete", None, "complete").status_code == 201
    assert post(client, f"/v1/missions/{mid}/positions", batch).status_code == 409
    selected[0] = actors["field_reporter-south"]
    assert post(client, f"/v1/missions/{mid}/positions", batch).status_code == 403
    assert client.get(f"/v1/missions/{mid}").status_code == 403
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(GPSObservation)) == 2
        assert session.get(Mission, mid).graph_version_id == "test-v1"
