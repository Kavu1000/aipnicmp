"""Fill the terrain columns of the hexagon grid from the Copernicus DEM.

Elevation is the strongest predictor available for coverage in Laos. A tower
serves what it can see, and in a country that is roughly three-quarters
mountain, line of sight is decided by terrain long before distance matters.
Two hexagons the same distance from the same tower — one on a valley floor,
one behind a ridge — are not the same question.

So two numbers per hexagon, not one:

* the mean elevation, which places the hexagon in the landscape;
* the spread of elevation inside it, which says whether it *is* a landscape.
  A flat plain and a gorge can share a mean and share nothing else, and a
  model given only the mean cannot tell them apart.

    python -m scripts.build_terrain_features --dry-run
    python -m scripts.build_terrain_features

Re-runnable; hexagons already carrying terrain are skipped unless --rebuild.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict

import h3
import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.features import HexFeature
from scripts.geodata import dem_tiles, fetch

log = logging.getLogger("terrain")

CHUNK = 5_000


def _tile_key(lat: float, lon: float) -> tuple[int, int]:
    """Which one-degree DEM tile a point falls in."""
    return (int(np.floor(lat)), int(np.floor(lon)))


async def build(dry_run: bool = False, rebuild: bool = False) -> int:
    async with SessionLocal() as session:
        query = select(
            HexFeature.h3_index, HexFeature.centroid_lat, HexFeature.centroid_lon
        )
        if not rebuild:
            query = query.where(HexFeature.elevation_mean_m.is_(None))
        rows = (await session.execute(query)).all()

    if not rows:
        log.info("every hexagon already has terrain; use --rebuild to redo it")
        return 0

    log.info("hexagons needing terrain: %d", len(rows))

    # Grouped by DEM tile so each raster is opened once and read once, rather
    # than once per hexagon. Opening a COG 280,000 times would dominate the
    # runtime completely.
    by_tile: dict[tuple[int, int], list[tuple[str, float, float]]] = defaultdict(list)
    for h3_index, lat, lon in rows:
        by_tile[_tile_key(lat, lon)].append((h3_index, lat, lon))

    log.info("DEM tiles to read: %d", len(by_tile))

    if dry_run:
        log.info("would download up to %d tiles (~5.4 MB each)", len(by_tile))
        return len(rows)

    urls = {}
    for url, name in dem_tiles():
        # Copernicus_DSM_COG_30_N18_00_E102_00_DEM -> (18, 102)
        parts = name.split("_")
        urls[(int(parts[4][1:]), int(parts[6][1:]))] = (url, name)

    updates: list[dict] = []
    written = 0
    missing_tiles = 0

    for key, members in sorted(by_tile.items()):
        source = urls.get(key)
        if source is None:
            missing_tiles += 1
            continue
        path = fetch(source[0], source[1], subdir="copernicus-dem-90m")
        if path is None:
            missing_tiles += 1
            log.warning("no DEM tile for N%02d E%03d", key[0], key[1])
            continue

        try:
            with rasterio.open(path) as dem:
                band = dem.read(1)
                nodata = dem.nodata
                for h3_index, lat, lon in members:
                    # The hexagon's own outline, not a square around its
                    # centre: at this cell size a bounding box pulls in ground
                    # from as far as the next hexagon, which would smear a
                    # ridge line across the valley beside it.
                    boundary = h3.cell_to_boundary(h3_index)
                    lats = [p[0] for p in boundary]
                    lons = [p[1] for p in boundary]
                    top, left = dem.index(min(lons), max(lats))
                    bottom, right = dem.index(max(lons), min(lats))
                    top, left = max(top, 0), max(left, 0)
                    bottom = min(bottom + 1, band.shape[0])
                    right = min(right + 1, band.shape[1])
                    if bottom <= top or right <= left:
                        continue

                    window = band[top:bottom, left:right].astype("float32")
                    if nodata is not None:
                        window = window[window != nodata]
                    else:
                        window = window.ravel()
                    if window.size == 0:
                        continue

                    updates.append(
                        {
                            "h3_index": h3_index,
                            "elevation_mean_m": float(window.mean()),
                            "elevation_min_m": float(window.min()),
                            "elevation_max_m": float(window.max()),
                            "terrain_ruggedness_m": float(window.std()),
                        }
                    )
        except RasterioIOError as problem:
            log.warning("unreadable tile %s: %s", path.name, problem)
            continue

        if len(updates) >= CHUNK:
            written += await _flush(updates)
            updates = []
            log.info("  %d hexagons done", written)

    if updates:
        written += await _flush(updates)

    log.info("terrain written for %d hexagons (%d tiles unavailable)", written, missing_tiles)
    return written


async def _flush(rows: list[dict]) -> int:
    """One statement per chunk, not one per hexagon.

    A statement each would be 280,000 round trips, and the database is reached
    through a tunnel — that is the difference between minutes and most of a
    day. ``bindparam`` turns the chunk into a single executemany.
    """
    # Bulk update by primary key: each row carries its own h3_index, so no
    # WHERE clause is needed and SQLAlchemy can send the chunk as a single
    # executemany. Spelling it as an explicit WHERE instead makes the ORM
    # refuse the batch outright.
    async with SessionLocal() as session:
        await session.execute(update(HexFeature), rows)
        await session.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--rebuild", action="store_true", help="Redo hexagons that already have terrain."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(build(dry_run=args.dry_run, rebuild=args.rebuild))


if __name__ == "__main__":
    main()
