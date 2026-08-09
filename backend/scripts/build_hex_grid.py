"""Lay down the national hexagon grid the coverage model predicts onto.

Reads the administrative boundaries already in the database and writes one
``hex_features`` row per hexagon of Lao PDR, tagged with the province and
district it falls in. Terrain, population and infrastructure columns are left
null; each has its own builder, and every one of them needs this grid first.

Why this exists at all: measurements only ever appear where somebody drove.
The model is trained on those hexagons and asked about the rest, so the "rest"
has to be enumerated independently of the measurements — before a single
reading is collected, and without changing when one arrives.

    python -m scripts.build_hex_grid --dry-run
    python -m scripts.build_hex_grid

Re-runnable. Hexagons are upserted by index, so an added province or a
corrected boundary can be folded in without rebuilding the country, and the
feature columns other builders have filled are left untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any, Iterable

import h3
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.area import AdminArea
from app.models.features import HexFeature

log = logging.getLogger("build_hex_grid")

# Rows per statement. Large enough that 280,000 hexagons do not become 280,000
# round trips, small enough to stay well inside the parameter limit a single
# statement can carry.
CHUNK = 2_000


def _rings(geometry: dict[str, Any]) -> Iterable[list]:
    """Every polygon in a geometry, whether it is one or many."""
    if geometry["type"] == "MultiPolygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "Polygon":
        yield geometry["coordinates"]


def cells_of(geometry: dict[str, Any], resolution: int) -> set[str]:
    """Every hexagon touching this geometry.

    ``contain="overlap"`` rather than the default centre test: a cell whose
    centre falls outside the border still covers ground inside it, and dropping
    those leaves an unpredicted fringe around the whole country — exactly the
    remote border areas this project exists to look at.
    """
    cells: set[str] = set()
    for polygon in _rings(geometry):
        # GeoJSON is (lon, lat); H3 wants (lat, lon).
        outer = [(lat, lon) for lon, lat in polygon[0]]
        holes = [[(lat, lon) for lon, lat in ring] for ring in polygon[1:]]
        shape = h3.LatLngPoly(outer, *holes)
        cells |= set(h3.polygon_to_cells_experimental(shape, resolution, contain="overlap"))
    return cells


async def build(dry_run: bool = False) -> int:
    resolution = settings.h3_resolution

    async with SessionLocal() as session:
        provinces = (
            await session.scalars(
                select(AdminArea).where(AdminArea.level == 1, AdminArea.boundary.is_not(None))
            )
        ).all()
        districts = (
            await session.scalars(
                select(AdminArea).where(AdminArea.level == 2, AdminArea.boundary.is_not(None))
            )
        ).all()

        if not provinces:
            raise SystemExit(
                "No level-1 boundaries in the database. Load them first:\n"
                "  python -m scripts.import_admin_areas <cod-ab-file>"
            )

        log.info("provinces %d, districts %d", len(provinces), len(districts))

        # District first, then province: a district is inside exactly one
        # province, so the coarser pass fills whatever the finer one missed
        # rather than overwriting it.
        owner: dict[str, tuple[str | None, str | None]] = {}
        for province in provinces:
            geometry = province.boundary
            if isinstance(geometry, str):
                geometry = json.loads(geometry)
            for cell in cells_of(geometry, resolution):
                owner[cell] = (province.code, None)

        for district in districts:
            geometry = district.boundary
            if isinstance(geometry, str):
                geometry = json.loads(geometry)
            for cell in cells_of(geometry, resolution):
                adm1 = district.parent_code or owner.get(cell, (None, None))[0]
                owner[cell] = (adm1, district.code)

        log.info("hexagons covering the country: %d", len(owner))

        if dry_run:
            tagged = sum(1 for a1, a2 in owner.values() if a2)
            total_km2 = sum(h3.cell_area(c, unit="km^2") for c in owner)
            log.info("would write %d rows", len(owner))
            log.info("  with a district: %d (%.1f%%)", tagged, tagged / len(owner) * 100)
            log.info("  total area: %.0f km2", total_km2)
            return len(owner)

        written = 0
        batch: list[dict[str, Any]] = []
        for cell, (adm1, adm2) in owner.items():
            lat, lon = h3.cell_to_latlng(cell)
            batch.append(
                {
                    "h3_index": cell,
                    "resolution": resolution,
                    "centroid_lat": lat,
                    "centroid_lon": lon,
                    "area_km2": h3.cell_area(cell, unit="km^2"),
                    "adm1_code": adm1,
                    "adm2_code": adm2,
                    "sources": "grid",
                }
            )
            if len(batch) >= CHUNK:
                written += await _flush(session, batch)
                batch = []
        if batch:
            written += await _flush(session, batch)

        await session.commit()
        log.info("wrote %d hexagons", written)
        return written


async def _flush(session, rows: list[dict[str, Any]]) -> int:
    """Upsert one chunk.

    Only the grid's own columns are updated. A feature builder may already have
    filled elevation or population for these hexagons, and rebuilding the grid
    after a boundary correction must not silently discard that work.
    """
    statement = pg_insert(HexFeature).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["h3_index"],
        set_={
            "resolution": statement.excluded.resolution,
            "centroid_lat": statement.excluded.centroid_lat,
            "centroid_lon": statement.excluded.centroid_lon,
            "area_km2": statement.excluded.area_km2,
            "adm1_code": statement.excluded.adm1_code,
            "adm2_code": statement.excluded.adm2_code,
        },
    )
    await session.execute(statement)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count and measure the grid without writing anything.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(build(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
