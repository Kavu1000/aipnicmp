"""The public preview: what a stranger sees before signing in.

Everything on this router answers with country-wide aggregates only — never
a device count, never a field that resolves to one person's movement. The
reasoning for each cut is in ``_public_feature`` and in
``docs/decisions.md``.

Deliberately its own router rather than a flag threaded through the signed-in
one. ``router.py`` keeps its allowlist model — closed unless explicitly
opened — and this file is where "explicitly opened to a stranger" lives, in
one place, so that question never has to be answered by reading a dozen
scattered ``if user is None`` checks.

**Per-network coverage is public here, on record.** An earlier version of
this router refused an ``operator`` parameter outright, on the reasoning that
a network's own coverage quality is that company's competitive information.
The platform's owner decided otherwise: every network's coverage, exactly as
measured, is part of what this platform publishes — see decision 26 in
``docs/decisions.md``. What stays gated behind
sign-in is not the per-network *map* but the per-network *operations* data:
mast positions, the collector fleet, device counts, and anything else that
could place a person rather than describe a place.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_read_session
from app.models.area import AdminArea
from app.models.tile import H3Tile, H3TileOperator
from app.services.areas import area_or_none, area_payload, children_of, coverage_by_area
from app.services.coverage import coverage_summary, network_catalogue
from app.services.geo import h3_polygon_geojson

router = APIRouter(prefix="/public", tags=["public"])

# Narrower than the signed-in /tiles endpoint's 6.0 degrees. The data behind
# both is identical; what differs is that a signed-in request comes from an
# account that can be rate-limited or revoked, and an anonymous one cannot.
MAX_BBOX_DEGREES = 3.0
MAX_FEATURES = 4000
CACHE_SECONDS = 60

# Viewports answered recently, kept for as long as this router already tells
# browsers an answer stays current.
#
# The map is a handful of hot viewports — the capital, whichever province is
# in the news — asked for by every visitor, and the query behind one takes
# under a millisecond to run and closer to a second to reach. Holding the
# built response removes that round trip entirely for the second visitor
# onward, and for the same visitor reloading the page.
#
# Not Redis: this is one small dict per process, correct at any number of
# processes because a stale entry can only be CACHE_SECONDS out of date, and
# the tiles behind it are rebuilt by a scheduled aggregation run, not
# continuously. Adding a shared cache would add a service to the deployment
# to save nothing this does not already save.
_TILE_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_TILE_CACHE_MAX = 256


def _cache_key(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, operator: str | None
) -> tuple[Any, ...]:
    # Rounded so that two viewports differing in the seventh decimal — a
    # millimetre on the ground — are the one question they actually are.
    return (round(min_lat, 4), round(min_lon, 4), round(max_lat, 4), round(max_lon, 4), operator)


def _closed() -> HTTPException:
    # 404, not 403. A 403 confirms the router exists and is merely refusing;
    # whether the preview is on at all is nobody's business but this
    # server's, and PUBLIC_PREVIEW_ENABLED=false is meant to make it
    # disappear, not visibly lock a door.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def _require_enabled() -> None:
    if not settings.public_preview_enabled:
        raise _closed()


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"


def _public_feature(tile: H3Tile) -> dict[str, Any]:
    """One hexagon, stripped to what a stranger may see.

    Not ``tiles._feature`` with a third boolean: a flag on that function is
    exactly the shape a future edit would use to start handing the public
    ``device_count`` or ``last_measured_at`` by accident. A hexagon plus a
    moment is a record of where somebody was and when; nothing below is.
    """
    return {
        "type": "Feature",
        "geometry": h3_polygon_geojson(tile.h3_index),
        "properties": {
            "h3_index": tile.h3_index,
            "dominant_state": tile.dominant_state,
            "colour": tile.colour,
            "is_predicted": tile.is_predicted,
            "measured": not tile.is_predicted,
            # The tile's own rebuild timestamp, shared by every hexagon in the
            # same aggregation run — not last_measured_at, which is the
            # moment a particular phone was last there.
            "updated_at": tile.updated_at.isoformat() if tile.updated_at else None,
        },
    }


def _public_operator_feature(tile: H3TileOperator) -> dict[str, Any]:
    """One hexagon of one network's own coverage, same shape as
    ``_public_feature``.

    Always ``is_predicted: False`` — the Layer 4 model, once it exists,
    predicts the combined map only, never one company's network in
    isolation, so a per-operator tile is measured or it does not exist.
    """
    return {
        "type": "Feature",
        "geometry": h3_polygon_geojson(tile.h3_index),
        "properties": {
            "h3_index": tile.h3_index,
            "dominant_state": tile.dominant_state,
            "colour": tile.colour,
            "is_predicted": False,
            "measured": True,
            "updated_at": tile.updated_at.isoformat() if tile.updated_at else None,
        },
    }


@router.get("/networks")
async def public_networks(
    response: Response, session: AsyncSession = Depends(get_read_session)
) -> dict[str, Any]:
    """Every Lao network, measured or not — which names ``/tiles``'s
    ``operator`` parameter accepts.

    Which companies operate in Laos is public knowledge regardless of this
    platform; listing the ones nobody has measured yet, rather than omitting
    them, says "no collector carries that SIM" instead of implying "no
    coverage" — the same distinction ``dashboard/operator-names`` draws for
    signed-in readers.
    """
    _require_enabled()
    _cache(response)
    return {"networks": await network_catalogue(session)}


@router.get("/summary")
async def public_summary(
    response: Response, session: AsyncSession = Depends(get_read_session)
) -> dict[str, Any]:
    """Headline coverage figures — the same ones the sign-in-gated dashboard
    shows, because none of them name a network or a person."""
    _require_enabled()
    _cache(response)
    return await coverage_summary(session)


@router.get("/tiles")
async def public_tiles(
    response: Response,
    min_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    operator: str | None = Query(
        default=None,
        description=(
            "Restrict to one network's own hexagons — see /public/networks for the "
            "accepted values. Omit for the combined, all-network view."
        ),
    ),
    session: AsyncSession = Depends(get_read_session),
) -> dict[str, Any]:
    """Coverage hexagons inside a viewport.

    Combined across every network by default; one network's own coverage
    when ``operator`` is given. Bounding box only — still no ``area``
    shortcut, the one escape hatch the signed-in ``/tiles`` endpoint offers
    that would let a request describe more of the country than this router's
    viewport limit allows.
    """
    _require_enabled()

    if max_lat <= min_lat or max_lon <= min_lon:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty bounding box")
    if (max_lat - min_lat) > MAX_BBOX_DEGREES or (max_lon - min_lon) > MAX_BBOX_DEGREES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"bounding box must span less than {MAX_BBOX_DEGREES} degrees per side, zoom in",
        )

    if operator is not None:
        known = {row["operator"] for row in await network_catalogue(session)}
        if operator not in known:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown network {operator!r}; see /public/networks",
            )

    key = _cache_key(min_lat, min_lon, max_lat, max_lon, operator)
    cached = _TILE_CACHE.get(key)
    if cached is not None and cached[0] > time.monotonic():
        _cache(response)
        return cached[1]

    model: type[H3Tile] | type[H3TileOperator] = H3TileOperator if operator else H3Tile
    conditions: list[Any] = [
        model.centroid_lat.between(min_lat, max_lat),
        model.centroid_lon.between(min_lon, max_lon),
    ]
    if operator is not None:
        conditions.append(H3TileOperator.operator_name == operator)

    tiles = (
        await session.scalars(select(model).where(*conditions).limit(MAX_FEATURES + 1))
    ).all()
    if len(tiles) > MAX_FEATURES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"more than {MAX_FEATURES} hexagons in view, zoom in",
        )

    feature = _public_operator_feature if operator else _public_feature
    body: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [feature(tile) for tile in tiles],  # type: ignore[arg-type]
    }
    if operator is not None:
        body["operator"] = operator

    # Emptied rather than evicted one by one: the entries all expire within a
    # minute of each other anyway, so tracking which is oldest would be
    # bookkeeping in exchange for one extra cache hit.
    if len(_TILE_CACHE) >= _TILE_CACHE_MAX:
        _TILE_CACHE.clear()
    _TILE_CACHE[key] = (time.monotonic() + CACHE_SECONDS, body)

    _cache(response)
    return body


@router.get("/areas")
async def public_areas(
    response: Response,
    level: int | None = Query(default=None, ge=0, le=3),
    session: AsyncSession = Depends(get_read_session),
) -> dict[str, Any]:
    """The administrative hierarchy, without geometry — a dropdown's worth.

    No ``parent`` or ``q`` search, unlike the signed-in ``/areas``: the public
    preview's area picker walks provinces and districts, not a free-text
    search over every village in the country.
    """
    _require_enabled()
    # A bare level (no parent to walk from) means "every area at this level",
    # not "children of the root at this level" — the root's only children are
    # the country itself, at level 0. children_of's parent_code filter would
    # make ?level=1 return nothing, which is the one call this endpoint
    # exists for: "give me the provinces".
    if level is not None:
        areas = list(
            await session.scalars(
                select(AdminArea).where(AdminArea.level == level).order_by(AdminArea.name_en)
            )
        )
    else:
        areas = list(await children_of(session, None))
    _cache(response)
    return {
        "count": len(areas),
        "areas": [area_payload(area, include_boundary=False) for area in areas],
    }


@router.get("/areas/{code}")
async def public_area(
    code: str, response: Response, session: AsyncSession = Depends(get_read_session)
) -> dict[str, Any]:
    """One area's border and its combined-network coverage."""
    _require_enabled()
    area = await area_or_none(session, code)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such area")

    stats = await coverage_by_area(session, level=area.level, codes=[code])
    coverage = stats.get(code) if area.level else stats.get(None)

    _cache(response)
    return {
        "area": area_payload(area, include_boundary=True),
        "coverage": coverage,
    }


@router.get("/areas/{code}/children")
async def public_area_children(
    code: str, response: Response, session: AsyncSession = Depends(get_read_session)
) -> dict[str, Any]:
    """Every child area, with geometry and coverage — the public choropleth."""
    _require_enabled()
    parent = await area_or_none(session, code)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such area")

    children = await children_of(session, code)
    if not children:
        _cache(response)
        return {"type": "FeatureCollection", "parent": code, "level": None, "features": []}

    level = children[0].level
    stats = await coverage_by_area(session, level=level, codes=[child.code for child in children])

    features = []
    for child in children:
        coverage = stats.get(child.code)
        properties = area_payload(child, include_boundary=False)
        properties["coverage"] = coverage
        properties["colour"] = (coverage or {}).get("colour", "grey")
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

    _cache(response)
    return {
        "type": "FeatureCollection",
        "parent": code,
        "level": level,
        "features": features,
    }
