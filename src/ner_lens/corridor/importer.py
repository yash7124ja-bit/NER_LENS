"""Deterministic replay/import boundary for the audited corridor bands."""

from __future__ import annotations

import hashlib
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
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IMPORT_MANIFEST = PROJECT_ROOT / "data" / "manifests" / "a-m1-03-corridor-import.json"
DEFAULT_V3_MAPPING = (
    PROJECT_ROOT
    / "data"
    / "corridor"
    / "graphhopper"
    / "real_evidence"
    / "v3"
    / "corridor_edge_mapping.json"
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


def _canonical_band_specs(specs: list[BandSpec]) -> str:
    payload = [
        {
            "band_id": spec.band_id,
            "sequence": spec.sequence,
            "segment_type": spec.segment_type,
            "direction": spec.direction,
            "geometry_endpoints": spec.geometry_endpoints,
            "restrictions": spec.restrictions,
            "citations": spec.citations,
        }
        for spec in specs
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _validate_primary_band_specs(specs: list[BandSpec]) -> None:
    band_ids = tuple(spec.band_id for spec in specs)
    if len(specs) != len(PRIMARY_BAND_IDS) or band_ids != PRIMARY_BAND_IDS:
        raise ValueError("band specs must contain exactly six ordered primary bands")
    if len(set(band_ids)) != len(band_ids):
        raise ValueError("band specs must contain unique bands")


def _resolve_manifest_fixture(manifest: dict[str, Any]) -> Path:
    data_root = (PROJECT_ROOT / "data").resolve()
    fixture_path = (PROJECT_ROOT / manifest["fixture_path"]).resolve()
    try:
        fixture_path.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("fixture path must remain within the repository data boundary") from exc
    if not fixture_path.is_file():
        raise ValueError("committed fixture path does not exist")
    return fixture_path


def load_import_manifest(path: Path = DEFAULT_IMPORT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    recorded_hash = manifest.get("manifest_sha256")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        raise ValueError("import manifest checksum is missing")
    payload = dict(manifest)
    payload["manifest_sha256"] = ""
    calculated_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if calculated_hash != recorded_hash:
        raise ValueError("import manifest checksum mismatch")
    required = {
        "corridor_key",
        "graph_version",
        "graph_sha256",
        "source_url",
        "fixture_path",
        "audit_band_ids",
        "v3_mapping_path",
        "v3_mapping_sha256",
    }
    if not required.issubset(manifest):
        raise ValueError("import manifest is incomplete")
    if tuple(manifest["audit_band_ids"]) != PRIMARY_BAND_IDS:
        raise ValueError("import manifest audit bands do not match the primary corridor")
    return manifest


def validate_v3_band_mapping(
    path: Path = DEFAULT_V3_MAPPING, *, expected_sha256: str | None = None
) -> dict[str, tuple[str, ...]]:
    if expected_sha256 is not None and _normalized_file_sha256(path) != expected_sha256:
        raise ValueError("v3 corridor mapping checksum mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    bands = payload.get("bands")
    if not isinstance(bands, list):
        raise ValueError("v3 corridor mapping has no bands")
    result: dict[str, tuple[str, ...]] = {}
    for band in bands:
        band_id = band.get("band_id")
        by_profile = band.get("by_profile")
        if band_id not in PRIMARY_BAND_IDS or not isinstance(by_profile, dict):
            continue
        query_ids = []
        for profile in ("light_goods", "rigid_truck", "emergency"):
            receipt = by_profile.get(profile)
            query_id = receipt.get("query_id") if isinstance(receipt, dict) else None
            if not isinstance(query_id, str) or not query_id.startswith("nh27_leg"):
                raise ValueError(f"v3 mapping receipt missing for {band_id}/{profile}")
            query_ids.append(query_id)
        result[band_id] = tuple(query_ids)
    if tuple(result) != PRIMARY_BAND_IDS:
        raise ValueError("v3 corridor mapping does not cover all primary bands")
    return result


def get_active_corridor(
    factory: sessionmaker[Session], corridor_key: str = "guwahati_silchar_nh27"
) -> CorridorVersion | None:
    with factory() as session:
        return session.scalar(
            select(CorridorVersion)
            .where(
                CorridorVersion.corridor_key == corridor_key,
                CorridorVersion.status == "active",
            )
            .order_by(CorridorVersion.effective_from.desc())
        )


def map_audited_bands_to_segments(
    factory: sessionmaker[Session],
    corridor_version_id: str,
    mapping: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    with factory() as session:
        segments = session.scalars(
            select(RoadSegment).where(RoadSegment.corridor_version_id == corridor_version_id)
        ).all()
    by_ref = {segment.external_ref: segment.id for segment in segments}
    if tuple(mapping) != PRIMARY_BAND_IDS:
        raise ValueError("band mapping does not match the primary corridor")
    missing = [band_id for band_id in PRIMARY_BAND_IDS if band_id not in by_ref]
    if missing:
        raise ValueError(f"imported corridor is missing audited bands: {missing}")
    return {band_id: by_ref[band_id] for band_id in PRIMARY_BAND_IDS}


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
        manifest_path: Path = DEFAULT_IMPORT_MANIFEST,
    ) -> ImportResult:
        manifest = load_import_manifest(manifest_path)
        if graph_version != manifest["graph_version"]:
            raise ValueError("graph version is not in the committed import manifest")
        if graph_sha256 != manifest["graph_sha256"]:
            raise ValueError("graph checksum is not in the committed import manifest")
        if source_url != manifest["source_url"]:
            raise ValueError("source URL is not in the committed import manifest")
        fixture_path = _resolve_manifest_fixture(manifest)
        if _normalized_file_sha256(fixture_path) != manifest["graph_sha256"]:
            raise ValueError("fixture checksum does not match the committed graph checksum")
        verified_specs = load_primary_band_specs(fixture_path)
        _validate_primary_band_specs(verified_specs)
        _validate_primary_band_specs(specs)
        if _canonical_band_specs(specs) != _canonical_band_specs(verified_specs):
            raise ValueError("band specs do not match the verified fixture")
        validate_v3_band_mapping(
            PROJECT_ROOT / manifest["v3_mapping_path"],
            expected_sha256=manifest["v3_mapping_sha256"],
        )
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

            version_id = _stable_id("corridor", self.corridor_key, graph_version, graph_sha256)
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
                segment_id = _stable_id(
                    "segment", self.corridor_key, graph_version, graph_sha256, spec.band_id
                )
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


def _stable_id(
    kind: str, corridor_key: str, graph_version: str, graph_sha256: str, band_id: str = ""
) -> str:
    value = ":".join((kind, corridor_key, graph_version, graph_sha256, band_id))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def _normalized_file_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()
