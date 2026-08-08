from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.services.aggregate import rebuild_tiles

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    """A single shared token, deliberately minimal for the pilot.

    Real role separation (public / operator / ministry, proposal 3.5) needs an
    identity provider decision that has not been made yet. Until then this
    endpoint is closed by default: an unset token locks it rather than opening
    it, so a forgotten config cannot expose the rebuild.
    """
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid X-Admin-Token header required",
        )


@router.post("/rebuild-tiles", dependencies=[Depends(require_admin)])
async def rebuild(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Recompute every H3 tile from the stored measurements.

    Safe to run at any time: aggregation is a pure function of the measurement
    table, so a bad run is fixed by fixing the rule and running it again.
    """
    written = await rebuild_tiles(session)
    return {"tiles_written": written, "resolution": settings.h3_resolution}
