"""Administrative areas: the country, its provinces, districts and villages.

Three endpoints, answering three different questions.

``GET /areas`` walks the hierarchy, and is what a Country → Province → District
→ Village selector reads one level at a time.

``GET /areas/{code}`` returns one area's border and its coverage, which is what
the map draws and outlines when that area is chosen.

``GET /areas/{code}/children`` returns every child *with* its border and its
coverage in one FeatureCollection — the whole point being that a national view
should be 18 shaded provinces, not 300,000 hexagons nobody can read.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.area import LEVEL_NAMES, AdminArea
from app.services.areas import (
    area_or_none,
    area_payload,
    children_of,
    coverage_by_area,
)

router = APIRouter(prefix="/areas", tags=["map"])


@router.get("")
async def list_areas(
    parent: str | None = Query(
        default=None,
        description="Children of this area. Omit for the root — the country itself.",
    ),
    level: int | None = Query(default=None, ge=0, le=3),
    q: str | None = Query(default=None, min_length=2, max_length=80, description="Name search"),
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The hierarchy, without geometry.

    Boundaries are deliberately omitted: a district list is a dropdown, and
    sending several megabytes of polygon to populate one would make the filter
    slower than the map it filters.
    """
    if q:
        query = select(AdminArea).where(AdminArea.name_en.ilike(f"%{q}%"))
        if level is not None:
            query = query.where(AdminArea.level == level)
        areas = (await session.scalars(query.order_by(AdminArea.level, AdminArea.name_en).limit(limit))).all()
    elif level is not None and parent is None:
        areas = (
            await session.scalars(
                select(AdminArea)
                .where(AdminArea.level == level)
                .order_by(AdminArea.name_en)
                .limit(limit)
            )
        ).all()
    else:
        areas = list(await children_of(session, parent))[:limit]

    return {
        "count": len(areas),
        "parent": parent,
        "areas": [area_payload(area, include_boundary=False) for area in areas],
    }


@router.get("/{code}")
async def get_area(
    code: str,
    operator: str | None = Query(
        default=None, description="Restrict the coverage figures to one network."
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """One area's border and what has been measured inside it."""
    area = await area_or_none(session, code)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such area")

    stats = await coverage_by_area(
        session, level=area.level, codes=[code], operator=operator
    )
    # Level 0 has no column to group by, so its figures come back under None.
    coverage = stats.get(code) if area.level else stats.get(None)

    return {
        "area": area_payload(area, include_boundary=True),
        "operator": operator,
        # Null means nothing has been measured here yet — which the client
        # states plainly rather than rendering as zero coverage.
        "coverage": coverage,
    }


@router.get("/{code}/children")
async def area_children(
    code: str,
    operator: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Every child area, with geometry and coverage, as one FeatureCollection.

    This is the choropleth the map shows when zoomed out. A village published
    as a point rather than a polygon is emitted as a Point feature, carrying
    the radius the platform used — so the client can draw a circle and say what
    it is, instead of a border that was never surveyed.
    """
    parent = await area_or_none(session, code)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such area")

    children = await children_of(session, code)
    if not children:
        return {"type": "FeatureCollection", "parent": code, "level": None, "features": []}

    level = children[0].level
    stats = await coverage_by_area(
        session, level=level, codes=[child.code for child in children], operator=operator
    )

    features = []
    for child in children:
        coverage = stats.get(child.code)
        properties = area_payload(child, include_boundary=False)
        properties["coverage"] = coverage
        # Grey until measured, so an unvisited district is visibly unvisited
        # rather than quietly shaded like a measured one.
        properties["colour"] = (coverage or {}).get("colour", "grey")

        # How much of the area the colour actually rests on.
        #
        # Sent flat, and alongside the colour, because the two belong together:
        # a district with one hexagon in it has a colour, and painting it as
        # confidently as a district with four hundred says something the
        # measurements do not. One reading in Sisattanak covers 3% of it. The
        # client shades by this, so thin evidence looks thin.
        properties["measured_share_pct"] = (
            round(coverage["measured_area_km2"] / child.area_km2 * 100, 3)
            if coverage and child.area_km2
            else 0.0
        )

        geometry = child.boundary or {
            "type": "Point",
            "coordinates": [child.centroid_lon, child.centroid_lat],
        }
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})

    return {
        "type": "FeatureCollection",
        "parent": code,
        "level": level,
        "operator": operator,
        "level_name": LEVEL_NAMES.get(level),
        "features": features,
    }
