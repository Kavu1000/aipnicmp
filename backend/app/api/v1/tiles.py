from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.tile import H3Tile, H3TileOperator
from app.services.areas import area_or_none, tile_column
from app.services.geo import h3_polygon_geojson

router = APIRouter(prefix="/tiles", tags=["map"])

# A viewport request must not become a request for the whole country.
MAX_BBOX_DEGREES = 6.0
MAX_TILES = 20_000


def _feature(tile: H3Tile, *, detailed: bool) -> dict[str, Any]:
    """One hexagon as a GeoJSON feature.

    ``detailed`` is false for tiles resting on very few contributors. The colour
    still shows — suppressing it would blank out exactly the remote places this
    project exists to reveal — but the counts and timestamps that could pin the
    reading to one traveller's journey are withheld.
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
    if detailed:
        properties.update(
            {
                "measurements": tile.measurement_count,
                "devices": tile.device_count,
                "avg_rsrp_dbm": tile.avg_rsrp_dbm,
                "avg_download_kbps": tile.avg_download_kbps,
                "avg_latency_ms": tile.avg_latency_ms,
                "worst_state": tile.worst_state,
                "last_measured_at": tile.last_measured_at.isoformat() if tile.last_measured_at else None,
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
    if detailed:
        properties.update(
            {
                "measurements": tile.measurement_count,
                "devices": tile.device_count,
                "avg_rsrp_dbm": tile.avg_rsrp_dbm,
                "avg_download_kbps": tile.avg_download_kbps,
                "worst_state": tile.worst_state,
                "last_measured_at": tile.last_measured_at.isoformat() if tile.last_measured_at else None,
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
    operator: str | None = Query(
        default=None,
        description="Restrict to one network. Omit for the combined view: can anyone get service here?",
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
