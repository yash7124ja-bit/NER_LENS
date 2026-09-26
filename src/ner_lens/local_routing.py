"""Route baselines from a private, dated GraphHopper import."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from ner_lens.config import Settings
from ner_lens.sources import PARSER_VERSION, SourceSnapshot, parse_records

PROFILES = {"light_goods", "rigid_truck", "emergency"}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _private_origin(value: str, *, resolve: bool) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not parsed.port
    ):
        raise ValueError("invalid_private_graphhopper_url")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        if not addresses or any(
            not (ipaddress.ip_address(address[4][0]).is_private
                 or ipaddress.ip_address(address[4][0]).is_loopback)
            for address in addresses
        ):
            raise ValueError("graphhopper_must_use_private_network")
    return value.rstrip("/")


def _bounded_json(client: httpx.Client, url: str, *, params=None) -> tuple[bytes, dict]:
    with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("graphhopper_response_too_large")
            chunks.append(chunk)
    raw = b"".join(chunks)
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("graphhopper_schema_invalid")
    return raw, body


def retrieve_local_graphhopper(
    settings: Settings, *, points: list, profile: str, transport=None
) -> SourceSnapshot:
    now = datetime.now(timezone.utc)
    snapshot = SourceSnapshot(
        id=str(uuid4()), source="graphhopper_local", url="private://graphhopper/route",
        retrieved_at=now, status="failed", reason="unavailable",
        parser_version=f"{PARSER_VERSION}-local-profile-v1", records=[],
    )
    try:
        if profile not in PROFILES:
            raise ValueError("unsupported_vehicle_profile")
        if not settings.graphhopper_data_date:
            raise ValueError("graphhopper_data_date_required")
        expected = datetime.fromisoformat(settings.graphhopper_data_date.replace("Z", "+00:00"))
        if expected.tzinfo is None:
            raise ValueError("graphhopper_data_date_required")
        origin = _private_origin(settings.graphhopper_local_url, resolve=transport is None)
        with httpx.Client(
            timeout=settings.api_request_timeout_seconds, follow_redirects=False,
            transport=transport, trust_env=False,
        ) as client:
            _, info = _bounded_json(client, origin + "/info")
            actual = info.get("data_date")
            if actual != settings.graphhopper_data_date:
                raise ValueError("graphhopper_graph_version_mismatch")
            if profile not in {item.get("name") for item in info.get("profiles", [])
                               if isinstance(item, dict)}:
                raise ValueError("graphhopper_profile_missing")
            raw, _ = _bounded_json(
                client, origin + "/route",
                params=[*(('point', f"{lat},{lon}") for lon, lat in points),
                        ("profile", profile), ("points_encoded", "false")],
            )
        snapshot.raw = raw
        snapshot.sha256 = hashlib.sha256(raw).hexdigest()
        snapshot.records = parse_records("graphhopper", raw, now)
        for record in snapshot.records:
            record.update(
                source="graphhopper_local", vehicle_profile=profile,
                source_record_id=hashlib.sha256(
                    json.dumps(record, sort_keys=True).encode()
                ).hexdigest(),
                observed_at=actual, published_at=None, retrieved_at=now.isoformat(),
                snapshot_sha256=snapshot.sha256, parser_version=snapshot.parser_version,
                units={"distance_m": "m", "duration_seconds": "s"},
            )
        snapshot.license = "ODbL 1.0; OpenStreetMap contributors"
        snapshot.status, snapshot.reason = "available", "private_graph_profile_validated"
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        snapshot.reason = str(exc) if isinstance(exc, ValueError) else "graphhopper_schema_invalid"
    except (httpx.HTTPError, OSError):
        snapshot.reason = "private_graphhopper_unavailable"
    return snapshot
