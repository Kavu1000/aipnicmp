"""What each handset manages to report, and why it belongs on the page.

Not an inventory column. A reading with no signal strength is classified
pessimistically — the platform will not credit coverage it cannot verify — so a
handset that withholds the figure produces more weak hexagons than one that
does not, on identical ground. And a handset that hears few neighbouring cells
starves the estimator that places masts. Both differences reach the findings,
so both belong where somebody reading the findings can see them.
"""

from __future__ import annotations

from app.services.coverage import android_version, reporting_capability
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll


async def test_a_handset_that_withholds_signal_strength_is_visible(
    client, session, device_key, public_key_b64
):
    """The confounder, made countable.

    Half these readings carry no RSRP, which is what an OEM that does not
    expose the metric looks like from here.
    """
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(
                record_id=f"rec-cap{i:04d}",
                minutes_ago=60 - i,
                lat=BASE_LAT + i * 0.001,
                lon=BASE_LON,
                registered=True,
                network_type="LTE",
                cells=4 if i % 2 else 8,
                signal=(
                    {"rsrp_dbm": -95.0, "level": 3}
                    if i % 2
                    else {"rsrp_dbm": None, "level": 3}
                ),
            ),
            device_key,
        )
        for i in range(6)
    ]
    assert (
        await client.post(
            "/api/v1/measurements/batch", json=batch(records, batch_id="batch-cap")
        )
    ).json()["accepted"] == 6

    capability = await reporting_capability(session)
    assert len(capability) == 1
    stats = next(iter(capability.values()))

    assert stats["readings"] == 6
    assert stats["rsrp_pct"] == 50.0
    # Averaged, not summed: the question is what this phone typically hears.
    assert stats["cells_seen"] == 6.0


async def test_the_capability_reaches_the_collectors_view(
    client, session, device_key, public_key_b64
):
    """It has to be on the page beside the device, or it explains nothing."""
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(record_id=f"rec-cap2{i:04d}", minutes_ago=30 - i, lat=BASE_LAT),
            device_key,
        )
        for i in range(3)
    ]
    assert (
        await client.post(
            "/api/v1/measurements/batch", json=batch(records, batch_id="batch-cap2")
        )
    ).json()["accepted"] == 3

    body = (await client.get("/api/v1/dashboard/collectors")).json()
    device = next(d for d in body["collectors"] if d["capability"])
    assert device["capability"]["readings"] == 3
    assert device["capability"]["rsrp_pct"] is not None
    assert "android_version" in device


async def test_an_enrolled_phone_with_no_readings_has_no_capability(
    client, session, public_key_b64
):
    """Absent rather than zero. Nothing is known about a phone that has not
    reported, and 0% would read as a handset that reports nothing."""
    await enroll(client, public_key_b64)

    body = (await client.get("/api/v1/dashboard/collectors")).json()
    assert body["collectors"]
    assert all(d["capability"] is None for d in body["collectors"])


def test_the_android_level_is_shown_as_a_version_people_know():
    """API 35 means nothing to a reader; Android 15 does."""
    assert android_version(34) == "14"
    assert android_version(35) == "15"
    assert android_version(30) == "11"
    assert android_version(None) is None
    # An unmapped level shows its own number rather than a wrong version.
    assert android_version(99) == "99"
