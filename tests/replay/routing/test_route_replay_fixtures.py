"""B-M0-01 structural/provenance tests for the route audit replay fixtures.

Scope: verify the fixture graph and case files are well-formed, checksummed,
and honestly labelled. This does NOT implement or test the GraphHopper
adapter (B-M1-02); it validates the audit artifacts required by
docs/MILESTONES.md B-M0-01.
"""
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_DIR = REPO_ROOT / "data" / "corridor" / "graphhopper"
GRAPH_FILE = GRAPH_DIR / "fixture_graph.v1.json"
CHECKSUM_FILE = GRAPH_DIR / "fixture_graph.v1.sha256"
CASES_DIR = Path(__file__).resolve().parent / "cases"

REQUIRED_CASE_IDS = {
    "closed_edge",
    "vehicle_restriction",
    "direction_restriction",
    "bridge_tunnel_access",
    "graphhopper_outage",
    "no_feasible_route",
}

REQUIRED_BAND_FIELDS = {
    "band_id",
    "route_id",
    "segment_type",
    "direction",
    "topology_routable",
    "surface",
    "restrictions",
    "hazard_context",
    "missing_legality_data",
    "planned_unopened",
}

REQUIRED_RESTRICTION_FIELDS = {
    "maxheight_m",
    "maxweight_t",
    "hgv",
    "access",
    "construction",
    "turn_restrictions",
}


def load_graph():
    return json.loads(GRAPH_FILE.read_text(encoding="utf-8"))


def test_graph_file_exists_and_is_labelled_synthetic():
    graph = load_graph()
    assert graph["label"] == "synthetic_replay_fixture"
    assert graph["is_real_osm_extract"] is False
    assert graph["provenance"]["real_osm_extract_status"] == "not_yet_obtained"


def test_checksum_matches_recorded_provenance():
    # Normalize CRLF->LF before hashing so the checksum is stable across
    # checkouts regardless of core.autocrlf; git may rewrite line endings
    # in the working tree on Windows checkout, but must not silently break
    # this reproducibility check.
    raw = GRAPH_FILE.read_bytes().replace(b"\r\n", b"\n")
    computed = hashlib.sha256(raw).hexdigest()
    recorded_line = CHECKSUM_FILE.read_text(encoding="utf-8").strip()
    recorded_hash = recorded_line.split()[0]
    assert computed == recorded_hash, (
        "fixture_graph.v1.json changed without recomputing its checksum file"
    )


def test_every_band_has_required_fields():
    graph = load_graph()
    assert graph["bands"], "fixture graph must declare at least one band"
    for band in graph["bands"]:
        missing = REQUIRED_BAND_FIELDS - band.keys()
        assert not missing, f"{band.get('band_id')} missing fields: {missing}"
        restriction_missing = REQUIRED_RESTRICTION_FIELDS - band["restrictions"].keys()
        assert not restriction_missing, (
            f"{band['band_id']} restrictions missing: {restriction_missing}"
        )


def test_missing_legality_data_is_visible_not_silently_assumed():
    """Any band with an unknown/null restriction value must declare it in
    missing_legality_data instead of silently treating it as permissive."""
    graph = load_graph()
    for band in graph["bands"]:
        r = band["restrictions"]
        unknown_fields = [
            name
            for name in ("maxheight_m", "maxweight_t")
            if r.get(name) is None
        ]
        if r.get("hgv") == "unknown":
            unknown_fields.append("hgv")
        for field in unknown_fields:
            assert field in band["missing_legality_data"], (
                f"{band['band_id']} has unknown {field} but does not disclose it "
                "in missing_legality_data"
            )


def test_no_band_uses_risk_alone_as_an_exclusion_field():
    """hazard_context / landslide_susceptibility must never appear inside the
    restrictions object used for hard exclusion. Risk ranks; it never excludes."""
    graph = load_graph()
    for band in graph["bands"]:
        assert "landslide_susceptibility" not in band["restrictions"]
        assert "risk" not in band["restrictions"]


@pytest.mark.parametrize("case_id", sorted(REQUIRED_CASE_IDS))
def test_required_deterministic_case_file_exists(case_id):
    case_file = CASES_DIR / f"{case_id}.json"
    assert case_file.exists(), f"missing required deterministic case fixture: {case_id}"
    payload = json.loads(case_file.read_text(encoding="utf-8"))
    assert payload["case_id"] == case_id
    assert payload["label"] == "replay_fixture"


def test_all_case_files_are_accounted_for():
    on_disk = {p.stem for p in CASES_DIR.glob("*.json")}
    assert on_disk == REQUIRED_CASE_IDS, (
        f"case directory drift: on_disk={on_disk} required={REQUIRED_CASE_IDS}"
    )
