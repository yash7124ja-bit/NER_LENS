"""Canonical idempotency-key and request hashing helpers."""

from __future__ import annotations

import hashlib
import json


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 255:
        raise ValueError("idempotency key must be 1-255 UTF-8 bytes")
    return value


def canonical_request_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
