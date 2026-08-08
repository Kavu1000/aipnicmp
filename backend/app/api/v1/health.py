from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.device import Device
from app.models.measurement import Measurement
from app.models.tile import H3Tile

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}


@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Confirms the database answers and that PostGIS is actually installed —
    a missing extension otherwise surfaces much later, during a migration."""
    await session.execute(text("SELECT 1"))
    postgis = await session.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
    )
    return {"status": "ok", "postgis": postgis or "not installed"}


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Headline numbers for the dashboard and for demonstrating the pilot."""
    measurements = await session.scalar(select(func.count()).select_from(Measurement))
    devices = await session.scalar(select(func.count()).select_from(Device))
    tiles = await session.scalar(select(func.count()).select_from(H3Tile))
    no_service = await session.scalar(
        select(func.count()).select_from(Measurement).where(Measurement.radio_state == "NO_CELL")
    )
    latest = await session.scalar(select(func.max(Measurement.captured_at)))

    return {
        "measurements": measurements or 0,
        "devices": devices or 0,
        "tiles": tiles or 0,
        "no_service_measurements": no_service or 0,
        "latest_measurement_at": latest.isoformat() if latest else None,
        "h3_resolution": settings.h3_resolution,
    }
