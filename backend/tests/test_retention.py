"""Aging exact fixes down to the hexagon they already belong to.

The promise being kept is narrow and worth stating exactly: the platform keeps
enough to publish coverage and stops keeping enough to reconstruct where a
person went. Everything here guards one half of that — either that the route is
really gone, or that the coverage findings really survive.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.measurement import Measurement
from app.services.aggregate import rebuild_tiles
from app.services.geo import h3_centroid, to_h3
from app.services.retention import coarsen_old_fixes, retention_status
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


async def _drive(client, device_key, public_key_b64, *, count=8, prefix="ret"):
    """A short stretch of road: distinct fixes, all inside a few hexagons."""
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(
                record_id=f"rec-{prefix}{i:04d}",
                minutes_ago=120 - i,
                lat=BASE_LAT + i * 0.002,
                lon=BASE_LON + i * 0.002,
            ),
            device_key,
        )
        for i in range(count)
    ]
    response = await client.post(
        "/api/v1/measurements/batch", json=batch(records, batch_id=f"batch-{prefix}")
    )
    assert response.json()["accepted"] == count, response.text


async def test_the_route_is_gone_but_the_hexagon_remains(
    client, session, device_key, public_key_b64
):
    """The whole point, in one test.

    Afterwards every reading still says which hexagon it was in — so the map is
    untouched — and no reading still says where on the road the phone was.
    """
    await _drive(client, device_key, public_key_b64)

    before = (await session.execute(select(Measurement))).scalars().all()
    distinct_fixes_before = {(round(m.lat, 6), round(m.lon, 6)) for m in before}
    hexagons_before = {m.h3_index for m in before}
    assert len(distinct_fixes_before) == len(before), "fixture must have distinct fixes"

    # Old enough to be past any sane window.
    moved = await coarsen_old_fixes(session, older_than_days=0.0001, now=NOW)
    assert moved == len(before)

    after = (await session.execute(select(Measurement))).scalars().all()
    assert {m.h3_index for m in after} == hexagons_before

    # Every surviving coordinate is its own hexagon's centre, and nothing else.
    for row in after:
        lat, lon = h3_centroid(row.h3_index)
        assert (round(row.lat, 9), round(row.lon, 9)) == (round(lat, 9), round(lon, 9))
        assert row.coarsened_at is not None
        # An accuracy figure for a position that is no longer a measurement
        # would be a fiction, and a convincing one.
        assert row.gps_accuracy_m is None

    # The route is unrecoverable: readings that shared a hexagon are now
    # indistinguishable by position.
    distinct_after = {(m.lat, m.lon) for m in after}
    assert len(distinct_after) == len(hexagons_before) < len(distinct_fixes_before)


async def test_the_map_is_unchanged_by_it(client, session, device_key, public_key_b64):
    """Coverage is built from the hexagon index, so nothing published moves."""
    await _drive(client, device_key, public_key_b64, prefix="map")
    await rebuild_tiles(session)

    viewport = {
        "min_lat": BASE_LAT - 0.5, "min_lon": BASE_LON - 0.5,
        "max_lat": BASE_LAT + 0.5, "max_lon": BASE_LON + 0.5,
    }
    before = (await client.get("/api/v1/tiles", params=viewport)).json()["features"]

    await coarsen_old_fixes(session, older_than_days=0.0001, now=NOW)
    await rebuild_tiles(session)

    after = (await client.get("/api/v1/tiles", params=viewport)).json()["features"]
    def published(features: list[dict]) -> list[tuple]:
        return sorted(
            (
                f["properties"]["h3"],
                f["properties"]["colour"],
                f["properties"]["state"],
                f["properties"].get("measurements"),
            )
            for f in features
        )

    assert published(after) == published(before)
    assert published(before), "the fixture must have produced tiles to compare"

    # And a coarsened fix still lands in the hexagon it was counted in.
    for row in (await session.execute(select(Measurement))).scalars().all():
        assert to_h3(row.lat, row.lon, 8) == row.h3_index


async def test_recent_readings_are_left_alone(client, session, device_key, public_key_b64):
    """A window that swallowed today's data would defeat the platform."""
    await _drive(client, device_key, public_key_b64, prefix="new")

    assert await coarsen_old_fixes(session, older_than_days=90, now=NOW) == 0
    rows = (await session.execute(select(Measurement))).scalars().all()
    assert all(row.coarsened_at is None for row in rows)
    assert len({(m.lat, m.lon) for m in rows}) == len(rows)


async def test_running_twice_does_nothing_the_second_time(
    client, session, device_key, public_key_b64
):
    """The sweep runs nightly forever; it must not rewrite the table forever."""
    await _drive(client, device_key, public_key_b64, prefix="idem")

    first = await coarsen_old_fixes(session, older_than_days=0.0001, now=NOW)
    assert first > 0
    later = NOW + timedelta(days=1)
    assert await coarsen_old_fixes(session, older_than_days=0.0001, now=later) == 0

    # And the stamp records the first pass, not the last one to look at it.
    rows = (await session.execute(select(Measurement))).scalars().all()
    assert all(row.coarsened_at.replace(tzinfo=timezone.utc) == NOW for row in rows)


async def test_disabled_by_configuration_keeps_everything(
    client, session, device_key, public_key_b64
):
    """Zero means keep exact fixes — a decision, not an accident."""
    await _drive(client, device_key, public_key_b64, prefix="off")
    assert await coarsen_old_fixes(session, older_than_days=0, now=NOW) == 0
    rows = (await session.execute(select(Measurement))).scalars().all()
    assert all(row.coarsened_at is None for row in rows)


async def test_the_status_answers_what_do_you_keep(
    client, session, device_key, public_key_b64
):
    """So the retention claim can be checked rather than believed."""
    await _drive(client, device_key, public_key_b64, prefix="stat", count=6)

    before = await retention_status(session)
    assert before["measurements"] == 6
    assert before["exact_fix_held"] == 6
    assert before["coarsened_to_hexagon"] == 0
    assert before["oldest_exact_fix"] is not None

    await coarsen_old_fixes(session, older_than_days=0.0001, now=NOW)

    after = await retention_status(session)
    assert after["coarsened_to_hexagon"] == 6
    assert after["exact_fix_held"] == 0
    assert after["due_next_sweep"] == 0
    assert after["oldest_exact_fix"] is None
