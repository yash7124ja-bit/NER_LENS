from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ner_lens.config import Settings
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.evidence.service import EvidenceService
from ner_lens.identity.service import AuthContext
from ner_lens.status.models import StatusConflict, StatusDecision
from ner_lens.status.service import IdempotencyConflict, ReviewService, StatusService

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
OFFICER = "replay_district_officer"
REVIEWER = "replay_reviewer"
JURISDICTION = "replay_guwahati_silchar"
SEGMENT_ID = "22222222-2222-4222-8222-222222222222"


def actor(actor_id: str, role: str) -> AuthContext:
    return AuthContext(
        actor_id=actor_id,
        actor_type="synthetic",
        roles=(role,),
        jurisdiction_ids=(JURISDICTION,),
        mission_ids=(),
        session_id=f"session-{actor_id}",
        token_issued_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        status_authority_actor_id=OFFICER if role == "district_officer" else None,
    )


def build_factory():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(
            CorridorVersion(
                id="11111111-1111-4111-8111-111111111111",
                corridor_key="guwahati_silchar_nh27",
                graph_version="ner-lens-route-audit-fixture-v1",
                graph_sha256="7" * 64,
                status="active",
                effective_from=NOW,
            )
        )
        session.add(
            RoadSegment(
                id=SEGMENT_ID,
                corridor_version_id="11111111-1111-4111-8111-111111111111",
                external_ref="band_1_jalukbari_nagaon",
                segment_type="road",
                direction="both",
                geometry={"type": "LineString", "coordinates": [[91.7, 26.1], [92.0, 26.0]]},
                vehicle_constraints={},
            )
        )
        session.commit()
    return factory


def record_evidence(factory, evidence_type="field_report", source_record_id="receipt-1"):
    evidence_service = EvidenceService()
    snapshot = evidence_service.record_snapshot(
        factory,
        source="replay_fixture",
        source_url="replay://fixture_graph.v1",
        retrieved_at=NOW,
        source_published_at=NOW,
        content_sha256="a" * 64,
        parser_version="fixture-parser-v1",
        raw_payload={"source_record_id": source_record_id},
        terms_label="replay-fixture",
        now=NOW,
    )
    return evidence_service.record_evidence(
        factory,
        snapshot_id=snapshot.id,
        evidence_type=evidence_type,
        source="replay_fixture",
        source_record_id=source_record_id,
        observed_at=NOW - timedelta(minutes=5),
        retrieved_at=NOW,
        geometry={"type": "Point", "coordinates": [91.8, 26.05]},
        raw_value={"condition": "blocked"},
        units={},
        now=NOW,
    )


def test_only_replay_reviewer_can_review_and_idempotency_replays_original():
    factory = build_factory()
    evidence = record_evidence(factory)
    service = ReviewService()
    first = service.review_evidence(
        factory,
        evidence_id=evidence.id,
        actor=actor(REVIEWER, "reviewer"),
        action="accept",
        note="replay review",
        jurisdiction_id=JURISDICTION,
        request_id="review-request-1",
        idempotency_key="review-key-1",
    )
    replay = service.review_evidence(
        factory,
        evidence_id=evidence.id,
        actor=actor(REVIEWER, "reviewer"),
        action="accept",
        note="replay review",
        jurisdiction_id=JURISDICTION,
        request_id="review-request-2",
        idempotency_key="review-key-1",
    )
    assert replay.review_id == first.review_id
    assert replay.audit_event_id == first.audit_event_id
    with pytest.raises(IdempotencyConflict):
        service.review_evidence(
            factory,
            evidence_id=evidence.id,
            actor=actor(REVIEWER, "reviewer"),
            action="reject",
            note="changed body",
            jurisdiction_id=JURISDICTION,
            request_id="review-request-3",
            idempotency_key="review-key-1",
        )
    with pytest.raises(PermissionError):
        service.review_evidence(
            factory,
            evidence_id=evidence.id,
            actor=actor("ordinary-reviewer", "reviewer"),
            action="accept",
            note="not replay identity",
            jurisdiction_id=JURISDICTION,
            request_id="review-request-4",
            idempotency_key="review-key-2",
        )
    assert first.audit_event_id
    assert first.before_hash != first.after_hash


def test_status_scope_expiry_conflict_and_forbidden_risk_transition():
    factory = build_factory()
    evidence = record_evidence(factory)
    service = ReviewService()
    service.review_evidence(
        factory,
        evidence_id=evidence.id,
        actor=actor(REVIEWER, "reviewer"),
        action="accept",
        note="accept",
        jurisdiction_id=JURISDICTION,
        request_id="review-request",
        idempotency_key="review-key",
    )
    status_service = StatusService()
    decision = status_service.decide_status(
        factory,
        segment_id=SEGMENT_ID,
        actor=actor(OFFICER, "district_officer"),
        status="restricted",
        vehicle_scope=["rigid_truck"],
        direction="forward",
        reason_code="damage",
        evidence_ids=[evidence.id],
        effective_at=NOW,
        valid_until=NOW + timedelta(hours=1),
        jurisdiction_id=JURISDICTION,
        request_id="status-request",
        idempotency_key="status-key",
    )
    assert decision.status == "restricted"
    replayed_decision = status_service.decide_status(
        factory,
        segment_id=SEGMENT_ID,
        actor=actor(OFFICER, "district_officer"),
        status="restricted",
        vehicle_scope=["rigid_truck"],
        direction="forward",
        reason_code="damage",
        evidence_ids=[evidence.id],
        effective_at=NOW,
        valid_until=NOW + timedelta(hours=1),
        jurisdiction_id=JURISDICTION,
        request_id="status-request-retry",
        idempotency_key="status-key",
    )
    assert replayed_decision.decision_id == decision.decision_id
    assert replayed_decision.audit_event_id == decision.audit_event_id
    assert status_service.get_current_status(
        factory, segment_id=SEGMENT_ID, vehicle_profile="rigid_truck", direction="forward", at=NOW
    ).status == "restricted"
    assert status_service.get_current_status(
        factory, segment_id=SEGMENT_ID, vehicle_profile="light_goods", direction="forward", at=NOW
    ).status == "unknown"
    assert status_service.get_current_status(
        factory,
        segment_id=SEGMENT_ID,
        vehicle_profile="rigid_truck",
        direction="forward",
        at=NOW + timedelta(hours=2),
    ).status == "unknown"

    weather = record_evidence(factory, evidence_type="weather", source_record_id="weather-1")
    with pytest.raises(ValueError, match="risk or weather"):
        status_service.decide_status(
            factory,
            segment_id=SEGMENT_ID,
            actor=actor(OFFICER, "district_officer"),
            status="closed",
            vehicle_scope=["all"],
            direction="both",
            reason_code="flooded",
            evidence_ids=[weather.id],
            effective_at=NOW,
            valid_until=NOW + timedelta(hours=1),
            jurisdiction_id=JURISDICTION,
            request_id="status-weather",
            idempotency_key="status-weather-key",
        )

    conflict = status_service.decide_status(
        factory,
        segment_id=SEGMENT_ID,
        actor=actor(OFFICER, "district_officer"),
        status="open",
        vehicle_scope=["rigid_truck"],
        direction="forward",
        reason_code="reopened",
        evidence_ids=[evidence.id],
        effective_at=NOW + timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=2),
        jurisdiction_id=JURISDICTION,
        request_id="status-conflict",
        idempotency_key="status-conflict-key",
    )
    assert conflict.status == "open"
    with factory() as session:
        assert session.query(StatusConflict).count() == 1
        assert session.query(StatusDecision).count() == 2
