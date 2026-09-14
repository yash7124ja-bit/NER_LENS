"""Environment-backed configuration without requiring a live dependency."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    """Local file is a fallback; injected deployment/test values always win."""
    if os.getenv("NER_LENS_ENV_FILE") == "":
        return
    path = os.getenv("NER_LENS_ENV_FILE", str(Path(__file__).resolve().parents[2] / ".env"))
    load_dotenv(path, override=False, interpolate=False)


def normalize_database_url(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def utc_datetime(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = "sqlite+pysqlite:///:memory:"
    environment: str = "replay"
    api_request_timeout_seconds: int = 10
    session_ttl_seconds: int = 28800
    login_attempt_limit: int = 5
    login_window_seconds: int = 900
    session_cookie_name: str = "ner_lens_session"
    session_cookie_secure: bool = False
    auth_allowed_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    proxy_secret: str = ""
    providers: dict[str, str] = field(default_factory=dict, repr=False)
    source_refresh_seconds: int = 3600

    @classmethod
    def from_env(cls) -> "Settings":
        load_environment()
        timeout = os.getenv("API_REQUEST_TIMEOUT_SECONDS") or "10"
        try:
            timeout_seconds = int(timeout)
        except ValueError as exc:
            raise ValueError("API_REQUEST_TIMEOUT_SECONDS must be an integer") from exc
        if timeout_seconds <= 0:
            raise ValueError("API_REQUEST_TIMEOUT_SECONDS must be positive")

        def positive(name: str, default: int) -> int:
            value = int(os.getenv(name) or str(default))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            return value

        return cls(
            database_url=normalize_database_url(
                os.getenv("DATABASE_URL") or "sqlite:///ner_lens_replay.sqlite"
            ),
            environment=os.getenv("NER_LENS_ENV") or cls().environment,
            api_request_timeout_seconds=timeout_seconds,
            session_ttl_seconds=positive("SESSION_TTL_SECONDS", cls().session_ttl_seconds),
            login_attempt_limit=positive("LOGIN_ATTEMPT_LIMIT", cls().login_attempt_limit),
            login_window_seconds=positive("LOGIN_WINDOW_SECONDS", cls().login_window_seconds),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", cls().session_cookie_name),
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
            auth_allowed_origins=tuple(
                value.strip()
                for value in os.getenv("AUTH_ALLOWED_ORIGINS", "").split(",")
                if value.strip()
            ),
            allowed_hosts=tuple(
                filter(
                    None, os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
                )
            )
            + tuple(filter(None, [os.getenv("RENDER_EXTERNAL_HOSTNAME")])),
            proxy_secret=os.getenv("PROXY_SECRET", ""),
            providers={name: os.getenv(name, "") for name in (
                "COPERNICUS_API_URL", "COPERNICUS_API_KEY", "NASA_EARTHDATA_TOKEN",
                "MAPPLS_API_KEY", "GRAPHHOPPER_API_KEY", "SACHET_RSS_URL", "IMD_API_STATUS",
                "IMD_API_URL", "SOURCE_ROUTE_POINTS",
            )},
            source_refresh_seconds=positive("SOURCE_REFRESH_SECONDS", 3600),
        )
