"""Scoped baseline route comparisons. Missing verification policy means no recommendation."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import LineString
from shapely.ops import transform
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.config import utc_datetime
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.identity.models import AuditEvent
from ner_lens.identity.replay import authorize_corridor
from ner_lens.identity.service import AuthorizationService, ResourceScope
from ner_lens.local_routing import retrieve_local_graphhopper
from ner_lens.operations import (
    EvidenceReview,
    FieldReport,
    Mission,
    Point,
    StatusDecision,
    effective_status,
)
from ner_lens.sources import SourceSnapshot, retrieve
from ner_lens.spatial import assert_corridor_point, projected_corridor


class RouteComparisonRecord(Base):
    __tablename__ = "route_comparison"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key", name="uq_route_actor_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridor_version.id"))
    graph_version: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class RouteSelectionRecord(Base):
    __tablename__ = "route_selection"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_route_selection_actor_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), index=True)
    comparison_id: Mapped[str] = mapped_column(ForeignKey("route_comparison.id"))
    route_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MissionImpactRecord(Base):
    __tablename__ = "mission_impact"
    __table_args__ = (UniqueConstraint(
        "mission_id", "decision_id", "route_selection_id", name="uq_mission_impact_basis"
    ),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridor_version.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), index=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("status_decision.id"))
    route_selection_id: Mapped[str] = mapped_column(ForeignKey("route_selection.id"))
    state: Mapped[str] = mapped_column(String(16))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class RouteChangeApproval(Base):
    __tablename__ = "route_change_approval"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_route_change_actor_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    impact_id: Mapped[str] = mapped_column(ForeignKey("mission_impact.id"))
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), index=True)
    comparison_id: Mapped[str] = mapped_column(ForeignKey("route_comparison.id"))
    route_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class RouteAlert(Base):
    __tablename__ = "route_alert"
    __table_args__ = (UniqueConstraint("approval_id", name="uq_route_alert_approval"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("route_change_approval.id"))
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission.id"), index=True)
    recipient_actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class AlertDeliveryAttempt(Base):
    __tablename__ = "alert_delivery_attempt"
    __table_args__ = (UniqueConstraint("alert_id", "channel", name="uq_alert_delivery_channel"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("route_alert.id"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[str] = mapped_column(String(24))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertAcknowledgment(Base):
    __tablename__ = "alert_acknowledgment"
    __table_args__ = (
        UniqueConstraint("alert_id", name="uq_alert_acknowledgment"),
        UniqueConstraint("actor_id", "idempotency_key", name="uq_alert_ack_actor_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("route_alert.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    selection_id: Mapped[str | None] = mapped_column(ForeignKey("route_selection.id"))


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corridor_id: str
    graph_version_id: str
    origin: Point
    destination: Point
    vehicle_profile: str = Field(pattern="^(light_goods|rigid_truck|emergency)$")
    mission_id: str | None = None
    impact_id: str | None = None
    departure_at: AwareDatetime
    deadline_at: AwareDatetime
    alternative_limit: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def deadline(self):
        if self.deadline_at <= self.departure_at:
            raise ValueError("deadline must follow departure")
        return self


class RouteSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comparison_id: str
    route_id: str


class RouteChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impact_id: str
    comparison_id: str
    route_id: str
    reason: str = Field(min_length=10, max_length=1000)


class AlertAcknowledgmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(accept|decline)$")


def current_impact(session, mission: Mission, impact_id: str, now: datetime):
    impact = session.get(MissionImpactRecord, impact_id)
    if (
        impact is None
        or impact.mission_id != mission.id
        or impact.state != "active"
        or mission.state not in ("accepted", "active")
    ):
        raise HTTPException(409, "impact_not_active")
    selected = session.get(RouteSelectionRecord, impact.route_selection_id)
    latest = session.scalar(
        select(RouteSelectionRecord)
        .where(RouteSelectionRecord.mission_id == mission.id)
        .order_by(RouteSelectionRecord.selected_at.desc(), RouteSelectionRecord.id.desc())
    )
    if selected is None or latest is None or selected.id != latest.id:
        raise HTTPException(409, "selected_route_changed")
    graph = session.get(CorridorVersion, mission.corridor_id)
    if graph is None or graph.graph_version != mission.graph_version_id:
        raise HTTPException(409, "graph_version_changed")
    status = effective_status(
        session,
        impact.payload["segment_id"],
        now,
        vehicle_profile=mission.payload["vehicle_profile"],
    )
    if status.get("decision_id") != impact.decision_id or status["status"] not in (
        "closed",
        "restricted",
    ):
        raise HTTPException(409, "authority_decision_changed")
    return impact, selected


def current_route_candidate(session, mission, impact, route, expires_at, now):
    if now >= expires_at:
        raise HTTPException(409, "source_snapshot_expired")
    candidate_segments = set(route.get("segment_ids", []))
    corridor_segments = set(session.scalars(select(RoadSegment.id).where(
        RoadSegment.corridor_version_id == mission.corridor_id
    )).all())
    if (not candidate_segments or not candidate_segments <= corridor_segments
            or impact.payload["segment_id"] in candidate_segments):
        raise HTTPException(409, "candidate_coverage_unverified")
    for segment_id in candidate_segments:
        status = effective_status(session, segment_id, now,
                                  vehicle_profile=mission.payload["vehicle_profile"])
        expected = route.get("decision_snapshots", {}).get(segment_id)
        if (expected is None or status.get("decision_id") != expected.get("decision_id")
                or status["freshness"] != expected.get("freshness")
                or status["status"] in ("closed", "restricted")):
            raise HTTPException(409, "candidate_decision_changed")


def alert_view(session, alert):
    delivery = session.scalar(select(AlertDeliveryAttempt).where(
        AlertDeliveryAttempt.alert_id == alert.id
    ))
    acknowledgment = session.scalar(select(AlertAcknowledgment).where(
        AlertAcknowledgment.alert_id == alert.id
    ))
    return {
        **alert.payload,
        "delivery_state": "delivered_in_app" if delivery else "queued_in_app",
        "delivered_at": utc_datetime(delivery.attempted_at).isoformat() if delivery else None,
        "acknowledgment": None if acknowledgment is None else {
            "decision": acknowledgment.decision,
            "acknowledged_at": utc_datetime(acknowledgment.acknowledged_at).isoformat(),
            "selection_id": acknowledgment.selection_id,
        },
    }


def build_router(factory, current_actor, settings):
    router = APIRouter(tags=["routing"])

    @router.get("/v1/corridors/{corridor_id}/map-route")
    def map_route(corridor_id: str, request: Request, actor=Depends(current_actor)):
        with factory() as session:
            corridor = session.get(CorridorVersion, corridor_id)
            if not corridor:
                raise HTTPException(404, "corridor_not_found")
            if not authorize_corridor(
                factory, actor, request.state.request_id, jurisdiction_id=corridor.jurisdiction_id
            ):
                raise HTTPException(403)
            now = datetime.now(timezone.utc)
            snapshots = session.scalars(
                select(SourceSnapshot)
                .where(SourceSnapshot.source == "mappls", SourceSnapshot.status == "available")
                .order_by(SourceSnapshot.retrieved_at.desc())
                .limit(50)
            ).all()
            for snapshot in snapshots:
                if (
                    now - utc_datetime(snapshot.retrieved_at)
                ).total_seconds() < settings.source_refresh_seconds:
                    for record in snapshot.records:
                        if record.get("corridor_id") == corridor_id:
                            return {
                                "provider": "mappls",
                                "retrieved_at": utc_datetime(snapshot.retrieved_at),
                                "route": record,
                                "cached": True,
                            }
            segments = session.scalars(
                select(RoadSegment)
                .where(RoadSegment.corridor_version_id == corridor_id)
                .order_by(RoadSegment.external_ref)
            ).all()
            if not segments:
                raise HTTPException(409, "corridor_has_no_segments")
            points = [segments[0].geometry["coordinates"][0]]
            points.extend(segment.geometry["coordinates"][-1] for segment in segments)
            snapshot = retrieve("mappls", settings, points=points)
            if snapshot.status != "available":
                session.add(snapshot)
                session.commit()
                raise HTTPException(502, "mappls_" + snapshot.reason)
            snapshot.records = [
                {**record, "corridor_id": corridor_id} for record in snapshot.records
            ]
            session.add(snapshot)
            session.commit()
            return {
                "provider": "mappls",
                "retrieved_at": utc_datetime(snapshot.retrieved_at),
                "route": snapshot.records[0],
                "cached": False,
            }

    @router.post("/v1/routes/compare")
    def compare(
        body: RouteRequest,
        request: Request,
        actor=Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError:
            raise HTTPException(422, "invalid_idempotency_key") from None
        digest = canonical_request_hash(body.model_dump(mode="json"))
        with factory() as session:
            corridor = session.get(CorridorVersion, body.corridor_id)
            if not corridor:
                raise HTTPException(404)
            decision = AuthorizationService(session_factory=factory).authorize(
                actor,
                "compare_routes",
                ResourceScope(jurisdiction_id=corridor.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not decision.allowed:
                raise HTTPException(403)
            if body.graph_version_id not in (corridor.id, corridor.graph_version):
                raise HTTPException(409, "graph_version_changed")
            if body.mission_id:
                mission = session.get(Mission, body.mission_id)
                if (
                    not mission
                    or mission.actor_id != actor.actor_id
                    or mission.corridor_id != corridor.id
                ):
                    raise HTTPException(403)
                if mission.state == "planned":
                    if body.impact_id is not None:
                        raise HTTPException(422, "planned_mission_has_no_impact")
                elif body.impact_id:
                    current_impact(session, mission, body.impact_id, datetime.now(timezone.utc))
                else:
                    raise HTTPException(409, "active_impact_required")
                if (
                    mission.graph_version_id != corridor.graph_version
                    or mission.payload["vehicle_profile"] != body.vehicle_profile
                    or mission.payload["origin"] != body.origin.model_dump(mode="json")
                    or mission.payload["destination"] != body.destination.model_dump(mode="json")
                    or datetime.fromisoformat(mission.payload["delivery_window"]["end"])
                    != body.deadline_at
                ):
                    raise HTTPException(409, "mission_route_request_mismatch")
            old = session.scalar(
                select(RouteComparisonRecord).where(
                    RouteComparisonRecord.actor_id == actor.actor_id,
                    RouteComparisonRecord.idempotency_key == idempotency_key,
                )
            )
            if old:
                if old.request_hash != digest:
                    raise HTTPException(409, "idempotency_conflict")
                return old.payload
            try:
                assert_corridor_point(session, corridor.id, body.origin.coordinates)
                assert_corridor_point(session, corridor.id, body.destination.coordinates)
            except ValueError:
                raise HTTPException(422, "outside_corridor_bounds") from None
            points = [body.origin.coordinates, body.destination.coordinates]
            if settings.graphhopper_local_url:
                provider = "graphhopper_local"
                snapshot = retrieve_local_graphhopper(
                    settings, points=points, profile=body.vehicle_profile
                )
            else:
                provider = "mappls" if settings.providers.get("MAPPLS_API_KEY") else "graphhopper"
                snapshot = retrieve(provider, settings, points=points)
            session.add(snapshot)
            if snapshot.status != "available":
                session.commit()
                raise HTTPException(502, "upstream_unavailable")
            _, transformer, buffer_m = projected_corridor(session, corridor.id)
            segments = session.scalars(
                select(RoadSegment).where(RoadSegment.corridor_version_id == corridor.id)
            ).all()
            routes, excluded = [], []
            for candidate in snapshot.records[: body.alternative_limit]:
                shape = transform(
                    transformer.transform, LineString(candidate["geometry"]["coordinates"])
                )
                linked = [
                    segment
                    for segment in segments
                    if shape.intersects(
                        transform(
                            transformer.transform, LineString(segment.geometry["coordinates"])
                        ).buffer(buffer_m)
                    )
                ]
                statuses = {
                    segment.id: effective_status(
                        session, segment.id, body.departure_at, vehicle_profile=body.vehicle_profile
                    )
                    for segment in linked
                }
                blocked = [
                    key for key, status in statuses.items()
                    if status["status"] == "closed"
                    or (body.impact_id and status["status"] == "restricted")
                ]
                if blocked:
                    excluded.extend(
                        {"segment_id": key, "reason": "active_authority_restriction"}
                        for key in blocked
                    )
                    continue
                routes.append(
                    {
                        "route_id": str(uuid4()),
                        "geometry": candidate["geometry"],
                        "segment_ids": [s.id for s in linked],
                        "decision_snapshots": {
                            key: {
                                "decision_id": status.get("decision_id"),
                                "freshness": status["freshness"],
                            }
                            for key, status in statuses.items()
                        },
                        "distance_m": candidate["distance_m"],
                        "travel_time_seconds": {
                            "p50": candidate["duration_seconds"],
                            "low": None,
                            "high": None,
                            "basis": (
                                "graphhopper_profile_free_flow_unvalidated"
                                if provider == "graphhopper_local"
                                else "car_free_flow_baseline_unvalidated"
                            ),
                        },
                        "risk_exposure": {
                            "probability_weighted_minutes": None,
                            "state": "insufficient_evidence",
                        },
                        "uncertainty_score": None,
                        "blocked_segment_ids": [],
                        "key_evidence_ids": [],
                        "score_components": {
                            "travel_minutes": candidate["duration_seconds"] / 60,
                            "risk": None,
                            "uncertainty": None,
                            "staleness": None,
                            "deadline_penalty": None,
                        },
                        "reason": (
                            "Baseline only: vehicle legality, policy weights "
                            "and hazard coverage are unverified."
                        ),
                    }
                )
            result = {
                "comparison_id": str(uuid4()),
                "provider": provider,
                "source_snapshot_id": snapshot.id,
                "source_sha256": snapshot.sha256,
                "retrieved_at": utc_datetime(snapshot.retrieved_at).isoformat(),
                "graph_version_id": corridor.graph_version,
                "mission_id": body.mission_id,
                "impact_id": body.impact_id,
                "vehicle_profile": body.vehicle_profile,
                "departure_at": body.departure_at.isoformat(),
                "vehicle_entitlement": (
                    "graphhopper_profile_applied_legality_unverified"
                    if provider == "graphhopper_local" else "unverified_car_baseline"
                ),
                "policy_id": None,
                "policy_version": None,
                "mode": "insufficient_evidence" if routes else "no_verified_feasible_route",
                "recommended_route_id": None,
                "routes": routes,
                "blocking_constraints": excluded,
                "warnings": [
                    "No approved route verification policy is configured.",
                    "Synthetic corridor matching is not a validated road-edge association.",
                    "Time interval and traffic/disruption delay are not measured.",
                    *(["OSM height, weight and HGV tags are incomplete; "
                       "vehicle legality is unverified."]
                      if provider == "graphhopper_local" else []),
                ],
                "request_id": request.state.request_id,
            }
            session.add(
                RouteComparisonRecord(
                    id=result["comparison_id"],
                    actor_id=actor.actor_id,
                    corridor_id=corridor.id,
                    graph_version=corridor.graph_version,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    created_at=datetime.now(timezone.utc),
                    payload=result,
                )
            )
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    actor_id=actor.actor_id,
                    action="routes.compared",
                    target_type="route_comparison",
                    target_id=result["comparison_id"],
                    request_id=request.state.request_id,
                    jurisdiction_id=corridor.jurisdiction_id,
                    outcome="allowed",
                    reason=result["mode"],
                    after_hash=canonical_request_hash(result),
                )
            )
            session.commit()
            return result

    @router.get("/v1/missions/{mission_id}/route-selection")
    def get_selection(mission_id: str, actor=Depends(current_actor)):
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if not mission or actor.actor_id not in (mission.actor_id, mission.driver_actor_id):
                raise HTTPException(403)
            decision = AuthorizationService(session_factory=factory).authorize(
                actor,
                "view_mission" if mission.actor_id == actor.actor_id else "view_assigned_mission",
                ResourceScope(jurisdiction_id=mission.jurisdiction_id),
            )
            if not decision.allowed:
                raise HTTPException(403)
            row = session.scalar(select(RouteSelectionRecord).where(
                RouteSelectionRecord.mission_id == mission_id
            ).order_by(RouteSelectionRecord.selected_at.desc(), RouteSelectionRecord.id.desc()))
            comparison = session.get(RouteComparisonRecord, row.comparison_id) if row else None
            route = None
            if (comparison and comparison.corridor_id == mission.corridor_id
                    and comparison.payload.get("mission_id") == mission_id):
                route = next((candidate for candidate in comparison.payload.get("routes", [])
                              if candidate.get("route_id") == row.route_id), None)
            return {"selection": None if row is None else {
                "selection_id": row.id, "comparison_id": row.comparison_id,
                "route_id": row.route_id, "selected_at": utc_datetime(row.selected_at),
                "expires_at": utc_datetime(row.expires_at),
                "route": route,
                "source": None if route is None else {
                    "provider": comparison.payload.get("provider"),
                    "source_snapshot_id": comparison.payload.get("source_snapshot_id"),
                    "retrieved_at": comparison.payload.get("retrieved_at"),
                    "graph_version_id": comparison.graph_version,
                    "vehicle_entitlement": comparison.payload.get("vehicle_entitlement"),
                    "vehicle_profile": comparison.payload.get("vehicle_profile"),
                },
                "status": "expired_baseline"
                if datetime.now(timezone.utc) >= utc_datetime(row.expires_at)
                else "planning_baseline_only",
            }}

    @router.get("/v1/corridors/{corridor_id}/mission-impacts")
    def mission_impacts(corridor_id: str, request: Request, actor=Depends(current_actor)):
        # ponytail: read-through assessment; use an event worker if fanout grows.
        with factory() as session:
            corridor = session.get(CorridorVersion, corridor_id)
            if not corridor:
                raise HTTPException(404, "corridor_not_found")
            access = AuthorizationService(session_factory=factory).authorize(
                actor, "compare_routes", ResourceScope(jurisdiction_id=corridor.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)
            now = datetime.now(timezone.utc)
            segment_ids = set(session.scalars(select(RoadSegment.id).where(
                RoadSegment.corridor_version_id == corridor_id
            )).all())
            active_ids, unassessed = set(), []
            missions = session.scalars(select(Mission).where(
                Mission.corridor_id == corridor_id,
                Mission.state.in_(("planned", "accepted", "active"))
            )).all()
            for mission in missions:
                selection = session.scalar(select(RouteSelectionRecord).where(
                    RouteSelectionRecord.mission_id == mission.id
                ).order_by(RouteSelectionRecord.selected_at.desc(), RouteSelectionRecord.id.desc()))
                if selection is None:
                    unassessed.append({"mission_id": mission.id, "reason": "no_selected_baseline"})
                    continue
                comparison = session.get(RouteComparisonRecord, selection.comparison_id)
                if (
                    mission.graph_version_id != corridor.graph_version
                    or comparison is None
                    or comparison.graph_version != corridor.graph_version
                ):
                    unassessed.append({"mission_id": mission.id, "reason": "graph_changed"})
                    continue
                route = next((item for item in comparison.payload.get("routes", [])
                              if item["route_id"] == selection.route_id), None)
                if route is None:
                    unassessed.append({"mission_id": mission.id, "reason": "route_missing"})
                    continue
                for segment_id in set(route.get("segment_ids", [])) & segment_ids:
                    status = effective_status(session, segment_id, now,
                                              vehicle_profile=mission.payload["vehicle_profile"])
                    if status["status"] not in ("closed", "restricted"):
                        continue
                    baseline = route.get("decision_snapshots", {}).get(segment_id, {})
                    if (status.get("decision_id") == baseline.get("decision_id")
                            and status["freshness"] == baseline.get("freshness")):
                        continue
                    decision_id = status["decision_id"]
                    source_decision = session.get(StatusDecision, decision_id)
                    row = session.scalar(select(MissionImpactRecord).where(
                        MissionImpactRecord.mission_id == mission.id,
                        MissionImpactRecord.decision_id == decision_id,
                        MissionImpactRecord.route_selection_id == selection.id,
                    ))
                    payload = {
                        "segment_id": segment_id, "status": status["status"],
                        "decision_evidence_ids": status.get("evidence_ids", []),
                        "decision_valid_until": utc_datetime(
                            source_decision.valid_until
                        ).isoformat(),
                        "route_id": selection.route_id,
                        "comparison_id": comparison.id,
                        "source_snapshot_id": comparison.payload.get("source_snapshot_id"),
                        "graph_version_id": corridor.graph_version,
                        "assessment_basis": "selected_geometry_baseline_unverified",
                    }
                    if row is None:
                        row = MissionImpactRecord(
                            id=str(uuid4()), corridor_id=corridor_id, mission_id=mission.id,
                            decision_id=decision_id, route_selection_id=selection.id,
                            state="active", assessed_at=now, resolved_at=None, payload=payload,
                        )
                        session.add(row)
                    elif row.state != "active":
                        row.state, row.resolved_at = "active", None
                    active_ids.add(row.id)
            session.flush()
            rows = session.scalars(select(MissionImpactRecord).where(
                MissionImpactRecord.corridor_id == corridor_id
            ).order_by(MissionImpactRecord.assessed_at.desc(), MissionImpactRecord.id.desc())).all()
            for row in rows:
                if row.state == "active" and row.id not in active_ids:
                    row.state, row.resolved_at = "resolved", now
            result = {
                "corridor_id": corridor_id,
                "assessed_at": now.isoformat(),
                "assessments": [{
                    **row.payload, "impact_id": row.id, "mission_id": row.mission_id,
                    "decision_id": row.decision_id, "route_selection_id": row.route_selection_id,
                    "state": row.state, "resolved_at": (
                        utc_datetime(row.resolved_at).isoformat() if row.resolved_at else None
                    ),
                } for row in rows],
                "unassessed": unassessed,
            }
            session.commit()
            return result

    @router.post("/v1/missions/{mission_id}/route-selection", status_code=201)
    def select_route(mission_id: str, body: RouteSelectionInput, request: Request,
                     actor=Depends(current_actor), idempotency_key: str = Header()):
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError:
            raise HTTPException(422, "invalid_idempotency_key") from None
        digest = canonical_request_hash({"mission_id": mission_id, **body.model_dump()})
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if not mission or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            decision = AuthorizationService(session_factory=factory).authorize(
                actor, "compare_routes", ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not decision.allowed:
                raise HTTPException(403)
            old = session.scalar(select(RouteSelectionRecord).where(
                RouteSelectionRecord.actor_id == actor.actor_id,
                RouteSelectionRecord.idempotency_key == idempotency_key,
            ))
            if old:
                if old.request_hash != digest:
                    raise HTTPException(409, "idempotency_conflict")
                return {"selection_id": old.id, "status": "planning_baseline_only"}
            comparison = session.get(RouteComparisonRecord, body.comparison_id)
            if (not comparison or comparison.actor_id != actor.actor_id
                    or comparison.corridor_id != mission.corridor_id
                    or comparison.payload.get("mission_id") != mission_id):
                raise HTTPException(403)
            graph = session.get(CorridorVersion, mission.corridor_id)
            if (mission.state != "planned" or graph.graph_version != comparison.graph_version
                    or mission.graph_version_id != graph.graph_version):
                raise HTTPException(409, "graph_or_mission_changed")
            result = comparison.payload
            route = next(
                (item for item in result["routes"] if item["route_id"] == body.route_id),
                None,
            )
            if route is None:
                raise HTTPException(422, "route_not_in_comparison")
            retrieved = datetime.fromisoformat(result["retrieved_at"])
            expires = retrieved + timedelta(seconds=settings.source_refresh_seconds)
            if datetime.now(timezone.utc) >= expires:
                raise HTTPException(409, "source_snapshot_expired")
            departure = datetime.fromisoformat(result["departure_at"])
            decision_at = max(datetime.now(timezone.utc), departure)
            for segment_id, expected in route["decision_snapshots"].items():
                current = effective_status(session, segment_id, decision_at,
                                           vehicle_profile=result["vehicle_profile"])
                if (current.get("decision_id") != expected["decision_id"]
                        or current["freshness"] != expected["freshness"]):
                    raise HTTPException(409, "decision_snapshot_changed")
            row = RouteSelectionRecord(
                id=str(uuid4()), mission_id=mission_id, comparison_id=comparison.id,
                route_id=body.route_id, actor_id=actor.actor_id, idempotency_key=idempotency_key,
                request_hash=digest, selected_at=datetime.now(timezone.utc), expires_at=expires,
            )
            session.add(row)
            session.add(AuditEvent(
                id=str(uuid4()), actor_id=actor.actor_id, action="routes.baseline_selected",
                target_type="mission", target_id=mission_id, request_id=request.state.request_id,
                jurisdiction_id=mission.jurisdiction_id, outcome="allowed",
                reason="planning_baseline_only", after_hash=digest,
            ))
            session.commit()
            return {"selection_id": row.id, "status": "planning_baseline_only"}

    @router.get("/v1/missions/{mission_id}/route-change-approval")
    def get_route_change(mission_id: str, request: Request, actor=Depends(current_actor)):
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if not mission or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            access = AuthorizationService(session_factory=factory).authorize(
                actor,
                "view_mission",
                ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)
            row = session.scalar(
                select(RouteChangeApproval)
                .where(RouteChangeApproval.mission_id == mission_id)
                .order_by(RouteChangeApproval.approved_at.desc(), RouteChangeApproval.id.desc())
            )
            return {"approval": None if row is None else row.payload}

    @router.post("/v1/missions/{mission_id}/route-change-approval", status_code=201)
    def approve_route_change(
        mission_id: str,
        body: RouteChangeInput,
        request: Request,
        actor=Depends(current_actor),
        idempotency_key: str = Header(),
    ):
        if len(body.reason.strip()) < 10:
            raise HTTPException(422, "reason_required")
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError:
            raise HTTPException(422, "invalid_idempotency_key") from None
        digest = canonical_request_hash({"mission_id": mission_id, **body.model_dump()})
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if not mission or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            access = AuthorizationService(session_factory=factory).authorize(
                actor,
                "compare_routes",
                ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)
            old = session.scalar(
                select(RouteChangeApproval).where(
                    RouteChangeApproval.actor_id == actor.actor_id,
                    RouteChangeApproval.idempotency_key == idempotency_key,
                )
            )
            if old:
                if old.request_hash != digest:
                    raise HTTPException(409, "idempotency_conflict")
                return old.payload
            now = datetime.now(timezone.utc)
            impact, selected = current_impact(session, mission, body.impact_id, now)
            if mission.driver_actor_id is None:
                raise HTTPException(409, "assigned_driver_required")
            previous = session.scalar(select(RouteChangeApproval).where(
                RouteChangeApproval.impact_id == impact.id
            ).order_by(RouteChangeApproval.approved_at.desc()))
            if previous and now < datetime.fromisoformat(previous.payload["expires_at"]):
                raise HTTPException(409, "impact_already_approved")
            comparison = session.get(RouteComparisonRecord, body.comparison_id)
            if (
                comparison is None
                or comparison.actor_id != actor.actor_id
                or comparison.corridor_id != mission.corridor_id
                or comparison.graph_version != mission.graph_version_id
                or comparison.payload.get("mission_id") != mission_id
                or comparison.payload.get("impact_id") != impact.id
            ):
                raise HTTPException(409, "comparison_mismatch")
            result = comparison.payload
            route = next(
                (
                    candidate
                    for candidate in result.get("routes", [])
                    if candidate["route_id"] == body.route_id
                ),
                None,
            )
            if route is None or route["route_id"] == selected.route_id:
                raise HTTPException(422, "new_candidate_route_required")
            expires = datetime.fromisoformat(result["retrieved_at"]) + timedelta(
                seconds=settings.source_refresh_seconds
            )
            current_route_candidate(session, mission, impact, route, expires, now)
            approval_id = str(uuid4())
            payload = {
                "approval_id": approval_id,
                "impact_id": impact.id,
                "mission_id": mission_id,
                "comparison_id": comparison.id,
                "comparison_hash": canonical_request_hash(result),
                "route_id": route["route_id"],
                "selected_route_id": selected.route_id,
                "route_snapshot": route,
                "source_snapshot_id": result["source_snapshot_id"],
                "source_sha256": result.get("source_sha256"),
                "graph_version_id": mission.graph_version_id,
                "decision_id": impact.decision_id,
                "reason": body.reason.strip(),
                "approved_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "status": "pending_driver_acknowledgment",
                "limitation": "Replay planning baseline; no vehicle or road clearance.",
            }
            session.add(
                RouteChangeApproval(
                    id=approval_id,
                    impact_id=impact.id,
                    mission_id=mission_id,
                    comparison_id=comparison.id,
                    route_id=route["route_id"],
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    approved_at=now,
                    payload=payload,
                )
            )
            alert_id = str(uuid4())
            session.add(RouteAlert(
                id=alert_id, approval_id=approval_id, mission_id=mission_id,
                recipient_actor_id=mission.driver_actor_id, created_at=now,
                payload={
                    "alert_id": alert_id, "approval_id": approval_id, "mission_id": mission_id,
                    "kind": "route_change", "language": "en",
                    "template_key": "route_change_replay_en_v1",
                    "message": (
                        "A dispatcher approved a candidate route change. Review before accepting; "
                        "this replay route is not road or vehicle clearance."
                    ),
                    "reason": body.reason.strip(), "route_id": route["route_id"],
                    "created_at": now.isoformat(), "expires_at": expires.isoformat(),
                    "vehicle_profile": result.get("vehicle_profile"),
                    "vehicle_entitlement": result.get("vehicle_entitlement"),
                    "retrieved_at": result.get("retrieved_at"),
                    "uncertainty_score": route.get("uncertainty_score"),
                    "linked_segment_count": len(route.get("segment_ids", [])),
                },
            ))
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    actor_id=actor.actor_id,
                    action="routes.change_approved",
                    target_type="mission",
                    target_id=mission_id,
                    request_id=request.state.request_id,
                    jurisdiction_id=mission.jurisdiction_id,
                    outcome="allowed",
                    reason="pending_driver_acknowledgment",
                    after_hash=canonical_request_hash(payload),
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "approval_conflict") from None
            return payload

    @router.get("/v1/alerts")
    def list_alerts(request: Request, actor=Depends(current_actor)):
        with factory() as session:
            alerts = session.scalars(select(RouteAlert).where(
                RouteAlert.recipient_actor_id == actor.actor_id
            ).order_by(RouteAlert.created_at.desc())).all()
            visible = []
            for alert in alerts:
                mission = session.get(Mission, alert.mission_id)
                if mission is None or mission.driver_actor_id != actor.actor_id:
                    continue
                access = AuthorizationService(session_factory=factory).authorize(
                    actor, "view_assigned_mission",
                    ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                    request_id=request.state.request_id,
                )
                if access.allowed:
                    visible.append(alert)
            for alert in visible:
                if not session.scalar(select(AlertDeliveryAttempt).where(
                    AlertDeliveryAttempt.alert_id == alert.id
                )):
                    session.add(AlertDeliveryAttempt(
                        id=str(uuid4()), alert_id=alert.id, channel="in_app",
                        outcome="delivered", attempted_at=datetime.now(timezone.utc),
                    ))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()  # Another read recorded the same delivery first.
            return {"alerts": [alert_view(session, alert) for alert in visible]}

    @router.get("/v1/missions/{mission_id}/route-alert")
    def get_mission_alert(mission_id: str, request: Request, actor=Depends(current_actor)):
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if mission is None or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            access = AuthorizationService(session_factory=factory).authorize(
                actor, "view_mission", ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)
            alert = session.scalar(select(RouteAlert).where(
                RouteAlert.mission_id == mission_id
            ).order_by(RouteAlert.created_at.desc(), RouteAlert.id.desc()))
            return {"alert": None if alert is None else alert_view(session, alert)}

    @router.get("/v1/missions/{mission_id}/timeline")
    def mission_timeline(mission_id: str, request: Request, actor=Depends(current_actor)):
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if mission is None or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            access = AuthorizationService(session_factory=factory).authorize(
                actor, "view_mission", ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)

            events = []

            def add(kind, row_id, at, actor_id, status, **source_ids):
                events.append({
                    "event_id": row_id, "kind": kind, "at": utc_datetime(at).isoformat(),
                    "actor_id": actor_id, "status": status,
                    "source_ids": {"mission_id": mission_id, **source_ids},
                })

            add("mission", mission.id, mission.created_at, mission.actor_id, "created")
            for event in session.scalars(select(AuditEvent).where(
                AuditEvent.target_id == mission_id,
                AuditEvent.target_type == "mission",
                AuditEvent.action.like("mission.%"),
            )).all():
                if event.action != "mission.created":
                    add("mission", event.id, event.occurred_at, event.actor_id,
                        event.action.removeprefix("mission."))

            selections = session.scalars(select(RouteSelectionRecord).where(
                RouteSelectionRecord.mission_id == mission_id
            )).all()
            impacts = session.scalars(select(MissionImpactRecord).where(
                MissionImpactRecord.mission_id == mission_id
            )).all()
            approvals = session.scalars(select(RouteChangeApproval).where(
                RouteChangeApproval.mission_id == mission_id
            )).all()
            alerts = session.scalars(select(RouteAlert).where(
                RouteAlert.mission_id == mission_id
            )).all()
            for comparison in session.scalars(select(RouteComparisonRecord).where(
                RouteComparisonRecord.corridor_id == mission.corridor_id,
                RouteComparisonRecord.actor_id == mission.actor_id,
            )).all():
                if comparison.payload.get("mission_id") == mission_id:
                    add("comparison", comparison.id, comparison.created_at, comparison.actor_id,
                        comparison.payload.get("mode", "recorded"),
                        comparison_id=comparison.id,
                        source_snapshot_id=comparison.payload.get("source_snapshot_id"))
            for row in selections:
                add("selection", row.id, row.selected_at, row.actor_id, "selected",
                    selection_id=row.id, comparison_id=row.comparison_id, route_id=row.route_id)
            decision_ids = set()
            for row in impacts:
                decision_ids.add(row.decision_id)
                add("impact", row.id, row.assessed_at, None, "assessed",
                    impact_id=row.id, decision_id=row.decision_id,
                    selection_id=row.route_selection_id)
                if row.resolved_at:
                    add("impact_resolution", row.id, row.resolved_at, None, "resolved",
                        impact_id=row.id, decision_id=row.decision_id)
            for row in approvals:
                add("approval", row.id, row.approved_at, row.actor_id,
                    "pending_driver_acknowledgment", approval_id=row.id,
                    impact_id=row.impact_id, comparison_id=row.comparison_id,
                    route_id=row.route_id)
            for row in alerts:
                add("alert", row.id, row.created_at, None, "queued_in_app",
                    alert_id=row.id, approval_id=row.approval_id)
                for delivery in session.scalars(select(AlertDeliveryAttempt).where(
                    AlertDeliveryAttempt.alert_id == row.id
                )).all():
                    add("alert_delivery", delivery.id, delivery.attempted_at, None,
                        delivery.outcome, alert_id=row.id, channel=delivery.channel)
                for acknowledgment in session.scalars(select(AlertAcknowledgment).where(
                    AlertAcknowledgment.alert_id == row.id
                )).all():
                    add("acknowledgment", acknowledgment.id, acknowledgment.acknowledged_at,
                        acknowledgment.actor_id, acknowledgment.decision,
                        alert_id=row.id, selection_id=acknowledgment.selection_id)
            for decision_id in decision_ids:
                decision = session.get(StatusDecision, decision_id)
                if decision is None or decision.jurisdiction_id != mission.jurisdiction_id:
                    continue
                segment = session.get(RoadSegment, decision.segment_id)
                if segment is None or segment.corridor_version_id != mission.corridor_id:
                    continue
                add("status_decision", decision.id, decision.created_at, decision.actor_id,
                    decision.payload.get("status", "unknown"), decision_id=decision.id,
                    segment_id=decision.segment_id)
                for evidence_id in decision.payload.get("evidence_ids", []):
                    report = session.get(FieldReport, evidence_id)
                    if report is None or report.segment_id != decision.segment_id:
                        continue
                    add("field_report", report.id, report.received_at, report.actor_id,
                        report.response.get("review_state", "submitted"),
                        report_id=report.id, decision_id=decision.id,
                        segment_id=report.segment_id)
                    for review in session.scalars(select(EvidenceReview).where(
                        EvidenceReview.evidence_id == report.id
                    )).all():
                        add("review", review.id, review.created_at, review.actor_id,
                            review.payload.get("action", "reviewed"),
                            report_id=report.id, decision_id=decision.id,
                            review_id=review.id)
            events.sort(key=lambda item: (item["at"], item["kind"], item["event_id"]))
            return {"mission_id": mission_id, "data_mode": "replay", "events": events}

    @router.post("/v1/alerts/{alert_id}/acknowledge", status_code=201)
    def acknowledge_alert(alert_id: str, body: AlertAcknowledgmentInput, request: Request,
                          actor=Depends(current_actor), idempotency_key: str = Header()):
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError:
            raise HTTPException(422, "invalid_idempotency_key") from None
        digest = canonical_request_hash({"alert_id": alert_id, **body.model_dump()})
        with factory() as session:
            alert = session.get(RouteAlert, alert_id)
            if alert is None or alert.recipient_actor_id != actor.actor_id:
                raise HTTPException(403)
            mission = session.get(Mission, alert.mission_id)
            if mission is None or mission.driver_actor_id != actor.actor_id:
                raise HTTPException(403)
            access = AuthorizationService(session_factory=factory).authorize(
                actor, "view_assigned_mission",
                ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id,
            )
            if not access.allowed:
                raise HTTPException(403)
            old = session.scalar(select(AlertAcknowledgment).where(
                AlertAcknowledgment.actor_id == actor.actor_id,
                AlertAcknowledgment.idempotency_key == idempotency_key,
            ))
            if old:
                if old.request_hash != digest:
                    raise HTTPException(409, "idempotency_conflict")
                return {"alert_id": old.alert_id, "decision": old.decision,
                        "selection_id": old.selection_id}
            if session.scalar(select(AlertAcknowledgment).where(
                AlertAcknowledgment.alert_id == alert_id
            )):
                raise HTTPException(409, "alert_already_acknowledged")
            now = datetime.now(timezone.utc)
            approval = session.get(RouteChangeApproval, alert.approval_id)
            selection = None
            if body.decision == "accept":
                impact, _ = current_impact(session, mission, approval.impact_id, now)
                route = approval.payload["route_snapshot"]
                expires = datetime.fromisoformat(approval.payload["expires_at"])
                current_route_candidate(session, mission, impact, route, expires, now)
                selection = RouteSelectionRecord(
                    id=str(uuid4()), mission_id=mission.id, comparison_id=approval.comparison_id,
                    route_id=approval.route_id, actor_id=actor.actor_id,
                    idempotency_key=str(uuid4()), request_hash=digest,
                    selected_at=now, expires_at=expires,
                )
                session.add(selection)
                impact.state, impact.resolved_at = "resolved", now
            session.add(AlertAcknowledgment(
                id=str(uuid4()), alert_id=alert_id, actor_id=actor.actor_id,
                idempotency_key=idempotency_key, request_hash=digest,
                decision=body.decision, acknowledged_at=now,
                selection_id=selection.id if selection else None,
            ))
            session.add(AuditEvent(
                id=str(uuid4()), actor_id=actor.actor_id,
                action=f"alerts.route_change_{body.decision}", target_type="route_alert",
                target_id=alert_id, request_id=request.state.request_id,
                jurisdiction_id=mission.jurisdiction_id, outcome="allowed",
                reason="replay_baseline_only", after_hash=digest,
            ))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "acknowledgment_conflict") from None
            return {"alert_id": alert_id, "decision": body.decision,
                    "selection_id": selection.id if selection else None}

    return router
