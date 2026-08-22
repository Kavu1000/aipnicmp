from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.services.auth import require_user
from app.services.coverage import coverage_summary

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


# Gated individually rather than by moving it: it lives beside the health
# checks for historical reasons, but it is coverage data, not liveness. A load
# balancer needs /health; nobody needs the national figures without an account.
@router.get("/stats", dependencies=[Depends(require_user)])
async def stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Headline numbers for the map header.

    Shares an implementation with the dashboard summary so the map and the
    operator view can never quote different figures for the same thing.
    """
    return await coverage_summary(session)
