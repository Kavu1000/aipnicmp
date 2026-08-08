"""End-to-end tests of the phone-facing API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import CellObservation, Measurement
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record

pytestmark = pytest.mark.asyncio

INSTALL_ID = "install-0123456789abcdef"


async def enroll(client: AsyncClient, public_key_b64: str) -> None:
    response = await client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {
                "install_id": INSTALL_ID,
                "model": "SM-A125F",
                "manufacturer": "samsung",
                "android_api": 34,
                "app_version": "0.1.0",
            },
            "public_key": public_key_b64,
        },
    )
    assert response.status_code == 200, response.text


def batch(records: list[dict], batch_id: str = "batch-00000001", **extra) -> dict:
    return {
        "batch_id": batch_id,
        "device": {"install_id": INSTALL_ID},
        "records": records,
        **extra,
    }


async def test_health(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_enrolment_rejects_a_malformed_key(client: AsyncClient):
    response = await client.post(
        "/api/v1/devices/enroll",
        json={"device": {"install_id": INSTALL_ID}, "public_key": "aGVsbG8gd29ybGQ="},
    )
    assert response.status_code == 422


async def test_enrolment_will_not_rotate_an_existing_key(client: AsyncClient, public_key_b64: str):
    """Otherwise anyone who learned an install id could substitute their own key
    and sign whatever they liked."""
    await enroll(client, public_key_b64)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64

    attacker = Ed25519PrivateKey.generate()
    attacker_pub = base64.b64encode(
        attacker.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()

    response = await client.post(
        "/api/v1/devices/enroll",
        json={"device": {"install_id": INSTALL_ID}, "public_key": attacker_pub},
    )
    assert response.status_code == 409


async def test_unenrolled_device_cannot_upload(client: AsyncClient, device_key):
    response = await client.post(
        "/api/v1/measurements/batch",
        json=batch([sign_record(make_record(), device_key)]),
    )
    assert response.status_code == 401


async def test_upload_stores_measurements_and_cells(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await enroll(client, public_key_b64)

    records = [
        sign_record(
            make_record(record_id=f"rec-{i:08d}", minutes_ago=60 - i * 5, lat=BASE_LAT + i * 0.01),
            device_key,
        )
        for i in range(4)
    ]
    response = await client.post("/api/v1/measurements/batch", json=batch(records))
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["accepted"] == 4
    assert body["rejected"] == []

    stored = (await session.scalars(select(Measurement))).all()
    assert len(stored) == 4
    assert all(m.signature_valid for m in stored)
    assert all(m.h3_index for m in stored)
    assert all(m.radio_state == "LTE_GOOD" for m in stored)

    cells = (await session.scalars(select(CellObservation))).all()
    assert len(cells) == 4 * 3  # one serving plus two neighbours per record


async def test_no_service_reading_survives_the_round_trip(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The proposal's core claim: a place with no signal at all must arrive as
    evidence, classified NO_CELL, not as a gap."""
    await enroll(client, public_key_b64)

    record = sign_record(
        make_record(
            record_id="rec-nosignal",
            registered=False,
            network_type=None,
            cells=0,
            minutes_ago=3 * 24 * 60,
            signal={"rsrp_dbm": None, "level": 0},
        ),
        device_key,
    )
    response = await client.post("/api/v1/measurements/batch", json=batch([record]))
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] == 1

    stored = await session.scalar(select(Measurement).where(Measurement.client_record_id == "rec-nosignal"))
    assert stored is not None
    assert stored.radio_state == "NO_CELL"
    assert stored.upload_delay_s > 3 * 24 * 3600 - 60


async def test_reupload_is_idempotent(client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str):
    """A device that never received our response must be able to retry without
    doubling its own readings."""
    await enroll(client, public_key_b64)
    records = [sign_record(make_record(), device_key)]

    first = await client.post("/api/v1/measurements/batch", json=batch(records))
    second = await client.post("/api/v1/measurements/batch", json=batch(records, batch_id="batch-00000002"))

    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1

    stored = (await session.scalars(select(Measurement))).all()
    assert len(stored) == 1


async def test_good_records_survive_a_batch_containing_a_bad_one(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A device in a remote area may not get another upload window for days, so
    one bad record must not cost it the whole journey."""
    await enroll(client, public_key_b64)

    good = sign_record(make_record(record_id="rec-good-01", minutes_ago=40), device_key)
    unsigned = make_record(record_id="rec-unsigned", minutes_ago=35, lat=BASE_LAT + 0.005)
    out_of_area = sign_record(
        make_record(record_id="rec-faraway", minutes_ago=30, lat=48.85, lon=2.35), device_key
    )
    good_two = sign_record(
        make_record(record_id="rec-good-02", minutes_ago=25, lat=BASE_LAT + 0.01), device_key
    )

    response = await client.post(
        "/api/v1/measurements/batch", json=batch([good, unsigned, out_of_area, good_two])
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["accepted"] == 2
    reasons = {r["client_record_id"]: r["reason"] for r in body["rejected"]}
    assert reasons["rec-unsigned"] == "bad_signature"
    # The out-of-area point also breaks the journey, so either check may claim
    # it first; both are correct rejections.
    assert reasons["rec-faraway"] in {"out_of_area", "impossible_trajectory"}

    stored = {m.client_record_id for m in (await session.scalars(select(Measurement))).all()}
    assert stored == {"rec-good-01", "rec-good-02"}


async def test_a_tampered_record_is_rejected(client: AsyncClient, device_key, public_key_b64: str):
    """Sign a genuine dead-zone reading, then move it to a different village
    before upload — exactly the attack proposal 3.5 describes."""
    await enroll(client, public_key_b64)

    genuine = sign_record(make_record(record_id="rec-moved"), device_key)
    moved = {**genuine, "lat": BASE_LAT + 0.4}

    response = await client.post("/api/v1/measurements/batch", json=batch([moved]))
    assert response.json()["accepted"] == 0
    assert response.json()["rejected"][0]["reason"] == "bad_signature"


async def test_report_endpoint_accepts_a_citizen_report(client: AsyncClient):
    response = await client.post(
        "/api/v1/reports",
        json={
            "lat": BASE_LAT,
            "lon": BASE_LON,
            "category": "no_service",
            "description": "No signal at the school for the past week",
        },
    )
    assert response.status_code == 201
    assert response.json()["h3_index"]


async def test_stats_reports_the_pilot_numbers(
    client: AsyncClient, device_key, public_key_b64: str
):
    await enroll(client, public_key_b64)
    await client.post(
        "/api/v1/measurements/batch",
        json=batch([sign_record(make_record(record_id="rec-stat-01"), device_key)]),
    )

    response = await client.get("/api/v1/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["measurements"] == 1
    assert body["devices"] == 1
