from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.auth import deny_operator_accounts, operator_scope
from app.models.tile import CandidateSite
from app.services.coverage import (
    collectors,
    tower_summary,
    coverage_summary,
    known_operators,
    network_catalogue,
    operator_breakdown,
    priority_areas,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", dependencies=[Depends(deny_operator_accounts)])
async def summary(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Headline coverage, framed by what it would cost to fix.

    Includes how little of the country has been measured. That is not a
    weakness to hide — a pilot that claims national coverage would be
    dismissed on sight, and the honest figure is itself the argument for more
    collectors.
    """
    return await coverage_summary(session)


@router.get("/operators")
async def operators(
    scope: str | None = Depends(operator_scope),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Coverage per network, worst first."""
    rows = await operator_breakdown(session)
    # A network account sees its own row. The others are its competitors'
    # coverage, which is the whole reason this scope exists.
    if scope is not None:
        rows = [row for row in rows if row["operator"] == scope]
    return {"operators": rows}


@router.get("/priority-areas", dependencies=[Depends(deny_operator_accounts)])
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
async def operator_names(
    scope: str | None = Depends(operator_scope),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Which networks can be filtered on, and which exist but are unmeasured.

    A network account sees only its own entry: which companies exist in Laos is
    public knowledge, but how much of each network has been measured is not.

    ``operators`` is the list of values the ``operator`` query parameter
    accepts — networks with data. ``networks`` is every Lao network including
    the ones nobody has measured, so a filter can show them as unmeasured
    rather than imply they do not exist. "Unitel has no coverage here" and
    "nobody has checked Unitel here" are opposite claims.
    """
    operators = await known_operators(session)
    networks = await network_catalogue(session)
    if scope is not None:
        operators = [name for name in operators if name == scope]
        networks = [row for row in networks if row["operator"] == scope]
    return {"operators": operators, "networks": networks}


@router.get("/collectors", dependencies=[Depends(deny_operator_accounts)])
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


@router.get("/towers")
async def towers(
    scope: str | None = Depends(operator_scope),
    area: str | None = Query(default=None, description="Province or district code."),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Base stations per operator, for the country or one administrative area."""
    body = await tower_summary(session, area)
    if scope is not None:
        body["operators"] = [row for row in body["operators"] if row["operator"] == scope]
        body["cells"] = sum(row["cells"] for row in body["operators"])
        body["sites"] = sum(row["sites"] for row in body["operators"])
    return body
