"""What a hexagon publishes when one person is behind it.

The rule protects against one thing: reconstructing a traveller's journey from
a public map. A hexagon is 0.84 km2, so a hexagon plus a moment is a record of
where somebody was and when. A hexagon plus an average is not.

These pin which side of that line each field falls on, because the fields are
easy to move by accident and the consequence is somebody's movements.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.aggregate import rebuild_tiles
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll

VIEWPORT = {
    "min_lat": BASE_LAT - 0.5, "min_lon": BASE_LON - 0.5,
    "max_lat": BASE_LAT + 0.5, "max_lon": BASE_LON + 0.5,
}


async def _one_collector(client, session, device_key, public_key_b64):
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(record_id=f"rec-priv{i:04d}", minutes_ago=60 - i, lat=BASE_LAT, lon=BASE_LON),
            device_key,
        )
        for i in range(4)
    ]
    assert (
        await client.post(
            "/api/v1/measurements/batch", json=batch(records, batch_id="batch-priv")
        )
    ).json()["accepted"] == 4
    await rebuild_tiles(session)


async def test_a_single_collector_hexagon_never_says_when(
    client, session, device_key, public_key_b64
):
    """The timestamp is the field that locates a person, so it is the one held."""
    await _one_collector(client, session, device_key, public_key_b64)

    features = (await client.get("/api/v1/tiles", params=VIEWPORT)).json()["features"]
    assert features
    for feature in features:
        properties = feature["properties"]
        assert properties["low_confidence"] is True
        # Withheld: these place a traveller at a moment, or count them.
        assert "last_measured_at" not in properties
        assert "devices" not in properties
        assert "worst_state" not in properties
        # Published: the evidence behind the colour, which places nobody.
        assert properties["measurements"] >= 1
        assert "avg_rsrp_dbm" in properties
        # And the finding itself, always.
        assert properties["colour"] and properties["state"]


async def test_enough_collectors_unlock_the_timing(
    client, session, device_key, public_key_b64
):
    """With more than one journey behind it, no reading belongs to anybody."""
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    await _one_collector(client, session, device_key, public_key_b64)

    second = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        second.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    install_id = "install-privacy0000002"
    await client.post(
        "/api/v1/devices/enroll",
        json={"device": {"install_id": install_id}, "public_key": public},
    )
    records = [
        sign_record(
            make_record(
                record_id=f"rec-priv2{i:04d}", minutes_ago=30 - i, lat=BASE_LAT, lon=BASE_LON
            ),
            second,
        )
        for i in range(4)
    ]
    response = await client.post(
        "/api/v1/measurements/batch",
        json={
            "batch_id": "batch-priv2",
            "device": {"install_id": install_id},
            "records": records,
        },
    )
    assert response.json()["accepted"] == 4, response.text

    await rebuild_tiles(session)

    features = (await client.get("/api/v1/tiles", params=VIEWPORT)).json()["features"]
    unlocked = [f["properties"] for f in features if not f["properties"].get("low_confidence")]
    assert unlocked, f"{settings.tile_min_devices} devices should unlock the timing"
    for properties in unlocked:
        assert properties["last_measured_at"]
        assert properties["devices"] >= settings.tile_min_devices
