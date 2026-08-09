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
    },
)
