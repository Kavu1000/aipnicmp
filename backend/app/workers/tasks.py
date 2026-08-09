from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.tile import H3Tile
from app.services.aggregate import rebuild_tiles
from app.workers.celery_app import celery_app

"""How far back an incremental run reaches beyond the last tile write.

Covers the gap between a measurement's received_at being stamped and its
transaction becoming visible, so a record committed while a rebuild was
running is not skipped by the next one. Rebuilding a hexagon is idempotent,
so overlapping is free; missing one is not.
"""
WATERMARK_OVERLAP = timedelta(minutes=5)


async def _incremental() -> int:
    """Rebuild only the hexagons touched since the last run.

    The watermark is the newest tile write, which makes this self-healing: if
    the worker is down for three hours, the next run finds a three-hour-old
    watermark and picks up everything that arrived meanwhile. Nothing extra is
    persisted to track it, so there is no watermark to drift out of step with
    the tiles it describes.
    """
    async with SessionLocal() as session:
        watermark = await session.scalar(select(func.max(H3Tile.updated_at)))
        if watermark is None:
            # Nothing has ever been aggregated; there is no "since" to speak of.
            return await rebuild_tiles(session)
        return await rebuild_tiles(session, since=watermark - WATERMARK_OVERLAP)


async def _full() -> int:
    async with SessionLocal() as session:
        return await rebuild_tiles(session)


@celery_app.task(name="app.workers.tasks.rebuild_tiles_task")
def rebuild_tiles_task() -> dict[str, int]:
    """Bring the public map up to date with what has arrived.

    Runs every minute. It is cheap because it only revisits hexagons that
    gained a measurement — usually none, in which case it does no work at all.
    Each hexagon it does revisit is rebuilt from its whole history, so this
    produces the same tiles a full rebuild would.
    """
    return {"tiles_written": asyncio.run(_incremental())}


@celery_app.task(name="app.workers.tasks.rebuild_all_tiles_task")
def rebuild_all_tiles_task() -> dict[str, int]:
    """Recompute the whole country from scratch, overnight.

    The incremental pass cannot notice a hexagon whose measurements were
    *removed*, or repair a tile written by code that has since been fixed.
    Only a full pass drops stale tiles, so it is also what takes deleted data
    off the map.

    Overnight because it scans the entire measurement table, and 03:00 in
    Vientiane is when the fewest phones are collecting.
    """
    return {"tiles_written": asyncio.run(_full())}
