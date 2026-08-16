"""Where the fleet believes each base station stands.

Derived from the platform's own readings rather than a purchased database, so
it sharpens with every drive. Only the cells whose observations were spread
widely enough to constrain a position are published: a mast estimated from
readings taken in one car park is a guess wearing coordinates, and this map is
read by people deciding where to spend money.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.cell import ObservedCell

router = APIRouter(prefix="/cells", tags=["cells"])


@router.get("")
async def observed_cells(session: AsyncSession = Depends(get_session)) -> dict:
    """Placed cells as GeoJSON, with the uncertainty that came with them.

    ``uncertainty_m`` is never smaller than half the spread of the readings
    behind it, so a client can draw the doubt rather than a false point. A
    reader who sees only a dot will believe the dot.
    """
    rows = (
        await session.scalars(
            select(ObservedCell)
            .where(ObservedCell.position_is_reliable.is_(True))
            .order_by(ObservedCell.observations.desc())
        )
    ).all()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [cell.est_lon, cell.est_lat]},
                "properties": {
                    "operator": cell.operator_name,
                    "cell": f"{cell.mcc}-{cell.mnc}-{cell.lac_tac}-{cell.cid}",
                    "observations": cell.observations,
                    "uncertainty_m": cell.uncertainty_m,
                    "spread_m": cell.spread_m,
                    "best_rsrp_dbm": cell.best_rsrp_dbm,
                    "last_seen_at": cell.last_seen_at.isoformat() if cell.last_seen_at else None,
                },
            }
            for cell in rows
        ],
    }
