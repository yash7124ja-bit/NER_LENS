"""Deterministic replay/import boundary for the audited corridor bands."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.corridor.models import CorridorVersion, RoadSegment, validate_linestring_4326
from ner_lens.db import session_scope

PRIMARY_BAND_IDS = (
    "band_1_jalukbari_nagaon",
    "band_2_nagaon_doboka",
    "band_3_doboka_lanka_lumding",
    "band_4_lumding_maibang",
    "band_5_maibang_harangajao_balachera_hill",
    "band_6_balachera_silchar",
)


@dataclass(slots=True)
class BandSpec:
    band_id: str
    sequence: int
    segment_type: str
    direction: str
    geometry_endpoints: list[list[float]]
    restrictions: dict[str, Any]
    citations: list[str]

    @property
    def geometry(self) -> dict[str, Any]:
        return {"type": "LineString", "coordinates": self.geometry_endpoints}


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: bool
    corridor_version_id: str
    segment_ids: tuple[str, ...]
    quarantined: list[str]


def load_primary_band_specs(path: Path) -> list[BandSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id = {band["band_id"]: band for band in payload["bands"]}
    return [
        BandSpec(
            band_id=band_id,
            sequence=by_id[band_id]["sequence"],
            segment_type=by_id[band_id]["segment_type"],
            direction=by_id[band_id]["direction"],
            geometry_endpoints=by_id[band_id]["geometry_endpoints"],
            restrictions=by_id[band_id]["restrictions"],
            citations=by_id[band_id].get("citations", []),
        )
        for band_id in PRIMARY_BAND_IDS
    ]


class CorridorImportService:
    corridor_key = "guwahati_silchar_nh27"

    def import_primary(
        self,
        factory: sessionmaker[Session],
        *,
        graph_version: str,
        graph_sha256: str,
        source_url: str,
        specs: list[BandSpec],
    ) -> ImportResult:
        with session_scope(factory) as session:
            existing = session.scalar(
                select(CorridorVersion).where(
                    CorridorVersion.corridor_key == self.corridor_key,
                    CorridorVersion.graph_version == graph_version,
                    CorridorVersion.graph_sha256 == graph_sha256,
                )
            )
            if existing:
                segments = session.scalars(
                    select(RoadSegment)
                    .where(RoadSegment.corridor_version_id == existing.id)
                    .order_by(RoadSegment.external_ref)
                ).all()
                return ImportResult(
                    created=False,
                    corridor_version_id=existing.id,
                    segment_ids=tuple(segment.id for segment in segments),
                    quarantined=[],
                )

            version_id = _stable_id("corridor", self.corridor_key, graph_version)
            version = CorridorVersion(
                id=version_id,
                corridor_key=self.corridor_key,
                graph_version=graph_version,
                graph_sha256=graph_sha256,
                source_url=source_url,
                provenance_label="replay",
                status="active",
                effective_from=datetime.now(timezone.utc),
            )
            session.add(version)
            segment_ids: list[str] = []
            quarantined: list[str] = []
            for spec in specs:
                try:
                    geometry = validate_linestring_4326(spec.geometry)
                except ValueError:
                    quarantined.append(spec.band_id)
                    continue
                segment_id = _stable_id("segment", self.corridor_key, graph_version, spec.band_id)
                session.add(
                    RoadSegment(
                        id=segment_id,
                        corridor_version_id=version_id,
                        external_ref=spec.band_id,
                        segment_type=spec.segment_type,
                        direction=spec.direction,
                        authority_ref=";".join(spec.citations) or None,
                        geometry=geometry,
                        vehicle_constraints=spec.restrictions,
                    )
                )
                segment_ids.append(segment_id)
            return ImportResult(
                created=True,
                corridor_version_id=version_id,
                segment_ids=tuple(segment_ids),
                quarantined=quarantined,
            )


def _stable_id(kind: str, corridor_key: str, graph_version: str, band_id: str = "") -> str:
    value = ":".join((kind, corridor_key, graph_version, band_id))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))
