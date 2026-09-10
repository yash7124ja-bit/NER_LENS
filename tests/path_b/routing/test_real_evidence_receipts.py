"""B-M0-01 second corrective-audit tests: validate the committed real-evidence
RECEIPTS, not a live service.

BOUNDARY STATEMENT: No GraphHopper server, Docker container, or network call
runs during these tests. The scratch sandbox that produced these receipts
(D:/SIH-2026/.m0-graph-sandbox2/) was deleted after evidence extraction, per
instruction not to commit large/generated artifacts. These tests check that
the committed JSON/YAML receipt files in
data/corridor/graphhopper/real_evidence/v2/ are internally consistent,
checksummed, and honestly labelled — they cannot and do not re-verify the
real world against a running GraphHopper instance. Re-running the real query
requires D:\\SIH-2026\\NER_LENS_ARTIFACTS\\m0\\ (the retained PBF) and
docker/GraphHopper, per REPRODUCE.md.
"""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "data" / "corridor" / "graphhopper" / "real_evidence" / "v2"
RAW_RESPONSES_DIR = EVIDENCE_DIR / "raw_responses"

EXPECTED_PROFILES = {"light_goods", "rigid_truck", "emergency"}
EXPECTED_ROUTE_IDS = {"route_nh27_primary", "route_nh6_alternative"}
EXPECTED_DATA_DATE = "2026-09-09T20:21:20Z"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_three_exact_profiles_present_in_info_response():
    info = load_json(EVIDENCE_DIR / "raw_info.json")
    names = {p["name"] for p in info["profiles"]}
    assert names == EXPECTED_PROFILES


def test_info_response_identifies_expected_graph_data_date():
    info = load_json(EVIDENCE_DIR / "raw_info.json")
    assert info["data_date"] == EXPECTED_DATA_DATE
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["osm_data_as_of"] == EXPECTED_DATA_DATE
    assert provenance["graphhopper"]["confirmed_data_date"] == EXPECTED_DATA_DATE


def test_both_route_hypotheses_have_a_receipt_for_every_profile():
    index = load_json(EVIDENCE_DIR / "response_index.json")
    seen = {(q["route_id"], q["profile"]) for q in index["queries"]}
    expected = {(r, p) for r in EXPECTED_ROUTE_IDS for p in EXPECTED_PROFILES}
    assert seen == expected, f"missing combinations: {expected - seen}"


@pytest.mark.parametrize(
    "route_id,profile",
    [(r, p) for r in sorted(EXPECTED_ROUTE_IDS) for p in sorted(EXPECTED_PROFILES)],
)
def test_raw_response_file_exists_and_hash_matches_index(route_id, profile):
    index = load_json(EVIDENCE_DIR / "response_index.json")
    entry = next(
        q for q in index["queries"] if q["route_id"] == route_id and q["profile"] == profile
    )
    response_path = RAW_RESPONSES_DIR / entry["response_file"]
    assert response_path.exists(), f"missing raw receipt for {route_id}/{profile}"
    assert sha256_of(response_path) == entry["sha256"], (
        f"raw response hash drift for {route_id}/{profile}"
    )
    body = load_json(response_path)
    assert "paths" in body and len(body["paths"]) >= 1


def test_info_response_hash_matches_provenance_record():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert sha256_of(EVIDENCE_DIR / "raw_info.json") == provenance["graphhopper"]["info_response_sha256"]


def test_result_summary_and_response_index_hashes_match_provenance():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert sha256_of(EVIDENCE_DIR / "result_summary.json") == provenance["result_summary_sha256"]
    assert sha256_of(EVIDENCE_DIR / "response_index.json") == provenance["response_index_sha256"]


def test_result_summary_references_expected_profiles_and_routes():
    summary = load_json(EVIDENCE_DIR / "result_summary.json")
    profiles_seen = {v["profile"] for v in summary.values()}
    routes_seen = {v["route_id"] for v in summary.values()}
    assert profiles_seen == EXPECTED_PROFILES
    assert routes_seen == EXPECTED_ROUTE_IDS
    assert len(summary) == 6


def test_required_provenance_fields_exist():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    required_top_level = {
        "osm_extract", "retention", "graphhopper", "vehicle_profiles",
        "routes_queried", "queries", "result_summary_file", "result_summary_sha256",
        "response_index_file", "response_index_sha256", "real_findings",
        "honest_limitations",
    }
    assert required_top_level.issubset(provenance.keys())

    osm = provenance["osm_extract"]
    for field in ("source_url", "licence", "byte_size", "md5", "sha256", "retrieval_timestamps_utc"):
        assert field in osm, f"osm_extract missing {field}"

    retention = provenance["retention"]
    for field in ("absolute_path", "byte_size", "md5", "sha256", "source_url",
                  "licence", "retrieved_at_utc", "hash_verified_after_route_run_at_utc"):
        assert field in retention, f"retention missing {field}"
    assert retention["retained_outside_git"] is True

    for profile in EXPECTED_PROFILES:
        p = provenance["vehicle_profiles"][profile]
        for field in ("source_file", "sha256", "max_weight_t", "max_height_m", "hgv_exempt"):
            assert field in p, f"vehicle_profiles.{profile} missing {field}"


def test_retention_record_uses_the_documented_artifacts_path():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    expected_path = r"D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf"
    assert provenance["retention"]["absolute_path"] == expected_path


def test_timestamps_are_independent_shell_clock_captures_not_bare_http_date():
    """Regression for the first corrective audit's timestamp inconsistency:
    the authoritative retrieval timestamps must be explicitly captured
    before/after each network call, and any HTTP Date header must be
    labelled informational only, not authoritative."""
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    ts = provenance["osm_extract"]["retrieval_timestamps_utc"]
    assert "local_clock_before_download" in ts
    assert "local_clock_after_download" in ts
    assert ts["method"].startswith("this session's shell")
    http_info = provenance["osm_extract"]["http_response_headers_informational_only"]
    assert "note" in http_info
    assert "not the retrieval time" in http_info["note"].lower()


def test_real_and_synthetic_evidence_cannot_be_confused():
    """The synthetic fixture and the real evidence must each be
    unambiguously labelled and must never share a graph_id/label."""
    synthetic = load_json(
        REPO_ROOT / "data" / "corridor" / "graphhopper" / "fixture_graph.v1.json"
    )
    assert synthetic["label"] == "synthetic_replay_fixture"
    assert synthetic["is_real_osm_extract"] is False
    # the fixture's own provenance status must not misleadingly claim no
    # real extract exists anywhere in this audit
    assert synthetic["provenance"]["real_osm_extract_status"] != "not_yet_obtained"

    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["sha256"] != ""
    # the real evidence has no "label" field claiming to be a replay/synthetic
    # fixture, and the synthetic fixture's graph_id differs from any real
    # extract identifier
    assert "graph_id" not in provenance
    assert synthetic["graph_id"] == "ner_lens_route_audit_fixture_v1"


def test_unknown_osm_restrictions_remain_unknown_in_real_receipts():
    """The real run must not silently invent hgv/height/weight values where
    OSM has none. Every query's real receipt must show hgv missing and
    max_height/max_weight unset, matching the desk audit's prediction."""
    summary = load_json(EVIDENCE_DIR / "result_summary.json")
    for query_id, entry in summary.items():
        details = entry["path_details_segment_value_counts"]
        assert details["hgv"] == {"missing": details["hgv"].get("missing", 0)} or set(
            details["hgv"].keys()
        ) == {"missing"}, f"{query_id} unexpectedly has a non-missing hgv value"
        assert set(details["max_height"].keys()) == {"None"}, query_id
        assert set(details["max_weight"].keys()) == {"None"}, query_id


def test_no_route_is_declared_operationally_verified():
    """A 200 response from GraphHopper is graph/vehicle-constraint feasibility,
    not an authorized operational status. Nothing in the committed receipts
    may assert an operational verification claim."""
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    limitations_text = " ".join(provenance["honest_limitations"]).lower()
    assert "not operationally verified" in limitations_text or "no route" in limitations_text

    for path in [EVIDENCE_DIR / "result_summary.json", EVIDENCE_DIR / "response_index.json"]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(payload).lower()
        assert "operationally_verified" not in serialized
        assert '"verified": true' not in serialized


def test_pbf_hash_recorded_in_provenance_matches_retention_record():
    """Cross-check that the two places the PBF hash is recorded (download
    provenance and retention record) agree; a real mismatch here would mean
    the retained file drifted from what was actually queried."""
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["sha256"] == provenance["retention"]["sha256"]
    assert provenance["osm_extract"]["md5"] == provenance["retention"]["md5"]
    assert provenance["osm_extract"]["byte_size"] == provenance["retention"]["byte_size"]


def test_nh6_waypoint_bias_is_explicitly_disclosed():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    nh6 = provenance["routes_queried"]["route_nh6_alternative"]
    assert nh6["via_points"], "NH-6 query must record its via-points"
    assert "WAYPOINT-BIASED" in nh6["note"]
    nh27 = provenance["routes_queried"]["route_nh27_primary"]
    assert nh27["via_points"] == []
