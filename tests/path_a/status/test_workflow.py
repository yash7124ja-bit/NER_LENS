from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from ner_lens.config import Settings
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.evidence.service import EvidenceService
from ner_lens.identity.models import Actor, AuditEvent, Jurisdiction, RoleAssignment, SessionRecord
from ner_lens.identity.service import AuthContext, AuthorizationService
from ner_lens.status.models import StatusConflict, StatusDecision
from ner_lens.status.service import (
    FreshnessPolicy,
    IdempotencyConflict,
    ReviewService,
    StatusService,
)

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
        session.add(Jurisdiction(id=JURISDICTION, code=JURISDICTION, name="Replay"))
        for actor_id, session_id, role in (
            (REVIEWER, f"session-{REVIEWER}", "reviewer"),
            (OFFICER, f"session-{OFFICER}", "district_officer"),
        ):
            session.add(Actor(id=actor_id, external_subject=actor_id, actor_type="synthetic"))
            session.add(
                SessionRecord(
                    id=session_id,
                    actor_id=actor_id,
                    token_issued_at=NOW - timedelta(hours=1),
                    expires_at=NOW + timedelta(hours=1),
                    active=True,
                )
            )
            session.add(
                RoleAssignment(
                    id=f"assignment-{role}",
                    actor_id=actor_id,
                    role=role,
                    jurisdiction_id=JURISDICTION,
                )
            )
        session.commit()
    return factory


def record_evidence(
    factory,
    evidence_type="field_report",
    source_record_id="receipt-1",
    observed_at=NOW - timedelta(minutes=5),
):
    evidence_service = EvidenceService()
    raw_payload = {"source_record_id": source_record_id}
    content_sha256 = hashlib.sha256(
        json.dumps(raw_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot = evidence_service.record_snapshot(
        factory,
        source="replay_fixture",
        source_url="replay://fixture_graph.v1",
        retrieved_at=NOW,
        source_published_at=NOW,
        content_sha256=content_sha256,
        parser_version="fixture-parser-v1",
        raw_payload=raw_payload,
        terms_label="replay-fixture",
        stale_after=timedelta(hours=6),
        now=NOW,
    )
    evidence = evidence_service.record_evidence(
        factory,
        snapshot_id=snapshot.id,
        evidence_type=evidence_type,
        source="replay_fixture",
        source_record_id=source_record_id,
        observed_at=observed_at,
        retrieved_at=NOW,
        geometry={"type": "Point", "coordinates": [91.8, 26.05]},
        raw_value={"condition": "blocked"},
        units={},
        valid_until=NOW + timedelta(hours=6),
        now=NOW,
    )
    return evidence_service.associate_evidence(
        factory,
        evidence_id=evidence.id,
        segment_id=SEGMENT_ID,
        method="manual_review",
    )


def test_only_replay_reviewer_can_review_and_idempotency_replays_original():
    factory = build_factory()
    evidence = record_evidence(factory)
    service = ReviewService(
        authorization_service=AuthorizationService(session_factory=factory)
    )
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
    fresh_service = ReviewService(
        authorization_service=AuthorizationService(session_factory=factory)
    )
    replayed_from_new_instance = fresh_service.review_evidence(
        factory,
        evidence_id=evidence.id,
        actor=actor(REVIEWER, "reviewer"),
        action="accept",
        note="replay review",
        jurisdiction_id=JURISDICTION,
        request_id="review-request-new-instance",
        idempotency_key="review-key-1",
    )
    assert replayed_from_new_instance.review_id == first.review_id
    with factory() as session:
        assert session.query(AuditEvent).count() == 1
    with factory() as session:
        session.get(SessionRecord, f"session-{REVIEWER}").revoked_at = NOW
        session.commit()
    with pytest.raises(PermissionError, match="expired or revoked"):
        service.review_evidence(
            factory,
            evidence_id=evidence.id,
            actor=actor(REVIEWER, "reviewer"),
            action="accept",
            note="replay review",
            jurisdiction_id=JURISDICTION,
            request_id="review-request-after-revoke",
            idempotency_key="review-key-1",
        )
    with factory() as session:
        assert session.query(AuditEvent).count() == 1


def test_status_scope_expiry_conflict_and_forbidden_risk_transition():
    factory = build_factory()
    evidence = record_evidence(factory)
    service = ReviewService(
        authorization_service=AuthorizationService(session_factory=factory)
    )
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
    status_service = StatusService(
        authorization_service=AuthorizationService(session_factory=factory),
        freshness_policy=FreshnessPolicy(max_event_age=timedelta(hours=6)),
    )
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
    with pytest.raises(ValueError, match="quarantined"):
        service.review_evidence(
            factory,
            evidence_id=weather.id,
            actor=actor(REVIEWER, "reviewer"),
            action="accept",
            note="must not accept weather",
            jurisdiction_id=JURISDICTION,
            request_id="weather-review",
            idempotency_key="weather-review-key",
        )
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
        vehicle_scope=["all"],
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


def test_old_event_with_fresh_retrieval_is_not_status_eligible():
    factory = build_factory()
    evidence = record_evidence(
        factory,
        observed_at=NOW - timedelta(hours=7),
        source_record_id="old-receipt",
    )
    ReviewService(
        authorization_service=AuthorizationService(session_factory=factory)
    ).review_evidence(
        factory,
        evidence_id=evidence.id,
        actor=actor(REVIEWER, "reviewer"),
        action="accept",
        note="accept old observation",
        jurisdiction_id=JURISDICTION,
        request_id="old-review",
        idempotency_key="old-review-key",
    )
    with pytest.raises(ValueError, match="stale"):
        StatusService(
            authorization_service=AuthorizationService(session_factory=factory),
            freshness_policy=FreshnessPolicy(max_event_age=timedelta(hours=6)),
        ).decide_status(
            factory,
            segment_id=SEGMENT_ID,
            actor=actor(OFFICER, "district_officer"),
            status="restricted",
            vehicle_scope=["rigid_truck"],
            direction="forward",
            reason_code="old-observation",
            evidence_ids=[evidence.id],
            effective_at=NOW,
            valid_until=NOW + timedelta(hours=1),
            jurisdiction_id=JURISDICTION,
            request_id="old-status",
            idempotency_key="old-status-key",
        )
