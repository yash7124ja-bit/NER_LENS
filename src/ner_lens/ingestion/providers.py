"""Sanitized, opt-in provider health probes.

These probes are diagnostic only. They never create evidence, mutate operational
status, or treat an HTTP success as permission to use a dataset or product.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Minimal response shape used by the stdlib transport and fake tests."""

    status_code: int
    headers: Mapping[str, str]
    body: str


Transport = Callable[..., HttpResponse]


@dataclass(frozen=True, slots=True)
class ProviderProbeConfig:
    """Environment-derived provider configuration; values are never returned."""

    copernicus_api_url: str | None = None
    copernicus_api_key: str | None = None
    nasa_earthdata_token: str | None = None
    mappls_api_key: str | None = None
    graphhopper_api_key: str | None = None

    @classmethod
    def from_environment(cls) -> ProviderProbeConfig:
        return cls(
            copernicus_api_url=os.getenv("COPERNICUS_API_URL"),
            copernicus_api_key=os.getenv("COPERNICUS_API_KEY"),
            nasa_earthdata_token=os.getenv("NASA_EARTHDATA_TOKEN"),
            mappls_api_key=os.getenv("MAPPLS_API_KEY"),
            graphhopper_api_key=os.getenv("GRAPHHOPPER_API_KEY"),
        )


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    dns_tls_reachable: bool | None
    credential_state: str
    entitlement_state: str
    schema_state: str
    geographic_coverage_state: str
    domain_adequacy: str
    checked_at: str
    error_code: str | None = None
    etag: str | None = None
    source_time: str | None = None
    status_mutation: str = "never"
    _extra: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.pop("_extra", None)
        return result


class ProviderHealthAdapter:
    """Run one explicitly enabled, bounded probe using a sanitized result."""

    def __init__(
        self,
        config: ProviderProbeConfig | None = None,
        *,
        transport: Transport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.config = config or ProviderProbeConfig.from_environment()
        self.transport = transport or _stdlib_transport
        self.timeout_seconds = timeout_seconds

    def probe(
        self,
        provider: str,
        *,
        enabled: bool = False,
        dataset_selected: bool = False,
        terms_approved: bool = False,
    ) -> ProviderHealth:
        if not enabled:
            return self._result(
                provider,
                dns_tls_reachable=None,
                credential_state="disabled_by_default",
                entitlement_state="not_tested",
                schema_state="not_tested",
                geographic_coverage_state="not_tested",
                domain_adequacy="diagnostic_only",
                error_code="provider_disabled",
            )
        probes = {
            "copernicus": self._copernicus,
            "nasa": self._nasa,
            "mappls": self._mappls,
            "sachet": self._sachet,
            "graphhopper": self._graphhopper,
            "imd": self._imd,
        }
        probe = probes.get(provider)
        if probe is None:
            return self._result(
                provider,
                dns_tls_reachable=None,
                credential_state="unknown",
                entitlement_state="unknown",
                schema_state="not_tested",
                geographic_coverage_state="unknown",
                domain_adequacy="diagnostic_only",
                error_code="unsupported_provider",
            )
        return probe(dataset_selected=dataset_selected, terms_approved=terms_approved)

    def _copernicus(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        config = self.config
        if not config.copernicus_api_url or not config.copernicus_api_key:
            return self._result(
                "copernicus",
                dns_tls_reachable=None,
                credential_state="not_configured",
                entitlement_state="not_tested_dataset_selection_required",
                schema_state="not_tested",
                geographic_coverage_state="not_tested",
                domain_adequacy="dataset_and_terms_required",
                error_code="configuration_missing",
            )
        common = dict(
            credential_state="configured",
            entitlement_state="not_tested_dataset_selection_required",
            schema_state="not_tested_auth_only",
            geographic_coverage_state="not_tested",
            domain_adequacy="dataset_and_terms_required",
        )
        if not dataset_selected or not terms_approved:
            return self._result(
                "copernicus",
                dns_tls_reachable=None,
                error_code="dataset_and_terms_required",
                **common,
            )
        url = config.copernicus_api_url.rstrip("/") + "/profiles/v1/account/verification/pat"
        response, error = self._request(
            "POST", url, headers={"Authorization": f"Bearer {config.copernicus_api_key}"}
        )
        if error:
            return self._result("copernicus", dns_tls_reachable=None, error_code=error, **common)
        assert response is not None
        credential_state = "authenticated" if 200 <= response.status_code < 300 else (
            "rejected" if response.status_code in {401, 403} else "unknown"
        )
        return self._result(
            "copernicus",
            dns_tls_reachable=True,
            error_code=_http_error(response),
            **{**common, "credential_state": credential_state},
        )

    def _nasa(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        del dataset_selected, terms_approved
        url = "https://cmr.earthdata.nasa.gov/search/collections.json"
        response, error = self._request("GET", url, params={"page_size": "1"})
        common = dict(
            credential_state="not_tested_without_selected_protected_granule",
            entitlement_state="not_tested_without_selected_protected_granule",
            geographic_coverage_state="global_catalog_discovery_only",
            domain_adequacy="dataset_discovery_only",
        )
        if error:
            return self._result(
                "nasa",
                dns_tls_reachable=None,
                schema_state="not_tested",
                error_code=error,
                **common,
            )
        assert response is not None
        schema_state = (
            "valid" if _is_json_object(response.body) else "invalid"
        ) if response.status_code < 400 else "not_tested"
        return self._result(
            "nasa",
            dns_tls_reachable=True,
            schema_state=schema_state,
            error_code=(
                _http_error(response)
                or ("schema_invalid" if schema_state == "invalid" else None)
            ),
            **common,
        )

    def _mappls(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        del dataset_selected, terms_approved
        if not self.config.mappls_api_key:
            return self._result(
                "mappls",
                dns_tls_reachable=None,
                credential_state="not_configured",
                entitlement_state="not_tested",
                schema_state="not_tested",
                geographic_coverage_state="not_tested",
                domain_adequacy="single_geocode_only",
                error_code="configuration_missing",
            )
        url = "https://search.mappls.com/search/address/geocode"
        response, error = self._request(
            "GET",
            url,
            params={"address": "Shillong, Meghalaya", "access_token": self.config.mappls_api_key},
        )
        if error:
            return self._result(
                "mappls",
                dns_tls_reachable=None,
                credential_state="configured",
                entitlement_state="unknown",
                schema_state="not_tested",
                geographic_coverage_state="single_geocode_only",
                domain_adequacy="single_geocode_only",
                error_code=error,
            )
        assert response is not None
        schema_state = "valid" if _is_json_object(response.body) else "invalid"
        entitlement = "not_verified_static_or_rest_key"
        if response.status_code in {401, 403}:
            entitlement = "rejected"
        return self._result(
            "mappls",
            dns_tls_reachable=True,
            credential_state="rejected" if response.status_code in {401, 403} else "configured",
            entitlement_state=entitlement,
            schema_state=schema_state if response.status_code < 400 else "not_tested",
            geographic_coverage_state="single_geocode_only",
            domain_adequacy="single_geocode_only",
            error_code=(
                _http_error(response)
                or ("schema_invalid" if schema_state == "invalid" else None)
            ),
        )

    def _sachet(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        del dataset_selected, terms_approved
        url = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
        response, error = self._request("GET", url)
        common = dict(
            credential_state="public_no_auth",
            entitlement_state="public_feed_terms_required",
            geographic_coverage_state="india_feed_not_corridor_verified",
            domain_adequacy="alert_context_only_no_status_mutation",
        )
        if error:
            return self._result(
                "sachet",
                dns_tls_reachable=None,
                schema_state="not_tested",
                error_code=error,
                **common,
            )
        assert response is not None
        source_time = _rss_source_time(response.body) if response.status_code < 400 else None
        schema_state = (
            "valid" if source_time is not None else "invalid"
        ) if response.status_code < 400 else "not_tested"
        return self._result(
            "sachet",
            dns_tls_reachable=True,
            schema_state=schema_state,
            etag=response.headers.get("etag") or response.headers.get("ETag"),
            source_time=source_time,
            error_code=(
                _http_error(response)
                or ("schema_invalid" if schema_state == "invalid" else None)
            ),
            **common,
        )

    def _imd(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        del dataset_selected, terms_approved
        return self._result(
            "imd",
            dns_tls_reachable=None,
            credential_state="permission_required",
            entitlement_state="permission_required",
            schema_state="not_tested",
            geographic_coverage_state="not_tested",
            domain_adequacy="permission_required_no_probe",
            error_code="permission_required",
        )

    def _graphhopper(self, *, dataset_selected: bool, terms_approved: bool) -> ProviderHealth:
        del dataset_selected, terms_approved
        if not self.config.graphhopper_api_key:
            return self._result(
                "graphhopper",
                dns_tls_reachable=None,
                credential_state="not_configured",
                entitlement_state="not_tested",
                schema_state="not_tested",
                geographic_coverage_state="two_close_ner_points_only",
                domain_adequacy="demo_decision_support_not_sole_emergency_routing",
                error_code="configuration_missing",
            )
        url = "https://graphhopper.com/api/1/route"
        response, error = self._request(
            "GET",
            url,
            params={
                "point": ["26.1445,91.7362", "26.1447,91.7365"],
                "profile": "car",
                "points_encoded": "false",
                "instructions": "false",
                "key": self.config.graphhopper_api_key,
            },
        )
        if error:
            return self._result(
                "graphhopper",
                dns_tls_reachable=None,
                credential_state="configured",
                entitlement_state="unknown",
                schema_state="not_tested",
                geographic_coverage_state="two_close_ner_points_only",
                domain_adequacy="demo_decision_support_not_sole_emergency_routing",
                error_code=error,
            )
        assert response is not None
        parsed = _json(response.body)
        schema_state = (
            "valid"
            if isinstance(parsed, dict) and isinstance(parsed.get("paths"), list)
            else "invalid"
        )
        return self._result(
            "graphhopper",
            dns_tls_reachable=True,
            credential_state="authenticated" if response.status_code < 400 else "rejected",
            entitlement_state="hosted_route_response_only",
            schema_state=schema_state if response.status_code < 400 else "not_tested",
            geographic_coverage_state="two_close_ner_points_only",
            domain_adequacy="demo_decision_support_not_sole_emergency_routing",
            error_code=(
                _http_error(response)
                or ("schema_invalid" if schema_state == "invalid" else None)
            ),
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | list[str]] | None = None,
    ) -> tuple[HttpResponse | None, str | None]:
        try:
            return (
                self.transport(
                    method,
                    url,
                    headers=dict(headers or {}),
                    params=dict(params or {}),
                    timeout=self.timeout_seconds,
                ),
                None,
            )
        except TimeoutError:
            return None, "timeout"
        except (OSError, urllib.error.URLError):
            return None, "transport_error"
        except Exception:
            return None, "transport_error"

    def _result(self, provider: str, **kwargs: object) -> ProviderHealth:
        return ProviderHealth(
            provider=provider,
            checked_at=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )


def _stdlib_transport(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    params: Mapping[str, str | list[str]],
    timeout: float,
) -> HttpResponse:
    query = urllib.parse.urlencode(params, doseq=True)
    request_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(request_url, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_000).decode("utf-8", errors="replace")
            return HttpResponse(response.status, dict(response.headers.items()), body)
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, dict(error.headers.items()), "")


def _http_error(response: HttpResponse) -> str | None:
    return None if 200 <= response.status_code < 400 else f"http_{response.status_code}"


def _json(body: str) -> object | None:
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return None


def _is_json_object(body: str) -> bool:
    return isinstance(_json(body), dict)


def _rss_source_time(body: str) -> str | None:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    for tag in ("lastBuildDate", "pubDate", "published", "updated"):
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == tag and element.text:
                return element.text.strip()
    return None
