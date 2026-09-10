"""B-M0-01 third routing-evidence-correction tests: validate the committed
real-evidence RECEIPTS in real_evidence/v3/, not a live service.

BOUNDARY STATEMENT: No GraphHopper server, Docker container, or network call
runs during these tests. The scratch sandbox that produced these receipts
(D:/SIH-2026/.m0-graph-sandbox3/) was deleted after evidence extraction, per
instruction not to commit large/generated artifacts. These tests check that
the committed JSON/YAML receipt files in
data/corridor/graphhopper/real_evidence/v3/ are internally consistent,
checksummed, and honestly labelled -- they cannot and do not re-verify the
real world against a running GraphHopper instance. Re-running the real query
requires D:\\SIH-2026\\NER_LENS_ARTIFACTS\\m0\\ (the retained PBF) and
docker/GraphHopper, per REPRODUCE.md.

v2 is superseded (see ../v2_superseded/SUPERSEDED.md); a subset of tests
here also check that v2 remains clearly marked as superseded rather than
silently deleted or left ambiguous.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPHHOPPER_DIR = REPO_ROOT / "data" / "corridor" / "graphhopper"
EVIDENCE_DIR = GRAPHHOPPER_DIR / "real_evidence" / "v3"
RAW_RESPONSES_DIR = EVIDENCE_DIR / "raw_responses"
V2_SUPERSEDED_DIR = GRAPHHOPPER_DIR / "real_evidence" / "v2_superseded"

EXPECTED_PROFILES = {"light_goods", "rigid_truck", "emergency"}
EXPECTED_DATA_DATE = "2026-09-09T20:21:20Z"
EXPECTED_BAND_IDS = {
    "band_1_jalukbari_nagaon",
    "band_2_nagaon_doboka",
    "band_3_doboka_lanka_lumding",
    "band_4_lumding_maibang",
    "band_5_maibang_harangajao_balachera_hill",
    "band_6_balachera_silchar",
}
LEG_PREFIXES = [
    "nh27_leg1_band1_jalukbari_nagaon",
    "nh27_leg2_band2_nagaon_doboka",
    "nh27_leg3_band3_doboka_lanka_lumding",
    "nh27_leg4_band4_lumding_maibang",
    "nh27_leg5_band5_maibang_harangajao_balachera",
    "nh27_leg6_band6_balachera_silchar",
]
ROUTE_KIND_PREFIXES = ["nh27_control_direct", "nh27_via_bands"] + LEG_PREFIXES + ["nh6_alternative"]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def strip_json_comments(text):
    """GraphHopper's custom_model loader (Jackson with ALLOW_JAVA_COMMENTS)
    accepts leading `//` line comments; json.loads does not. Strip them the
    same way before parsing so these tests read the exact committed file."""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("//")
    )


def load_custom_model(path):
    return json.loads(strip_json_comments(path.read_text(encoding="utf-8")))


def sha256_of(path):
    """LF-normalized: some committed JSON receipts were written by Python's
    json.dump() in text mode on Windows (CRLF); git normalizes line endings
    on add/checkout, so hashing raw bytes could drift across checkouts.
    Normalizing here matches the LF-normalized hashes recorded in
    real_extract_provenance.yaml and mirrors the fix already applied to
    fixture_graph.v1.sha256. This is a no-op for files with no CRLF (e.g.
    the curl-written raw_info.json / raw_responses/*.json)."""
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


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


def test_all_27_route_kind_profile_combinations_have_a_receipt():
    index = load_json(EVIDENCE_DIR / "response_index.json")
    seen = {q["query_id"] for q in index["queries"]}
    expected = {f"{kind}_{profile}" for kind in ROUTE_KIND_PREFIXES for profile in EXPECTED_PROFILES}
    assert seen == expected, f"missing combinations: {expected - seen}"
    assert len(index["queries"]) == 27


@pytest.mark.parametrize(
    "query_id",
    [f"{kind}_{profile}" for kind in ROUTE_KIND_PREFIXES for profile in sorted(EXPECTED_PROFILES)],
)
def test_raw_response_file_exists_and_hash_matches_index(query_id):
    index = load_json(EVIDENCE_DIR / "response_index.json")
    entry = next(q for q in index["queries"] if q["query_id"] == query_id)
    response_path = EVIDENCE_DIR / entry["response_file"]
    assert response_path.exists(), f"missing raw receipt for {query_id}"
    assert sha256_of(response_path) == entry["sha256"], f"raw response hash drift for {query_id}"
    body = load_json(response_path)
    assert "paths" in body and len(body["paths"]) >= 1


def test_nh27_via_bands_query_covers_all_six_audited_bands():
    """The 'NH-27 candidate' threaded query and the independent per-band leg
    queries must together account for exactly the six audited bands -- no
    band silently dropped, no extra band invented."""
    mapping = load_json(EVIDENCE_DIR / "corridor_edge_mapping.json")
    band_ids = {b["band_id"] for b in mapping["bands"]}
    assert band_ids == EXPECTED_BAND_IDS


def test_nh27_control_direct_is_not_presented_as_corridor_proof():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    control = provenance["routes_queried"]["route_nh27_control_direct"]
    assert "CONTROL ONLY" in control["role"]
    assert "NOT presented as NH-27 corridor proof" in control["role"]
    via_bands = provenance["routes_queried"]["route_nh27_via_bands"]
    assert "THE NH-27 CANDIDATE" in via_bands["role"]


def test_leg_distance_sum_matches_threaded_via_bands_query():
    """Cross-check: GraphHopper's multi-point response must equal the
    concatenation of the independent per-leg queries. A mismatch would mean
    the two evidence layers disagree and neither could be trusted alone."""
    mapping = load_json(EVIDENCE_DIR / "corridor_edge_mapping.json")
    for profile, check in mapping["consistency_check"].items():
        assert abs(check["difference_m"]) < 1.0, f"{profile}: leg sum does not match threaded query"


def test_corridor_edge_mapping_and_result_summary_hashes_match_provenance():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert sha256_of(EVIDENCE_DIR / "result_summary.json") == provenance["result_summary_sha256"]
    assert sha256_of(EVIDENCE_DIR / "response_index.json") == provenance["response_index_sha256"]
    assert sha256_of(EVIDENCE_DIR / "corridor_edge_mapping.json") == provenance["corridor_edge_mapping_sha256"]


def test_info_response_hash_matches_provenance_record():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert sha256_of(EVIDENCE_DIR / "raw_info.json") == provenance["graphhopper"]["info_response_sha256"]


def test_required_provenance_fields_exist():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    required_top_level = {
        "osm_extract", "retention", "graphhopper", "vehicle_profiles",
        "routes_queried", "result_summary_file", "result_summary_sha256",
        "response_index_file", "response_index_sha256",
        "corridor_edge_mapping_file", "corridor_edge_mapping_sha256",
        "real_findings", "honest_limitations",
    }
    assert required_top_level.issubset(provenance.keys())

    osm = provenance["osm_extract"]
    for field in ("source_url", "licence", "byte_size", "md5", "sha256"):
        assert field in osm, f"osm_extract missing {field}"

    retention = provenance["retention"]
    for field in ("absolute_path", "byte_size", "md5", "sha256", "source_url",
                  "licence", "reverification_before_mount_utc", "reverification_after_route_run_utc"):
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


def test_pbf_hash_unchanged_since_v2_and_matches_retention_record():
    """The PBF was reused (not re-downloaded) for v3; its hash must be
    identical to the retention record and to itself before/after this run."""
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["sha256"] == provenance["retention"]["sha256"]
    assert provenance["osm_extract"]["md5"] == provenance["retention"]["md5"]
    assert provenance["osm_extract"]["byte_size"] == provenance["retention"]["byte_size"]
    assert provenance["osm_extract"]["not_redownloaded_this_run"] is True
    # must match the byte-for-byte value already recorded by v2 (v2 is
    # preserved, not deleted, specifically so this cross-check is possible)
    v2_provenance = load_yaml(V2_SUPERSEDED_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["sha256"] == v2_provenance["osm_extract"]["sha256"]
    assert provenance["osm_extract"]["md5"] == v2_provenance["osm_extract"]["md5"]


def test_v2_is_marked_superseded():
    superseded_note = V2_SUPERSEDED_DIR / "SUPERSEDED.md"
    assert superseded_note.exists()
    text = superseded_note.read_text(encoding="utf-8").lower()
    assert "superseded" in text
    assert "v3" in text


# --- Task 2: rigid-truck hard-exclusion regression tests ---------------

def test_rigid_truck_hard_excludes_delivery_and_destination_hgv():
    model = load_custom_model(EVIDENCE_DIR / "rigid_truck.json")
    rules = model["priority"]
    matching = [
        r for r in rules
        if "DELIVERY" in r["if"] and "DESTINATION" in r["if"]
    ]
    assert matching, "expected a priority rule gating on hgv==DELIVERY and hgv==DESTINATION"
    for r in matching:
        assert r["multiply_by"] == "0", (
            f"hgv DELIVERY/DESTINATION must be a hard exclusion (multiply_by 0), got {r}"
        )


def test_rigid_truck_hard_excludes_private_road_access():
    model = load_custom_model(EVIDENCE_DIR / "rigid_truck.json")
    rules = model["priority"]
    matching = [r for r in rules if "road_access == PRIVATE" in r["if"]]
    assert matching, "expected a priority rule gating on road_access == PRIVATE"
    for r in matching:
        assert r["multiply_by"] == "0", (
            f"road_access==PRIVATE must be a hard exclusion (multiply_by 0), got {r}"
        )


def test_rigid_truck_restrictions_are_never_a_small_penalty():
    """Regression for the exact v2 defect: no priority rule may convert
    hgv==DELIVERY/DESTINATION or road_access==PRIVATE into a fractional
    (e.g. 0.1) penalty instead of a hard 0 exclusion."""
    model = load_custom_model(EVIDENCE_DIR / "rigid_truck.json")
    for r in model["priority"]:
        condition = r["if"]
        if any(term in condition for term in ("DELIVERY", "DESTINATION", "PRIVATE")):
            multiplier = r["multiply_by"]
            assert multiplier in ("0", 0), (
                f"restriction condition {condition!r} must multiply_by 0, "
                f"not a penalty value like {multiplier!r}"
            )


def test_rigid_truck_max_weight_exception_cannot_bypass_the_vehicle_limit():
    """No authorization-backed applicability input exists in M0 for
    max_weight_except; the model must exclude below-limit max_weight
    unconditionally, never carve out an except-tagged bypass."""
    model = load_custom_model(EVIDENCE_DIR / "rigid_truck.json")
    weight_rules = [r for r in model["priority"] if "max_weight" in r["if"]]
    assert weight_rules, "expected a max_weight exclusion rule"
    for r in weight_rules:
        assert "max_weight_except" not in r["if"], (
            f"max_weight_except must not gate the max_weight exclusion, got {r}"
        )
        assert r["multiply_by"] == "0"


@pytest.mark.parametrize("profile_file", ["light_goods.json", "emergency.json"])
def test_other_profiles_also_drop_the_max_weight_exception_bypass(profile_file):
    """Consistency extension: the same no-authorization-input rationale
    applies to every profile, not just rigid_truck."""
    model = load_custom_model(EVIDENCE_DIR / profile_file)
    weight_rules = [r for r in model["priority"] if "max_weight" in r["if"]]
    assert weight_rules
    for r in weight_rules:
        assert "max_weight_except" not in r["if"]
        assert r["multiply_by"] == "0"


def test_no_invented_delivery_destination_private_government_or_emergency_exemption():
    """emergency.json and light_goods.json must not grant an exemption for
    DELIVERY/DESTINATION/PRIVATE/government access beyond car_access."""
    for profile_file in ("emergency.json", "light_goods.json"):
        model = load_custom_model(EVIDENCE_DIR / profile_file)
        text = json.dumps(model)
        for forbidden in ("DELIVERY", "DESTINATION", "GOVERNMENT"):
            assert forbidden not in text, f"{profile_file} must not reference {forbidden} at all"


# --- shared invariants (real vs synthetic, no operational-verified claim) --

def test_real_and_synthetic_evidence_cannot_be_confused():
    synthetic = load_json(GRAPHHOPPER_DIR / "fixture_graph.v1.json")
    assert synthetic["label"] == "synthetic_replay_fixture"
    assert synthetic["is_real_osm_extract"] is False
    assert synthetic["provenance"]["real_osm_extract_status"] != "not_yet_obtained"

    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    assert provenance["osm_extract"]["sha256"] != ""
    assert "graph_id" not in provenance
    assert synthetic["graph_id"] == "ner_lens_route_audit_fixture_v1"


def test_unknown_osm_restrictions_remain_unknown_in_real_receipts():
    summary = load_json(EVIDENCE_DIR / "result_summary.json")
    for query_id, entry in summary.items():
        assert set(entry["max_height_distinct_values"]) == {"None"}, query_id
        assert set(entry["max_weight_distinct_values"]) == {"None"}, query_id
        hgv_keys = set(entry["hgv_distance_m"].keys())
        assert hgv_keys == {"missing"}, f"{query_id} unexpectedly has a non-missing hgv value: {hgv_keys}"


def test_no_route_is_declared_operationally_verified():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    limitations_text = " ".join(provenance["honest_limitations"]).lower()
    assert "not operationally verified" in limitations_text or "no route" in limitations_text

    for path in [EVIDENCE_DIR / "result_summary.json", EVIDENCE_DIR / "response_index.json",
                 EVIDENCE_DIR / "corridor_edge_mapping.json"]:
        serialized = path.read_text(encoding="utf-8").lower()
        assert "operationally_verified" not in serialized
        assert '"verified": true' not in serialized


def test_nh6_waypoint_bias_is_explicitly_disclosed():
    provenance = load_yaml(EVIDENCE_DIR / "real_extract_provenance.yaml")
    nh6 = provenance["routes_queried"]["route_nh6_alternative"]
    assert nh6["via_points"], "NH-6 query must record its via-points"
    assert "WAYPOINT-BIASED" in nh6["note"]
    control = provenance["routes_queried"]["route_nh27_control_direct"]
    assert control["via_points"] == []


def test_no_route_is_fabricated_as_pure_nh27_when_it_is_a_real_mix():
    """The via-bands NH-27 share must be reported as a real fraction, never
    smoothed to 100%, and the mapping must disclose the other real refs
    found on the path."""
    mapping = load_json(EVIDENCE_DIR / "corridor_edge_mapping.json")
    for profile, comp in mapping["overall_route_comparison"].items():
        assert 0 < comp["via_bands_nh27_ref_share"] < 1, (
            f"{profile}: NH27 share must be a genuine fraction, not 0 or a fabricated 1.0"
        )
