"""Scoped baseline route comparisons. Missing verification policy means no recommendation."""

from datetime import datetime, timezone
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
from ner_lens.operations import Mission, Point, effective_status
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
                blocked = [
                    segment.id
                    for segment in linked
                    if effective_status(
                        session, segment.id, body.departure_at, vehicle_profile=body.vehicle_profile
                    )["status"]
                    == "closed"
                ]
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
                "retrieved_at": utc_datetime(snapshot.retrieved_at).isoformat(),
                "graph_version_id": corridor.graph_version,
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

    return router
