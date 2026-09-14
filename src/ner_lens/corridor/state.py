"""Read the imported replay bands without asserting road operability."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.config import utc_datetime
from ner_lens.contracts import (
    CorridorList,
    CorridorState,
    CorridorSummary,
    ExternalReference,
    Provenance,
    SegmentState,
    StateQuery,
)
from ner_lens.corridor.models import CorridorVersion, RoadSegment
from ner_lens.identity.replay import authorize_corridor
from ner_lens.identity.service import AuthContext

LIMITATIONS = [
    "Replay evidence is not current operational status or a route recommendation.",
    "Geometry represents coarse audit-band endpoints, not navigable road geometry.",
    "Geometry and restrictions are hand-authored synthetic fixtures, not measured road facts.",
    "Provenance retrieved_at is the local fixture import time, not a source observation time.",
    "Provider access does not establish passability; status requires a scoped authority decision.",
    "Risk probabilities, vehicle clearance and travel-time intervals are not measured.",
]


def provenance(version: CorridorVersion) -> Provenance:
    return Provenance(
        fixture_sha256=version.graph_sha256,
        observed_at=None,
        retrieved_at=utc_datetime(version.effective_from),
        graph_version=version.graph_version,
    )


def list_corridors(
    factory: sessionmaker[Session],
    actor: AuthContext,
    request_id: str,
) -> CorridorList:
    if not actor.jurisdiction_ids:
        raise PermissionError("No assigned corridor scope")
    with factory() as session:
        versions = session.scalars(
            select(CorridorVersion)
            .where(
                CorridorVersion.status == "active",
                CorridorVersion.provenance_label == "replay",
                CorridorVersion.jurisdiction_id.in_(actor.jurisdiction_ids),
            )
            .order_by(CorridorVersion.corridor_key, CorridorVersion.effective_from.desc())
        ).all()
    if not versions:
        raise LookupError("No assigned replay corridor is available")
    permitted = [
        version
        for version in versions
        if authorize_corridor(
            factory,
            actor,
            request_id,
            jurisdiction_id=version.jurisdiction_id,
        )
    ]
    if not permitted:
        raise PermissionError("Role cannot read the assigned corridors")
    return CorridorList(
        corridors=[
            CorridorSummary(
                corridor_id=UUID(version.id),
                corridor_version_id=UUID(version.id),
                name=version.name or version.corridor_key,
                graph_version=version.graph_version,
            )
            for version in permitted
        ],
        provenance=provenance(permitted[0]),
        limitations=LIMITATIONS,
    )


def read_state(
    factory: sessionmaker[Session],
    corridor_id: UUID,
    query: StateQuery,
    actor: AuthContext,
    request_id: str,
) -> CorridorState:
    with factory() as session:
        version = session.get(CorridorVersion, str(corridor_id))
    if version is None or version.status != "active" or version.provenance_label != "replay":
        raise LookupError("Corridor was not found")
    if version.jurisdiction_id is None or not authorize_corridor(
        factory,
        actor,
        request_id,
        jurisdiction_id=version.jurisdiction_id,
    ):
        raise PermissionError("Corridor is outside the assigned scope")
    now = datetime.now(timezone.utc)
    if query.at and not utc_datetime(version.effective_from) <= query.at <= now:
        raise ValueError("Historical versions and future assessments are unavailable")
    with factory() as session:
        rows = session.scalars(
            select(RoadSegment)
            .where(RoadSegment.corridor_version_id == version.id)
            .order_by(RoadSegment.external_ref, RoadSegment.id)
        ).all()
    start = 0
    if query.cursor is not None:
        indices = [i for i, row in enumerate(rows) if row.id == str(query.cursor)]
        if not indices:
            raise ValueError("Cursor does not belong to this corridor")
        start = indices[0] + 1
    page = rows[start : start + query.limit]
    from ner_lens.operations import EvidenceReview, FieldReport, effective_status

    with factory() as session:
        decisions = {
            row.id: effective_status(
                session, row.id, query.at or now, vehicle_profile=query.vehicle_profile or "all"
            )
            for row in page
        }
    accepted = {row.id: [] for row in page}
    with factory() as session:
        reports = session.scalars(
            select(FieldReport).where(FieldReport.segment_id.in_(accepted))
        ).all()
        for report in reports:
            review = session.scalar(
                select(EvidenceReview)
                .where(
                    EvidenceReview.evidence_id == report.id,
                    EvidenceReview.created_at <= (query.at or now),
                )
                .order_by(EvidenceReview.created_at.desc())
                .limit(1)
            )
            observed = datetime.fromisoformat(report.payload["observed_at"])
            if review and review.payload["action"] == "accept" and observed <= (query.at or now):
                accepted[report.segment_id].append(observed)
    return CorridorState(
        corridor_id=corridor_id,
        corridor_version_id=UUID(version.id),
        as_of=query.at or now,
        segments=[
            SegmentState(
                segment_id=UUID(row.id),
                external_refs=[ExternalReference(source="replay_audit_band", id=row.external_ref)],
                geometry=row.geometry,
                operational_status={
                    "value": decisions[row.id]["status"],
                    "vehicle_scope": decisions[row.id].get("vehicle_scope", ["all"]),
                    "valid_until": decisions[row.id].get("valid_until"),
                },
                segment_type=row.segment_type,
                direction=row.direction,
                vehicle_constraints=row.vehicle_constraints,
                evidence_age_seconds=int(
                    ((query.at or now) - max(accepted[row.id])).total_seconds()
                )
                if accepted[row.id]
                else None,
                source_health="reviewed_evidence" if accepted[row.id] else "no_evidence",
                evidence=[] if query.include_evidence else None,
            )
            for row in page
        ],
        next_cursor=UUID(page[-1].id) if start + len(page) < len(rows) else None,
        provenance=provenance(version),
        limitations=LIMITATIONS,
    )
