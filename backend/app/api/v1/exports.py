"""Download endpoints.

Scoped exactly like the map, through the same dependency. An export is the one
place where a scoping mistake is permanent — a file on somebody's disk cannot
be un-shared once the wrong network's coverage is in it — so nothing here
queries without going through ``enforce_scope`` first.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import export
from app.services.auth import enforce_scope

router = APIRouter(prefix="/exports", tags=["exports"])


def _stamp(kind: str, suffix: str) -> str:
    """A filename that says what it is and when, so downloads do not collide.

    A folder of files all called `tiles.csv (3)` is how a reader ends up
    comparing last month's coverage against this month's without noticing.
    """
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"aipnicmp-{kind}-{day}.{suffix}"


def _attach(body: str | bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tiles.geojson")
async def tiles_geojson(
    operator: str | None = Depends(enforce_scope),
    area: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Measured hexagons as polygons, for QGIS and anything else that reads GeoJSON."""
    rows = await export.tile_rows(session, operator=operator, area=area)
    return _attach(
        json.dumps(export.tiles_geojson(rows)),
        "application/geo+json",
        _stamp("hexagons", "geojson"),
    )


@router.get("/tiles.csv")
async def tiles_csv(
    operator: str | None = Depends(enforce_scope),
    area: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await export.tile_rows(session, operator=operator, area=area)
    return _attach(export.tiles_csv(rows), "text/csv", _stamp("hexagons", "csv"))


@router.get("/areas.csv")
async def areas_csv(
    operator: str | None = Depends(enforce_scope),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """One row per province and district: the table a budget is argued from."""
    rows = await export.area_rows(session, operator=operator)
    return _attach(export.areas_csv(rows), "text/csv", _stamp("areas", "csv"))


@router.get("/weak-areas.csv")
async def weak_areas_csv(
    operator: str | None = Depends(enforce_scope),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Weak-4G hexagons ranked by people times decibels short.

    The rows an RF planner can work from: where, how far under, how many people
    and what the ground looks like. It stops short of a remedy, because the
    remedy depends on tilts, azimuths and bands that only the operator holds —
    and on whether the shortfall survives being measured outside a car, which
    the manifest in the bundle explains at length.
    """
    rows = await export.weak_area_rows(session, operator=operator)
    return _attach(export.weak_areas_csv(rows), "text/csv", _stamp("weak-areas", "csv"))


@router.get("/cells.geojson")
async def cells_geojson(
    operator: str | None = Depends(enforce_scope),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Observed cells. Not mast positions — see the manifest in the bundle."""
    rows = await export.cell_rows(session, operator=operator)
    return _attach(
        json.dumps(export.cells_geojson(rows)),
        "application/geo+json",
        _stamp("cells", "geojson"),
    )


@router.get("/bundle.zip")
async def bundle(
    operator: str | None = Depends(enforce_scope),
    area: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Everything above with the manifest, in one archive.

    The recommended download. The individual files exist for someone wiring
    this into a pipeline; a person taking data away should take the caveats
    with it, and the surest way to arrange that is to put them in the same
    file.
    """
    return _attach(
        await export.bundle(session, operator=operator, area=area),
        "application/zip",
        _stamp("export", "zip"),
    )
