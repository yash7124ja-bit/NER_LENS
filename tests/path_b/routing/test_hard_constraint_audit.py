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

import pytest
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
    """
    reasons = []
    band_id = band["band_id"]
    r = band["restrictions"]

    if band_id in hard_excluded_band_ids:
        reasons.append((band_id, "applicable_active_closure"))

    if _direction_blocked(band["direction"], direction):
        reasons.append((band_id, "direction_not_permitted"))

    if r["maxheight_m"] is not None and profile["max_height_m"] > r["maxheight_m"]:
        reasons.append((band_id, "maxheight_exceeded"))

    if r["maxweight_t"] is not None and profile["max_weight_t"] > r["maxweight_t"]:
        reasons.append((band_id, "maxweight_exceeded"))

    if r["hgv"] == "no" and not profile["hgv_exempt"]:
        reasons.append((band_id, "hgv_access_restricted"))

    return reasons


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
