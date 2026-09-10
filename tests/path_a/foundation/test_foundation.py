from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.config import Settings
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.health import build_health_router, check_database_ready
from ner_lens.identity.models import AuditEvent, IdempotencyRecord


def test_sqlite_replay_repository_persists_foundation_entities_and_geojson():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])

    corridor_id = "11111111-1111-4111-8111-111111111111"
    segment_id = "22222222-2222-4222-8222-222222222222"
    with factory() as session:
        session.add(
            CorridorVersion(
                id=corridor_id,
                corridor_key="guwahati_silchar_nh27",
                graph_version="replay-graph-v1",
                graph_sha256="a" * 64,
                status="active",
                effective_from=datetime.now(timezone.utc),
            )
        )
        session.add(
            RoadSegment(
                id=segment_id,
                corridor_version_id=corridor_id,
                external_ref="osm:way/123",
                segment_type="road",
                direction="forward",
                geometry={
                    "type": "LineString",
                    "coordinates":[[91.7, 26.1], [92.8, 24.8]],
                },
                vehicle_constraints={"max_weight_t": 16.0},
            )
        )
        session.commit()

        stored = session.scalar(select(RoadSegment).where(RoadSegment.id == segment_id))

    assert stored is not None
    assert stored.geometry["type"] == "LineString"
    assert stored.geometry["coordinates"][0] == [91.7, 26.1]


def test_geometry_and_status_constraints_reject_invalid_values():
    with pytest.raises(ValueError, match="EPSG:4326"):
        RoadSegment(
            id="22222222-2222-4222-8222-222222222222",
            corridor_version_id="11111111-1111-4111-8111-111111111111",
            external_ref="osm:way/123",
            segment_type="road",
            direction="forward",
            geometry={"type": "Point", "coordinates": [91.7, 26.1]},
        )

    with pytest.raises(ValueError, match="status"):
        CorridorVersion(
            id="11111111-1111-4111-8111-111111111111",
            corridor_key="guwahati_silchar_nh27",
            graph_version="replay-graph-v1",
            graph_sha256="a" * 64,
            status="open",
            effective_from=datetime.now(timezone.utc),
        )


def test_idempotency_hash_and_expiry_are_scoped_and_deterministic():
    key = validate_idempotency_key("client-retry-1")
    first = canonical_request_hash({"b": 2, "a": 1})
    second = canonical_request_hash({"a": 1, "b": 2})
    assert key == "client-retry-1"
    assert first == second

    now = datetime.now(timezone.utc)
    record = IdempotencyRecord(
        id="33333333-3333-4333-8333-333333333333",
        actor_id="44444444-4444-4444-8444-444444444444",
        method="POST",
        path="/v1/evidence",
        idempotency_key=key,
        request_hash=first,
        status_code=201,
        response_body_hash="b" * 64,
        expires_at=now + timedelta(hours=24),
    )
    assert record.expires_at > now
    with pytest.raises(ValueError):
        validate_idempotency_key("")


def test_audit_event_is_append_only_by_model_contract():
    event = AuditEvent(
        id="55555555-5555-4555-8555-555555555555",
        actor_id="44444444-4444-4444-8444-444444444444",
        action="foundation.created",
        target_type="corridor_version",
        target_id="11111111-1111-4111-8111-111111111111",
        request_id="66666666-6666-4666-8666-666666666666",
        before_hash=None,
        after_hash="c" * 64,
        outcome="accepted",
    )
    assert event.before_hash is None
    assert event.after_hash == "c" * 64
    assert event.immutable is True


def test_health_router_separates_liveness_from_database_readiness():
    live_router = build_health_router(lambda: True)
    ready_router = build_health_router(lambda: False)
    assert live_router.live().status == "live"
    assert ready_router.live().status == "live"
    assert check_database_ready(lambda: True).status == "ready"
    assert check_database_ready(lambda: False).status == "not_ready"
    assert check_database_ready(lambda: False).http_status == 503
