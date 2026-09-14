"""Replay API shell. Start with uvicorn ner_lens.app:app --host 127.0.0.1."""

import asyncio
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from ner_lens.config import Settings
from ner_lens.contracts import (
    CorridorList,
    CorridorState,
    ErrorResponse,
    Liveness,
    LoginRequest,
    Readiness,
    SessionResponse,
    StateQuery,
)
from ner_lens.corridor.importer import PROJECT_ROOT
from ner_lens.corridor.state import list_corridors, read_state
from ner_lens.db import build_session_factory
from ner_lens.identity.accounts import InvalidCredentials, RateLimited, login, logout, profile
from ner_lens.identity.replay import authenticate
from ner_lens.identity.service import AuthContext
from ner_lens.operations import build_router as operations_router
from ner_lens.routing import build_router as routing_router
from ner_lens.sources import health as source_health
from ner_lens.sources import refresh as refresh_sources

_migration_config = Config()
_migration_config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
SCHEMA_HEAD = ScriptDirectory.from_config(_migration_config).get_current_head()
bearer = HTTPBearer(auto_error=False)


def create_app(
    settings: Settings | None = None,
    factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.environment != "replay" or not settings.database_url.startswith(
        ("sqlite", "postgresql")
    ):
        raise ValueError("This API supports SQLite or PostgreSQL replay only")
    if settings.database_url.startswith("postgresql") and (
        not settings.session_cookie_secure or not settings.proxy_secret
    ):
        raise ValueError("Hosted replay requires Secure cookies and a proxy secret")
    owned_factory = factory is None
    factory = factory or build_session_factory(settings)
    session_cookie = APIKeyCookie(name=settings.session_cookie_name, auto_error=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def poll_sources():
            while True:
                try:
                    await asyncio.to_thread(
                        refresh_sources,
                        factory,
                        settings,
                    )
                except Exception:
                    # Database failures must not terminate the API or expose provider secrets.
                    logging.getLogger(__name__).warning("Source collection could not be persisted")
                await asyncio.sleep(settings.source_refresh_seconds)

        task = asyncio.create_task(poll_sources()) if any(settings.providers.values()) else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if owned_factory:
            factory.kw["bind"].dispose()

    app = FastAPI(
        title="NER LENS Replay API",
        version="0.1.0",
        lifespan=lifespan,
        description="Local replay corridor explorer. No live status or route recommendations.",
        responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 429, 503)},
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.url.hostname not in settings.allowed_hosts:
            return error(request, 400, "invalid_request", "Host is not permitted")
        if settings.proxy_secret and request.url.path.startswith("/v1/"):
            if not hmac.compare_digest(
                request.headers.get("x-ner-lens-proxy", ""), settings.proxy_secret
            ):
                return error(request, 403, "forbidden", "Access is not permitted")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                check_origin(request)
            except HTTPException:
                return error(request, 403, "forbidden", "Request origin is not permitted")
            length = 0
            chunks = []
            async for chunk in request.stream():
                length += len(chunk)
                if length > settings.max_request_bytes:
                    return error(request, 413, "payload_too_large", "Request exceeds upload limit")
                chunks.append(chunk)
            request._body = b"".join(chunks)
        try:
            response = await call_next(request)
        except Exception:
            # Do not let exception text (which may contain request data) reach server logs.
            response = error(request, 500, "internal_error", "An unexpected server error occurred")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def error(request: Request, status: int, code: str, message: str, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or [],
                    "retryable": status in (429, 503),
                    "request_id": request.state.request_id,
                }
            },
            headers={
                "X-Request-ID": request.state.request_id,
                "Cache-Control": "no-store",
                **({"WWW-Authenticate": "Bearer"} if status == 401 else {}),
                **({"Retry-After": str(settings.login_window_seconds)} if status == 429 else {}),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        codes = {
            400: "invalid_request",
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            405: "invalid_request",
            409: "conflict",
            413: "payload_too_large",
            415: "unsupported_media_type",
            422: "unprocessable_entity",
            502: "upstream_unavailable",
            429: "rate_limited",
            503: "degraded",
        }
        messages = {
            401: "A valid sign-in session is required",
            403: "Access is not permitted",
            404: "Resource was not found",
            503: "Replay database is not ready",
            429: "Too many sign-in attempts. Please try again later.",
        }
        return error(
            request,
            exc.status_code,
            codes.get(exc.status_code, "invalid_request"),
            messages.get(exc.status_code, "Request is not supported"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(map(str, item["loc"])), "reason": item["type"]}
            for item in exc.errors()
        ]
        return error(request, 400, "invalid_request", "Request validation failed", details)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, _exc: SQLAlchemyError):
        return error(request, 503, "degraded", "Replay database is not ready")

    def current_actor(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
        cookie_value: Annotated[str | None, Depends(session_cookie)],
    ) -> AuthContext:
        require_database()
        token = credentials.credentials if credentials else cookie_value
        actor = authenticate(factory, token) if token else None
        if actor is None:
            raise HTTPException(401)
        return actor

    @app.get("/v1/maps/config")
    def map_config(actor: Annotated[AuthContext, Depends(current_actor)]):
        from urllib.parse import urlsplit

        url = settings.map_style_url
        parsed = urlsplit(url)
        if url and (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
        ):
            raise HTTPException(503, "invalid_public_map_style")
        return {"style_url": url or None, "offline_tiles": False}

    def check_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403)
        if origin:
            current = urlsplit(str(request.url))
            expected = f"{current.scheme}://{current.netloc}"
            if origin != expected and origin not in settings.auth_allowed_origins:
                raise HTTPException(403)

    @app.post("/v1/auth/login", response_model=SessionResponse)
    def sign_in(body: LoginRequest, request: Request, response: Response):
        check_origin(request)
        require_database()
        try:
            token, actor, user = login(
                factory,
                email=body.email,
                password=body.password,
                request_id=request.state.request_id,
                client_key=(
                    request.headers.get("x-ner-lens-client", "unknown")
                    if settings.proxy_secret
                    else request.client.host
                    if request.client
                    else "unknown"
                ),
                session_ttl_seconds=settings.session_ttl_seconds,
                attempt_limit=settings.login_attempt_limit,
                window_seconds=settings.login_window_seconds,
            )
        except InvalidCredentials:
            return error(request, 401, "unauthenticated", "Email or password is incorrect.")
        except RateLimited:
            raise HTTPException(429) from None
        old_token = request.cookies.get(settings.session_cookie_name)
        if old_token:
            logout(factory, old_token, request.state.request_id)
        response.set_cookie(
            settings.session_cookie_name,
            token,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )
        return SessionResponse(user=user, expires_at=actor.expires_at)

    @app.get("/v1/auth/session", response_model=SessionResponse)
    def session_info(actor: Annotated[AuthContext, Depends(current_actor)]):
        try:
            return SessionResponse(user=profile(factory, actor), expires_at=actor.expires_at)
        except InvalidCredentials:
            raise HTTPException(401) from None

    @app.post("/v1/auth/logout", status_code=204)
    def sign_out(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        check_origin(request)
        require_database()
        token = (
            credentials.credentials
            if credentials
            else request.cookies.get(settings.session_cookie_name)
        )
        if token:
            logout(factory, token, request.state.request_id)
        response = Response(status_code=204)
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="strict",
        )
        return response

    @app.get("/health/live", response_model=Liveness)
    def live():
        return {"status": "live"}

    def require_database():
        with factory() as session:
            inspector = inspect(session.get_bind())
            required = {
                "alembic_version",
                "actor",
                "session_record",
                "role_assignment",
                "corridor_version",
                "road_segment",
                "audit_event",
                "jurisdiction",
                "idempotency_record",
                "local_account",
                "login_throttle",
                "source_snapshot",
                "status_authority",
                "field_report",
                "mission",
                "route_comparison",
            }
            if not required.issubset(inspector.get_table_names()):
                raise HTTPException(503)
            revision = (
                session.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
            if revision != [SCHEMA_HEAD]:
                raise HTTPException(503)

    @app.get("/health/ready", response_model=Readiness)
    def ready():
        require_database()
        return {"status": "ready", "components": {"database": "ready", "migrations": "compatible"}}

    @app.get("/health/sources")
    def sources(actor: Annotated[AuthContext, Depends(current_actor)]):
        require_database()
        return source_health(factory, settings)

    @app.get("/v1/models/current")
    def model_card(actor: Annotated[AuthContext, Depends(current_actor)]):
        filename = os.getenv("EVALUATION_MODEL_CARD")
        if not filename:
            return {
                "status": "not_measured",
                "approved_for_operations": False,
                "metrics": None,
                "abstention": "No approved, evaluated model is configured.",
            }
        try:
            path = Path(filename)
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError()
            card = json.loads(path.read_text(encoding="utf-8"))
            if card.get("status") not in {
                "TEST_ONLY_SYNTHETIC",
                "UNAPPROVED_RETROSPECTIVE_EVALUATION",
            }:
                raise ValueError()
            fields = (
                "status",
                "dataset_sha256",
                "cutoff",
                "training_cutoff",
                "test_season",
                "results",
                "limitations",
                "abstention",
            )
            return {**{key: card.get(key) for key in fields}, "approved_for_operations": False}
        except (OSError, ValueError, AttributeError):
            raise HTTPException(503) from None

    @app.get("/v1/corridors", response_model=CorridorList)
    def corridors(request: Request, actor: Annotated[AuthContext, Depends(current_actor)]):
        try:
            return list_corridors(factory, actor, request.state.request_id)
        except LookupError as exc:
            raise HTTPException(404) from exc
        except PermissionError as exc:
            raise HTTPException(403) from exc

    @app.get(
        "/v1/corridors/{corridor_id}/state",
        response_model=CorridorState,
        response_model_exclude_none=False,
    )
    def state(
        corridor_id: UUID,
        query: Annotated[StateQuery, Query()],
        request: Request,
        actor: Annotated[AuthContext, Depends(current_actor)],
    ):
        try:
            return read_state(factory, corridor_id, query, actor, request.state.request_id)
        except LookupError as exc:
            raise HTTPException(404) from exc
        except ValueError as exc:
            raise HTTPException(400) from exc
        except PermissionError as exc:
            raise HTTPException(403) from exc

    from ner_lens.administration import build_router as administration_router
    from ner_lens.media import build_router as media_router

    app.include_router(administration_router(factory, current_actor, settings))
    app.include_router(media_router(factory, current_actor))
    app.include_router(operations_router(factory, current_actor))
    app.include_router(routing_router(factory, current_actor, settings))
    return app


app = create_app()
