"""Fill the population column of the hexagon grid from WorldPop.

Population is what turns a coverage gap into a priority. Two hexagons with no
service are not the same finding if one holds a village of eight hundred and
the other holds nobody — and the whole argument of the proposal is that money
should follow people, not kilometres.

WorldPop's *unconstrained* 100 m grid, not the constrained one. The constrained
product places people only where building footprints were detected, which is
more precise where it works, but for Laos it accounts for 4.98 million people
against a true 7.28 million. The missing third is not randomly distributed: it
is the settlements the footprint detection missed, which are overwhelmingly the
small rural ones. Losing exactly those would bias this platform against the
places it exists to find. The unconstrained grid is UN-adjusted and totals
7,275,553 against the UN's 7,275,000.

    python -m scripts.build_population_features --dry-run
    python -m scripts.build_population_features
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import h3
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.features import HexFeature
from scripts.geodata import fetch

log = logging.getLogger("population")

WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/LAO/lao_ppp_2020_UNadj.tif"
)
CHUNK = 5_000


async def build(dry_run: bool = False, rebuild: bool = False) -> int:
    async with SessionLocal() as session:
        query = select(HexFeature.h3_index)
        if not rebuild:
            query = query.where(HexFeature.population.is_(None))
        wanted = set((await session.scalars(query)).all())

    if not wanted:
        log.info("every hexagon already has population; use --rebuild to redo it")
        return 0

    log.info("hexagons needing population: %d", len(wanted))
    if dry_run:
        log.info("would download %s (~124 MB)", WORLDPOP_URL.rsplit("/", 1)[-1])
        return len(wanted)

    path = fetch(WORLDPOP_URL, "lao_ppp_2020_unconstrained.tif", subdir="worldpop")
    if path is None:
        raise SystemExit(f"WorldPop raster unavailable: {WORLDPOP_URL}")

    updates: list[dict] = []
    written = 0

    with rasterio.open(path) as raster:
        band = raster.read(1)
        nodata = raster.nodata
        # WorldPop marks unpopulated land with its nodata value rather than 0,
        # so this has to become 0 before anything is summed — left as -99999 it
        # would turn empty countryside into enormous negative populations.
        if nodata is not None:
            band = np.where(band == nodata, 0.0, band)
        band = np.where(np.isfinite(band), band, 0.0)

        for h3_index in wanted:
            boundary = h3.cell_to_boundary(h3_index)
            lats = [p[0] for p in boundary]
            lons = [p[1] for p in boundary]

            top, left = raster.index(min(lons), max(lats))
            bottom, right = raster.index(max(lons), min(lats))
            top, left = max(top, 0), max(left, 0)
            bottom = min(bottom + 1, band.shape[0])
            right = min(right + 1, band.shape[1])
            if bottom <= top or right <= left:
                continue

            window = band[top:bottom, left:right]

            # Masked to the hexagon itself, not its bounding box. These are
            # per-pixel head counts, so a box would count the corners that
            # belong to the neighbouring hexagons too — every person near a
            # boundary would be counted two or three times, and the national
            # total would come out far above the real one.
            polygon = {
                "type": "Polygon",
                "coordinates": [[(lon, lat) for lat, lon in boundary]],
            }
            inside = ~geometry_mask(
                [polygon],
                out_shape=window.shape,
                transform=raster.window_transform(((top, bottom), (left, right))),
                invert=False,
            )
            updates.append(
                {"h3_index": h3_index, "population": float(window[inside].sum())}
            )

            if len(updates) >= CHUNK:
                written += await _flush(updates)
                updates = []
                log.info("  %d hexagons done", written)

    if updates:
        written += await _flush(updates)

    log.info("population written for %d hexagons", written)
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
