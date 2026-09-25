"""Persisted, scoped report/review/status and mission/GPS operational workflow."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.identity.models import (
    Actor,
    AuditEvent,
    IdempotencyRecord,
    LocalAccount,
    RoleAssignment,
)
from ner_lens.identity.service import AuthContext, AuthorizationService, ResourceScope
from ner_lens.spatial import assert_corridor_point


def now_utc():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class FieldReport(Base):
    __tablename__ = "field_report"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_report_id: Mapped[str] = mapped_column(String(128), unique=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    segment_id: Mapped[str] = mapped_column(ForeignKey("road_segment.id"), index=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("jurisdiction.id"), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict] = mapped_column(JSON)


class EvidenceReview(Base):
    __tablename__ = "evidence_review"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("field_report.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class FieldClarification(Base):
    __tablename__ = "field_clarification"
    __table_args__ = (UniqueConstraint("review_id", name="uq_clarification_review"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("field_report.id"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("evidence_review.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(4000))


class StatusDecision(Base):
    __tablename__ = "status_decision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("road_segment.id"), index=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("jurisdiction.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class Vehicle(Base):
    __tablename__ = "vehicle"
    __table_args__ = (
        UniqueConstraint("jurisdiction_id", "alias", name="uq_vehicle_jurisdiction_alias"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("jurisdiction.id"), index=True)
    alias: Mapped[str] = mapped_column(String(64))
    profile: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Mission(Base):
    __tablename__ = "mission"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridor_version.id"))
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("jurisdiction.id"), index=True)
    graph_version_id: Mapped[str] = mapped_column(String(128))
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicle.id"))
    driver_actor_id: Mapped[str | None] = mapped_column(ForeignKey("actor.id"))
    receiving_facility: Mapped[str | None] = mapped_column(String(255))
    receiving_contact: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(16), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class MissionAssignment(Base):
    __tablename__ = "mission_assignment"
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), primary_key=True)


class GPSObservation(Base):
    __tablename__ = "gps_observation"
    __table_args__ = (
        UniqueConstraint("mission_id", "device_id", "sequence", name="uq_gps_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    sequence: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    flags: Mapped[list] = mapped_column(JSON)


class MutationResponse(Base):
    __tablename__ = "mutation_response"
    id: Mapped[str] = mapped_column(ForeignKey("idempotency_record.id"), primary_key=True)
    body: Mapped[dict] = mapped_column(JSON)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Input):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]

    @model_validator(mode="before")
    @classmethod
    def numeric_coordinates(cls, value):
        coordinates = value.get("coordinates") if isinstance(value, dict) else None
        if (
            not isinstance(coordinates, (list, tuple))
            or len(coordinates) != 2
            or any(
                isinstance(number, bool) or not isinstance(number, (int, float))
                for number in coordinates
            )
        ):
            raise ValueError("coordinates must contain two JSON numbers")
        return value

    @model_validator(mode="after")
    def valid(self):
        lon, lat = self.coordinates
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("coordinates must be [longitude, latitude] in EPSG:4326")
        return self


class ReportInput(Input):
    client_report_id: str = Field(min_length=1, max_length=128)
    client_sequence: int = Field(ge=0)
    segment_id: str = Field(min_length=1, max_length=36)
    observed_at: AwareDatetime
    geometry: Point
    accuracy_m: float = Field(ge=0, le=100000)
    status_claim: Literal["open", "restricted", "blocked", "closed", "unknown"]
    condition_code: str = Field(min_length=1, max_length=128)
    note: str = Field(max_length=4000)
    device_id: str = Field(min_length=1, max_length=128)
    clock_offset_seconds: float = Field(default=0, ge=-86400, le=86400)


class ReviewInput(Input):
    action: Literal["accept", "reject", "merge", "needs_clarification"]
    note: str = Field(min_length=1, max_length=4000)
    merge_into_evidence_id: str | None = None

    @model_validator(mode="after")
    def merge_target(self):
        if (self.action == "merge") != bool(self.merge_into_evidence_id):
            raise ValueError(
                "merge action requires a merge target; other actions cannot supply one"
            )
        return self


class ClarificationInput(Input):
    note: str = Field(min_length=1, max_length=4000)


class StatusInput(Input):
    segment_id: str
    status: Literal["open", "restricted", "closed", "unknown"]
    vehicle_scope: list[str] = Field(min_length=1, max_length=20)
    direction: Literal["forward", "reverse", "both"]
    reason_code: Literal[
        "authority_order", "flooded", "landslide", "damage", "restriction", "reopened", "expiry"
    ]
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    effective_at: AwareDatetime
    valid_until: AwareDatetime
    note: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def interval(self):
        if self.valid_until <= self.effective_at:
            raise ValueError("valid_until must follow effective_at")
        return self


class Window(Input):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start:
            raise ValueError("delivery end must follow start")
        return self


class Consent(Input):
    basis: Literal["mission_assignment", "explicit_consent"]
    recorded_at: AwareDatetime


class MissionInput(Input):
    cargo_class: str = Field(min_length=1, max_length=128)
    priority: Literal["routine", "high", "emergency"]
    origin: Point
    destination: Point
    delivery_window: Window
    vehicle_profile: Literal["light_goods", "rigid_truck", "emergency"]
    vehicle_id: str | None = None
    driver_actor_id: str | None = None
    receiving_facility: str | None = Field(default=None, min_length=1, max_length=255)
    receiving_contact: str | None = Field(default=None, min_length=1, max_length=255)
    corridor_id: str
    route_id: str | None = None
    gps_consent: Consent
    assigned_actor_ids: list[str] = Field(default_factory=list, max_length=100)


class ConfirmationInput(Input):
    basis: Literal["dispatcher_observation", "receiver_attestation"]
    note: str = Field(min_length=1, max_length=1000)


class CancellationInput(Input):
    reason: str = Field(min_length=1, max_length=1000)


class Position(Input):
    sequence: int = Field(ge=0)
    captured_at: AwareDatetime
    geometry: Point
    accuracy_m: float = Field(ge=0, le=100000)
    speed_mps: float | None = Field(default=None, ge=0, le=1000)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)


class PositionsInput(Input):
    device_id: str = Field(min_length=1, max_length=128)
    sequence_start: int = Field(ge=0)
    points: list[Position] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def sequences(self):
        seq = [point.sequence for point in self.points]
        if len(set(seq)) != len(seq) or min(seq) != self.sequence_start:
            raise ValueError("sequences must be unique and sequence_start must equal the minimum")
        return self


def effective_status(session, segment_id, at=None, *, direction="both", vehicle_profile="all"):
    """Latest applicable decision; expiry never resurrects an older open decision."""
    at = at or now_utc()
    rows = session.scalars(
        select(StatusDecision)
        .where(
            StatusDecision.segment_id == segment_id,
            StatusDecision.effective_at <= at,
        )
        .order_by(
            StatusDecision.effective_at.desc(),
            StatusDecision.created_at.desc(),
            StatusDecision.id.desc(),
        )
    ).all()
    applicable = [
        row
        for row in rows
        if (
            row.payload["direction"] == "both"
            or direction == "both"
            or row.payload["direction"] == direction
        )
        and (
            "all" in row.payload["vehicle_scope"]
            or vehicle_profile == "all"
            or vehicle_profile in row.payload["vehicle_scope"]
        )
    ]
    # A general read cannot imply every direction/vehicle is open from one scoped decision.
    if not applicable:
        return {
            "segment_id": segment_id,
            "status": "unknown",
            "freshness": "missing",
            "evidence_ids": [],
        }
    latest = applicable[0]
    expired = utc(latest.valid_until) <= at
    scoped = (direction == "both" and latest.payload["direction"] != "both") or (
        vehicle_profile == "all" and "all" not in latest.payload["vehicle_scope"]
    )
    return {
        **latest.payload,
        "decision_id": latest.id,
        "status": "unknown" if expired or scoped else latest.payload["status"],
        "freshness": "expired" if expired else "scope_required" if scoped else "current",
        "operational_mode": "decision_support",
    }


def build_router(factory, current_actor):
    router = APIRouter(tags=["operations"])

    def audit_authorization(event):
        with factory.begin() as session:
            session.add(event)

    authorization = AuthorizationService(session_factory=factory, audit_sink=audit_authorization)

    def fail(code, detail):
        raise HTTPException(code, detail)

    def authorize(actor, action, jurisdiction, **scope):
        decision = authorization.authorize(
            actor, action, ResourceScope(jurisdiction_id=jurisdiction, **scope)
        )
        if not decision.allowed:
            fail(403, decision.code)

    def corridor(session, corridor_id):
        row = session.get(CorridorVersion, corridor_id)
        if not row or not row.jurisdiction_id:
            fail(404, "corridor_not_found")
        return row

    def segment_scope(session, segment_id):
        row = session.get(RoadSegment, segment_id)
        if not row:
            fail(404, "segment_not_found")
        return corridor(session, row.corridor_version_id).jurisdiction_id

    def validate_point(session, corridor_id, coordinates):
        try:
            assert_corridor_point(session, corridor_id, coordinates)
        except ValueError as exc:
            fail(422, str(exc))

    def latest_review(session, evidence_id):
        return session.scalar(
            select(EvidenceReview)
            .where(EvidenceReview.evidence_id == evidence_id)
            .order_by(EvidenceReview.created_at.desc(), EvidenceReview.id.desc())
        )

    def mutate(session, actor, path, key, payload, jurisdiction, action, create):
        try:
            return apply_mutation(session, actor, path, key, payload, jurisdiction, action, create)
        except IntegrityError:
            session.rollback()
            old = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.actor_id == actor.actor_id,
                    IdempotencyRecord.method == "POST",
                    IdempotencyRecord.path == path,
                    IdempotencyRecord.idempotency_key == key,
                )
            )
            if old and old.request_hash == canonical_request_hash(payload):
                return session.get(MutationResponse, old.id).body
            fail(409, "idempotency_conflict")

    def apply_mutation(session, actor, path, key, payload, jurisdiction, action, create):
        try:
            validate_idempotency_key(key)
        except ValueError as exc:
            fail(422, str(exc))
        digest = canonical_request_hash(payload)
        old = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == actor.actor_id,
                IdempotencyRecord.method == "POST",
                IdempotencyRecord.path == path,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        if old:
            if old.request_hash != digest:
                fail(409, "idempotency_conflict")
            return session.get(MutationResponse, old.id).body
        request_id, audit_id = str(uuid4()), str(uuid4())
        body = create(request_id, audit_id)
        record_id = str(uuid4())
        session.add(
            AuditEvent(
                id=audit_id,
                actor_id=actor.actor_id,
                action=action,
                target_type="operations",
                target_id=body.get(
                    "decision_id", body.get("mission_id", body.get("field_report_id", path))
                ),
                request_id=request_id,
                jurisdiction_id=jurisdiction,
                before_hash=None,
                after_hash=canonical_request_hash(body),
                reason=payload.get("note", action),
                outcome="allowed",
            )
        )
        session.add(
            IdempotencyRecord(
                id=record_id,
                actor_id=actor.actor_id,
                method="POST",
                path=path,
                idempotency_key=key,
                request_hash=digest,
                status_code=201,
                response_body_hash=canonical_request_hash(body),
                expires_at=now_utc() + timedelta(days=365),
            )
        )
        session.flush()
        session.add(MutationResponse(id=record_id, body=body))
        session.commit()
        return body

    @router.get("/v1/corridors/{corridor_id}/capabilities")
    def capabilities(corridor_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            graph = corridor(session, corridor_id)
            authorize(actor, "read_corridor_state", graph.jurisdiction_id)
            actions = {}
            for action in (
                "create_field_report",
                "review_evidence",
                "publish_status",
                "create_mission",
                "compare_routes",
                "submit_gps",
                "view_mission",
            ):
                decision = authorization.authorize(
                    actor,
                    action,
                    ResourceScope(
                        jurisdiction_id=graph.jurisdiction_id,
                        status_authority_actor_id=actor.actor_id,
                    ),
                )
                actions[action] = {"allowed": decision.allowed, "reason": decision.code}
            return {"actions": actions, "data_mode": "replay"}

    @router.post("/v1/field-reports", status_code=201)
    def report(
        body: ReportInput,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
        x_ner_lens_actor: str | None = Header(default=None),
    ):
        with factory() as session:
            jurisdiction = segment_scope(session, body.segment_id)
            authorize(actor, "create_field_report", jurisdiction)
            if x_ner_lens_actor is not None and x_ner_lens_actor != actor.actor_id:
                fail(403, "session_actor_changed")
            validate_point(
                session,
                session.get(RoadSegment, body.segment_id).corridor_version_id,
                body.geometry.coordinates,
            )
            payload = body.model_dump(mode="json")

            def create(request_id, _audit):
                if body.observed_at > now_utc():
                    fail(422, "observation_in_future")
                old = session.scalar(
                    select(FieldReport).where(FieldReport.client_report_id == body.client_report_id)
                )
                if old:
                    if old.actor_id != actor.actor_id or old.payload != payload:
                        fail(409, "idempotency_conflict")
                    return old.response
                report_id = str(uuid4())
                received = now_utc()
                response = {
                    "field_report_id": report_id,
                    "client_report_id": body.client_report_id,
                    "sync_state": "accepted_for_review",
                    "review_state": "unreviewed",
                    "received_at": received.isoformat(),
                    "media_state": "none",
                    "request_id": request_id,
                }
                session.add(
                    FieldReport(
                        id=report_id,
                        client_report_id=body.client_report_id,
                        actor_id=actor.actor_id,
                        segment_id=body.segment_id,
                        jurisdiction_id=jurisdiction,
                        received_at=received,
                        payload=payload,
                        response=response,
                    )
                )
                return response

            return mutate(
                session,
                actor,
                "/v1/field-reports",
                idempotency_key,
                payload,
                jurisdiction,
                "field_report.created",
                create,
            )

    @router.get("/v1/field-reports")
    def reports(
        segment_id: str,
        limit: int = Query(100, ge=1, le=500),
        actor: AuthContext = Depends(current_actor),
    ):
        with factory() as session:
            jurisdiction = segment_scope(session, segment_id)
            reviewer = "reviewer" in actor.roles
            officer = "district_officer" in actor.roles
            authorize(
                actor,
                "review_evidence"
                if reviewer
                else "read_corridor_state"
                if officer
                else "view_own_report",
                jurisdiction,
            )
            query = select(FieldReport).where(FieldReport.segment_id == segment_id)
            if not reviewer and not officer:
                query = query.where(FieldReport.actor_id == actor.actor_id)
            rows = session.scalars(
                query.order_by(FieldReport.received_at.desc()).limit(limit)
            ).all()
            return {
                "reports": [
                    {
                        **row.payload,
                        **row.response,
                        "review_state": review.payload["action"]
                        if (review := latest_review(session, row.id))
                        else "unreviewed",
                    }
                    for row in rows
                ]
            }

    @router.post("/v1/reviews/{evidence_id}", status_code=201)
    def review(
        evidence_id: str,
        body: ReviewInput,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            report = session.get(FieldReport, evidence_id)
            if not report:
                fail(404, "evidence_not_found")
            authorize(actor, "review_evidence", report.jurisdiction_id)

            def create(request_id, audit_id):
                if body.action == "merge":
                    target = session.get(FieldReport, body.merge_into_evidence_id)
                    if (
                        not target
                        or target.segment_id != report.segment_id
                        or target.id == report.id
                    ):
                        fail(422, "merge_target_must_be_other_report_on_same_segment")
                    target_review = latest_review(session, target.id)
                    if not target_review or target_review.payload["action"] != "accept":
                        fail(422, "merge_target_must_be_accepted")
                review_id = str(uuid4())
                session.add(
                    EvidenceReview(
                        id=review_id,
                        evidence_id=evidence_id,
                        actor_id=actor.actor_id,
                        created_at=now_utc(),
                        payload=body.model_dump(mode="json"),
                    )
                )
                return {
                    "review_id": review_id,
                    "evidence_id": evidence_id,
                    "review_state": body.action,
                    "audit_event_id": audit_id,
                    "request_id": request_id,
                }

            return mutate(
                session,
                actor,
                f"/v1/reviews/{evidence_id}",
                idempotency_key,
                body.model_dump(mode="json"),
                report.jurisdiction_id,
                "evidence.reviewed",
                create,
            )

    @router.get("/v1/field-reports/{evidence_id}/history")
    def report_history(evidence_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            report = session.get(FieldReport, evidence_id)
            if not report:
                fail(404, "evidence_not_found")
            reviewer = "reviewer" in actor.roles and report.actor_id != actor.actor_id
            authorize(actor, "review_evidence" if reviewer else "view_own_report",
                      report.jurisdiction_id,
                      **({} if reviewer else {"owner_actor_id": report.actor_id}))
            reviews = session.scalars(select(EvidenceReview).where(
                EvidenceReview.evidence_id == evidence_id
            ).order_by(EvidenceReview.created_at, EvidenceReview.id)).all()
            responses = session.scalars(select(FieldClarification).where(
                FieldClarification.evidence_id == evidence_id
            ).order_by(FieldClarification.created_at, FieldClarification.id)).all()
            latest = reviews[-1] if reviews else None
            answered = any(row.review_id == latest.id for row in responses) if latest else False
            history = [
                {"kind": "review", "id": row.id, "action": row.payload["action"],
                 "note": row.payload["note"], "actor_id": row.actor_id,
                 "at": utc(row.created_at).isoformat(),
                 "merge_into_evidence_id": row.payload.get("merge_into_evidence_id")}
                for row in reviews
            ] + [
                {"kind": "clarification", "id": row.id, "review_id": row.review_id,
                 "note": row.note, "actor_id": row.actor_id,
                 "at": utc(row.created_at).isoformat()}
                for row in responses
            ]
            history.sort(key=lambda row: (row["at"], row["id"]))
            return {"evidence_id": evidence_id, "review_state": latest.payload["action"]
                    if latest else "unreviewed", "can_respond": not reviewer and bool(latest)
                    and latest.payload["action"] == "needs_clarification" and not answered,
                    "history": history}

    @router.post("/v1/field-reports/{evidence_id}/clarifications", status_code=201)
    def clarify(evidence_id: str, body: ClarificationInput,
                actor: AuthContext = Depends(current_actor),
                idempotency_key: str = Header()):
        with factory() as session:
            report = session.get(FieldReport, evidence_id)
            if not report:
                fail(404, "evidence_not_found")
            authorize(actor, "view_own_report", report.jurisdiction_id,
                      owner_actor_id=report.actor_id)

            def create(request_id, _audit):
                review = latest_review(session, evidence_id)
                if not review or review.payload["action"] != "needs_clarification":
                    fail(409, "clarification_not_requested")
                if session.scalar(select(FieldClarification).where(
                    FieldClarification.review_id == review.id
                )):
                    fail(409, "clarification_already_answered")
                row = FieldClarification(
                    id=str(uuid4()), evidence_id=evidence_id, review_id=review.id,
                    actor_id=actor.actor_id, created_at=now_utc(), note=body.note,
                )
                session.add(row)
                return {"clarification_id": row.id, "field_report_id": evidence_id,
                        "review_id": review.id, "request_id": request_id}

            return mutate(session, actor, f"/v1/field-reports/{evidence_id}/clarifications",
                          idempotency_key, body.model_dump(mode="json"),
                          report.jurisdiction_id, "evidence.clarified", create)

    @router.post("/v1/status-decisions", status_code=201)
    def status(
        body: StatusInput,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            jurisdiction = segment_scope(session, body.segment_id)
            authorize(
                actor, "publish_status", jurisdiction, status_authority_actor_id=actor.actor_id
            )
            payload = body.model_dump(mode="json")

            def create(request_id, audit_id):
                if body.valid_until <= now_utc():
                    fail(422, "status_already_expired")
                if (
                    not body.evidence_ids
                    and body.reason_code != "authority_order"
                    and body.status != "unknown"
                ):
                    fail(422, "accepted_evidence_required")
                for evidence_id in body.evidence_ids:
                    evidence = session.get(FieldReport, evidence_id)
                    revision = latest_review(session, evidence_id)
                    if (
                        not evidence
                        or evidence.segment_id != body.segment_id
                        or not revision
                        or revision.payload["action"] != "accept"
                    ):
                        fail(422, "accepted_segment_evidence_required")
                decision_id = str(uuid4())
                session.add(
                    StatusDecision(
                        id=decision_id,
                        segment_id=body.segment_id,
                        jurisdiction_id=jurisdiction,
                        actor_id=actor.actor_id,
                        created_at=now_utc(),
                        effective_at=body.effective_at,
                        valid_until=body.valid_until,
                        payload=payload,
                    )
                )
                return {
                    **payload,
                    "decision_id": decision_id,
                    "audit_event_id": audit_id,
                    "request_id": request_id,
                }

            return mutate(
                session,
                actor,
                "/v1/status-decisions",
                idempotency_key,
                payload,
                jurisdiction,
                "status.published",
                create,
            )

    @router.get("/v1/status-decisions")
    def statuses(
        segment_id: str,
        direction: Literal["forward", "reverse", "both"] = "both",
        vehicle_profile: str = "all",
        actor: AuthContext = Depends(current_actor),
    ):
        with factory() as session:
            authorize(actor, "read_corridor_state", segment_scope(session, segment_id))
            return effective_status(
                session, segment_id, direction=direction, vehicle_profile=vehicle_profile
            )

    def mission_scope(session, actor, mission_id, action):
        row = session.get(Mission, mission_id)
        if not row:
            fail(404, "mission_not_found")
        if action == "submit_gps":
            if row.driver_actor_id != actor.actor_id and not session.get(
                MissionAssignment, (actor.actor_id, mission_id)
            ):
                fail(403, "mission_assignment_required")
            authorize(actor, action, row.jurisdiction_id)
        elif action == "view_assigned_mission":
            if row.driver_actor_id != actor.actor_id:
                fail(403, "mission_assignment_required")
            authorize(actor, action, row.jurisdiction_id)
        else:
            authorize(actor, "view_mission", row.jurisdiction_id, owner_actor_id=row.actor_id)
        return row

    def mission_view(session, row, *, private=False):
        last = session.scalar(
            select(GPSObservation)
            .where(GPSObservation.mission_id == row.id)
            .order_by(GPSObservation.captured_at.desc())
            .limit(1)
        )
        deadline = datetime.fromisoformat(row.payload["delivery_window"]["end"])
        history = session.scalars(
            select(AuditEvent).where(
                AuditEvent.target_id == row.id,
                AuditEvent.action.like("mission.%"),
            ).order_by(AuditEvent.occurred_at, AuditEvent.id)
        ).all() if private else []
        return {
            **{
                key: value for key, value in row.payload.items()
                if private or key not in {"confirmation", "cancellation_reason"}
            },
            "mission_id": row.id,
            "state": row.state,
            "graph_version_id": row.graph_version_id,
            "created_at": utc(row.created_at).isoformat(),
            "started_at": utc(row.started_at).isoformat() if row.started_at else None,
            "jurisdiction_id": row.jurisdiction_id,
            "vehicle_id": row.vehicle_id,
            "driver_actor_id": row.driver_actor_id,
            "receiving_facility": row.receiving_facility,
            **({"receiving_contact": row.receiving_contact} if private else {}),
            "last_fix": {**last.payload, "flags": last.flags} if last else None,
            "last_fix_age_seconds": max(0, (now_utc() - utc(last.captured_at)).total_seconds())
            if last
            else None,
            "completed_at": utc(row.completed_at).isoformat() if row.completed_at else None,
            "deadline_state": "overdue"
            if deadline < (utc(row.completed_at) if row.completed_at else now_utc())
            else "within_window",
            "delay_estimate": None,
            "delay_estimate_basis": "no_verified_eta",
            "checkpoints": [],
            **({"state_history": [
                {"action": event.action, "actor_id": event.actor_id,
                 "at": utc(event.occurred_at).isoformat()}
                for event in history
            ]} if private else {}),
        }

    @router.post("/v1/missions", status_code=201)
    def mission(
        body: MissionInput,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            graph = corridor(session, body.corridor_id)
            authorize(actor, "create_mission", graph.jurisdiction_id)

            def create(request_id, _audit):
                if (
                    body.delivery_window.end <= now_utc()
                    or body.gps_consent.recorded_at > now_utc()
                ):
                    fail(422, "invalid_deadline_or_consent_time")
                validate_point(session, graph.id, body.origin.coordinates)
                validate_point(session, graph.id, body.destination.coordinates)
                if body.route_id:
                    fail(422, "route_binding_not_available")
                if body.driver_actor_id and not body.vehicle_id:
                    fail(422, "driver_requires_vehicle")
                if body.receiving_contact and not body.receiving_facility:
                    fail(422, "contact_requires_facility")
                if body.vehicle_id:
                    vehicle = session.get(Vehicle, body.vehicle_id)
                    if (
                        not vehicle
                        or not vehicle.active
                        or vehicle.jurisdiction_id != graph.jurisdiction_id
                        or vehicle.profile != body.vehicle_profile
                    ):
                        fail(422, "vehicle_inactive_unscoped_or_incompatible")
                if body.driver_actor_id:
                    driver = session.get(Actor, body.driver_actor_id)
                    assignment = session.scalar(
                        select(RoleAssignment).where(
                            RoleAssignment.actor_id == body.driver_actor_id,
                            RoleAssignment.role == "driver",
                            RoleAssignment.jurisdiction_id == graph.jurisdiction_id,
                        )
                    )
                    if not driver or not driver.active or not assignment:
                        fail(422, "driver_inactive_or_unscoped")
                for actor_id in body.assigned_actor_ids:
                    stored = session.get(Actor, actor_id)
                    assignment = session.scalar(
                        select(RoleAssignment).where(
                            RoleAssignment.actor_id == actor_id,
                            RoleAssignment.role == "field_reporter",
                            RoleAssignment.jurisdiction_id == graph.jurisdiction_id,
                        )
                    )
                    if not stored or not stored.active or not assignment:
                        fail(422, "assigned_actor_must_be_active_scoped_field_reporter")
                row = Mission(
                    id=str(uuid4()),
                    actor_id=actor.actor_id,
                    corridor_id=graph.id,
                    jurisdiction_id=graph.jurisdiction_id,
                    graph_version_id=graph.graph_version,
                    vehicle_id=body.vehicle_id,
                    driver_actor_id=body.driver_actor_id,
                    receiving_facility=body.receiving_facility,
                    receiving_contact=body.receiving_contact,
                    state="planned",
                    created_at=now_utc(),
                    payload=body.model_dump(
                        mode="json",
                        exclude={
                            "vehicle_id",
                            "driver_actor_id",
                            "receiving_facility",
                            "receiving_contact",
                        },
                    ),
                )
                session.add(row)
                session.flush()
                for actor_id in set(body.assigned_actor_ids):
                    session.add(MissionAssignment(actor_id=actor_id, mission_id=row.id))
                if body.driver_actor_id or body.vehicle_id:
                    session.add(
                        AuditEvent(
                            id=str(uuid4()),
                            actor_id=actor.actor_id,
                            action="mission.assignment_created",
                            target_type="mission",
                            target_id=row.id,
                            jurisdiction_id=graph.jurisdiction_id,
                            request_id=request_id,
                            outcome="allowed",
                            reason=f"driver={body.driver_actor_id};vehicle={body.vehicle_id}",
                        )
                    )
                return {**mission_view(session, row, private=True), "request_id": request_id}

            return mutate(
                session,
                actor,
                "/v1/missions",
                idempotency_key,
                body.model_dump(mode="json"),
                graph.jurisdiction_id,
                "mission.created",
                create,
            )

    @router.get("/v1/vehicles")
    def vehicles(corridor_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            graph = corridor(session, corridor_id)
            authorize(actor, "create_mission", graph.jurisdiction_id)
            rows = session.scalars(
                select(Vehicle)
                .where(Vehicle.jurisdiction_id == graph.jurisdiction_id, Vehicle.active.is_(True))
                .order_by(Vehicle.alias)
            ).all()
            return {
                "vehicles": [
                    {"vehicle_id": row.id, "alias": row.alias, "profile": row.profile}
                    for row in rows
                ]
            }

    @router.get("/v1/mission-assignees")
    def assignees(corridor_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            graph = corridor(session, corridor_id)
            authorize(actor, "create_mission", graph.jurisdiction_id)
            rows = (
                session.scalars(
                    select(Actor)
                    .join(RoleAssignment)
                    .where(
                        Actor.active.is_(True),
                        RoleAssignment.role == "field_reporter",
                        RoleAssignment.jurisdiction_id == graph.jurisdiction_id,
                    )
                )
                .unique()
                .all()
            )
            drivers = (
                session.scalars(
                    select(Actor)
                    .join(RoleAssignment)
                    .where(
                        Actor.active.is_(True),
                        RoleAssignment.role == "driver",
                        RoleAssignment.jurisdiction_id == graph.jurisdiction_id,
                    )
                )
                .unique()
                .all()
            )
            return {
                "actors": [
                    {
                        "actor_id": row.id,
                        "display_name": account.display_name
                        if (account := session.get(LocalAccount, row.id))
                        else "Field reporter",
                    }
                    for row in rows
                ],
                "drivers": [
                    {
                        "actor_id": row.id,
                        "display_name": account.display_name
                        if (account := session.get(LocalAccount, row.id))
                        else "Driver",
                    }
                    for row in drivers
                ],
            }

    @router.get("/v1/missions")
    def missions(corridor_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            graph = corridor(session, corridor_id)
            query = select(Mission).where(Mission.corridor_id == corridor_id)
            if "driver" in actor.roles:
                authorize(actor, "view_assigned_mission", graph.jurisdiction_id)
                query = query.where(Mission.driver_actor_id == actor.actor_id)
            elif "field_reporter" in actor.roles:
                authorize(actor, "submit_gps", graph.jurisdiction_id)
                query = query.join(MissionAssignment).where(
                    MissionAssignment.actor_id == actor.actor_id
                )
            else:
                authorize(actor, "view_mission", graph.jurisdiction_id)
                query = query.where(Mission.actor_id == actor.actor_id)
            rows = session.scalars(query.order_by(Mission.created_at.desc()).limit(100)).all()
            return {"missions": [mission_view(session, row) for row in rows]}

    @router.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            action = (
                "view_assigned_mission"
                if "driver" in actor.roles
                else "submit_gps"
                if "field_reporter" in actor.roles
                else "view_mission"
            )
            return mission_view(
                session, mission_scope(session, actor, mission_id, action),
                private=action != "submit_gps",
            )

    @router.post("/v1/missions/{mission_id}/start", status_code=201)
    def start(
        mission_id: str,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            stored = session.get(Mission, mission_id)
            if stored and stored.driver_actor_id:
                action = "view_assigned_mission"
            else:
                action = "submit_gps" if "field_reporter" in actor.roles else "view_mission"
            row = mission_scope(session, actor, mission_id, action)

            def create(request_id, _audit):
                if datetime.fromisoformat(row.payload["delivery_window"]["end"]) <= now_utc():
                    fail(409, "mission_deadline_passed")
                if row.state != ("accepted" if row.driver_actor_id else "planned"):
                    fail(409, "mission_already_started")
                row.state, row.started_at = "active", now_utc()
                return {
                    **mission_view(session, row),
                    "gps_session_id": row.id,
                    "request_id": request_id,
                }

            return mutate(
                session,
                actor,
                f"/v1/missions/{mission_id}/start",
                idempotency_key,
                {},
                row.jurisdiction_id,
                "mission.started",
                create,
            )

    @router.post("/v1/missions/{mission_id}/complete", status_code=201)
    def complete(
        mission_id: str,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            action = "submit_gps" if "field_reporter" in actor.roles else "view_mission"
            row = mission_scope(session, actor, mission_id, action)

            def create(request_id, _audit):
                if row.driver_actor_id:
                    fail(409, "driver_declaration_and_dispatcher_confirmation_required")
                if row.state != "active":
                    fail(409, "mission_not_active")
                row.state, row.completed_at = "completed", now_utc()
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(
                session,
                actor,
                f"/v1/missions/{mission_id}/complete",
                idempotency_key,
                {},
                row.jurisdiction_id,
                "mission.completed",
                create,
            )

    @router.post("/v1/missions/{mission_id}/accept", status_code=201)
    def accept_mission(mission_id: str, actor: AuthContext = Depends(current_actor),
                       idempotency_key: str = Header()):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "view_assigned_mission")

            def create(request_id, _audit):
                if row.state != "planned":
                    fail(409, "mission_not_planned")
                if datetime.fromisoformat(row.payload["delivery_window"]["end"]) <= now_utc():
                    fail(409, "mission_deadline_passed")
                row.state = "accepted"
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(session, actor, f"/v1/missions/{mission_id}/accept", idempotency_key,
                          {}, row.jurisdiction_id, "mission.accepted", create)

    @router.post("/v1/missions/{mission_id}/reject", status_code=201)
    def reject_mission(mission_id: str, actor: AuthContext = Depends(current_actor),
                       idempotency_key: str = Header()):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "view_assigned_mission")

            def create(request_id, _audit):
                if row.state != "planned":
                    fail(409, "mission_not_planned")
                row.state = "rejected"
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(session, actor, f"/v1/missions/{mission_id}/reject", idempotency_key,
                          {}, row.jurisdiction_id, "mission.rejected", create)

    @router.post("/v1/missions/{mission_id}/declare-delivery", status_code=201)
    def declare_delivery(mission_id: str, actor: AuthContext = Depends(current_actor),
                         idempotency_key: str = Header()):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "view_assigned_mission")

            def create(request_id, _audit):
                if row.state != "active":
                    fail(409, "mission_not_active")
                row.state = "delivered"
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(session, actor, f"/v1/missions/{mission_id}/declare-delivery",
                          idempotency_key, {}, row.jurisdiction_id,
                          "mission.driver_declared_delivery", create)

    @router.post("/v1/missions/{mission_id}/confirm-delivery", status_code=201)
    def confirm_delivery(mission_id: str, body: ConfirmationInput,
                         actor: AuthContext = Depends(current_actor),
                         idempotency_key: str = Header()):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "view_mission")

            def create(request_id, _audit):
                if not row.driver_actor_id or row.state != "delivered":
                    fail(409, "driver_declaration_required")
                row.state, row.completed_at = "completed", now_utc()
                row.payload = {**row.payload, "confirmation": body.model_dump(mode="json")}
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(session, actor, f"/v1/missions/{mission_id}/confirm-delivery",
                          idempotency_key, body.model_dump(mode="json"), row.jurisdiction_id,
                          "mission.delivery_confirmed", create)

    @router.post("/v1/missions/{mission_id}/cancel", status_code=201)
    def cancel_mission(mission_id: str, body: CancellationInput,
                       actor: AuthContext = Depends(current_actor),
                       idempotency_key: str = Header()):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "view_mission")

            def create(request_id, _audit):
                if row.state not in ("planned", "accepted", "active", "delivered"):
                    fail(409, "mission_cannot_be_cancelled")
                row.state = "cancelled"
                row.payload = {**row.payload, "cancellation_reason": body.reason}
                return {**mission_view(session, row), "request_id": request_id}

            return mutate(session, actor, f"/v1/missions/{mission_id}/cancel",
                          idempotency_key, body.model_dump(mode="json"), row.jurisdiction_id,
                          "mission.cancelled", create)

    @router.post("/v1/missions/{mission_id}/positions", status_code=201)
    def positions(
        mission_id: str,
        body: PositionsInput,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        with factory() as session:
            row = mission_scope(session, actor, mission_id, "submit_gps")

            def create(request_id, _audit):
                if row.state != "active":
                    fail(409, "mission_not_active")
                received = now_utc()
                accepted, duplicates, rejected, flagged = [], [], [], []
                for point in sorted(
                    body.points, key=lambda point: (point.captured_at, point.sequence)
                ):
                    payload = point.model_dump(mode="json")
                    old = session.scalar(
                        select(GPSObservation).where(
                            GPSObservation.mission_id == mission_id,
                            GPSObservation.device_id == body.device_id,
                            GPSObservation.sequence == point.sequence,
                        )
                    )
                    if old:
                        if old.payload != payload:
                            fail(409, "gps_sequence_conflict")
                        duplicates.append(point.sequence)
                        continue
                    if point.captured_at > received or point.captured_at < utc(row.started_at):
                        rejected.append(point.sequence)
                        continue
                    validate_point(session, row.corridor_id, point.geometry.coordinates)
                    previous = session.scalar(
                        select(GPSObservation)
                        .where(
                            GPSObservation.mission_id == mission_id,
                            GPSObservation.device_id == body.device_id,
                            GPSObservation.captured_at <= point.captured_at,
                        )
                        .order_by(GPSObservation.captured_at.desc())
                        .limit(1)
                    )
                    flags = []
                    if previous:
                        a, b = (
                            previous.payload["geometry"]["coordinates"],
                            point.geometry.coordinates,
                        )
                        lat1, lat2 = math.radians(a[1]), math.radians(b[1])
                        h = (
                            math.sin((lat2 - lat1) / 2) ** 2
                            + math.cos(lat1)
                            * math.cos(lat2)
                            * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
                        )
                        distance = 6371000 * 2 * math.asin(min(1, math.sqrt(h)))
                        seconds = (point.captured_at - utc(previous.captured_at)).total_seconds()
                        # ponytail: 100 m/s flags only; calibrate by fleet before alerting.
                        if (
                            distance
                            > previous.payload["accuracy_m"] + point.accuracy_m + 100 * seconds
                        ):
                            flags.append("impossible_jump")
                    newest = session.scalar(
                        select(GPSObservation)
                        .where(
                            GPSObservation.mission_id == mission_id,
                            GPSObservation.device_id == body.device_id,
                        )
                        .order_by(GPSObservation.sequence.desc())
                        .limit(1)
                    )
                    if newest and point.sequence < newest.sequence:
                        flags.append("out_of_order")
                    session.add(
                        GPSObservation(
                            id=str(uuid4()),
                            mission_id=mission_id,
                            device_id=body.device_id,
                            sequence=point.sequence,
                            captured_at=point.captured_at,
                            received_at=received,
                            payload=payload,
                            flags=flags,
                        )
                    )
                    session.flush()
                    accepted.append(point.sequence)
                    if flags:
                        flagged.append(point.sequence)
                return {
                    "mission_id": mission_id,
                    "accepted": accepted,
                    "duplicate": duplicates,
                    "rejected": rejected,
                    "flagged": flagged,
                    "received_at": received.isoformat(),
                    "request_id": request_id,
                }

            return mutate(
                session,
                actor,
                f"/v1/missions/{mission_id}/positions",
                idempotency_key,
                body.model_dump(mode="json"),
                row.jurisdiction_id,
                "gps.received",
                create,
            )

    return router
