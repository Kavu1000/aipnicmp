from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.radio import RadioState
from app.db.session import get_session
from app.services.auth import enforce_scope, operator_scope
from app.models.tile import H3Tile, H3TileOperator
from app.services.areas import area_or_none, tile_column
from app.services.geo import h3_polygon_geojson

router = APIRouter(prefix="/tiles", tags=["map"])

# A viewport request must not become a request for the whole country.
MAX_BBOX_DEGREES = 6.0
MAX_TILES = 20_000


def _feature(tile: H3Tile, *, detailed: bool) -> dict[str, Any]:
    """One hexagon as a GeoJSON feature.

    ``detailed`` is false for tiles resting on very few contributors, and it
    governs *when* rather than *how much*.

    What identifies a person is time. A hexagon is 0.84 km2, so "last measured
    Tuesday 14:32" beside one is a record of where somebody was and when; an
    average signal strength over that hexagon is not, and the colour has
    already disclosed that a phone passed through. Withholding all of it
    together left 98% of the map showing a colour and nothing else, which
    protected nobody further and cost every reader the evidence.

    So the count and the averages are always published. The timestamp, the
    device count and the worst single reading — the fields that place a
    traveller at a moment — wait for enough separate contributors.
    """
    properties: dict[str, Any] = {
        "h3": tile.h3_index,
        # The hexagon's centre. Published with the colour rather than with the
        # detail, because the polygon itself is already in this response — the
        # centre of a shape you have been given is not a new disclosure, and
        # withholding it only stopped the client offering directions to a place
        # it was already drawing.
        "lat": tile.centroid_lat,
        "lon": tile.centroid_lon,
        "colour": tile.colour,
        "state": tile.dominant_state,
        "predicted": tile.is_predicted,
    }
    if tile.is_predicted:
        properties["confidence"] = tile.prediction_confidence
    # Always: how much evidence, and what it averaged to. Neither places
    # anybody at a time.
    properties.update(
        {
            "measurements": tile.measurement_count,
            "avg_rsrp_dbm": tile.avg_rsrp_dbm,
            "avg_download_kbps": tile.avg_download_kbps,
            "avg_latency_ms": tile.avg_latency_ms,
        }
    )
    if detailed:
        properties.update(
            {
                "devices": tile.device_count,
                "worst_state": tile.worst_state,
                "last_measured_at": (
                    tile.last_measured_at.isoformat() if tile.last_measured_at else None
                ),
            }
        )
    else:
        properties["low_confidence"] = True

    return {
        "type": "Feature",
        "geometry": h3_polygon_geojson(tile.h3_index),
        "properties": properties,
    }


def _operator_feature(tile: H3TileOperator, *, detailed: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "h3": tile.h3_index,
        # The hexagon's centre. Published with the colour rather than with the
        # detail, because the polygon itself is already in this response — the
        # centre of a shape you have been given is not a new disclosure, and
        # withholding it only stopped the client offering directions to a place
        # it was already drawing.
        "lat": tile.centroid_lat,
        "lon": tile.centroid_lon,
        "colour": tile.colour,
        "state": tile.dominant_state,
        "predicted": False,
        "operator": tile.operator_name,
    }
    # Same split as above: evidence always, timing only with enough behind it.
    properties.update(
        {
            "measurements": tile.measurement_count,
            "avg_rsrp_dbm": tile.avg_rsrp_dbm,
            "avg_download_kbps": tile.avg_download_kbps,
        }
    )
    if detailed:
        properties.update(
            {
                "devices": tile.device_count,
                "worst_state": tile.worst_state,
                "last_measured_at": (
                    tile.last_measured_at.isoformat() if tile.last_measured_at else None
                ),
            }
        )
    else:
        properties["low_confidence"] = True

    return {
        "type": "Feature",
        "geometry": h3_polygon_geojson(tile.h3_index),
        "properties": properties,
    }


async def _area_filter(
    session: AsyncSession, code: str, *, operator: bool
) -> tuple[Any, dict[str, Any]]:
    """Turn an area code into a WHERE clause and the area's own description.

    The clause is an equality on a column stamped at rebuild time, not a
    geometry test — which is what lets a province filter work on a server with
    no PostGIS, and what keeps it fast enough to run on every request.
    """
    area = await area_or_none(session, code)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such area")

    column = tile_column(area.level, operator=operator)
    describe = {
        "code": area.code,
        "level": area.level,
        "name_en": area.name_en,
        "name_lo": area.name_lo,
    }
    # Level 0 is the country: every tile is in it, so there is nothing to
    # filter on and the size guard below is what protects the request.
    return (column == code if column is not None else None), describe


def _guard_size(count: int, code: str) -> None:
    if count > MAX_TILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{code} holds {count} tiles, more than the {MAX_TILES} this endpoint will "
                "return. Use /areas/{code}/children for a summary by child area, or select a "
                "smaller area."
            ),
        )


@router.get("")
async def get_tiles(
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    area: str | None = Query(
        default=None,
        description=(
            "Restrict to one administrative area. Replaces the bounding box: the area's own "
            "extent is the query, so no viewport is needed."
        ),
    ),
    include_predicted: bool = Query(default=True),
    operator: str | None = Depends(enforce_scope),
    scope: str | None = Depends(operator_scope),
    state: RadioState | None = Query(
        default=None,
        description=(
            "Restrict to one radio state, so a reader can ask where a single "
            "problem is rather than reading five colours at once."
        ),
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Coverage tiles inside a viewport or an administrative area, as GeoJSON.

    Grey is absent by design: a tile with no measurement and no prediction is
    simply not returned, and the map shows its own background. "Not measured"
    is a statement the client renders, not data the server invents.
    """
    bbox = (min_lat, min_lon, max_lat, max_lon)
    has_bbox = all(value is not None for value in bbox)

    if area is None and not has_bbox:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="give either an area code or a complete bounding box",
        )

    model = H3TileOperator if operator else H3Tile
    conditions: list[Any] = []
    described: dict[str, Any] | None = None

    if area is not None:
        clause, described = await _area_filter(session, area, operator=bool(operator))
        if clause is not None:
            conditions.append(clause)
    elif has_bbox:
        if max_lat <= min_lat or max_lon <= min_lon:  # type: ignore[operator]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="empty bounding box"
            )
        if (max_lat - min_lat) > MAX_BBOX_DEGREES or (max_lon - min_lon) > MAX_BBOX_DEGREES:  # type: ignore[operator]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"bounding box must span less than {MAX_BBOX_DEGREES} degrees per side",
            )
        conditions.append(model.centroid_lat.between(min_lat, max_lat))
        conditions.append(model.centroid_lon.between(min_lon, max_lon))

    if operator:
        conditions.append(H3TileOperator.operator_name == operator)
    elif not include_predicted:
        conditions.append(H3Tile.is_predicted.is_(False))

    # A network account sees its own coverage, and the places where nothing at
    # all was heard.
    #
    # Per-operator tiles exist only where that operator was observed, so a
    # strict scope would hide every hexagon with no service — which is the one
    # thing an operator most needs in order to decide where to build, and the
    # finding this platform exists to produce. A dead zone attributes nothing
    # to anybody: it says nobody was there, so it leaks no competitor's
    # coverage. Fetched separately below and merged.

    if state is not None:
        # The median state, which is what the tile is drawn as. Filtering on
        # the worst reading instead would return hexagons the map shows green,
        # and a filter whose results contradict the colours beside them is
        # worse than no filter.
        conditions.append(model.dominant_state == state.value)

    def restrict(query: Select) -> Select:
        return query.where(*conditions) if conditions else query

    if area is not None:
        # Truncating a whole-country request to the first 20,000 hexagons would
        # draw a map that is wrong in a way nobody could see. Refuse instead,
        # and name the endpoint that answers the question properly.
        _guard_size(
            await session.scalar(restrict(select(func.count()).select_from(model))) or 0, area
        )

    tiles = (await session.scalars(restrict(select(model)).limit(MAX_TILES))).all()

    body: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [
            (
                _operator_feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
                if operator
                else _feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
            )
            for tile in tiles
        ],
    }
    # The dead zones a network account is still entitled to see.
    #
    # Only for scoped accounts, and only NO_CELL: an unscoped reader already
    # has the combined map, and any other state would attribute coverage to
    # somebody. Fetched with the same area or viewport conditions, minus the
    # operator ones, so the two halves describe the same ground.
    if scope is not None and state in (None, RadioState.NO_CELL):
        dead = (
            await session.scalars(
                select(H3Tile)
                .where(
                    H3Tile.dominant_state == RadioState.NO_CELL.value,
                    *(
                        [
                            H3Tile.centroid_lat.between(min_lat, max_lat),
                            H3Tile.centroid_lon.between(min_lon, max_lon),
                        ]
                        if has_bbox and area is None
                        else []
                    ),
                )
                .limit(MAX_TILES)
            )
        ).all()
        seen = {feature["properties"].get("h3") for feature in body["features"]}
        body["features"].extend(
            _feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
            for tile in dead
            if tile.h3_index not in seen
        )

    if operator:
        body["operator"] = operator
    if described is not None:
        body["area"] = described
    return body


@router.get("/{h3_index}")
async def get_tile(h3_index: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    tile = await session.scalar(select(H3Tile).where(H3Tile.h3_index == h3_index))
    if tile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tile not measured yet")
    return _feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
