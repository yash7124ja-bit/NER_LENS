"""Environment-backed configuration without requiring a live dependency."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = "sqlite+pysqlite:///:memory:"
    environment: str = "replay"
    api_request_timeout_seconds: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        timeout = os.getenv("API_REQUEST_TIMEOUT_SECONDS", "10")
        try:
            timeout_seconds = int(timeout)
        except ValueError as exc:
            raise ValueError("API_REQUEST_TIMEOUT_SECONDS must be an integer") from exc
        if timeout_seconds <= 0:
            raise ValueError("API_REQUEST_TIMEOUT_SECONDS must be positive")
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            environment=os.getenv("NER_LENS_ENV", cls.environment),
            api_request_timeout_seconds=timeout_seconds,
        )
