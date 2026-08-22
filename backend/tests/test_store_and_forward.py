"""The offline path, end to end.

Proposal 2.3 calls store-and-forward the core of the design, and it is the one
path where a mistake is silent: a record captured in a dead zone is uploaded
hours later from somewhere else entirely, and if the server refuses it the
collector has no way to know and no way to collect it again.

These tests describe a real drive — readings taken deep in the countryside,
carried for four hours, uploaded from a town 150 km away — and pin the things
that would quietly throw them away.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import Measurement
from tests.conftest import make_record, sign_record
from tests.test_ingest_api import batch, enroll

# A stretch of road far from anywhere, and the town the collector reached later.
REMOTE_LAT, REMOTE_LON = 19.8845, 102.1350
TOWN_LAT, TOWN_LON = 17.9757, 102.6331


def _dead_zone_run(count: int = 6) -> list[dict]:
    """Readings taken with no service at all, four hours before the upload."""
    return [
        make_record(
            record_id=f"rec-saf{index:05d}",
            minutes_ago=240 + (count - index) * 2,
            # Moving along a road at about 30 km/h between readings.
            lat=REMOTE_LAT + index * 0.009,
            lon=REMOTE_LON + index * 0.004,
            registered=False,
            network_type=None,
            cells=0,
            signal={"rsrp_dbm": None, "level": 0},
        )
        for index in range(count)
    ]


async def test_a_dead_zone_run_uploaded_from_a_town_is_accepted(
    client: AsyncClient, device_key, public_key_b64: str
):
    """The defining case: captured with no service, uploaded 150 km away.

    The upload position is deliberately nowhere near the readings, because that
    is what store-and-forward looks like from the server's side.
    """
    await enroll(client, public_key_b64)
    records = [sign_record(r, device_key) for r in _dead_zone_run()]

    response = await client.post(
        "/api/v1/measurements/batch",
        json=batch(
            records,
            batch_id="batch-saf00001",
            uploaded_from_lat=TOWN_LAT,
            uploaded_from_lon=TOWN_LON,
        ),
    )

    body = response.json()
    assert body["accepted"] == 6, body
    assert body["rejected"] == []


async def test_the_coordinates_stored_are_the_ones_the_phone_recorded(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Not the upload position, and not rounded away.

    A record signed in a dead zone carries the place it was taken. If anything
    in the chain substituted where the phone happened to be when it finally got
    signal, every dead zone in the country would be filed under the nearest
    town — which is precisely the map this project exists to correct.
    """
    await enroll(client, public_key_b64)
    sent = _dead_zone_run(3)
    records = [sign_record(r, device_key) for r in sent]

    await client.post(
        "/api/v1/measurements/batch",
        json=batch(
            records,
            batch_id="batch-saf00002",
            uploaded_from_lat=TOWN_LAT,
            uploaded_from_lon=TOWN_LON,
        ),
    )

    stored = {
        row.client_record_id: (row.lat, row.lon)
        for row in (await session.scalars(select(Measurement))).all()
    }
    for record in sent:
        assert stored[record["client_record_id"]] == (record["lat"], record["lon"])
        # Nowhere near the town it was uploaded from.
        assert abs(stored[record["client_record_id"]][0] - TOWN_LAT) > 1.0


async def test_the_delay_is_recorded_rather_than_held_against_the_record(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Four hours in a pocket is normal here, and worth keeping visible."""
    await enroll(client, public_key_b64)
    records = [sign_record(r, device_key) for r in _dead_zone_run(2)]

    await client.post(
        "/api/v1/measurements/batch",
        json=batch(records, batch_id="batch-saf00003"),
    )

    delays = [row.upload_delay_s for row in (await session.scalars(select(Measurement))).all()]
    assert all(delay is not None and delay > 4 * 3600 - 600 for delay in delays), delays


async def test_a_week_in_a_dead_zone_still_uploads(
    client: AsyncClient, device_key, public_key_b64: str
):
    """The queue holds 20,000 records — about a week of continuous sampling.

    Anything the phone is willing to keep, the server has to be willing to
    take, or the cap is a promise the two halves disagree about.
    """
    await enroll(client, public_key_b64)
    old = [
        sign_record(
            make_record(
                record_id=f"rec-week{index:04d}",
                minutes_ago=7 * 24 * 60 + index,
                lat=REMOTE_LAT,
                lon=REMOTE_LON,
                registered=False,
                network_type=None,
                cells=0,
                signal={"rsrp_dbm": None, "level": 0},
            ),
            device_key,
        )
        for index in range(3)
    ]

    response = await client.post(
        "/api/v1/measurements/batch", json=batch(old, batch_id="batch-saf00004")
    )
    assert response.json()["accepted"] == 3, response.text


async def test_a_forged_jump_inside_the_run_is_still_caught(
    client: AsyncClient, device_key, public_key_b64: str
):
    """Store-and-forward must not become a hole in the trajectory check.

    A long gap between capture and upload is expected; a reading that could not
    have been reached from the one before it is not, however offline the device
    claims to have been.
    """
    await enroll(client, public_key_b64)
    run = _dead_zone_run(3)
    # Same minute as its neighbour, but 400 km away.
    run.append(
        make_record(
            record_id="rec-saf-forged",
            minutes_ago=240,
            lat=REMOTE_LAT + 3.6,
            lon=REMOTE_LON,
            registered=False,
            network_type=None,
            cells=0,
            signal={"rsrp_dbm": None, "level": 0},
        )
    )
    records = [sign_record(r, device_key) for r in run]

    response = await client.post(
        "/api/v1/measurements/batch", json=batch(records, batch_id="batch-saf00005")
    )
    body = response.json()

    assert body["accepted"] == 3, body
    assert [r["client_record_id"] for r in body["rejected"]] == ["rec-saf-forged"]
    assert body["rejected"][0]["reason"] == "impossible_trajectory"
