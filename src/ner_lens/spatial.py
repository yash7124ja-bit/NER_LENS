"""Metre-based corridor validation; never buffer longitude/latitude degrees."""

from math import floor

from geoalchemy2.functions import ST_DWithin, ST_Transform
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform, unary_union
from sqlalchemy import select

from ner_lens.corridor.models import CorridorVersion, RoadSegment


def projected_corridor(session, corridor_id: str):
    corridor = session.get(CorridorVersion, str(corridor_id))
    if corridor is None:
        raise ValueError("corridor_not_found")
    geometries = session.scalars(
        select(RoadSegment.geometry).where(RoadSegment.corridor_version_id == str(corridor_id))
    ).all()
    if not geometries:
        raise ValueError("corridor_geometry_missing")
    lines = unary_union([LineString(item["coordinates"]) for item in geometries])
    centre = lines.centroid
    if not -80 <= centre.y <= 84:
        raise ValueError("corridor_projection_unsupported")
    zone = min(60, max(1, floor((centre.x + 180) / 6) + 1))
    epsg = (32600 if centre.y >= 0 else 32700) + zone
    transformer = Transformer.from_crs(4326, epsg, always_xy=True)
    projected = transform(transformer.transform, lines)
    return projected, transformer, corridor.route_buffer_km * 1000


def assert_corridor_point(session, corridor_id: str, coordinates) -> None:
    if (
        not isinstance(coordinates, (list, tuple))
        or len(coordinates) != 2
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in coordinates)
        or not -180 <= coordinates[0] <= 180
        or not -90 <= coordinates[1] <= 90
    ):
        raise ValueError("invalid_coordinates")
    lines, transformer, buffer_m = projected_corridor(session, str(corridor_id))
    point = Point(*transformer.transform(*coordinates))
    if not lines.buffer(buffer_m).covers(point):
        raise ValueError("outside_corridor_bounds")


def postgis_nearby(geometry_column, point_expression, distance_m: float, projected_epsg: int):
    """Explicit projected predicate for PostGIS analysis queries, with GeoAlchemy2."""
    if distance_m < 0 or not (32601 <= projected_epsg <= 32760):
        raise ValueError("invalid_spatial_query")
    return ST_DWithin(
        ST_Transform(geometry_column, projected_epsg),
        ST_Transform(point_expression, projected_epsg),
        distance_m,
    )
