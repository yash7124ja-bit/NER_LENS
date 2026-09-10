"""Replay-only review and status state machine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.audit.service import AuditLog
from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.corridor.models import RoadSegment
from ner_lens.evidence.models import Evidence, EvidenceReview, ReviewIdempotency
from ner_lens.identity.service import AuthContext
from ner_lens.status.models import StatusConflict, StatusDecision, StatusIdempotency

REPLAY_REVIEWER = "replay_reviewer"
REPLAY_OFFICER = "replay_district_officer"
REPLAY_JURISDICTION = "replay_guwahati_silchar"
REVIEW_ACTIONS = frozenset({"accept", "reject", "merge", "needs_clarification"})
STATUSES = frozenset({"open", "restricted", "closed", "unknown"})
DIRECTIONS = frozenset({"forward", "reverse", "both"})


class IdempotencyConflict(ValueError):
    """The same actor/key was used for a different request body."""


@dataclass(frozen=True, slots=True)
class ReviewResult:
    review_id: str
    evidence_id: str
    review_state: str
    audit_event_id: str
    request_id: str
    before_hash: str
    after_hash: str


@dataclass(frozen=True, slots=True)
class StatusResult:
    decision_id: str | None
    segment_id: str
    status: str
    vehicle_scope: tuple[str, ...]
    direction: str
    reason_code: str
    evidence_ids: tuple[str, ...]
    audit_event_id: str | None
    conflict_ids: tuple[str, ...] = ()


class ReviewService:
    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self.audit_log = audit_log or AuditLog()

    def review_evidence(
        self,
        factory: sessionmaker[Session],
        *,
        evidence_id: str,
        actor: AuthContext,
        action: str,
        note: str,
        jurisdiction_id: str,
        request_id: str,
        idempotency_key: str,
        merge_into_evidence_id: str | None = None,
    ) -> ReviewResult:
        _require_replay_identity(actor, REPLAY_REVIEWER, jurisdiction_id)
        if action not in REVIEW_ACTIONS:
            raise ValueError("unsupported review action")
        validate_idempotency_key(idempotency_key)
        request_hash = canonical_request_hash(
            {
                "evidence_id": evidence_id,
                "action": action,
                "note": note,
                "jurisdiction_id": jurisdiction_id,
                "merge_into_evidence_id": merge_into_evidence_id,
            }
        )
        with _session_scope(factory) as session:
            prior = session.scalar(
                select(ReviewIdempotency).where(
                    ReviewIdempotency.actor_id == actor.actor_id,
                    ReviewIdempotency.idempotency_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise IdempotencyConflict("review idempotency key conflicts with request body")
                return _review_result(session.get(EvidenceReview, prior.review_id))
            evidence = session.get(Evidence, evidence_id)
            if evidence is None:
                raise ValueError("evidence does not exist")
            before_hash = canonical_request_hash(
                {"review_state": evidence.review_state, "quality_flags": evidence.quality_flags}
            )
            resulting_state = _review_state(evidence.review_state, action)
            if action == "merge":
                if (
                    merge_into_evidence_id is None
                    or session.get(Evidence, merge_into_evidence_id) is None
                ):
                    raise ValueError("merge requires an existing target evidence record")
            evidence.review_state = resulting_state
            if (
                resulting_state == "conflict"
                and "review_disagreement" not in evidence.quality_flags
            ):
                evidence.quality_flags = [*evidence.quality_flags, "review_disagreement"]
            after_hash = canonical_request_hash(
                {"review_state": evidence.review_state, "quality_flags": evidence.quality_flags}
            )
            review = EvidenceReview(
                id=str(uuid.uuid4()),
                evidence_id=evidence.id,
                actor_id=actor.actor_id,
                action=action,
                note=note,
                merge_into_evidence_id=merge_into_evidence_id,
                resulting_state=resulting_state,
                request_id=request_id,
                idempotency_key=idempotency_key,
                before_hash=before_hash,
                after_hash=after_hash,
                audit_event_id="pending",
                occurred_at=datetime.now(timezone.utc),
            )
            session.add(review)
            session.flush()
            audit = self.audit_log.append(
                actor_id=actor.actor_id,
                action="evidence.review",
                target_type="evidence",
                target_id=evidence.id,
                request_id=request_id,
                before_hash=before_hash,
                after_hash=after_hash,
            )
            review.audit_event_id = audit.id
            session.add(
                ReviewIdempotency(
                    id=str(uuid.uuid4()),
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    review_id=review.id,
                )
            )
            session.flush()
            return ReviewResult(
                review_id=review.id,
                evidence_id=evidence.id,
                review_state=resulting_state,
                audit_event_id=audit.id,
                request_id=request_id,
                before_hash=before_hash,
                after_hash=after_hash,
            )


class StatusService:
    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self.audit_log = audit_log or AuditLog()

    def decide_status(
        self,
        factory: sessionmaker[Session],
        *,
        segment_id: str,
        actor: AuthContext,
        status: str,
        vehicle_scope: list[str],
        direction: str,
        reason_code: str,
        evidence_ids: list[str],
        effective_at: datetime,
        valid_until: datetime | None,
        jurisdiction_id: str,
        request_id: str,
        idempotency_key: str,
        note: str = "",
    ) -> StatusResult:
        _require_replay_identity(actor, REPLAY_OFFICER, jurisdiction_id)
        if actor.status_authority_actor_id != actor.actor_id:
            raise PermissionError("server-bound status authority is required")
        if status not in STATUSES:
            raise ValueError("unsupported operational status")
        if direction not in DIRECTIONS:
            raise ValueError("unsupported status direction")
        if not vehicle_scope or len(set(vehicle_scope)) != len(vehicle_scope):
            raise ValueError("vehicle_scope must be non-empty and unique")
        _require_aware(effective_at, "effective_at")
        if valid_until is not None:
            _require_aware(valid_until, "valid_until")
            if valid_until <= effective_at:
                raise ValueError("valid_until must be after effective_at")
        if status != "unknown" and valid_until is None:
            raise ValueError("non-unknown status requires valid_until")
        validate_idempotency_key(idempotency_key)
        request_hash = canonical_request_hash(
            {
                "segment_id": segment_id,
                "status": status,
                "vehicle_scope": vehicle_scope,
                "direction": direction,
                "reason_code": reason_code,
                "evidence_ids": evidence_ids,
                "effective_at": effective_at.isoformat(),
                "valid_until": valid_until.isoformat() if valid_until else None,
                "jurisdiction_id": jurisdiction_id,
                "note": note,
            }
        )
        with _session_scope(factory) as session:
            prior = session.scalar(
                select(StatusIdempotency).where(
                    StatusIdempotency.actor_id == actor.actor_id,
                    StatusIdempotency.idempotency_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise IdempotencyConflict("status idempotency key conflicts with request body")
                return _status_result(session.get(StatusDecision, prior.status_decision_id))
            if session.get(RoadSegment, segment_id) is None:
                raise ValueError("segment does not exist")
            evidence = session.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))).all()
            if len(evidence) != len(set(evidence_ids)):
                raise ValueError("every evidence ID must exist")
            if status in {"restricted", "closed"}:
                if not evidence_ids and reason_code != "authority_order":
                    raise ValueError("restricted or closed status requires accepted evidence")
                if any(item.evidence_type in {"risk", "weather"} for item in evidence):
                    raise ValueError("risk or weather evidence cannot change status")
                if any(item.review_state != "accepted" for item in evidence):
                    raise ValueError("status evidence must be accepted")
            before = _current_decision(session, segment_id, vehicle_scope, direction, effective_at)
            before_hash = canonical_request_hash(_status_payload(before))
            decision = StatusDecision(
                id=str(uuid.uuid4()),
                segment_id=segment_id,
                actor_id=actor.actor_id,
                jurisdiction_id=jurisdiction_id,
                status=status,
                vehicle_scope=vehicle_scope,
                direction=direction,
                reason_code=reason_code,
                evidence_ids=evidence_ids,
                effective_at=effective_at,
                valid_until=valid_until,
                note=note,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=datetime.now(timezone.utc),
                audit_event_id="pending",
            )
            session.add(decision)
            session.flush()
            for existing in _overlapping_decisions(
                session, segment_id, vehicle_scope, direction, effective_at
            ):
                if existing.status != status:
                    session.add(
                        StatusConflict(
                            id=str(uuid.uuid4()),
                            segment_id=segment_id,
                            existing_decision_id=existing.id,
                            incoming_decision_id=decision.id,
                            reason="disagreeing applicable status decisions are preserved",
                            created_at=datetime.now(timezone.utc),
                        )
                    )
            after_hash = canonical_request_hash(_status_payload(decision))
            audit = self.audit_log.append(
                actor_id=actor.actor_id,
                action="status.decide",
                target_type="segment",
                target_id=segment_id,
                request_id=request_id,
                before_hash=before_hash,
                after_hash=after_hash,
            )
            decision.audit_event_id = audit.id
            session.add(
                StatusIdempotency(
                    id=str(uuid.uuid4()),
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    status_decision_id=decision.id,
                )
            )
            session.flush()
            return _status_result(decision)

    def get_current_status(
        self,
        factory: sessionmaker[Session],
        *,
        segment_id: str,
        vehicle_profile: str,
        direction: str,
        at: datetime,
    ) -> StatusResult:
        _require_aware(at, "at")
        with factory() as session:
            decisions = session.scalars(
                select(StatusDecision).where(
                    StatusDecision.segment_id == segment_id,
                    StatusDecision.effective_at <= at,
                )
            ).all()
            applicable = [
                decision
                for decision in decisions
                if _applies(decision, vehicle_profile, direction)
            ]
            current = [
                decision
                for decision in applicable
                if decision.valid_until is None or _as_utc(decision.valid_until) > at
            ]
            conflicts = session.scalars(
                select(StatusConflict).where(StatusConflict.segment_id == segment_id)
            ).all()
            if not current:
                return StatusResult(
                    decision_id=None,
                    segment_id=segment_id,
                    status="unknown",
                    vehicle_scope=(),
                    direction=direction,
                    reason_code="expiry" if applicable else "no_current_status",
                    evidence_ids=(),
                    audit_event_id=None,
                    conflict_ids=tuple(item.id for item in conflicts),
                )
            decision = max(current, key=lambda item: (item.effective_at, item.created_at, item.id))
            result = _status_result(decision)
            return StatusResult(
                decision_id=result.decision_id,
                segment_id=result.segment_id,
                status=result.status,
                vehicle_scope=result.vehicle_scope,
                direction=result.direction,
                reason_code=result.reason_code,
                evidence_ids=result.evidence_ids,
                audit_event_id=result.audit_event_id,
                conflict_ids=tuple(item.id for item in conflicts),
            )


def _session_scope(factory: sessionmaker[Session]):
    from ner_lens.db import session_scope

    return session_scope(factory)


def _require_replay_identity(actor: AuthContext, expected_id: str, jurisdiction_id: str) -> None:
    if (
        actor.actor_id != expected_id
        or actor.actor_type != "synthetic"
        or jurisdiction_id != REPLAY_JURISDICTION
        or jurisdiction_id not in actor.jurisdiction_ids
    ):
        raise PermissionError("replay identity or jurisdiction scope is not authorized")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _review_state(previous: str, action: str) -> str:
    if action == "accept":
        return "conflict" if previous == "rejected" else "accepted"
    if action == "reject":
        return "conflict" if previous == "accepted" else "rejected"
    if action == "merge":
        return "merged"
    return "needs_clarification"


def _review_result(review: EvidenceReview | None) -> ReviewResult:
    if review is None:
        raise ValueError("idempotency record points to missing review")
    return ReviewResult(
        review_id=review.id,
        evidence_id=review.evidence_id,
        review_state=review.resulting_state,
        audit_event_id=review.audit_event_id,
        request_id=review.request_id,
        before_hash=review.before_hash,
        after_hash=review.after_hash,
    )


def _status_result(decision: StatusDecision | None) -> StatusResult:
    if decision is None:
        raise ValueError("idempotency record points to missing status decision")
    return StatusResult(
        decision_id=decision.id,
        segment_id=decision.segment_id,
        status=decision.status,
        vehicle_scope=tuple(decision.vehicle_scope),
        direction=decision.direction,
        reason_code=decision.reason_code,
        evidence_ids=tuple(decision.evidence_ids),
        audit_event_id=decision.audit_event_id,
    )


def _status_payload(decision: StatusDecision | None) -> dict[str, Any]:
    if decision is None:
        return {"status": "unknown"}
    return {
        "id": decision.id,
        "status": decision.status,
        "vehicle_scope": decision.vehicle_scope,
        "direction": decision.direction,
        "effective_at": decision.effective_at.isoformat(),
        "valid_until": decision.valid_until.isoformat() if decision.valid_until else None,
        "evidence_ids": decision.evidence_ids,
    }


def _applies(decision: StatusDecision, vehicle_profile: str, direction: str) -> bool:
    vehicle_match = "all" in decision.vehicle_scope or vehicle_profile in decision.vehicle_scope
    direction_match = decision.direction == "both" or decision.direction == direction
    return vehicle_match and direction_match


def _current_decision(
    session: Session,
    segment_id: str,
    vehicle_scope: list[str],
    direction: str,
    at: datetime,
) -> StatusDecision | None:
    decisions = session.scalars(
        select(StatusDecision).where(
            StatusDecision.segment_id == segment_id,
            StatusDecision.effective_at <= at,
        )
    ).all()
    applicable = [
        decision
        for decision in decisions
        if _scope_overlaps(decision, vehicle_scope, direction)
        and (decision.valid_until is None or _as_utc(decision.valid_until) > at)
    ]
    return max(
        applicable,
        key=lambda item: (item.effective_at, item.created_at, item.id),
        default=None,
    )


def _scope_overlaps(decision: StatusDecision, vehicle_scope: list[str], direction: str) -> bool:
    vehicle_match = (
        "all" in decision.vehicle_scope
        or "all" in vehicle_scope
        or bool(set(decision.vehicle_scope).intersection(vehicle_scope))
    )
    direction_match = (
        decision.direction == "both" or direction == "both" or decision.direction == direction
    )
    return vehicle_match and direction_match


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetime round-trip for deterministic comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _overlapping_decisions(
    session: Session,
    segment_id: str,
    vehicle_scope: list[str],
    direction: str,
    at: datetime,
) -> list[StatusDecision]:
    decisions = session.scalars(
        select(StatusDecision).where(
            StatusDecision.segment_id == segment_id,
            StatusDecision.effective_at <= at,
        )
    ).all()
    return [
        decision
        for decision in decisions
        if set(decision.vehicle_scope).intersection(vehicle_scope)
        and (decision.direction == "both" or direction == "both" or decision.direction == direction)
    ]
