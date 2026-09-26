from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

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
from ner_lens.operations import (
    FieldReport,
    GPSObservation,
    Mission,
    Vehicle,
    build_router,
    effective_status,
)
from ner_lens.routing import build_router as routing_router
from ner_lens.sources import SourceSnapshot


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
            "driver",
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
    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)
    app.include_router(build_router(
        factory, lambda: selected[0],
        Settings(database_url=url, field_report_max_age_seconds=3600),
    ))
    app.include_router(routing_router(factory, lambda: selected[0], Settings(database_url=url)))
    with TestClient(app) as client:
        yield client, factory, selected, actors
    with factory.begin() as session:
        session.execute(update(Mission).where(
            Mission.state.not_in(("planned", "active", "completed"))
        ).values(state="planned"))
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


def test_route_baseline_selection_rejects_stale_and_changed_decisions(api, monkeypatch):
    client, factory, selected, actors = api
    selected[0] = actors["dispatcher-north"]
    now = datetime.now(timezone.utc)
    mission = post(client, "/v1/missions", {
        "cargo_class": "medicine", "priority": "high",
        "origin": {"type": "Point", "coordinates": [92, 25]},
        "destination": {"type": "Point", "coordinates": [92.1, 25.1]},
        "delivery_window": {"start": now.isoformat(),
                            "end": (now + timedelta(hours=2)).isoformat()},
        "vehicle_profile": "rigid_truck", "corridor_id": "north",
        "gps_consent": {"basis": "mission_assignment", "recorded_at": now.isoformat()},
    })
    assert mission.status_code == 201, mission.text
    mid = mission.json()["mission_id"]

    def snapshot(age=0):
        return SourceSnapshot(
            id=str(uuid4()), source="mappls", url="https://route.mappls.com/route/direction",
            retrieved_at=datetime.now(timezone.utc) - timedelta(seconds=age),
            status="available", reason="retrieval_validated", sha256="a" * 64,
            parser_version="test", records=[{
                "geometry": {"type": "LineString", "coordinates": [[92, 25], [92.1, 25.1]]},
                "distance_m": 1000, "duration_seconds": 120,
            }],
        )

    monkeypatch.setattr("ner_lens.routing.retrieve", lambda *a, **k: snapshot())
    payload = {
        "corridor_id": "north", "graph_version_id": "test-v1", "mission_id": mid,
        "origin": mission.json()["origin"], "destination": mission.json()["destination"],
        "vehicle_profile": "rigid_truck", "departure_at": now.isoformat(),
        "deadline_at": mission.json()["delivery_window"]["end"],
    }
    comparison = post(client, "/v1/routes/compare", payload, "compare")
    assert comparison.status_code == 200, comparison.text
    result = comparison.json()
    assert result["recommended_route_id"] is None
    assert result["vehicle_entitlement"] == "unverified_car_baseline"
    assert result["source_snapshot_id"] and result["routes"][0]["geometry"]
    route_id = result["routes"][0]["route_id"]
    path = f"/v1/missions/{mid}/route-selection"
    choice = {"comparison_id": result["comparison_id"], "route_id": route_id}
    first = post(client, path, choice, "select")
    assert first.status_code == 201, first.text
    assert post(client, path, choice, "select").json() == first.json()
    assert post(client, path, {**choice, "route_id": "other"}, "select").status_code == 409
    saved = client.get(path).json()["selection"]
    assert saved["route_id"] == route_id
    assert saved["route"] == result["routes"][0]
    assert saved["source"]["source_snapshot_id"] == result["source_snapshot_id"]
    assert saved["source"]["vehicle_entitlement"] == "unverified_car_baseline"
    with factory.begin() as session:
        session.get(Mission, mid).driver_actor_id = "driver-north"
    selected[0] = actors["driver-north"]
    assert client.get(path).json()["selection"]["route"] == result["routes"][0]
    selected[0] = actors["driver-south"]
    assert client.get(path).status_code == 403
    selected[0] = actors["dispatcher-south"]
    assert post(client, path, choice).status_code == 403
    selected[0] = actors["dispatcher-north"]
    assert post(client, "/v1/routes/compare", {
        **payload, "vehicle_profile": "light_goods"
    }).status_code == 409

    with factory.begin() as session:
        from ner_lens.routing import RouteComparisonRecord
        record = session.get(RouteComparisonRecord, result["comparison_id"])
        record.payload = {**record.payload, "retrieved_at": (now - timedelta(hours=2)).isoformat()}
    assert post(client, path, choice).status_code == 409

    fresh = post(client, "/v1/routes/compare", payload, "compare-fresh").json()
    fresh_choice = {
        "comparison_id": fresh["comparison_id"],
        "route_id": fresh["routes"][0]["route_id"],
    }
    with factory.begin() as session:
        from ner_lens.operations import StatusDecision
        session.add(StatusDecision(
            id=str(uuid4()), segment_id="north", actor_id="district_officer-north",
            jurisdiction_id="north", effective_at=now - timedelta(minutes=1),
            valid_until=now + timedelta(hours=1), created_at=now,
            payload={"status": "closed", "direction": "both", "vehicle_scope": ["all"]},
        ))
    assert post(client, path, fresh_choice).status_code == 409
    blocked = post(client, "/v1/routes/compare", payload, "compare-blocked")
    assert blocked.status_code == 200
    assert blocked.json()["routes"] == []
    assert blocked.json()["mode"] == "no_verified_feasible_route"
    with factory.begin() as session:
        session.get(CorridorVersion, "north").graph_version = "test-v2"
    assert post(client, path, fresh_choice).status_code == 409


def test_route_comparison_uses_private_graph_profile_when_configured(api, monkeypatch):
    _, factory, selected, actors = api
    selected[0] = actors["dispatcher-north"]
    settings = Settings(
        database_url=str(factory.kw["bind"].url),
        graphhopper_local_url="http://graphhopper:8989",
        graphhopper_data_date="2026-09-09T20:21:20Z",
    )
    calls = []

    def private_route(_settings, *, points, profile):
        calls.append((points, profile))
        return SourceSnapshot(
            id=str(uuid4()), source="graphhopper_local", url="private://graphhopper/route",
            retrieved_at=datetime.now(timezone.utc), status="available",
            reason="private_graph_profile_validated", sha256="b" * 64,
            parser_version="test", records=[{
                "geometry": {"type": "LineString", "coordinates": points},
                "distance_m": 1000, "duration_seconds": 120,
            }],
        )

    monkeypatch.setattr("ner_lens.routing.retrieve_local_graphhopper", private_route)
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)

    app.include_router(routing_router(factory, lambda: selected[0], settings))
    now = datetime.now(timezone.utc)
    with TestClient(app) as client:
        response = post(client, "/v1/routes/compare", {
            "corridor_id": "north", "graph_version_id": "test-v1",
            "origin": {"type": "Point", "coordinates": [92, 25]},
            "destination": {"type": "Point", "coordinates": [92.1, 25.1]},
            "vehicle_profile": "rigid_truck", "departure_at": now.isoformat(),
            "deadline_at": (now + timedelta(hours=2)).isoformat(),
        })
    assert response.status_code == 200, response.text
    assert calls == [([(92.0, 25.0), (92.1, 25.1)], "rigid_truck")]
    body = response.json()
    assert body["provider"] == "graphhopper_local"
    assert body["vehicle_entitlement"] == "graphhopper_profile_applied_legality_unverified"
    assert body["routes"][0]["travel_time_seconds"]["basis"] == (
        "graphhopper_profile_free_flow_unvalidated"
    )
    assert body["recommended_route_id"] is None


def test_mission_impacts_follow_selected_segments_and_decision_lifecycle(api):
    client, factory, selected, actors = api
    selected[0] = actors["dispatcher-north"]
    now = datetime.now(timezone.utc)
    from ner_lens.operations import StatusDecision
    from ner_lens.routing import MissionImpactRecord, RouteComparisonRecord, RouteSelectionRecord

    mission_ids = [str(uuid4()) for _ in range(3)]
    comparison_id = str(uuid4())
    routes = [{"route_id": str(uuid4()), "segment_ids": segments,
               "decision_snapshots": {"north": {"decision_id": None, "freshness": "missing"}}}
              for segments in (["north"], ["south"])]
    with factory.begin() as session:
        session.add(RouteComparisonRecord(
            id=comparison_id, actor_id="dispatcher-north", corridor_id="north",
            graph_version="test-v1", idempotency_key="impact-compare",
            request_hash="a" * 64, created_at=now,
            payload={"routes": routes, "source_snapshot_id": "source-1"},
        ))
        for index, mid in enumerate(mission_ids):
            session.add(Mission(
                id=mid, actor_id="dispatcher-north", corridor_id="north",
                jurisdiction_id="north", graph_version_id="test-v1",
                state="completed" if index == 1 else "active", created_at=now,
                payload={"vehicle_profile": "rigid_truck"},
            ))
            session.add(RouteSelectionRecord(
                id=str(uuid4()), mission_id=mid, comparison_id=comparison_id,
                route_id=routes[1 if index == 2 else 0]["route_id"],
                actor_id="dispatcher-north", idempotency_key=f"impact-select-{index}",
                request_hash="b" * 64, selected_at=now,
                expires_at=now + timedelta(hours=1),
            ))
    path = "/v1/corridors/north/mission-impacts"
    assert client.get(path).json()["assessments"] == []
    selected[0] = actors["dispatcher-south"]
    assert client.get(path).status_code == 403
    selected[0] = actors["dispatcher-north"]
    first_decision = str(uuid4())
    with factory.begin() as session:
        session.add(StatusDecision(
            id=first_decision, segment_id="north", actor_id="district_officer-north",
            jurisdiction_id="north", created_at=now,
            effective_at=now - timedelta(minutes=2), valid_until=now + timedelta(hours=1),
            payload={"status": "closed", "direction": "both", "vehicle_scope": ["all"],
                     "valid_until": (now + timedelta(hours=1)).isoformat(),
                     "evidence_ids": []},
        ))
    assessments = client.get(path).json()["assessments"]
    assert len(assessments) == 1
    assert assessments[0]["mission_id"] == mission_ids[0]
    assert assessments[0]["decision_id"] == first_decision
    assert assessments[0]["assessment_basis"] == "selected_geometry_baseline_unverified"
    assert client.get(path).json()["assessments"] == assessments
    with factory.begin() as session:
        assert session.query(MissionImpactRecord).count() == 1
        assert session.get(Mission, mission_ids[0]).state == "active"
        session.get(StatusDecision, first_decision).valid_until = now - timedelta(seconds=1)
    resolved = client.get(path).json()["assessments"]
    assert len(resolved) == 1 and resolved[0]["state"] == "resolved"
    with factory.begin() as session:
        session.add(StatusDecision(
            id=str(uuid4()), segment_id="north", actor_id="district_officer-north",
            jurisdiction_id="north", created_at=now + timedelta(seconds=1),
            effective_at=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1),
            payload={"status": "restricted", "direction": "both", "vehicle_scope": ["all"],
                     "valid_until": (now + timedelta(hours=1)).isoformat(),
                     "evidence_ids": []},
        ))
    refreshed = client.get(path).json()["assessments"]
    assert len(refreshed) == 2
    assert [item["state"] for item in refreshed].count("active") == 1
    with factory.begin() as session:
        session.get(CorridorVersion, "north").graph_version = "test-v2"
    changed = client.get(path).json()
    assert all(item["state"] == "resolved" for item in changed["assessments"])
    assert {item["mission_id"] for item in changed["unassessed"]} == {
        mission_ids[0], mission_ids[2]
    }


def test_route_change_approval_is_scoped_idempotent_and_does_not_switch_driver_route(
    api, monkeypatch
):
    client, factory, selected, actors = api
    selected[0] = actors["dispatcher-north"]
    now = datetime.now(timezone.utc)
    from ner_lens.operations import EvidenceReview, StatusDecision
    from ner_lens.routing import (
        AlertAcknowledgment,
        AlertDeliveryAttempt,
        MissionImpactRecord,
        RouteAlert,
        RouteChangeApproval,
        RouteComparisonRecord,
        RouteSelectionRecord,
    )

    mid, impact_id, decision_id, prior_id, comparison_id, report_id, review_id, other_id = (
        str(uuid4()) for _ in range(8)
    )
    old_route, alternate_route = str(uuid4()), str(uuid4())
    origin = {"type": "Point", "coordinates": [92, 25]}
    destination = {"type": "Point", "coordinates": [92.1, 25.1]}
    deadline = now + timedelta(hours=2)
    with factory.begin() as session:
        session.add(
            RoadSegment(
                id="north-bypass",
                corridor_version_id="north",
                external_ref="north-bypass",
                segment_type="road",
                direction="both",
                geometry={"type": "LineString", "coordinates": [[92, 25], [92.1, 25.1]]},
            )
        )
        session.add(
            Mission(
                id=mid,
                actor_id="dispatcher-north",
                corridor_id="north",
                jurisdiction_id="north",
                graph_version_id="test-v1",
                driver_actor_id="driver-north",
                state="active",
                created_at=now,
                payload={
                    "vehicle_profile": "rigid_truck",
                    "origin": origin,
                    "destination": destination,
                    "delivery_window": {"end": deadline.isoformat()},
                },
            )
        )
        session.add(
            FieldReport(
                id=report_id, client_report_id=report_id, actor_id="field_reporter-north",
                segment_id="north", jurisdiction_id="north", received_at=now,
                payload={"observed_at": now.isoformat()},
                response={"review_state": "accepted_for_review"},
            )
        )
        session.add(EvidenceReview(
            id=review_id, evidence_id=report_id, actor_id="reviewer-north",
            created_at=now, payload={"action": "accept"},
        ))
        session.add(
            StatusDecision(
                id=decision_id,
                segment_id="north",
                actor_id="district_officer-north",
                jurisdiction_id="north",
                created_at=now,
                effective_at=now - timedelta(minutes=1),
                valid_until=now + timedelta(hours=1),
                payload={"status": "closed", "direction": "both", "vehicle_scope": ["all"],
                         "evidence_ids": [report_id]},
            )
        )
        session.add(
            RouteComparisonRecord(
                id=comparison_id,
                actor_id="dispatcher-north",
                corridor_id="north",
                graph_version="test-v1",
                idempotency_key="alternate-compare",
                request_hash="a" * 64,
                created_at=now,
                payload={
                    "mission_id": mid,
                    "impact_id": impact_id,
                    "retrieved_at": now.isoformat(),
                    "source_snapshot_id": "source-1",
                    "source_sha256": "b" * 64,
                    "routes": [
                        {
                            "route_id": alternate_route,
                            "segment_ids": ["north-bypass"],
                            "decision_snapshots": {
                                "north-bypass": {"decision_id": None, "freshness": "missing"}
                            },
                        }
                    ],
                },
            )
        )
        session.add(RouteComparisonRecord(
            id=other_id, actor_id="dispatcher-north", corridor_id="north",
            graph_version="test-v1", idempotency_key="other-mission-compare",
            request_hash="9" * 64, created_at=now,
            payload={"mission_id": str(uuid4()), "routes": []},
        ))
        session.add(
            RouteComparisonRecord(
                id=prior_id,
                actor_id="dispatcher-north",
                corridor_id="north",
                graph_version="test-v1",
                idempotency_key="prior-compare",
                request_hash="c" * 64,
                created_at=now,
                payload={"routes": []},
            )
        )
        selection_id = str(uuid4())
        session.add(
            RouteSelectionRecord(
                id=selection_id,
                mission_id=mid,
                comparison_id=prior_id,
                route_id=old_route,
                actor_id="dispatcher-north",
                idempotency_key="prior-selection",
                request_hash="d" * 64,
                selected_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        session.add(
            MissionImpactRecord(
                id=impact_id,
                corridor_id="north",
                mission_id=mid,
                decision_id=decision_id,
                route_selection_id=selection_id,
                state="active",
                assessed_at=now,
                payload={"segment_id": "north"},
            )
        )
    monkeypatch.setattr(
        "ner_lens.routing.retrieve",
        lambda *a, **k: SourceSnapshot(
            id=str(uuid4()),
            source="mappls",
            url="https://route.mappls.com/route/direction",
            retrieved_at=datetime.now(timezone.utc),
            status="available",
            reason="retrieval_validated",
            sha256="e" * 64,
            parser_version="test",
            records=[
                {
                    "geometry": {"type": "LineString", "coordinates": [[92, 25], [92.1, 25.1]]},
                    "distance_m": 1000,
                    "duration_seconds": 120,
                }
            ],
        ),
    )
    compare_body = {
        "corridor_id": "north",
        "graph_version_id": "test-v1",
        "mission_id": mid,
        "origin": origin,
        "destination": destination,
        "vehicle_profile": "rigid_truck",
        "departure_at": now.isoformat(),
        "deadline_at": deadline.isoformat(),
    }
    assert post(client, "/v1/routes/compare", compare_body, "no-impact").status_code == 409
    comparison = post(
        client, "/v1/routes/compare", {**compare_body, "impact_id": impact_id}, "impacted-compare"
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["impact_id"] == impact_id
    assert comparison.json()["mode"] == "no_verified_feasible_route"
    path = f"/v1/missions/{mid}/route-change-approval"
    body = {
        "impact_id": impact_id,
        "comparison_id": comparison_id,
        "route_id": alternate_route,
        "reason": "Avoid the authority closure on the selected route",
    }
    selected[0] = actors["dispatcher-south"]
    assert post(client, path, body, "approve").status_code == 403
    selected[0] = actors["dispatcher-north"]
    assert post(client, path, {**body, "reason": "           "}, "blank-reason").status_code == 422
    first = post(client, path, body, "approve")
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "pending_driver_acknowledgment"
    assert post(client, path, body, "approve").json() == first.json()
    assert post(client, path, {**body, "reason": "Changed reason"}, "approve").status_code == 409
    assert post(client, path, body, "approve-again").status_code == 409
    assert client.get(path).json()["approval"]["approval_id"] == first.json()["approval_id"]
    with factory() as session:
        assert session.query(RouteChangeApproval).count() == 1
    saved = client.get(f"/v1/missions/{mid}/route-selection").json()["selection"]
    assert saved["route_id"] == old_route
    first_alert = client.get(f"/v1/missions/{mid}/route-alert").json()["alert"]
    fresh_comparison_id = str(uuid4())
    with factory.begin() as session:
        approval = session.query(RouteChangeApproval).one()
        approval.payload = {
            **approval.payload, "expires_at": (now - timedelta(seconds=1)).isoformat()
        }
        prior_comparison = session.get(RouteComparisonRecord, comparison_id)
        session.add(RouteComparisonRecord(
            id=fresh_comparison_id, actor_id="dispatcher-north", corridor_id="north",
            graph_version="test-v1", idempotency_key="fresh-compare", request_hash="f" * 64,
            created_at=now, payload={**prior_comparison.payload, "retrieved_at": now.isoformat()},
        ))
    fresh_body = {**body, "comparison_id": fresh_comparison_id}
    renewed = post(client, path, fresh_body, "approve-fresh")
    assert renewed.status_code == 201, renewed.text
    alert = client.get(f"/v1/missions/{mid}/route-alert").json()["alert"]
    assert alert["alert_id"] != first_alert["alert_id"]
    assert alert["delivery_state"] == "queued_in_app"
    selected[0] = actors["driver-south"]
    assert client.post(f"/v1/alerts/{alert['alert_id']}/acknowledge", json={"decision": "accept"},
                       headers={"Idempotency-Key": "wrong-driver"}).status_code == 403
    selected[0] = actors["driver-north"]
    inbox = client.get("/v1/alerts").json()["alerts"]
    assert inbox[0]["alert_id"] == alert["alert_id"]
    assert inbox[0]["delivery_state"] == "delivered_in_app"
    assert len(client.get("/v1/alerts").json()["alerts"]) == 2
    ack_path = f"/v1/alerts/{alert['alert_id']}/acknowledge"
    assert post(client, f"/v1/alerts/{first_alert['alert_id']}/acknowledge",
                {"decision": "accept"}, "stale-prior").status_code == 409
    with factory.begin() as session:
        approval = session.get(RouteChangeApproval, renewed.json()["approval_id"])
        original_payload = approval.payload
        approval.payload = {
            **original_payload, "expires_at": (now - timedelta(seconds=1)).isoformat()
        }
    assert post(client, ack_path, {"decision": "accept"}, "stale-accept").status_code == 409
    with factory.begin() as session:
        session.get(RouteChangeApproval, renewed.json()["approval_id"]).payload = original_payload
    acknowledged = post(client, ack_path, {"decision": "accept"}, "driver-accept")
    assert acknowledged.status_code == 201, acknowledged.text
    assert acknowledged.json()["selection_id"]
    assert (
        post(client, ack_path, {"decision": "accept"}, "driver-accept").json()
        == acknowledged.json()
    )
    assert post(client, ack_path, {"decision": "decline"}, "driver-accept").status_code == 409
    assert post(client, ack_path, {"decision": "decline"}, "driver-decline").status_code == 409
    driver_selection = client.get(f"/v1/missions/{mid}/route-selection").json()["selection"]
    assert driver_selection["route_id"] == alternate_route
    selected[0] = actors["dispatcher-north"]
    timeline = client.get(f"/v1/missions/{mid}/timeline")
    assert timeline.status_code == 200, timeline.text
    events = timeline.json()["events"]
    assert {event["kind"] for event in events} >= {
        "mission", "field_report", "review", "status_decision", "impact", "comparison",
        "selection", "approval", "alert", "alert_delivery", "acknowledgment",
    }
    assert {event["source_ids"]["mission_id"] for event in events} == {mid}
    assert other_id not in {event["event_id"] for event in events}
    assert next(event for event in events if event["kind"] == "review")["source_ids"] == {
        "mission_id": mid, "report_id": report_id, "decision_id": decision_id,
        "review_id": review_id,
    }
    assert [event["at"] for event in events] == sorted(event["at"] for event in events)
    selected[0] = actors["dispatcher-south"]
    assert client.get(f"/v1/missions/{mid}/timeline").status_code == 403
    selected[0] = actors["driver-north"]
    assert client.get(f"/v1/missions/{mid}/timeline").status_code == 403
    with factory.begin() as session:
        assert session.query(RouteAlert).count() == 2
        assert session.query(AlertDeliveryAttempt).count() == 2
        assert session.query(AlertAcknowledgment).count() == 1
        session.get(StatusDecision, decision_id).valid_until = now - timedelta(seconds=1)
    selected[0] = actors["dispatcher-north"]
    assert post(client, path, body, "approval-after-expiry").status_code == 409
    # The fixture downgrades this disposable database through the earlier unique-impact schema.
    with factory.begin() as session:
        session.query(AlertAcknowledgment).delete()
        session.query(AlertDeliveryAttempt).delete()
        session.query(RouteAlert).delete()
        session.delete(session.get(RouteChangeApproval, renewed.json()["approval_id"]))


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


def test_status_requires_fresh_observation_and_approved_age_policy(api):
    client, factory, selected, actors = api
    now = datetime.now(timezone.utc)
    old = post(client, "/v1/field-reports", {
        **report_body(), "observed_at": (now - timedelta(hours=2)).isoformat(),
    }).json()["field_report_id"]
    selected[0] = actors["reviewer-north"]
    assert post(client, f"/v1/reviews/{old}", {
        "action": "accept", "note": "Confirmed historical obstruction",
    }).status_code == 201
    selected[0] = actors["district_officer-north"]
    decision = {
        "segment_id": "north", "status": "closed", "vehicle_scope": ["all"],
        "direction": "both", "reason_code": "landslide", "evidence_ids": [old],
        "effective_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "note": "Reviewed obstruction",
    }
    stale = post(client, "/v1/status-decisions", decision)
    assert stale.status_code == 422
    assert stale.json()["detail"] == "evidence_observation_stale"

    selected[0] = actors["field_reporter-north"]
    fresh = post(client, "/v1/field-reports", report_body()).json()["field_report_id"]
    selected[0] = actors["reviewer-north"]
    assert post(client, f"/v1/reviews/{fresh}", {
        "action": "accept", "note": "Confirmed current obstruction",
    }).status_code == 201
    selected[0] = actors["district_officer-north"]
    decision["evidence_ids"] = [fresh]
    app_without_policy = FastAPI()
    app_without_policy.include_router(build_router(factory, lambda: selected[0]))
    with TestClient(app_without_policy) as unconfigured:
        assert post(unconfigured, "/v1/status-decisions", decision).status_code == 503
    assert post(client, "/v1/status-decisions", decision).status_code == 201


def test_report_clarification_history_is_scoped_and_does_not_publish_status(api):
    client, factory, selected, actors = api
    report = post(client, "/v1/field-reports", report_body())
    assert report.status_code == 201
    report_id = report.json()["field_report_id"]
    path = f"/v1/field-reports/{report_id}/history"
    reply_path = f"/v1/field-reports/{report_id}/clarifications"
    selected[0] = actors["reviewer-north"]
    review = post(client, f"/v1/reviews/{report_id}", {
        "action": "needs_clarification", "note": "Please explain the blockage"
    })
    assert review.status_code == 201
    assert client.get(path).json()["history"][0]["note"] == "Please explain the blockage"
    selected[0] = actors["field_reporter-south"]
    assert client.get(path).status_code == 403
    assert post(client, reply_path, {"note": "wrong owner"}).status_code == 403
    selected[0] = actors["reviewer-south"]
    assert client.get(path).status_code == 403
    selected[0] = actors["field_reporter-north"]
    assert client.get(path).json()["can_respond"] is True
    reply = post(client, reply_path, {"note": "Two trees across the carriageway"}, "reply")
    assert reply.status_code == 201, reply.text
    assert post(client, reply_path, {
        "note": "Two trees across the carriageway"
    }, "reply").json() == reply.json()
    assert post(client, reply_path, {"note": "another reply"}).status_code == 409
    history = client.get(path).json()
    assert history["can_respond"] is False
    assert [item["kind"] for item in history["history"]] == ["review", "clarification"]
    assert history["history"][1]["actor_id"] == "field_reporter-north"
    selected[0] = actors["reviewer-north"]
    assert post(client, f"/v1/reviews/{report_id}", {
        "action": "accept", "note": "Clarification resolved"
    }).status_code == 201
    assert len(client.get(path).json()["history"]) == 3
    selected[0] = actors["field_reporter-north"]
    duplicate = post(client, "/v1/field-reports", {
        **report_body(), "client_sequence": 2
    })
    assert duplicate.status_code == 201
    duplicate_id = duplicate.json()["field_report_id"]
    selected[0] = actors["reviewer-north"]
    merged = post(client, f"/v1/reviews/{duplicate_id}", {
        "action": "merge", "note": "Same obstruction as accepted report",
        "merge_into_evidence_id": report_id,
    })
    assert merged.status_code == 201, merged.text
    assert client.get(f"/v1/field-reports/{duplicate_id}/history").json()["history"][0][
        "merge_into_evidence_id"
    ] == report_id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FieldReport)) == 2
        assert effective_status(session, "north")["status"] == "unknown"


def test_authority_order_reference_and_decision_history(api):
    client, factory, selected, actors = api
    selected[0] = actors["district_officer-north"]
    now = datetime.now(timezone.utc)
    body = {
        "segment_id": "north", "status": "closed", "vehicle_scope": ["rigid_truck"],
        "direction": "both", "reason_code": "authority_order", "evidence_ids": [],
        "effective_at": now.isoformat(), "valid_until": (now + timedelta(hours=1)).isoformat(),
        "note": "Road authority closure",
    }
    assert post(client, "/v1/status-decisions", body).status_code == 422
    assert post(client, "/v1/status-decisions", {
        **body, "vehicle_scope": ["all", "rigid_truck"], "order_reference": "ORDER-1"
    }).status_code == 422
    first = post(client, "/v1/status-decisions", {
        **body, "order_reference": "ORDER-1"
    })
    assert first.status_code == 201, first.text
    second = post(client, "/v1/status-decisions", {
        **body, "status": "restricted", "order_reference": "ORDER-2"
    })
    assert second.status_code == 201, second.text
    assert second.json()["supersedes_decision_id"] == first.json()["decision_id"]
    assert second.json()["audit_event_id"]
    history_path = "/v1/status-decisions/history?segment_id=north"
    decisions = client.get(history_path).json()["decisions"]
    assert len(decisions) == 2
    assert decisions[0]["order_reference"] == "ORDER-2"
    assert decisions[1]["order_reference"] == "ORDER-1"
    assert all(row["actor_id"] == "district_officer-north" for row in decisions)
    selected[0] = actors["regional_viewer-south"]
    assert client.get(history_path).status_code == 403
    selected[0] = actors["regional_viewer-north"]
    assert client.get(history_path).status_code == 200
    with factory.begin() as session:
        from ner_lens.operations import StatusDecision
        earlier = session.get(StatusDecision, first.json()["decision_id"])
        earlier.effective_at = now - timedelta(minutes=3)
        decision = session.get(StatusDecision, second.json()["decision_id"])
        decision.effective_at = now - timedelta(minutes=2)
        decision.valid_until = now - timedelta(seconds=1)
    assert client.get(history_path).json()["decisions"][0]["expired"] is True
    assert client.get("/v1/status-decisions?segment_id=north&vehicle_profile=rigid_truck").json()[
        "status"
    ] == "unknown"


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


def test_unassigned_mission_is_not_visible_or_actionable(api):
    client, _, selected, actors = api
    selected[0] = actors["dispatcher-north"]
    now = datetime.now(timezone.utc)
    created = post(
        client,
        "/v1/missions",
        {
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
            "assigned_actor_ids": [],
        },
    )
    assert created.status_code == 201, created.text
    mission_id = created.json()["mission_id"]
    selected[0] = actors["field_reporter-north"]
    assert client.get("/v1/missions", params={"corridor_id": "north"}).json()["missions"] == []
    assert client.get(f"/v1/missions/{mission_id}").status_code == 403
    for action in ("start", "complete"):
        assert post(client, f"/v1/missions/{mission_id}/{action}", None).status_code == 403
    point = {
        "sequence": 1,
        "captured_at": now.isoformat(),
        "geometry": {"type": "Point", "coordinates": [92, 25]},
        "accuracy_m": 5,
    }
    assert (
        post(
            client,
            f"/v1/missions/{mission_id}/positions",
            {
                "device_id": "unassigned-test",
                "sequence_start": 1,
                "points": [point],
            },
        ).status_code
        == 403
    )
    selected[0] = actors["regional_viewer-north"]
    assert client.get(f"/v1/missions/{mission_id}").status_code == 403
    selected[0] = actors["field_reporter-south"]
    assert client.get("/v1/missions", params={"corridor_id": "north"}).status_code == 403
    selected[0] = replace(actors["field_reporter-north"], expires_at=now - timedelta(seconds=1))
    assert client.get("/v1/missions", params={"corridor_id": "north"}).status_code == 403


def test_scoped_vehicle_driver_and_private_receiving_assignment(api):
    client, factory, selected, actors = api
    with factory.begin() as session:
        for vehicle_id, jurisdiction, profile, active in (
            ("vehicle-north", "north", "rigid_truck", True),
            ("vehicle-light", "north", "light_goods", True),
            ("vehicle-inactive", "north", "rigid_truck", False),
            ("vehicle-south", "south", "rigid_truck", True),
        ):
            session.add(
                Vehicle(
                    id=vehicle_id,
                    jurisdiction_id=jurisdiction,
                    alias=vehicle_id,
                    profile=profile,
                    active=active,
                )
            )
    selected[0] = actors["dispatcher-north"]
    vehicles = client.get("/v1/vehicles", params={"corridor_id": "north"})
    assert vehicles.status_code == 200
    assert {item["vehicle_id"] for item in vehicles.json()["vehicles"]} == {
        "vehicle-north",
        "vehicle-light",
    }
    assert client.get("/v1/vehicles", params={"corridor_id": "south"}).status_code == 403
    assignees = client.get("/v1/mission-assignees", params={"corridor_id": "north"}).json()
    assert [driver["actor_id"] for driver in assignees["drivers"]] == ["driver-north"]
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
        "vehicle_id": "vehicle-north",
        "driver_actor_id": "driver-north",
        "receiving_facility": "Test hospital",
        "receiving_contact": "Receiving desk, internal extension 42",
        "corridor_id": "north",
        "gps_consent": {"basis": "mission_assignment", "recorded_at": now.isoformat()},
        "assigned_actor_ids": ["field_reporter-north"],
    }
    created = post(client, "/v1/missions", body, "mission-assignment")
    assert created.status_code == 201, created.text
    assert post(client, "/v1/missions", body, "mission-assignment").json() == created.json()
    mission_id = created.json()["mission_id"]
    listing = client.get("/v1/missions", params={"corridor_id": "north"}).json()["missions"]
    assert [item["mission_id"] for item in listing] == [mission_id]
    assert "receiving_contact" not in listing[0]
    assert (
        client.get(f"/v1/missions/{mission_id}").json()["receiving_contact"]
        == body["receiving_contact"]
    )
    selected[0] = actors["field_reporter-north"]
    assert "receiving_contact" not in client.get(f"/v1/missions/{mission_id}").json()
    selected[0] = actors["dispatcher-north"]
    with factory() as session:
        row = session.get(Mission, mission_id)
        assert (row.vehicle_id, row.driver_actor_id, row.receiving_facility) == (
            "vehicle-north",
            "driver-north",
            "Test hospital",
        )
        assert "receiving_contact" not in row.payload
        assert session.scalar(
            select(AuditEvent).where(
                AuditEvent.target_id == mission_id,
                AuditEvent.action == "mission.assignment_created",
            )
        )
    for change in (
        {"vehicle_id": "vehicle-light"},
        {"vehicle_id": "vehicle-inactive"},
        {"vehicle_id": "vehicle-south"},
        {"driver_actor_id": "driver-south"},
        {"driver_actor_id": "driver-north", "vehicle_id": None},
        {"delivery_window": None},
    ):
        assert post(client, "/v1/missions", {**body, **change}).status_code == 422
    with factory.begin() as session:
        session.get(Actor, "driver-north").active = False
    assert post(client, "/v1/missions", body).status_code == 422
    selected[0] = actors["driver-north"]
    assert client.get("/v1/missions", params={"corridor_id": "north"}).status_code == 403
    with factory.begin() as session:
        session.get(Actor, "driver-north").active = True
    assert [
        item["mission_id"]
        for item in client.get("/v1/missions", params={"corridor_id": "north"}).json()["missions"]
    ] == [mission_id]
    assert client.get(f"/v1/missions/{mission_id}").status_code == 200
    assert post(client, f"/v1/missions/{mission_id}/start", None).status_code == 409
    selected[0] = actors["driver-south"]
    assert client.get(f"/v1/missions/{mission_id}").status_code == 403


def test_assigned_driver_lifecycle_requires_separate_confirmation(api):
    client, factory, selected, actors = api
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add(Vehicle(id="vehicle-north", jurisdiction_id="north",
                            alias="Fleet A7", profile="rigid_truck", active=True))
    selected[0] = actors["dispatcher-north"]
    body = {
        "cargo_class": "medicine", "priority": "high",
        "origin": {"type": "Point", "coordinates": [92, 25]},
        "destination": {"type": "Point", "coordinates": [92.1, 25.1]},
        "delivery_window": {"start": now.isoformat(),
                            "end": (now + timedelta(hours=2)).isoformat()},
        "vehicle_profile": "rigid_truck", "vehicle_id": "vehicle-north",
        "driver_actor_id": "driver-north", "corridor_id": "north",
        "gps_consent": {"basis": "mission_assignment", "recorded_at": now.isoformat()},
    }
    created = post(client, "/v1/missions", body)
    assert created.status_code == 201, created.text
    mid = created.json()["mission_id"]
    assert post(client, f"/v1/missions/{mid}/start", None).status_code == 403
    assert post(client, f"/v1/missions/{mid}/complete", None).status_code == 409
    selected[0] = actors["driver-south"]
    assert post(client, f"/v1/missions/{mid}/accept", None).status_code == 403
    selected[0] = actors["driver-north"]
    assert post(client, f"/v1/missions/{mid}/declare-delivery", None).status_code == 409
    accepted = post(client, f"/v1/missions/{mid}/accept", None, "accept")
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["state"] == "accepted"
    assert post(client, f"/v1/missions/{mid}/accept", None, "accept").json() == accepted.json()
    started = post(client, f"/v1/missions/{mid}/start", None, "start")
    assert started.status_code == 201, started.text
    fix = {
        "device_id": "driver-device", "sequence_start": 1,
        "points": [{"sequence": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
                    "geometry": {"type": "Point", "coordinates": [92, 25]},
                    "accuracy_m": 10}],
    }
    assert post(client, f"/v1/missions/{mid}/positions", fix).status_code == 201
    declared = post(client, f"/v1/missions/{mid}/declare-delivery", None)
    assert declared.status_code == 201 and declared.json()["state"] == "delivered"
    selected[0] = actors["dispatcher-north"]
    assert client.get(f"/v1/missions/{mid}").json()["state_history"][-1]["action"] == (
        "mission.driver_declared_delivery"
    )
    confirmed = post(client, f"/v1/missions/{mid}/confirm-delivery", {
        "basis": "receiver_attestation", "note": "Receiver verbally confirmed receipt"
    })
    assert confirmed.status_code == 201 and confirmed.json()["state"] == "completed"
    assert client.get(f"/v1/missions/{mid}").json()["confirmation"]["basis"] == (
        "receiver_attestation"
    )
    assert "confirmation" not in client.get(
        "/v1/missions", params={"corridor_id": "north"}
    ).json()["missions"][0]
    assert post(client, f"/v1/missions/{mid}/cancel", {"reason": "too late"}).status_code == 409

    rejected_mission = post(client, "/v1/missions", body).json()["mission_id"]
    selected[0] = actors["driver-north"]
    assert post(client, f"/v1/missions/{rejected_mission}/reject", None).status_code == 201
    assert post(client, f"/v1/missions/{rejected_mission}/accept", None).status_code == 409
    with factory.begin() as session:
        assignment = session.scalar(select(RoleAssignment).where(
            RoleAssignment.actor_id == "driver-north", RoleAssignment.role == "driver"
        ))
        session.delete(assignment)
    assert client.get(f"/v1/missions/{mid}").status_code == 403
