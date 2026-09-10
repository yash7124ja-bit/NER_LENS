"""Health response boundary; liveness never implies database readiness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.responses import JSONResponse


@dataclass(frozen=True, slots=True)
class HealthPayload:
    status: str
    http_status: int = 200


@dataclass(frozen=True, slots=True)
class HealthRouter:
    router: APIRouter
    _database_check: Callable[[], bool]

    def live(self) -> HealthPayload:
        return HealthPayload(status="live")

    def ready(self) -> HealthPayload:
        ready = self._database_check()
        return HealthPayload(
            status="ready" if ready else "not_ready", http_status=200 if ready else 503
        )

    def ready_response(self) -> JSONResponse:
        payload = self.ready()
        return JSONResponse(status_code=payload.http_status, content={"status": payload.status})


def build_health_router(database_check: Callable[[], bool]) -> HealthRouter:
    service = HealthRouter(router=APIRouter(prefix="/health"), _database_check=database_check)
    service.router.add_api_route("/live", service.live, methods=["GET"], status_code=200)
    service.router.add_api_route("/ready", service.ready_response, methods=["GET"], status_code=200)
    return service


def check_database_ready(database_check: Callable[[], bool]) -> HealthPayload:
    ready = database_check()
    return HealthPayload(
        status="ready" if ready else "not_ready", http_status=200 if ready else 503
    )
