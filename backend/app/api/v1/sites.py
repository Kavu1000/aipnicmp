from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.tile import CandidateSite

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("")
async def list_candidate_sites(
    limit: int = Query(default=50, ge=1, le=500),
    province: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The ranked tower-site list — the output operators and the ministry act on.

    Each entry carries ``recommendation`` because the distinction between "no
    tower reaches here" and "a tower reaches here weakly" is the difference
    between a new site and an upgrade, and therefore between two very different
    budget lines.
    """
    query = select(CandidateSite).order_by(CandidateSite.rank.asc().nullslast())
    if province:
        query = query.where(CandidateSite.province == province)

    sites = (await session.scalars(query.limit(limit))).all()

    return {
        "count": len(sites),
        "sites": [
            {
                "id": site.id,
                "rank": site.rank,
                "lat": site.lat,
                "lon": site.lon,
                "score": site.score,
                "population_covered": site.population_covered,
                "unserved_population": site.unserved_population,
                "tiles_improved": site.tiles_improved,
                "recommendation": site.recommendation,
                "has_grid_power": site.has_grid_power,
                "province": site.province,
                "district": site.district,
                "model_version": site.model_version,
            }
            for site in sites
        ],
    }
