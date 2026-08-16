"""What must be on the schedule, and what a missing entry costs.

Everything the platform refreshes on its own runs from here. Nothing raises an
alarm when a beat entry is absent — the work simply never happens, and the only
symptom is a map that is quietly out of date. That has already happened twice:
once when beat shared the worker's health check and never started, and once
when cell placement was left as a script somebody had to remember to run.
"""

from __future__ import annotations

from app.workers.celery_app import celery_app


def _schedule() -> dict:
    return celery_app.conf.beat_schedule


def test_the_cell_layer_refreshes_without_anyone_running_a_script():
    """A route driven today must appear without a person remembering.

    Before this entry existed, sixty-four hexagons of measured coverage sat on
    the map with no cells beside them, twenty-four of which qualified and had
    simply never been written.
    """
    entry = _schedule().get("estimate-cell-sites")
    assert entry is not None, "cell placement is only as fresh as its schedule"
    assert entry["task"] == "app.workers.tasks.estimate_cell_sites_task"


def test_cell_placement_outlives_the_global_expiry():
    """The default expiry suits the minute tick and would discard this one.

    `task_default_expires` is 120 s, which is right for work redone every
    minute. This runs every two, so a worker busy when it fires would drop the
    run under the default and leave the layer stale with nothing in the log.
    """
    entry = _schedule()["estimate-cell-sites"]
    expires = entry["options"]["expires"]
    assert expires > celery_app.conf.task_default_expires
    # At least one whole cycle of grace, so a single slow pass costs a run
    # rather than the run after it as well.
    assert expires >= entry["schedule"].total_seconds()


def test_cell_placement_keeps_pace_with_the_hexagons():
    """A mast heard on a drive should not wait an hour beside a hexagon that
    updated within a minute.

    Placement is not what was slow — a pass over the current fleet takes under
    a second — so the cadence is what somebody driving actually feels, and it
    is pinned here rather than left to drift back to something restful.
    """
    cadence = _schedule()["estimate-cell-sites"]["schedule"].total_seconds()
    assert cadence <= 300, "cell placement should be minutes behind, not hours"


def test_the_schedule_still_carries_the_work_it_used_to():
    """Guards the entries a careless edit to this dict would take with it."""
    assert set(_schedule()) >= {
        "rebuild-tiles",
        "rebuild-tiles-full",
        "estimate-cell-sites",
    }


def test_every_scheduled_task_actually_exists():
    """A typo in a task name fails silently, at 03:10, in a container.

    Beat sends whatever string it is given; an unregistered name is rejected by
    the worker and the schedule goes on looking correct forever.
    """
    import app.workers.tasks  # noqa: F401  (registers the tasks)

    for name, entry in _schedule().items():
        assert entry["task"] in celery_app.tasks, f"{name} points at no such task"
