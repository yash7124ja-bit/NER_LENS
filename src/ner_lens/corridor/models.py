"""A-M1-01 corridor foundation models and GeoJSON boundary validation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import UserDefinedType


class _GeometryBind(FunctionElement):
    inherit_cache = True


class _GeometryJSON(FunctionElement):
    inherit_cache = True


@compiles(_GeometryBind)
@compiles(_GeometryJSON)
def _geometry_identity(element, compiler, **kw):
    return compiler.process(list(element.clauses)[0], **kw)


@compiles(_GeometryBind, "postgresql")
def _geometry_bind_pg(element, compiler, **kw):
    return f"ST_SetSRID(ST_GeomFromGeoJSON({_geometry_identity(element, compiler, **kw)}),4326)"


@compiles(_GeometryJSON, "postgresql")
def _geometry_json_pg(element, compiler, **kw):
    return f"ST_AsGeoJSON({_geometry_identity(element, compiler, **kw)})"


class Base(DeclarativeBase):
    pass


def validate_linestring_4326(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "LineString":
        raise ValueError("geometry must be an EPSG:4326 LineString")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("geometry must contain at least two EPSG:4326 coordinates")
    for coordinate in coordinates:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) != 2
            or not all(isinstance(number, (int, float)) for number in coordinate)
            or not -180 <= coordinate[0] <= 180
            or not -90 <= coordinate[1] <= 90
        ):
            raise ValueError("geometry coordinates must be [longitude, latitude] in EPSG:4326")
    return {"type": "LineString", "coordinates": [list(point) for point in coordinates]}


class Geometry4326(UserDefinedType):
    cache_ok = True

    def bind_expression(self, bindvalue):
        return _GeometryBind(bindvalue)

    def column_expression(self, column):
        expression = _GeometryJSON(column)
        expression.type = self
        return expression

    def get_col_spec(self, **_: Any) -> str:
        return "geometry(Geometry,4326)"

    def bind_processor(self, _dialect: Any):
        def process(value: Any) -> str | None:
            if value is None:
                return None
            return json.dumps(validate_linestring_4326(value), separators=(",", ":"))

        return process

    def result_processor(self, _dialect: Any, _coltype: Any):
        def process(value: Any) -> dict[str, Any] | None:
            if value is None or isinstance(value, dict):
                return value
            return json.loads(value)

        return process


@compiles(Geometry4326, "sqlite")
def _compile_geometry_for_replay(_type: Geometry4326, _compiler: Any, **_: Any) -> str:
    """Use JSON text in the deterministic replay repository; PostGIS uses geometry."""

    return "TEXT"


class CorridorVersion(Base):
    __tablename__ = "corridor_version"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded')", name="ck_corridor_version_status"
        ),
    )
    _allowed_statuses: ClassVar[set[str]] = {"draft", "active", "superseded"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corridor_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdiction.id"))
    graph_version: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="replay://unspecified"
    )
    provenance_label: Mapped[str] = mapped_column(String(32), nullable=False, default="replay")
    route_buffer_km: Mapped[float] = mapped_column(nullable=False, default=5.0)
    hazard_context_buffer_km: Mapped[float] = mapped_column(nullable=False, default=20.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value not in self._allowed_statuses:
            raise ValueError(f"status must be one of {sorted(self._allowed_statuses)}")
        return value


class RoadSegment(Base):
    __tablename__ = "road_segment"
    __table_args__ = (
        UniqueConstraint(
            "corridor_version_id",
            "external_ref",
            "direction",
            name="uq_segment_external_ref_direction",
        ),
        CheckConstraint(
            "segment_type IN ('road', 'bridge', 'tunnel', 'approach')",
            name="ck_road_segment_type",
        ),
        CheckConstraint(
            "direction IN ('both', 'forward', 'backward', 'forward_only', 'backward_only')",
            name="ck_road_segment_direction",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corridor_version_id: Mapped[str] = mapped_column(
        ForeignKey("corridor_version.id"), nullable=False, index=True
    )
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    segment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    authority_ref: Mapped[str | None] = mapped_column(String(255))
    geometry: Mapped[dict[str, Any]] = mapped_column(Geometry4326(), nullable=False)
    vehicle_constraints: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    @validates("geometry")
    def validate_geometry(self, _key: str, value: dict[str, Any]) -> dict[str, Any]:
        return validate_linestring_4326(value)
