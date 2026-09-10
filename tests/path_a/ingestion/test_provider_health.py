from __future__ import annotations

import json

from ner_lens.ingestion.providers import (
    HttpResponse,
    ProviderHealthAdapter,
    ProviderProbeConfig,
)


class FakeTransport:
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def __call__(self, method: str, url: str, **kwargs: object) -> HttpResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses[url]


def config(**values: str) -> ProviderProbeConfig:
    defaults = {
        "copernicus_api_url": "https://copernicus.example.test",
        "copernicus_api_key": "pat-fixture",
        "nasa_earthdata_token": "token-fixture",
        "mappls_api_key": "map-fixture",
        "graphhopper_api_key": "gh-fixture",
    }
    defaults.update(values)
    return ProviderProbeConfig(**defaults)


def test_disabled_by_default_does_not_call_provider_or_claim_health():
    transport = FakeTransport({})
    adapter = ProviderHealthAdapter(config(), transport=transport)

    result = adapter.probe("nasa")

    assert result.credential_state == "disabled_by_default"
    assert result.error_code == "provider_disabled"
    assert result.dns_tls_reachable is None
    assert transport.calls == []


def test_public_nasa_discovery_reports_schema_without_claiming_token_entitlement():
    transport = FakeTransport(
        {
            "https://cmr.earthdata.nasa.gov/search/collections.json": HttpResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"feed": {"entry": [{"id": "fixture-collection"}]}}),
            )
        }
    )
    adapter = ProviderHealthAdapter(config(), transport=transport)

    result = adapter.probe("nasa", enabled=True)

    assert result.provider == "nasa"
    assert result.dns_tls_reachable is True
    assert result.credential_state == "not_tested_without_selected_protected_granule"
    assert result.entitlement_state == "not_tested_without_selected_protected_granule"
    assert result.schema_state == "valid"
    assert result.error_code is None
    assert transport.calls[0]["method"] == "GET"
    assert "token-fixture" not in json.dumps(transport.calls[0], sort_keys=True)


def test_sachet_preserves_etag_and_source_time_and_never_mutates_status():
    url = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
    body = (
        "<?xml version='1.0'?><rss><channel>"
        "<lastBuildDate>2026-09-10T00:00:00Z</lastBuildDate>"
        "<item><title>fixture</title></item></channel></rss>"
    )
    transport = FakeTransport(
        {
            url: HttpResponse(
                status_code=200,
                headers={
                    "etag": '"fixture-etag"',
                    "last-modified": "Wed, 10 Sep 2026 00:00:00 GMT",
                },
                body=body,
            )
        }
    )
    adapter = ProviderHealthAdapter(config(), transport=transport)

    result = adapter.probe("sachet", enabled=True)

    assert result.schema_state == "valid"
    assert result.etag == '"fixture-etag"'
    assert result.source_time == "2026-09-10T00:00:00Z"
    assert result.status_mutation == "never"


def test_authenticated_probes_are_sanitized_and_failures_are_not_evidence():
    copernicus_url = "https://copernicus.example.test/profiles/v1/account/verification/pat"
    mappls_url = "https://search.mappls.com/search/address/geocode"
    graphhopper_url = "https://graphhopper.com/api/1/route"
    transport = FakeTransport(
        {
            copernicus_url: HttpResponse(status_code=401, headers={}, body="secret-error"),
            mappls_url: HttpResponse(status_code=503, headers={}, body="upstream-error"),
            graphhopper_url: HttpResponse(
                status_code=200, headers={}, body=json.dumps({"paths": [{}]})
            ),
        }
    )
    adapter = ProviderHealthAdapter(config(), transport=transport)

    copernicus = adapter.probe(
        "copernicus", enabled=True, dataset_selected=True, terms_approved=True
    )
    mappls = adapter.probe("mappls", enabled=True)
    graphhopper = adapter.probe("graphhopper", enabled=True)

    assert copernicus.credential_state == "rejected"
    assert copernicus.entitlement_state == "not_tested_dataset_selection_required"
    assert mappls.error_code == "http_503"
    assert mappls.dns_tls_reachable is True
    assert graphhopper.schema_state == "valid"
    assert graphhopper.domain_adequacy == "demo_decision_support_not_sole_emergency_routing"
    serialized = json.dumps(
        [copernicus.to_dict(), mappls.to_dict(), graphhopper.to_dict()], sort_keys=True
    )
    assert "secret-error" not in serialized
    assert "upstream-error" not in serialized
    assert "pat-fixture" not in serialized
    assert "map-fixture" not in serialized
    assert "gh-fixture" not in serialized


def test_missing_copernicus_dataset_or_terms_is_not_called():
    transport = FakeTransport({})
    adapter = ProviderHealthAdapter(config(), transport=transport)

    result = adapter.probe("copernicus", enabled=True)

    assert result.entitlement_state == "not_tested_dataset_selection_required"
    assert result.error_code == "dataset_and_terms_required"
    assert transport.calls == []


def test_imd_is_permission_gated_and_never_probed():
    transport = FakeTransport({})
    adapter = ProviderHealthAdapter(config(), transport=transport)

    result = adapter.probe("imd", enabled=True)

    assert result.credential_state == "permission_required"
    assert result.error_code == "permission_required"
    assert transport.calls == []
