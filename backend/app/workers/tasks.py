from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.tile import H3Tile
from app.services.aggregate import rebuild_tiles
from app.services.retention import coarsen_old_fixes
from app.workers.celery_app import celery_app
from scripts.estimate_cell_sites import build as estimate_cell_sites

"""How far back an incremental run reaches beyond the last tile write.

Covers the gap between a measurement's received_at being stamped and its
transaction becoming visible, so a record committed while a rebuild was
running is not skipped by the next one. Rebuilding a hexagon is idempotent,
so overlapping is free; missing one is not.
"""
WATERMARK_OVERLAP = timedelta(minutes=5)

log = logging.getLogger(__name__)


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


@celery_app.task(name="app.workers.tasks.estimate_cell_sites_task")
def estimate_cell_sites_task() -> dict[str, int]:
    """Re-place the observed cells from everything heard so far.

    Scheduled because it was not, and the difference was visible on the map:
    the hexagons refresh every minute from the tick above, while the cell
    layer only changed when somebody ran the script by hand. A route driven
    after the last manual run showed sixty-four measured hexagons and not one
    cell — twenty-four of which qualified and were simply never written.

    Every two minutes. This recomputes every cell from its whole history
    rather than only what changed, which sounds expensive and is not: a pass
    over the current fleet takes under a second. The delete and the insert
    share a transaction, so a reader sees the previous set or the new one,
    never an empty map.

    The duration is logged because it will not stay under a second. Finding
    the widest separation between a cell's readings compares every pair, so
    the cost per cell is quadratic in how often that cell was heard. When this
    starts approaching its two-minute window, the fix is to place only the
    cells that gained readings rather than to slow the schedule back down —
    the schedule is what somebody driving actually feels.
    """
    started = time.perf_counter()
    placed = asyncio.run(estimate_cell_sites())
    elapsed = time.perf_counter() - started
    log.info("placed %d cells in %.1f s", placed, elapsed)
    return {"cells": placed, "seconds": round(elapsed, 1)}


async def _coarsen() -> int:
    """Sweep repeatedly, because one pass is capped to keep the lock short."""
    done = 0
    async with SessionLocal() as session:
        while True:
            moved = await coarsen_old_fixes(session)
            done += moved
            if moved == 0:
                return done


@celery_app.task(name="app.workers.tasks.coarsen_old_fixes_task")
def coarsen_old_fixes_task() -> dict[str, int]:
    """Age exact GPS fixes down to the hexagon they already belong to.

    Nightly. A collector's readings are a position every ten seconds while they
    moved, which together is a record of where a person went — and the platform
    publishes hexagons, so keeping the fixes forever promises less than the map
    does. Nothing published changes: tiles are built from the hexagon index, and
    a hexagon's centre is inside that same hexagon.

    Runs after the full tile rebuild rather than before it, so a night's
    aggregation is never working against rows that are being rewritten
    underneath it.
    """
    return {"coarsened": asyncio.run(_coarsen())}
