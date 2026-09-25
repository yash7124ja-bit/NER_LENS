"""Scoped baseline route comparisons. Missing verification policy means no recommendation."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import LineString
from shapely.ops import transform
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.config import utc_datetime
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.identity.models import AuditEvent
from ner_lens.identity.replay import authorize_corridor
from ner_lens.identity.service import AuthorizationService, ResourceScope
from ner_lens.operations import Mission, Point, StatusDecision, effective_status
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


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corridor_id: str
    graph_version_id: str
    origin: Point
    destination: Point
    vehicle_profile: str = Field(pattern="^(light_goods|rigid_truck|emergency)$")
    mission_id: str | None = None
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
                if (
                    mission.state != "planned"
                    or mission.graph_version_id != corridor.graph_version
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
            provider = "mappls" if settings.providers.get("MAPPLS_API_KEY") else "graphhopper"
            snapshot = retrieve(
                provider,
                settings,
                points=[body.origin.coordinates, body.destination.coordinates],
            )
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
                blocked = [key for key, status in statuses.items() if status["status"] == "closed"]
                if blocked:
                    excluded.extend(
                        {"segment_id": key, "reason": "active_authority_closure"} for key in blocked
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
                            "basis": "car_free_flow_baseline_unvalidated",
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
                "vehicle_profile": body.vehicle_profile,
                "departure_at": body.departure_at.isoformat(),
                "vehicle_entitlement": "unverified_car_baseline",
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
            if not mission or mission.actor_id != actor.actor_id:
                raise HTTPException(403)
            decision = AuthorizationService(session_factory=factory).authorize(
                actor, "view_mission", ResourceScope(jurisdiction_id=mission.jurisdiction_id)
            )
            if not decision.allowed:
                raise HTTPException(403)
            row = session.scalar(select(RouteSelectionRecord).where(
                RouteSelectionRecord.mission_id == mission_id
            ).order_by(RouteSelectionRecord.selected_at.desc(), RouteSelectionRecord.id.desc()))
            return {"selection": None if row is None else {
                "selection_id": row.id, "comparison_id": row.comparison_id,
                "route_id": row.route_id, "selected_at": utc_datetime(row.selected_at),
                "expires_at": utc_datetime(row.expires_at),
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

    return router
