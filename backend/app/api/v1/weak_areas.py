"""Weak-4G ground, ranked, as shapes the map can draw.

The same rows as the weak-areas export, given geometry so they can be marked
in place rather than read off a spreadsheet beside the map. A planner looking
at a district should be able to see which hexagons are the ones worth arguing
about without exporting anything.

Ranked by population times decibels short — see ``export.weak_area_rows``. What
the map must not do with this is call it a recommendation: these are measured
hexagons ordered by how many people the shortfall reaches, and the remedy
depends on tilts and bands the platform does not hold.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.auth import enforce_scope
from app.services.export import weak_area_rows
from app.services.geo import h3_polygon_geojson

router = APIRouter(prefix="/weak-areas", tags=["weak-areas"])

#: How many to mark by default.
#:
#: All 57 numbered at once is a screenful of digits over the colour it is
#: meant to explain. The top of a ranked list is the part anybody acts on, and
#: the rest stay yellow on the map like they always were.
DEFAULT_LIMIT = 20


@router.get("")
async def weak_areas(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=200),
    area: str | None = Query(default=None, description="Province, district or village code."),
    band: str | None = Query(
        default=None,
        description="under_5db, 5_to_10db or over_10db.",
        pattern="^(under_5db|5_to_10db|over_10db)$",
    ),
    operator: str | None = Depends(enforce_scope),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The highest-ranked weak hexagons, as polygons carrying their rank.

    Ranks are assigned over everything in scope and only then filtered, so a
    number means the same thing whatever is being looked at: choosing a
    district shows its hexagons still carrying their national positions —
    ranks 3, 7 and 12 rather than a fresh 1, 2, 3 that would quietly imply the
    district holds the worst three in the country.
    """
    rows = await weak_area_rows(session, operator=operator)
    matched = [
        row
        for row in rows
        if (not band or row["shortfall_band"] == band)
        and (
            not area
            or area in (row.get("adm1_code"), row.get("adm2_code"), row.get("adm3_code"))
        )
    ]
    return {
        "type": "FeatureCollection",
        # Two totals, because "20 of 60" and "20 of 8" are different situations
        # and a reader who cannot see the difference will assume the first.
        "total": len(rows),
        "matched": len(matched),
        "features": [
            {
                "type": "Feature",
                "geometry": h3_polygon_geojson(row["h3_index"]),
                "properties": row,
            }
            for row in matched[:limit]
        ],
    }
