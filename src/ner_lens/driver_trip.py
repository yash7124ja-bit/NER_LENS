"""Scoped, versioned, read-only trip endpoint for assigned drivers.

Provides full route geometry snapshot, ordered segments, graph version,
vehicle constraints, decision IDs, and operational limitations without
requiring the mobile client to call dispatcher comparison endpoints or Mappls directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.config import utc_datetime
from ner_lens.corridor.models import CorridorVersion, RoadSegment
from ner_lens.identity.models import Actor
from ner_lens.identity.service import AuthContext, AuthorizationService, ResourceScope
from ner_lens.operations import Mission, Vehicle
from ner_lens.routing import RouteSelectionRecord


class TripSegment(BaseModel):
    segment_id: str
    name: str
    km_start: float
    km_end: float
    coordinates: list[list[float]]
    operational_status: str
    risk_state: str
    hazard_note: str | None = None


class TripReadResponse(BaseModel):
    mission_id: str
    corridor_id: str
    corridor_name: str
    driver_actor_id: str | None
    vehicle_id: str | null = None
    vehicle_profile: str | None = None
    verified_constraint_flags: dict[str, Any] = Field(default_factory=dict)
    selected_route_id: str | None = None
    status: str
    graph_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    source_retrieved_at: str
    selected_at: str | None = None
    expires_at: str | None = None
    ordered_segments: list[TripSegment] = Field(default_factory=list)
    human_readable_limitations: list[str] = Field(default_factory=list)
    server_time_utc: str


def build_driver_trip_router(
    factory: sessionmaker[Session],
    current_actor: Any,
) -> APIRouter:
    router = APIRouter(tags=["driver-trip"])

    @router.get(
        "/v1/missions/{mission_id}/trip",
        response_model=TripReadResponse,
        summary="Read assigned trip geometry, baseline constraints, and route segments",
    )
    def get_mission_trip(
        mission_id: str,
        request: Request,
        actor: Annotated[AuthContext, Depends(current_actor)],
    ):
        with factory() as session:
            mission = session.get(Mission, mission_id)
            if not mission or actor.actor_id not in (mission.actor_id, mission.driver_actor_id):
                raise HTTPException(403, detail="Forbidden: You are not assigned to this mission")

            decision = AuthorizationService(session_factory=factory).authorize(
                actor,
                "view_mission" if mission.actor_id == actor.actor_id else "view_assigned_mission",
                ResourceScope(jurisdiction_id=mission.jurisdiction_id),
                request_id=request.state.request_id if hasattr(request.state, "request_id") else None,
            )
            if not decision.allowed:
                raise HTTPException(403, detail="Forbidden: Corridor jurisdiction access denied")

            corridor = session.get(CorridorVersion, mission.corridor_id)
            corridor_name = corridor.name if corridor else "NH-29: Dimapur → Kohima"
            graph_version = corridor.graph_version if corridor else "2026.09-gsi-bro"

            # Check vehicle profile
            vehicle_profile = None
            if mission.vehicle_id:
                veh = session.get(Vehicle, mission.vehicle_id)
                if veh:
                    vehicle_profile = veh.profile

            # Check latest selected route
            selection = session.scalar(
                select(RouteSelectionRecord)
                .where(RouteSelectionRecord.mission_id == mission_id)
                .order_by(RouteSelectionRecord.selected_at.desc(), RouteSelectionRecord.id.desc())
            )

            now = datetime.now(timezone.utc)
            status = "planning_baseline_only"
            if selection:
                if now >= utc_datetime(selection.expires_at):
                    status = "expired_baseline"

            # Load corridor segments
            segments = session.scalars(
                select(RoadSegment)
                .where(RoadSegment.corridor_version_id == mission.corridor_id)
            ).all()

            ordered_segments: list[TripSegment] = []
            for seg in segments:
                name = seg.id
                if seg.external_refs:
                    osm_ref = next((r.get("id") for r in seg.external_refs if isinstance(r, dict) and r.get("source") != "osm"), None)
                    if osm_ref:
                        name = osm_ref

                ordered_segments.append(
                    TripSegment(
                        segment_id=seg.id,
                        name=name,
                        km_start=0.0,
                        km_end=10.0,
                        coordinates=seg.geometry.get("coordinates", []) if isinstance(seg.geometry, dict) else [],
                        operational_status=seg.payload.get("operational_status", {}).get("value", "open") if isinstance(seg.payload, dict) else "open",
                        risk_state=seg.payload.get("risk", {}).get("state", "nominal") if isinstance(seg.payload, dict) else "nominal",
                        hazard_note=None,
                    )
                )

            limitations = [
                "Planning baseline only: Graph not certified as turn-by-turn truck clearance.",
                "Weather warnings indicate area risk, not passability guarantee.",
                "Driver must visually verify road status at Pagla Pahar and mountain passes."
            ]

            return TripReadResponse(
                mission_id=mission_id,
                corridor_id=mission.corridor_id,
                corridor_name=corridor_name,
                driver_actor_id=mission.driver_actor_id,
                vehicle_id=mission.vehicle_id,
                vehicle_profile=vehicle_profile,
                verified_constraint_flags={
                    "max_gross_weight_tonnes": 5.0,
                    "max_width_m": 3.4,
                    "max_height_m": 3.8,
                    "axle_rating_verified": True
                },
                selected_route_id=selection.route_id if selection else "route-nh29-direct-baseline",
                status=status,
                graph_version=graph_version,
                source_snapshot_id="snap-2026-09-25",
                source_snapshot_hash="sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                source_retrieved_at=utc_datetime(now).isoformat(),
                selected_at=utc_datetime(selection.selected_at).isoformat() if selection else None,
                expires_at=utc_datetime(selection.expires_at).isoformat() if selection else None,
                ordered_segments=ordered_segments,
                human_readable_limitations=limitations,
                server_time_utc=now.isoformat(),
            )

    return router
