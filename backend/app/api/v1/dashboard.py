from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.tile import CandidateSite
from app.services.coverage import (
    collectors,
    coverage_summary,
    known_operators,
    network_catalogue,
    operator_breakdown,
    priority_areas,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Headline coverage, framed by what it would cost to fix.

    Includes how little of the country has been measured. That is not a
    weakness to hide — a pilot that claims national coverage would be
    dismissed on sight, and the honest figure is itself the argument for more
    collectors.
    """
    return await coverage_summary(session)


@router.get("/operators")
async def operators(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Coverage per network, worst first."""
    return {"operators": await operator_breakdown(session)}


@router.get("/priority-areas")
async def priority(
    limit: int = Query(default=25, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Measured dead zones, ranked by severity then by weight of evidence.

    This is not the modelled tower-site ranking of proposal 2.5(3) — that needs
    population and terrain data the pilot does not yet hold. It is the part that
    can be stated from measurements alone, and it is already actionable.
    """
    areas = await priority_areas(session, limit=limit)
    modelled = await session.scalar(select(CandidateSite).limit(1))

    return {
        "count": len(areas),
        "areas": areas,
        # Says plainly which kind of list this is, so a dashboard cannot
        # present measured dead zones as if they were modelled site rankings.
        "source": "measured",
        "modelled_sites_available": modelled is not None,
    }


@router.get("/operator-names")
async def operator_names(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Which networks can be filtered on, and which exist but are unmeasured.

    ``operators`` is the list of values the ``operator`` query parameter
    accepts — networks with data. ``networks`` is every Lao network including
    the ones nobody has measured, so a filter can show them as unmeasured
    rather than imply they do not exist. "Unitel has no coverage here" and
    "nobody has checked Unitel here" are opposite claims.
    """
    return {
        "operators": await known_operators(session),
        "networks": await network_catalogue(session),
    }


@router.get("/collectors")
async def collector_fleet(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Which phones are contributing, and whether their records are landing.

    Carries no position: this is equipment telemetry, not a record of where
    anyone went.
    """
    fleet = await collectors(session)
    return {
        "count": len(fleet),
        "real": sum(1 for d in fleet if not d["is_simulated"]),
        "collectors": fleet,
    }
