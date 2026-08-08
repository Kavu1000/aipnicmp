"""Geodesy and H3 helpers."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import h3

EARTH_RADIUS_M = 6_371_008.8

# Rough bounding box for Lao PDR, used only to reject obviously impossible
# coordinates. Deliberately generous: a border village must not be discarded
# for sitting a kilometre outside a tidy rectangle.
LAO_BBOX = (13.5, 100.0, 23.0, 108.0)  # (min_lat, min_lon, max_lat, max_lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def in_lao_bbox(lat: float, lon: float) -> bool:
    min_lat, min_lon, max_lat, max_lon = LAO_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def to_h3(lat: float, lon: float, resolution: int) -> str:
    return h3.latlng_to_cell(lat, lon, resolution)


def h3_centroid(cell: str) -> tuple[float, float]:
    lat, lon = h3.cell_to_latlng(cell)
    return lat, lon


def h3_boundary(cell: str) -> list[tuple[float, float]]:
    """Hexagon vertices as (lat, lon), for GeoJSON output."""
    return list(h3.cell_to_boundary(cell))


def h3_polygon_geojson(cell: str) -> dict:
    """GeoJSON Polygon geometry, closed ring, in (lon, lat) order."""
    ring = [[lon, lat] for lat, lon in h3_boundary(cell)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def cells_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float, resolution: int) -> list[str]:
    """Every H3 cell covering a bounding box — used to answer map viewport queries."""
    poly = h3.LatLngPoly(
        [(min_lat, min_lon), (min_lat, max_lon), (max_lat, max_lon), (max_lat, min_lon)]
    )
    return list(h3.polygon_to_cells(poly, resolution))
