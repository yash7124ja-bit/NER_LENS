"""Server-only provider retrievals and persisted, fail-closed source health.

Provider metadata and baseline routes are not operational road-status evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from uuid import uuid4
from xml.etree import ElementTree

import httpx
from sqlalchemy import JSON, DateTime, Integer, LargeBinary, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.config import Settings, utc_datetime
from ner_lens.corridor.models import Base, validate_linestring_4326
from ner_lens.db import build_session_factory

PROVIDERS = ("copernicus", "nasa", "sachet", "imd", "graphhopper", "mappls")
HOSTS = {
    "copernicus": {"cds.climate.copernicus.eu"},
    "nasa": {"cmr.earthdata.nasa.gov"},
    "sachet": {"sachet.ndma.gov.in"},
    "imd": {"mausam.imd.gov.in", "api.imd.gov.in"},
    "graphhopper": {"graphhopper.com"},
    "mappls": {"route.mappls.com"},
}
PARSER_VERSION = "provider-access-v1"
MAX_BYTES = 2 * 1024 * 1024


class SourceSnapshot(Base):
    __tablename__ = "source_snapshot"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(512))
    license: Mapped[str | None] = mapped_column(String(255))
    parser_version: Mapped[str] = mapped_column(String(64))
    # Protected snapshots are never returned from the public health endpoint.
    raw: Mapped[bytes | None] = mapped_column(LargeBinary)
    records: Mapped[list] = mapped_column(JSON, default=list)


def safe_url(source: str, url: str, *, resolve: bool = True) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS[source]
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment or parsed.query):
        raise ValueError("invalid_source_url")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("invalid_source_address")


def parse_records(source: str, raw: bytes, retrieved: datetime) -> list[dict]:
    """Preserve metadata; reject unexpected schemas instead of treating them as empty feeds."""
    if source == "sachet":
        text = raw.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("unsafe_xml")
        root = ElementTree.fromstring(text)
        if root.tag != "rss" or root.find("channel") is None:
            raise ValueError("schema_changed")
        records = []
        for item in root.findall("./channel/item"):
            title, published = item.findtext("title"), item.findtext("pubDate")
            if not title or not published:
                raise ValueError("missing_publication_time")
            stamp = parsedate_to_datetime(published)
            if stamp.tzinfo is None or stamp > retrieved:
                raise ValueError("invalid_publication_time")
            records.append({
                "source_record_id": item.findtext("guid") or hashlib.sha256(
                    ElementTree.tostring(item)).hexdigest(),
                "published_at": stamp.isoformat(), "observed_at": None,
                "geometry": None, "payload": {"title": title}, "units": {},
                "quality_flags": ["unreviewed_alert", "not_road_passability", "geometry_missing"],
            })
        return records
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("schema_changed")
    if source in ("graphhopper", "mappls"):
        paths = body.get("paths" if source == "graphhopper" else "routes")
        if not isinstance(paths, list) or not paths:
            raise ValueError("no_route")
        records = []
        for path in paths:
            geometry = validate_linestring_4326(
                path.get("points" if source == "graphhopper" else "geometry"))
            distance = path.get("distance")
            duration = path.get("time" if source == "graphhopper" else "duration")
            if any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) or v < 0 for v in (distance, duration)):
                raise ValueError("invalid_route_units")
            records.append({"geometry": geometry, "distance_m": distance,
                            "duration_seconds": duration / 1000 if source == "graphhopper"
                            else duration, "quality_flags": ["baseline_only",
                            "vehicle_constraints_unverified", "not_road_passability"]})
        return records
    if source == "nasa":
        entries = body.get("feed", {}).get("entry")
        if not isinstance(entries, list):
            raise ValueError("schema_changed")
        return [{"source_record_id": e["id"], "title": e.get("title"),
                 "quality_flags": ["catalogue_metadata_only", "not_rainfall_observation"]}
                for e in entries]
    if source == "copernicus":
        if not body.get("id"):
            raise ValueError("schema_changed")
        return [{"source_record_id": body["id"], "title": body.get("title"),
                 "quality_flags": ["catalogue_metadata_only", "not_rainfall_observation"]}]
    # IMD products need their approved, product-specific schema before normalization.
    raise ValueError("product_schema_required")


def request_spec(source: str, settings: Settings, points: list | None):
    env = settings.providers
    headers, params = {}, []
    if source == "copernicus":
        if not env.get("COPERNICUS_API_KEY") or not env.get("COPERNICUS_API_URL"):
            raise ValueError("not_configured")
        url = env["COPERNICUS_API_URL"].rstrip("/")
        url += "/catalogue/v1/collections/reanalysis-era5-land"
        headers["PRIVATE-TOKEN"] = env["COPERNICUS_API_KEY"]
    elif source == "nasa":
        if not env.get("NASA_EARTHDATA_TOKEN"):
            raise ValueError("not_configured")
        url = "https://cmr.earthdata.nasa.gov/search/collections.json"
        headers["Authorization"] = "Bearer " + env["NASA_EARTHDATA_TOKEN"]
        params = [("keyword", "GPM IMERG"), ("page_size", "10")]
    elif source == "sachet":
        url = env.get("SACHET_RSS_URL", "")
        if not url:
            raise ValueError("not_configured")
        if urlsplit(url).path in ("", "/"):
            # The populated portal URL is not itself a feed; use NDMA's published RSS path.
            url = url.rstrip("/") + "/cap_public_website/rss/rss_india.xml"
    elif source == "imd":
        if env.get("IMD_API_STATUS") != "approved":
            raise ValueError("permission_required")
        url = env.get("IMD_API_URL", "")
        if not url:
            raise ValueError("endpoint_required")
    else:
        key = env.get(source.upper() + "_API_KEY")
        if not key:
            raise ValueError("not_configured")
        if points is None and env.get("SOURCE_ROUTE_POINTS"):
            points = json.loads(env["SOURCE_ROUTE_POINTS"])
        if points is None:
            raise ValueError("route_request_required")
        validate_linestring_4326({"type": "LineString", "coordinates": points})
        if len(points) > 10:
            raise ValueError("too_many_points")
        if source == "graphhopper":
            url = "https://graphhopper.com/api/1/route"
            params = [("point", f"{lat},{lon}") for lon, lat in points]
            params += [("profile", "car"), ("points_encoded", "false"), ("key", key)]
        else:
            coordinates = ";".join(f"{lon},{lat}" for lon, lat in points)
            url = "https://route.mappls.com/route/direction/route_adv/driving/" + coordinates
            params = [("access_token", key), ("geometries", "geojson"), ("steps", "false")]
    return url, headers, params


def retrieve(source: str, settings: Settings, *, points=None, transport=None) -> SourceSnapshot:
    now = datetime.now(timezone.utc)
    snapshot = SourceSnapshot(id=str(uuid4()), source=source, url="", retrieved_at=now,
                              status="failed", reason="unavailable", parser_version=PARSER_VERSION,
                              records=[])
    try:
        url, headers, params = request_spec(source, settings, points)
        safe_url(source, url, resolve=transport is None)
        # Never persist query credentials (or route coordinates in health URLs).
        snapshot.url = url if source != "mappls" else "https://route.mappls.com/route/direction"
        with httpx.Client(timeout=settings.api_request_timeout_seconds, follow_redirects=False,
                          transport=transport) as client:
            with client.stream("GET", url, headers=headers, params=params) as response:
                snapshot.http_status = response.status_code
                if response.status_code != 200:
                    snapshot.reason = ("authentication_failed" if response.status_code in (401, 403)
                                       else "rate_limited" if response.status_code == 429
                                       else "redirect_rejected" if response.is_redirect
                                       else "upstream_error")
                    return snapshot
                etag = response.headers.get("etag", "")
                if len(etag) <= 512 and not any(value and value in etag for key, value
                        in settings.providers.items() if "KEY" in key or "TOKEN" in key):
                    snapshot.etag = etag or None
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("response_too_large")
                    chunks.append(chunk)
                raw = b"".join(chunks)
        # A provider may echo its request. Never archive a credential-bearing response.
        secrets = [v.encode() for k, v in settings.providers.items()
                   if v and ("KEY" in k or "TOKEN" in k)]
        if any(secret in raw for secret in secrets):
            raise ValueError("credential_echo_rejected")
        snapshot.raw, snapshot.sha256 = raw, hashlib.sha256(raw).hexdigest()
        snapshot.records = parse_records(source, raw, now)
        for record in snapshot.records:
            record.setdefault("source_record_id", hashlib.sha256(
                json.dumps(record, sort_keys=True).encode()).hexdigest())
            record.setdefault("observed_at", None)
            record.setdefault("published_at", None)
            record.setdefault("geometry", None)
            record.setdefault("payload", {k: v for k, v in record.items()
                if k in ("title", "distance_m", "duration_seconds")})
            record.setdefault("units", {"distance_m": "m", "duration_seconds": "s"}
                              if source in ("graphhopper", "mappls") else {})
            record.update(source=source, retrieved_at=now.isoformat(),
                          snapshot_sha256=snapshot.sha256, parser_version=PARSER_VERSION)
        snapshot.status, snapshot.reason = "available", "retrieval_validated"
    except ValueError as exc:
        allowed = {"not_configured", "route_request_required", "permission_required",
                   "endpoint_required", "invalid_source_url", "invalid_source_address",
                   "response_too_large", "credential_echo_rejected", "no_route",
                   "product_schema_required"}
        snapshot.reason = str(exc) if str(exc) in allowed else "schema_invalid"
        snapshot.status = "blocked" if snapshot.reason in {
            "permission_required", "not_configured", "endpoint_required", "route_request_required"
        } else "failed"
    except (httpx.HTTPError, OSError, ElementTree.ParseError, KeyError, TypeError, AttributeError):
        snapshot.reason = "request_or_schema_failed"
    return snapshot


def refresh(factory, settings: Settings, *, sources=PROVIDERS, points=None, transport=None):
    results = []
    for source in sources:
        result = retrieve(source, settings, points=points, transport=transport)
        with factory.begin() as session:
            session.add(result)
        results.append({"source": source, "status": result.status, "reason": result.reason,
                        "http_status": result.http_status, "records": len(result.records)})
    return results


def health(factory, settings: Settings) -> dict:
    result = []
    now = datetime.now(timezone.utc)
    with factory() as session:
        for source in PROVIDERS:
            row = session.scalar(select(SourceSnapshot).where(SourceSnapshot.source == source)
                                 .order_by(SourceSnapshot.retrieved_at.desc()).limit(1))
            age = (now - utc_datetime(row.retrieved_at)).total_seconds() if row else None
            result.append({"source": source, "status": "not_checked" if row is None else
                           "stale" if row.status == "available" and
                           age > settings.source_refresh_seconds * 2 else row.status,
                           "reason": row.reason if row else "awaiting_retrieval",
                           "retrieved_at": utc_datetime(row.retrieved_at).isoformat()
                           if row else None, "record_count": len(row.records) if row else 0})
    return {"sources": result, "operational_status_effect": "none",
            "note": "Source access is not verified road passability or a hazard prediction."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=PROVIDERS, action="append")
    parser.add_argument("--points", help="JSON longitude/latitude pairs for baseline routing")
    args = parser.parse_args()
    settings = Settings.from_env()
    factory = build_session_factory(settings)
    try:
        points = json.loads(args.points) if args.points else None
        if points is not None:
            validate_linestring_4326({"type": "LineString", "coordinates": points})
        results = refresh(factory, settings, sources=args.source or PROVIDERS, points=points)
        print(json.dumps(results))
        return 0 if all(r["status"] == "available" for r in results) else 1
    finally:
        factory.kw["bind"].dispose()


if __name__ == "__main__":
    raise SystemExit(main())
