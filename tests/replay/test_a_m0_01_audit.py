"""Executable evidence checks for the A-M0-01 audit package."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "manifests" / "a-m0-01-source-terms.json"
FIXTURE_PATH = ROOT / "tests" / "replay" / "a-m0-01-fixtures.json"
AUDIT_PATH = ROOT / "docs" / "decisions" / "corridor-audit.md"

SOURCE_FIELDS = {
    "source_id",
    "kind",
    "access",
    "terms",
    "observed",
    "fixture_mode",
    "health",
    "required_before_runtime",
}
ALLOWED_FIXTURE_MODES = {"live_approved", "replay", "synthetic", "partner_dependent", "inaccessible"}
UNTRUSTED_TERMS = {"unknown", "not_obtained"}


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_manifest_has_required_fields_and_sources():
    manifest = _read_json(MANIFEST_PATH)

    assert manifest["task_id"] == "A-M0-01"
    assert manifest["manifest_id"] == "a-m0-01-source-terms"
    assert manifest["status"] == "blocked_p0"
    assert manifest["source_policy"] == "metadata_only_no_raw_private_or_unlicensed_payloads"
    assert manifest["sources"]
    probe = manifest["real_route_probe"]
    assert probe["evidence_source"].startswith("path-b commit 137575f")
    assert probe["status"] == "real_bounded_non_runtime_probe"
    assert set(probe["query_profiles"]) == {"light_goods", "rigid_truck", "emergency"}
    assert probe["queries_returned_http_200"] == 6
    assert probe["extract_retrieval_utc"]["authoritative_clock"] == (
        "local_shell_clock_not_cached_http_date"
    )
    assert probe["retained_pbf_outside_git"] is True
    assert probe["retained_pbf_path"].endswith("north-eastern-zone-260909.osm.pbf")
    assert probe["raw_receipts"]["info_response"] == "raw_info.json"
    assert probe["raw_receipts"]["route_responses"] == 6
    assert probe["raw_receipts"]["response_hashes_recorded"] is True
    assert len(probe["receipt_hashes"]) == 3
    assert probe["query_timestamps_utc"]
    assert probe["approximate_endpoints"] is True
    assert probe["nh6_waypoint_biased"] is True
    assert probe["receipt_form"] == (
        "raw_info_and_six_route_responses_with_sha256_index_and_aggregated_summary"
    )
    assert probe["does_not_establish"]

    for source in manifest["sources"]:
        assert SOURCE_FIELDS <= source.keys(), source
        assert source["fixture_mode"] in ALLOWED_FIXTURE_MODES
        assert source["required_before_runtime"]


def test_unlicensed_or_private_cases_are_rejected():
    fixtures = _read_json(FIXTURE_PATH)
    assert fixtures["not_live_validation"] is True

    for case in fixtures["cases"]:
        untrusted = case["mode"] in {"partner_dependent", "inaccessible"} or case["terms"] in UNTRUSTED_TERMS
        if untrusted:
            assert case["expected"] not in {"accept", "accept_metadata_only"}, case

    assert any(case["expected"] == "reject" for case in fixtures["cases"])


def test_replay_and_non_live_labels_are_explicit():
    fixtures = _read_json(FIXTURE_PATH)

    assert fixtures["provenance"] == "synthetic_contract_cases_only"
    assert fixtures["not_live_validation"] is True
    assert fixtures["cases"]
    assert {case["mode"] for case in fixtures["cases"]} <= ALLOWED_FIXTURE_MODES
    assert any(case["mode"] == "replay" for case in fixtures["cases"])
    assert "synthetic" in fixtures["provenance"]


def test_audit_checklist_covers_required_m0_inputs():
    audit = AUDIT_PATH.read_text(encoding="utf-8")

    required_sections = (
        "Prototype mission boundary",
        "Authority and reviewer route",
        "Label feasibility and ground-truth plan",
        "Source and terms ledger",
        "Replay fixtures and provenance boundary",
        "RouteVerificationPolicy inputs",
    )
    for section in required_sections:
        assert section in audit

    for required_fact in (
        "No named authority",
        "No interview or signed review protocol",
        "ML validation feasibility",
        "fallback",
        "Conservative default: **false**",
        "P0 BLOCKED",
        "Bounded real probe evidence (Path B commit `137575f`)",
    ):
        assert required_fact in audit


def test_structural_completeness_does_not_grant_p0_readiness():
    manifest = _read_json(MANIFEST_PATH)
    audit = AUDIT_PATH.read_text(encoding="utf-8")

    # A complete manifest is only a machine-checkable evidence envelope.
    assert manifest["sources"]
    assert manifest["status"] == "blocked_p0"

    # Missing facts remain blockers; the test must fail if evidence is silently
    # converted into a readiness pass.
    assert "P0 BLOCKED — do not start A-M1-01" in audit
    assert "Six HTTP 200 `/route` receipts" in audit
    assert "raw_info.json" in audit
    assert "Receipt hashes" in audit
    assert "exact project-specific `light_goods`" in audit
    assert "exact `light_goods`, `rigid_truck`, and `emergency` profiles" not in audit.split(
        "## 11. P0 decision record", maxsplit=1
    )[1]
    assert "aggregated/self-attested receipts" not in audit
    assert "NH-6 path is waypoint-biased" in audit
    assert "restriction detail is not exposed" in audit
    assert "no operational graph import" in audit
    assert "A named status authority and evidence reviewer" in audit
    assert "A permitted positive-event and passability/ground-truth ledger path" in audit
