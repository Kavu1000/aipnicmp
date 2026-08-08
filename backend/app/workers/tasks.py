from __future__ import annotations

import asyncio

from app.db.session import SessionLocal
from app.services.aggregate import rebuild_tiles
from app.workers.celery_app import celery_app


async def _rebuild() -> int:
    async with SessionLocal() as session:
        return await rebuild_tiles(session)


@celery_app.task(name="app.workers.tasks.rebuild_tiles_task")
def rebuild_tiles_task() -> dict[str, int]:
    """Recompute the public map from the measurement table.

    Runs hourly. The window is a deliberate trade: fresher tiles would mean
    recomputing the whole country far more often than the data changes, and a
    coverage map that is an hour old is still a coverage map.
    """
    written = asyncio.run(_rebuild())
    return {"tiles_written": written}
