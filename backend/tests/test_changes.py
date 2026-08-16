"""Detecting that a place got worse.

The one finding this platform can make today without extrapolating: 299
measured hexagons cannot support a national prediction, but they can each be
compared against themselves. So the bar here is not accuracy on unseen ground,
it is not crying wolf — a false outage sends somebody to a working tower, and
the second false alarm is the one that gets the whole feature ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.changes import detect_changes
from tests.conftest import BASE_LAT, make_record, sign_record
from tests.test_ingest_api import batch, enroll

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
GOOD = {"registered": True, "network_type": "LTE", "cells": 6,
        "signal": {"rsrp_dbm": -85.0, "level": 4}}
DEAD = {"registered": False, "network_type": None, "cells": 0,
        "signal": {"rsrp_dbm": None, "level": 0}}
WEAK = {"registered": True, "network_type": "LTE", "cells": 3,
        "signal": {"rsrp_dbm": -115.0, "level": 1}}


async def _send(client, device_key, tag, *, minutes, lat, radio, count=4):
    records = [
        sign_record(
            make_record(record_id=f"rec-{tag}{i:04d}", minutes_ago=minutes - i, lat=lat, **radio),
            device_key,
        )
        for i in range(count)
    ]
    response = await client.post(
        "/api/v1/measurements/batch", json=batch(records, batch_id=f"batch-{tag}")
    )
    assert response.json()["accepted"] == count, response.text


async def test_a_hexagon_that_went_dark_is_reported(client, session, device_key, public_key_b64):
    """Green last week, nothing today — the finding worth a phone call."""
    await enroll(client, public_key_b64)
    # Ten days back, then today. The window is seven days.
    await _send(client, device_key, "old", minutes=14400, lat=BASE_LAT, radio=GOOD)
    await _send(client, device_key, "new", minutes=30, lat=BASE_LAT, radio=DEAD)

    found = await detect_changes(session, window_days=7, now=None)
    assert len(found) == 1
    change = found[0]
    assert change["was"] == "LTE_GOOD"
    assert change["is_now"] == "NO_CELL"
    assert change["direction"] == "worse"
    assert change["colour_was"] == "green"
    assert change["colour_now"] == "red"
    # The evidence, so a reader can weigh it rather than take a verdict.
    assert change["readings_before"] == 4
    assert change["readings_after"] == 4


async def test_a_recovery_is_not_reported_as_a_fault(
    client, session, device_key, public_key_b64
):
    """Signed, not absolute: a repaired tower must not look like a broken one."""
    await enroll(client, public_key_b64)
    await _send(client, device_key, "was", minutes=14400, lat=BASE_LAT, radio=DEAD)
    await _send(client, device_key, "now", minutes=30, lat=BASE_LAT, radio=GOOD)

    found = await detect_changes(session, window_days=7)
    assert [item["direction"] for item in found] == ["better"]
    assert found[0]["steps"] == 4


async def test_an_unchanged_place_is_silent(client, session, device_key, public_key_b64):
    """Most hexagons do not change, and reporting them would bury the ones that do."""
    await enroll(client, public_key_b64)
    await _send(client, device_key, "same1", minutes=14400, lat=BASE_LAT, radio=GOOD)
    await _send(client, device_key, "same2", minutes=30, lat=BASE_LAT, radio=GOOD)

    assert await detect_changes(session, window_days=7) == []


async def test_one_reading_either_side_is_not_evidence(
    client, session, device_key, public_key_b64
):
    """A phone on the edge of a hexagon differs from its neighbour for reasons
    that have nothing to do with the network. Two readings must not raise an
    outage."""
    await enroll(client, public_key_b64)
    await _send(client, device_key, "thin1", minutes=14400, lat=BASE_LAT, radio=GOOD, count=1)
    await _send(client, device_key, "thin2", minutes=30, lat=BASE_LAT, radio=DEAD, count=1)

    assert await detect_changes(session, window_days=7) == []


async def test_a_place_visited_once_has_not_changed(
    client, session, device_key, public_key_b64
):
    """Never revisited is a freshness problem, not an outage, and saying
    otherwise would report every first visit as a change."""
    await enroll(client, public_key_b64)
    await _send(client, device_key, "once", minutes=30, lat=BASE_LAT, radio=DEAD)

    assert await detect_changes(session, window_days=7) == []


async def test_the_worst_drops_come_first(client, session, device_key, public_key_b64):
    """A ranked list is only useful if the top of it is where to look."""
    await enroll(client, public_key_b64)
    # One hexagon falls all the way to nothing; another only to weak.
    await _send(client, device_key, "bad1", minutes=14400, lat=BASE_LAT, radio=GOOD)
    await _send(client, device_key, "bad2", minutes=30, lat=BASE_LAT, radio=DEAD)
    await _send(client, device_key, "mild1", minutes=14400, lat=BASE_LAT + 0.05, radio=GOOD)
    await _send(client, device_key, "mild2", minutes=30, lat=BASE_LAT + 0.05, radio=WEAK)

    found = await detect_changes(session, window_days=7)
    assert len(found) == 2
    assert found[0]["is_now"] == "NO_CELL"
    assert found[0]["steps"] > found[1]["steps"]


async def test_the_endpoint_splits_worse_from_better(
    client, session, device_key, public_key_b64
):
    """Two different conversations: one is a fault report, one is good news."""
    await enroll(client, public_key_b64)
    await _send(client, device_key, "e1", minutes=14400, lat=BASE_LAT, radio=GOOD)
    await _send(client, device_key, "e2", minutes=30, lat=BASE_LAT, radio=DEAD)
    await _send(client, device_key, "e3", minutes=14400, lat=BASE_LAT + 0.05, radio=DEAD)
    await _send(client, device_key, "e4", minutes=30, lat=BASE_LAT + 0.05, radio=GOOD)

    body = (await client.get("/api/v1/dashboard/changes")).json()
    assert body["window_days"] == 7
    assert len(body["worse"]) == 1
    assert len(body["better"]) == 1
    assert body["worse"][0]["is_now"] == "NO_CELL"
