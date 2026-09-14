"""B-M0-01 deterministic hard-constraint audit tests.

This module implements a small, test-local, pure evaluator that mirrors the
hard-constraint filter described in ARCHITECTURE.md D-007 and
CONTRACTS.md's routing adapter contract: physical/legal vehicle and status
constraints are checked before any risk scoring, and risk alone never
excludes a route.

This is audit/test tooling only. It is NOT the GraphHopper adapter
(`src/ner_lens/routing/**`, B-M1-02) and must not be imported by runtime
code. Its only purpose is to prove the B-M0-01 fixture graph and vehicle
profiles behave deterministically for the six required cases:
closed edge, vehicle restriction, direction restriction,
bridge/tunnel/access constraints, GraphHopper outage, and no feasible route.
"""
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_FILE = REPO_ROOT / "data" / "corridor" / "graphhopper" / "fixture_graph.v1.json"
PROFILES_FILE = REPO_ROOT / "data" / "corridor" / "graphhopper" / "vehicle_profiles.yaml"
CASES_DIR = REPO_ROOT / "tests" / "replay" / "routing" / "cases"


def load_graph():
    return json.loads(GRAPH_FILE.read_text(encoding="utf-8"))


def load_profiles():
    return yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8"))["profiles"]


def load_case(case_id):
    return json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def band_index(graph):
    return {b["band_id"]: b for b in graph["bands"]}


def _direction_blocked(band_direction, requested_direction):
    if band_direction == "both":
        return False
    if band_direction == "forward_only":
        return requested_direction != "forward"
    if band_direction == "reverse_only":
        return requested_direction != "reverse"
    return False


def evaluate_band(band, profile, direction, hard_excluded_band_ids):
    """Return a list of (band_id, reason_code) hard-exclusion reasons.

    Deliberately does not look at hazard_context/landslide_susceptibility:
    risk never creates a hard exclusion (ARCHITECTURE.md D-007).

    Every check below runs for every profile. Only the profile's own
    max_height_m/max_weight_t/hgv_exempt values change the OUTCOME
    (vehicle_profiles.yaml hard_constraints_checked is identical across
    profiles for exactly this reason). Unknown/null/'unverified' values
    never produce a reason here; see coverage_state() for how missing
    legality data is surfaced instead of silently excluded or ignored.
    """
    reasons = []
    band_id = band["band_id"]
    r = band["restrictions"]

    if not band["topology_routable"]:
        reasons.append((band_id, "not_routable"))

    if band_id in hard_excluded_band_ids:
        reasons.append((band_id, "applicable_active_closure"))

    if band.get("planned_unopened"):
        reasons.append((band_id, "planned_road_not_open"))

    if _direction_blocked(band["direction"], direction):
        reasons.append((band_id, "direction_not_permitted"))

    for turn in r["turn_restrictions"]:
        if turn.get("applies_to_direction") == direction:
            reasons.append((band_id, "turn_restriction_applies"))

    if r["access"] in ("no", "private"):
        reasons.append((band_id, "access_denied"))

    if r["maxheight_m"] is not None and profile["max_height_m"] > r["maxheight_m"]:
        reasons.append((band_id, "maxheight_exceeded"))

    if r["maxweight_t"] is not None and profile["max_weight_t"] > r["maxweight_t"]:
        reasons.append((band_id, "maxweight_exceeded"))

    if r["hgv"] == "no" and not profile["hgv_exempt"]:
        reasons.append((band_id, "hgv_access_restricted"))

    if r["construction"] is True:
        reasons.append((band_id, "under_construction"))

    return reasons


def coverage_state(band):
    """The canonical conservative signal for unknown/missing legality data.

    Mirrors CONTRACTS.md's insufficient_evidence vocabulary at band-level
    audit granularity: missing data is visible and labelled, never treated
    as a confirmed permissive fact and never silently excluded either.
    """
    return "insufficient_evidence" if band["missing_legality_data"] else "confirmed"


def evaluate_bands_in_scope(graph, profiles, request):
    bands = band_index(graph)
    profile = profiles[request["vehicle_profile"]]
    hard_excluded = request.get("hard_excluded_band_ids", [])
    all_reasons = []
    for band_id in request["bands_in_scope"]:
        all_reasons.extend(
            evaluate_band(bands[band_id], profile, request["direction"], hard_excluded)
        )
    return all_reasons


def as_reason_set(reasons):
    return {(band_id, code) for band_id, code in reasons}


def test_closed_edge():
    case = load_case("closed_edge")
    graph = load_graph()
    profiles = load_profiles()

    reasons = evaluate_bands_in_scope(graph, profiles, case["request"])
    expected = {
        (item["band_id"], item["reason_code"]) for item in case["expected"]["excluded_bands"]
    }
    assert as_reason_set(reasons) == expected
    assert (len(reasons) == 0) == case["expected"]["route_feasible"]


def test_vehicle_restriction_excludes_only_applicable_profiles():
    case = load_case("vehicle_restriction")
    graph = load_graph()
    profiles = load_profiles()

    for request, expected in zip(case["requests"], case["expected"]):
        reasons = evaluate_bands_in_scope(graph, profiles, request)
        expected_reasons = {
            (item["band_id"], item["reason_code"]) for item in expected["excluded_bands"]
        }
        assert as_reason_set(reasons) == expected_reasons, request["vehicle_profile"]
        assert (len(reasons) == 0) == expected["route_feasible"]


def test_direction_restriction_does_not_depend_on_risk():
    case = load_case("direction_restriction")
    graph = load_graph()
    profiles = load_profiles()

    for request, expected in zip(case["requests"], case["expected"]):
        reasons = evaluate_bands_in_scope(graph, profiles, request)
        expected_reasons = {
            (item["band_id"], item["reason_code"]) for item in expected["excluded_bands"]
        }
        assert as_reason_set(reasons) == expected_reasons, request["direction"]
        assert (len(reasons) == 0) == expected["route_feasible"]

    # The band carries landslide_susceptibility=high; confirm the evaluator
    # never reads risk fields when deciding exclusion (D-007).
    hill_band = band_index(graph)["band_5_maibang_harangajao_balachera_hill"]
    assert hill_band["hazard_context"]["landslide_susceptibility"] == "high"
    forward_request = case["requests"][0]
    assert forward_request["direction"] == "forward"
    assert evaluate_bands_in_scope(graph, profiles, forward_request) == []


def test_bridge_tunnel_access_constraints():
    case = load_case("bridge_tunnel_access")
    graph = load_graph()
    profiles = load_profiles()

    for request, expected in zip(case["requests"], case["expected"]):
        reasons = evaluate_bands_in_scope(graph, profiles, request)
        expected_reasons = {
            (item["band_id"], item["reason_code"]) for item in expected["excluded_bands"]
        }
        assert as_reason_set(reasons) == expected_reasons, request["vehicle_profile"]
        assert (len(reasons) == 0) == expected["route_feasible"]


def test_graphhopper_outage_is_deterministic_and_not_a_hard_exclusion():
    case = load_case("graphhopper_outage")
    assert case["request"]["router_state"] == "unavailable"
    assert case["expected"]["http_status"] == 502
    assert case["expected"]["error_code"] == "upstream_unavailable"
    # route_feasible must be explicitly absent/null: an outage is not the
    # same fact as "every candidate hard-excluded".
    assert case["expected"]["route_feasible"] is None


def test_no_feasible_route_when_every_candidate_is_excluded():
    case = load_case("no_feasible_route")
    graph = load_graph()
    profiles = load_profiles()
    request = case["request"]

    per_route_feasible = {}
    for candidate in request["candidate_routes"]:
        route_request = {
            "vehicle_profile": request["vehicle_profile"],
            "direction": request["direction"],
            "bands_in_scope": candidate["bands_in_scope"],
            "hard_excluded_band_ids": request["hard_excluded_band_ids"],
        }
        reasons = evaluate_bands_in_scope(graph, profiles, route_request)
        route_id = candidate["route_id"]
        expected_route = case["expected"][route_id]
        expected_reasons = {
            (item["band_id"], item["reason_code"])
            for item in expected_route["excluded_bands"]
        }
        assert as_reason_set(reasons) == expected_reasons, route_id
        per_route_feasible[route_id] = len(reasons) == 0
        assert per_route_feasible[route_id] == expected_route["route_feasible"]

    assert not any(per_route_feasible.values()), (
        "fixture must model every candidate route as hard-excluded"
    )
    assert case["expected"]["audit_conclusion"] == "no_verified_feasible_route"
    assert case["expected"]["routes"] == []


# --- Corrective-audit coverage added after Terra P0 review (B-M0-01 fix) ---
# The six cases above cover closed edge / vehicle restriction / direction /
# bridge+tunnel+access / GraphHopper outage / no-feasible-route. Terra found
# the remaining MILESTONES.md categories — topology, surface (incl. explicit
# unknown), bridge/tunnel/approach as a structural fact, access, confirmed
# construction, turn restrictions, and planned/unopened-road exclusion —
# lacked executable checks. Each test below targets one synthetic
# `test_fixture_only` band added specifically for that category, so it
# cannot silently interact with the real-candidate bands used above.


def test_topology_not_routable_is_a_hard_exclusion():
    graph = load_graph()
    profiles = load_profiles()
    reasons = evaluate_bands_in_scope(
        graph,
        profiles,
        {
            "vehicle_profile": "rigid_truck",
            "direction": "forward",
            "bands_in_scope": ["band_test_disconnected_segment"],
            "hard_excluded_band_ids": [],
        },
    )
    assert as_reason_set(reasons) == {
        ("band_test_disconnected_segment", "not_routable")
    }


def test_surface_unverified_is_visible_not_excluded():
    graph = load_graph()
    profiles = load_profiles()
    band = band_index(graph)["band_alt_2_shillong_jowai"]
    assert band["surface"] == "unverified"
    assert "surface" in band["missing_legality_data"]
    # surface is never a field the evaluator checks for exclusion; confirm
    # no reason code named after surface can ever be produced.
    for profile_name in profiles:
        reasons = evaluate_band(band, profiles[profile_name], "forward", [])
        assert all("surface" not in code for _, code in reasons)


def test_bridge_structure_alone_is_not_a_hard_exclusion():
    graph = load_graph()
    profiles = load_profiles()
    band = band_index(graph)["band_test_clean_bridge"]
    assert band["segment_type"] == "bridge"
    for profile_name in profiles:
        reasons = evaluate_band(band, profiles[profile_name], "forward", [])
        assert reasons == [], (
            f"a bridge with no numeric/legal restriction must not exclude {profile_name}"
        )


def test_access_denied_excludes_every_profile():
    graph = load_graph()
    profiles = load_profiles()
    for profile_name in profiles:
        reasons = evaluate_bands_in_scope(
            graph,
            profiles,
            {
                "vehicle_profile": profile_name,
                "direction": "forward",
                "bands_in_scope": ["band_test_private_access"],
                "hard_excluded_band_ids": [],
            },
        )
        assert as_reason_set(reasons) == {("band_test_private_access", "access_denied")}


def test_confirmed_construction_excludes_every_profile():
    graph = load_graph()
    profiles = load_profiles()
    for profile_name in profiles:
        reasons = evaluate_bands_in_scope(
            graph,
            profiles,
            {
                "vehicle_profile": profile_name,
                "direction": "forward",
                "bands_in_scope": ["band_test_confirmed_construction"],
                "hard_excluded_band_ids": [],
            },
        )
        assert as_reason_set(reasons) == {
            ("band_test_confirmed_construction", "under_construction")
        }


def test_construction_false_is_not_excluded():
    """construction=false (confirmed absent) must not be excluded, and must
    be distinguishable from the many bands where construction is unaudited."""
    graph = load_graph()
    profiles = load_profiles()
    clean_band = band_index(graph)["band_2_nagaon_doboka"]
    assert clean_band["restrictions"]["construction"] is False
    reasons = evaluate_band(clean_band, profiles["rigid_truck"], "forward", [])
    assert all(code != "under_construction" for _, code in reasons)


def test_turn_restriction_blocks_only_its_direction():
    graph = load_graph()
    profiles = load_profiles()
    forward = evaluate_bands_in_scope(
        graph,
        profiles,
        {
            "vehicle_profile": "rigid_truck",
            "direction": "forward",
            "bands_in_scope": ["band_test_turn_restriction"],
            "hard_excluded_band_ids": [],
        },
    )
    reverse = evaluate_bands_in_scope(
        graph,
        profiles,
        {
            "vehicle_profile": "rigid_truck",
            "direction": "reverse",
            "bands_in_scope": ["band_test_turn_restriction"],
            "hard_excluded_band_ids": [],
        },
    )
    assert forward == []
    assert as_reason_set(reverse) == {
        ("band_test_turn_restriction", "turn_restriction_applies")
    }


def test_planned_unopened_road_excludes_every_profile_even_hgv_exempt_ones():
    """A planned/approved-but-not-open road must never be usable, even for
    a profile that is otherwise HGV-exempt. Risk/permission status of the
    surrounding data must not matter once planned_unopened is true."""
    graph = load_graph()
    profiles = load_profiles()
    band = band_index(graph)["band_alt_2_shillong_jowai"]
    assert band["planned_unopened"] is True
    for profile_name in ("light_goods", "emergency"):
        reasons = evaluate_band(band, profiles[profile_name], "forward", [])
        assert ("band_alt_2_shillong_jowai", "planned_road_not_open") in reasons


def test_unknown_fields_never_become_hard_exclusion():
    """Regression for the corrective-audit instruction: unknown legality or
    coverage must remain visible, never a confirmed closure. band_1 has
    unknown maxheight_m/maxweight_t/hgv for every profile and must be fully
    feasible for all of them."""
    graph = load_graph()
    profiles = load_profiles()
    band = band_index(graph)["band_1_jalukbari_nagaon"]
    assert band["missing_legality_data"] == sorted(["maxheight_m", "maxweight_t", "hgv"])
    for profile_name in profiles:
        reasons = evaluate_band(band, profiles[profile_name], "forward", [])
        assert reasons == [], f"unknown data wrongly excluded {profile_name}"


def test_coverage_state_flags_missing_data_without_excluding():
    graph = load_graph()
    profiles = load_profiles()
    incomplete_band = band_index(graph)["band_1_jalukbari_nagaon"]
    complete_band = band_index(graph)["band_3_doboka_lanka_lumding"]

    assert coverage_state(incomplete_band) == "insufficient_evidence"
    assert coverage_state(complete_band) == "confirmed"

    # insufficient_evidence coverage must not by itself appear as an
    # exclusion reason code.
    reasons = evaluate_band(incomplete_band, profiles["rigid_truck"], "forward", [])
    assert all(code != "insufficient_evidence" for _, code in reasons)
