from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.tile import H3Tile
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


@router.get("")
async def get_tiles(
    min_lat: float = Query(ge=-90, le=90),
    min_lon: float = Query(ge=-180, le=180),
    max_lat: float = Query(ge=-90, le=90),
    max_lon: float = Query(ge=-180, le=180),
    include_predicted: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Coverage tiles inside a viewport, as GeoJSON.

    Grey is absent by design: a tile with no measurement and no prediction is
    simply not returned, and the map shows its own background. "Not measured"
    is a statement the client renders, not data the server invents.
    """
    if max_lat <= min_lat or max_lon <= min_lon:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty bounding box")
    if (max_lat - min_lat) > MAX_BBOX_DEGREES or (max_lon - min_lon) > MAX_BBOX_DEGREES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"bounding box must span less than {MAX_BBOX_DEGREES} degrees per side",
        )

    query = select(H3Tile).where(
        H3Tile.centroid_lat.between(min_lat, max_lat),
        H3Tile.centroid_lon.between(min_lon, max_lon),
    )
    if not include_predicted:
        query = query.where(H3Tile.is_predicted.is_(False))

    tiles = (await session.scalars(query.limit(MAX_TILES))).all()

    return {
        "type": "FeatureCollection",
        "features": [
            _feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
            for tile in tiles
        ],
    }


@router.get("/{h3_index}")
async def get_tile(h3_index: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    tile = await session.scalar(select(H3Tile).where(H3Tile.h3_index == h3_index))
    if tile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tile not measured yet")
    return _feature(tile, detailed=tile.device_count >= settings.tile_min_devices)
