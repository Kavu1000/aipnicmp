"""GeoJSON polygon arithmetic, in pure Python.

Administrative boundaries need four operations: is this point inside, what is
the bounding box, how large is the area, and give me a smaller version of this
outline. All four are implemented here rather than pulled in from shapely.

That is a deliberate trade. Shapely would be more capable, but it carries GEOS
into every backend and worker image, and the platform's spatial story so far is
a single H3 dependency with PostGIS treated as an optional upgrade
(``app/db/postgis.py``). Four textbook algorithms are a smaller commitment than
a C library, and they run in the SQLite test suite exactly as they run in
production.

Coordinates are GeoJSON order — (lon, lat) — throughout. Mixing the two orders
is the classic way to put Laos in the Indian Ocean, so nothing in this module
accepts (lat, lon).
"""

from __future__ import annotations

from math import cos, radians, sin, sqrt
from typing import Any, Iterable

EARTH_RADIUS_M = 6_371_008.8

# A ring is a closed list of (lon, lat); a polygon is an exterior ring followed
# by zero or more holes; a shape is a list of polygons (a GeoJSON MultiPolygon,
# with a plain Polygon treated as a list of one).
Point = tuple[float, float]
Ring = list[Point]
Polygon = list[Ring]
Shape = list[Polygon]

BBox = tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)


def shape_of(geometry: dict[str, Any]) -> Shape:
    """Normalise a GeoJSON geometry to a list of polygons.

    Raises on anything that is not a Polygon or MultiPolygon: a boundary file
    that turns out to hold line strings should fail at import, loudly, rather
    than silently produce areas that contain nothing.
    """
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []

    if kind == "Polygon":
        return [[[(float(x), float(y)) for x, y in ring] for ring in coordinates]]
    if kind == "MultiPolygon":
        return [
            [[(float(x), float(y)) for x, y in ring] for ring in polygon]
            for polygon in coordinates
        ]
    raise ValueError(f"expected Polygon or MultiPolygon, got {kind!r}")


def to_geojson(shape: Shape) -> dict[str, Any]:
    """The inverse of :func:`shape_of`, collapsing single polygons."""
    if len(shape) == 1:
        return {
            "type": "Polygon",
            "coordinates": [[[x, y] for x, y in ring] for ring in shape[0]],
        }
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [[[x, y] for x, y in ring] for ring in polygon] for polygon in shape
        ],
    }


def bbox_of(shape: Shape) -> BBox:
    """Bounding box over every exterior ring."""
    lons: list[float] = []
    lats: list[float] = []
    for polygon in shape:
        if not polygon:
            continue
        for lon, lat in polygon[0]:
            lons.append(lon)
            lats.append(lat)
    if not lons:
        raise ValueError("empty geometry has no bounding box")
    return (min(lons), min(lats), max(lons), max(lats))


def point_in_ring(lon: float, lat: float, ring: Ring) -> bool:
    """Ray casting: count crossings of a ray heading east from the point.

    The half-open comparison ``(y_i > lat) != (y_j > lat)`` is what stops a
    vertex lying exactly on the ray from being counted twice — the bug that
    makes naive implementations report points outside a shape they are plainly
    inside.
    """
    inside = False
    count = len(ring)
    previous = count - 1
    for current in range(count):
        lon_i, lat_i = ring[current]
        lon_j, lat_j = ring[previous]
        if (lat_i > lat) != (lat_j > lat):
            crossing = (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
            if lon < crossing:
                inside = not inside
        previous = current
    return inside


def point_in_shape(lon: float, lat: float, shape: Shape) -> bool:
    """Inside any polygon's exterior and outside all of that polygon's holes."""
    for polygon in shape:
        if not polygon:
            continue
        if not point_in_ring(lon, lat, polygon[0]):
            continue
        if any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def ring_area_m2(ring: Ring) -> float:
    """Spherical area of a ring, by the excess formula.

    A planar shoelace on raw degrees would understate a Lao province by several
    percent, and the figure is published next to measured km² — two numbers on
    the same screen should not be computed to different standards.
    """
    if len(ring) < 3:
        return 0.0

    total = 0.0
    count = len(ring)
    for index in range(count):
        lon1, lat1 = ring[index]
        lon2, lat2 = ring[(index + 1) % count]
        total += radians(lon2 - lon1) * (2 + sin(radians(lat1)) + sin(radians(lat2)))
    return abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0)


def shape_area_km2(shape: Shape) -> float:
    """Total area, with holes subtracted."""
    total = 0.0
    for polygon in shape:
        if not polygon:
            continue
        total += ring_area_m2(polygon[0])
        total -= sum(ring_area_m2(hole) for hole in polygon[1:])
    return max(total, 0.0) / 1_000_000.0


def _ring_centroid(ring: Ring) -> tuple[float, float, float]:
    """Planar centroid and signed area of a ring, in degrees.

    Longitude is scaled by cos(latitude) so the centroid of a tall northern
    province does not drift east; the scale is removed again before returning.
    """
    if len(ring) < 3:
        return (0.0, 0.0, 0.0)

    mean_lat = sum(lat for _, lat in ring) / len(ring)
    scale = cos(radians(mean_lat)) or 1.0

    twice_area = 0.0
    x_sum = 0.0
    y_sum = 0.0
    count = len(ring)
    for index in range(count):
        lon1, lat1 = ring[index]
        lon2, lat2 = ring[(index + 1) % count]
        x1, x2 = lon1 * scale, lon2 * scale
        cross = x1 * lat2 - x2 * lat1
        twice_area += cross
        x_sum += (x1 + x2) * cross
        y_sum += (lat1 + lat2) * cross

    if twice_area == 0.0:
        return (0.0, 0.0, 0.0)
    return (x_sum / (3 * twice_area) / scale, y_sum / (3 * twice_area), abs(twice_area) / 2)


def centroid_of(shape: Shape) -> Point:
    """A representative point, taken from the largest polygon.

    Not the centroid of the union: for a province with an outlying island the
    combined centroid can land in the water between them. The largest part's
    centroid is where a label belongs and where a map should fly.
    """
    best: tuple[float, Point] | None = None
    for polygon in shape:
        if not polygon:
            continue
        lon, lat, area = _ring_centroid(polygon[0])
        if area > 0 and (best is None or area > best[0]):
            best = (area, (lon, lat))

    if best is not None:
        return best[1]

    min_lon, min_lat, max_lon, max_lat = bbox_of(shape)
    return ((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)


def _perpendicular_distance(point: Point, start: Point, end: Point, scale: float) -> float:
    px, py = point[0] * scale, point[1]
    sx, sy = start[0] * scale, start[1]
    ex, ey = end[0] * scale, end[1]

    dx, dy = ex - sx, ey - sy
    if dx == 0.0 and dy == 0.0:
        return sqrt((px - sx) ** 2 + (py - sy) ** 2)
    return abs(dy * px - dx * py + ex * sy - ey * sx) / sqrt(dx * dx + dy * dy)


def _simplify_ring(ring: Ring, tolerance: float, scale: float) -> Ring:
    """Douglas-Peucker, iterative so a 40,000-vertex coastline cannot blow the
    Python recursion limit."""
    if len(ring) < 4:
        return ring

    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        furthest = -1
        worst = tolerance
        for index in range(first + 1, last):
            distance = _perpendicular_distance(ring[index], ring[first], ring[last], scale)
            if distance > worst:
                worst = distance
                furthest = index
        if furthest != -1:
            keep[furthest] = True
            stack.append((first, furthest))
            stack.append((furthest, last))

    return [point for point, kept in zip(ring, keep) if kept]


def simplify(shape: Shape, tolerance_deg: float) -> Shape:
    """Thin the outlines for the wire, keeping every polygon closed and valid.

    A ring that would collapse below four points is kept at its original detail
    instead: a small island is better sent whole than sent as a triangle, and
    the saving would be a few hundred bytes.
    """
    if tolerance_deg <= 0:
        return shape

    simplified: Shape = []
    for polygon in shape:
        if not polygon:
            continue
        mean_lat = sum(lat for _, lat in polygon[0]) / len(polygon[0])
        scale = cos(radians(mean_lat)) or 1.0

        rings: Polygon = []
        for ring in polygon:
            thinned = _simplify_ring(ring, tolerance_deg, scale)
            if len(thinned) < 4:
                thinned = ring
            if thinned[0] != thinned[-1]:
                thinned = [*thinned, thinned[0]]
            rings.append(thinned)
        simplified.append(rings)
    return simplified


def count_points(shape: Shape) -> int:
    return sum(len(ring) for polygon in shape for ring in polygon)


class ShapeIndex:
    """A uniform grid over bounding boxes, so assignment is not a linear scan.

    A national rebuild asks "which district is this hexagon in?" once per
    hexagon. Against ~150 districts that is tolerable; against several thousand
    villages it is not, and the pilot is expected to grow into the second case.
    Bucketing by a whole degree keeps Laos to a few hundred cells and reduces
    each lookup to the handful of shapes that could possibly match.
    """

    CELL_DEGREES = 1.0

    def __init__(self, entries: Iterable[tuple[str, Shape, BBox]]) -> None:
        self._shapes: dict[str, tuple[Shape, BBox]] = {}
        self._grid: dict[tuple[int, int], list[str]] = {}

        for code, shape, bbox in entries:
            self._shapes[code] = (shape, bbox)
            min_lon, min_lat, max_lon, max_lat = bbox
            for x in range(self._cell(min_lon), self._cell(max_lon) + 1):
                for y in range(self._cell(min_lat), self._cell(max_lat) + 1):
                    self._grid.setdefault((x, y), []).append(code)

    @classmethod
    def _cell(cls, value: float) -> int:
        return int(value // cls.CELL_DEGREES)

    def __len__(self) -> int:
        return len(self._shapes)

    def find(self, lon: float, lat: float) -> str | None:
        """The code of the shape containing this point, or None.

        Where boundaries overlap — which happens in real files, at coastlines
        and in disputed strips — the first match wins and the result is stable
        for a given import, because candidates are ordered as they were loaded.
        """
        for code in self._grid.get((self._cell(lon), self._cell(lat)), ()):
            shape, (min_lon, min_lat, max_lon, max_lat) = self._shapes[code]
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            if point_in_shape(lon, lat, shape):
                return code
        return None
