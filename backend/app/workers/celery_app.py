"""Celery application (Layer 2's job queue).

Aggregation and model retraining run here rather than in the request path: an
upload from a phone with a brief coverage window must return quickly, and the
heavy work is idempotent, so deferring it costs nothing.
"""

from __future__ import annotations

from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "ai_pnicmp",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Vientiane",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # A minute-scale task must not pile up behind a slow run. If the queue is
    # already late the work is stale anyway, and the next tick redoes it.
    task_default_expires=120,
    beat_schedule={
        # Incremental: only the hexagons that gained a measurement, rebuilt
        # from their full history. Usually a no-op, which is what makes a
        # one-minute cadence affordable.
        "rebuild-tiles": {
            "task": "app.workers.tasks.rebuild_tiles_task",
            "schedule": timedelta(minutes=1),
            "options": {"expires": 120},
        },
        # Full: the only pass that removes tiles whose measurements are gone,
        # and the safety net if an incremental run is ever missed.
        "rebuild-tiles-full": {
            "task": "app.workers.tasks.rebuild_all_tiles_task",
            "schedule": crontab(hour=3, minute=10),
        },
        # Where each cell was heard, re-derived from the whole history.
        #
        # Every two minutes, because the work is not what made it slow. A full
        # pass over the current fleet takes 0.7 s — about one per cent of a
        # worker minute — while the hourly schedule it replaced meant a mast
        # heard on a drive could sit unplaced for fifty-nine minutes beside
        # hexagons that had updated within one.
        #
        # Two rather than one, offset from the tile tick, so a pass that grows
        # slower than expected has a whole cycle of headroom before it starts
        # overlapping itself. The cost per cell is quadratic in how often that
        # cell was heard, so this figure will not stay at 0.7 s: the task logs
        # its own duration, and that log is the thing to watch.
        "estimate-cell-sites": {
            "task": "app.workers.tasks.estimate_cell_sites_task",
            "schedule": timedelta(minutes=2),
            "options": {"expires": 240},
        },
        # Exact GPS fixes aged down to the hexagon they already sit in.
        #
        # 04:00, after the 03:10 full rebuild has finished, so a night's
        # aggregation is never reading rows this is rewriting. Nightly rather
        # than hourly because the window is measured in months and a missed
        # night costs nothing.
        "coarsen-old-fixes": {
            "task": "app.workers.tasks.coarsen_old_fixes_task",
            "schedule": crontab(hour=4, minute=0),
            "options": {"expires": 3600},
        },
    },
)
