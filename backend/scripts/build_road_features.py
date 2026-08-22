"""Fill the road-distance column of the hexagon grid from OpenStreetMap.

Distance to a road is a proxy for two things the coverage model cannot see
directly. Towers are built where they can be reached and powered, so road
distance stands in for the cost of serving a place; and collectors travel by
road, so it also describes where measurements can ever come from. A hexagon
twenty kilometres from the nearest track is both unlikely to be served and
unlikely to be measured, and the model should know those are the same hexagons.

The shapefile is parsed here rather than through a vector library. The only one
that would fit alongside rasterio brings a second copy of GDAL for a single
file, and the polyline record layout is a dozen lines of struct — cheaper to
read than to justify the dependency.

    python -m scripts.build_road_features --dry-run
    python -m scripts.build_road_features
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import struct
import zipfile
from collections import defaultdict

import numpy as np
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.features import HexFeature
from scripts.geodata import fetch

log = logging.getLogger("roads")

ROADS_URL = "https://download.geofabrik.de/asia/laos-latest-free.shp.zip"
ROADS_MEMBER = "gis_osm_roads_free_1.shp"

# No two consecutive vertices further apart than this, so "distance to the
# nearest vertex" is within a few tens of metres of "distance to the nearest
# road". A long straight highway carries vertices only at its bends, and
# without this a hexagon beside the middle of one would be recorded as
# kilometres from any road.
MAX_VERTEX_GAP_DEG = 0.0015  # ~165 m

# Side of the lookup grid. Big enough that most hexagons find a road in the
# first ring, small enough that a cell holds few vertices.
GRID_DEG = 0.05

EARTH_RADIUS_KM = 6371.0088
CHUNK = 5_000


def read_polylines(path, member: str):
    """Vertices of every polyline in a shapefile inside a zip.

    Only shape type 3 (PolyLine) is read; anything else in the file is skipped
    rather than guessed at.
    """
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(member)

    lons: list[float] = []
    lats: list[float] = []
    offset = 100  # fixed header
    total = len(raw)

    while offset < total:
        # Record header is big-endian; the content that follows is little.
        _, length = struct.unpack_from(">ii", raw, offset)
        offset += 8
        end = offset + length * 2
        shape_type = struct.unpack_from("<i", raw, offset)[0]
        if shape_type == 3:
            num_parts, num_points = struct.unpack_from("<ii", raw, offset + 36)
            points_at = offset + 44 + num_parts * 4
            coords = np.frombuffer(raw, dtype="<f8", count=num_points * 2, offset=points_at)
            coords = coords.reshape(-1, 2)
            lons.append(coords[:, 0])
            lats.append(coords[:, 1])
        offset = end

    return np.concatenate(lons), np.concatenate(lats)


def densify(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Insert points so no gap exceeds MAX_VERTEX_GAP_DEG.

    Vertices from different roads sit next to each other in this flat array, so
    pairs further apart than a few kilometres are treated as a break between
    roads rather than a straight run to interpolate along.
    """
    dx = np.diff(lons)
    dy = np.diff(lats)
    gaps = np.hypot(dx, dy)
    joins = (gaps > MAX_VERTEX_GAP_DEG) & (gaps < 0.5)

    out_lon = [lons]
    out_lat = [lats]
    for index in np.flatnonzero(joins):
        steps = int(gaps[index] / MAX_VERTEX_GAP_DEG)
        fractions = np.linspace(0, 1, steps + 1)[1:-1]
        out_lon.append(lons[index] + dx[index] * fractions)
        out_lat.append(lats[index] + dy[index] * fractions)
    return np.concatenate(out_lon), np.concatenate(out_lat)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


async def build(dry_run: bool = False, rebuild: bool = False) -> int:
    async with SessionLocal() as session:
        query = select(HexFeature.h3_index, HexFeature.centroid_lat, HexFeature.centroid_lon)
        if not rebuild:
            query = query.where(HexFeature.distance_to_road_km.is_(None))
        rows = (await session.execute(query)).all()

    if not rows:
        log.info("every hexagon already has a road distance; use --rebuild to redo it")
        return 0

    log.info("hexagons needing road distance: %d", len(rows))
    if dry_run:
        log.info("would download %s (~115 MB)", ROADS_URL.rsplit("/", 1)[-1])
        return len(rows)

    path = fetch(ROADS_URL, "laos-roads.shp.zip", subdir="osm")
    if path is None:
        raise SystemExit(f"road extract unavailable: {ROADS_URL}")

    lons, lats = read_polylines(path, ROADS_MEMBER)
    log.info("road vertices read: %d", len(lons))
    lons, lats = densify(lons, lats)
    log.info("after densifying: %d", len(lons))

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (lon, lat) in enumerate(zip(lons, lats)):
        buckets[(int(lat // GRID_DEG), int(lon // GRID_DEG))].append(index)
    log.info("lookup cells: %d", len(buckets))

    packed = {key: np.array(value) for key, value in buckets.items()}

    updates: list[dict] = []
    written = 0
    for h3_index, lat, lon in rows:
        cell_lat = int(lat // GRID_DEG)
        cell_lon = int(lon // GRID_DEG)

        # Widen the ring until something is found. Laos has roads throughout,
        # so this almost always stops at the first or second ring.
        candidates = None
        for ring in range(1, 12):
            picked = [
                packed[(cell_lat + dy, cell_lon + dx)]
                for dy in range(-ring, ring + 1)
                for dx in range(-ring, ring + 1)
                if (cell_lat + dy, cell_lon + dx) in packed
            ]
            if picked:
                candidates = np.concatenate(picked)
                break
        if candidates is None:
            continue

        distances = haversine_km(lat, lon, lats[candidates], lons[candidates])
        updates.append(
            {"h3_index": h3_index, "distance_to_road_km": round(float(distances.min()), 4)}
        )

        if len(updates) >= CHUNK:
            written += await _flush(updates)
            updates = []
            log.info("  %d hexagons done", written)

    if updates:
        written += await _flush(updates)

    log.info("road distance written for %d hexagons", written)
    return written


async def _flush(rows: list[dict]) -> int:
    async with SessionLocal() as session:
        await session.execute(update(HexFeature), rows)
        await session.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(build(dry_run=args.dry_run, rebuild=args.rebuild))


if __name__ == "__main__":
    main()
