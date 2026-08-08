"""Celery application (Layer 2's job queue).

Aggregation and model retraining run here rather than in the request path: an
upload from a phone with a brief coverage window must return quickly, and the
heavy work is idempotent, so deferring it costs nothing.
"""

from __future__ import annotations

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
    beat_schedule={
        "rebuild-tiles-hourly": {
            "task": "app.workers.tasks.rebuild_tiles_task",
            "schedule": crontab(minute=10),
        },
    },
)
