"""Health response boundary; liveness never implies database readiness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True, slots=True)
class HealthPayload:
    status: str


@dataclass(frozen=True, slots=True)
class HealthRouter:
    router: APIRouter
    _database_check: Callable[[], bool]

    def live(self) -> HealthPayload:
        return HealthPayload(status="live")

    def ready(self) -> HealthPayload:
        return HealthPayload(status="ready" if self._database_check() else "not_ready")


def build_health_router(database_check: Callable[[], bool]) -> HealthRouter:
    service = HealthRouter(router=APIRouter(prefix="/health"), _database_check=database_check)
    service.router.add_api_route("/live", service.live, methods=["GET"], status_code=200)
    service.router.add_api_route("/ready", service.ready, methods=["GET"], status_code=200)
    return service


def check_database_ready(database_check: Callable[[], bool]) -> HealthPayload:
    return HealthPayload(status="ready" if database_check() else "not_ready")
