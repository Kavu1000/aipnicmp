"""All five radio states, from a phone's reading to a colour on the map.

The colour is the whole product. A ministry reads it to decide where money
goes, and the five states map onto three very different budget lines — a red
hexagon asks for a tower, an orange one asks for an upgrade. Getting one wrong
does not look like a bug; it looks like a finding.

Each test here sends the raw observations a handset would actually report for
one state, runs the real ingest and aggregation, and checks the colour the map
endpoint publishes. Nothing is asserted against the lookup tables, because the
lookup tables are what could be wrong.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aggregate import rebuild_tiles
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll


async def _colour_for(
    client: AsyncClient,
    session: AsyncSession,
    device_key,
    public_key_b64: str,
    *,
    label: str,
    **radio,
) -> tuple[str, str]:
    """Push readings of one kind through the platform, return (colour, state)."""
    await enroll(client, public_key_b64)

    records = [
        sign_record(
            make_record(
                record_id=f"rec-{label}{index:04d}",
                minutes_ago=30 - index,
                lat=BASE_LAT,
                lon=BASE_LON,
                **radio,
            ),
            device_key,
        )
        for index in range(5)
    ]
    response = await client.post(
        "/api/v1/measurements/batch", json=batch(records, batch_id=f"batch-{label}")
    )
    assert response.json()["accepted"] == 5, response.text

    await rebuild_tiles(session)

    tiles = await client.get(
        "/api/v1/tiles",
        params={
            "min_lat": BASE_LAT - 0.5,
            "min_lon": BASE_LON - 0.5,
            "max_lat": BASE_LAT + 0.5,
            "max_lon": BASE_LON + 0.5,
        },
    )
    features = tiles.json()["features"]
    assert len(features) == 1, features
    properties = features[0]["properties"]
    return properties["colour"], properties["state"]


async def test_good_lte_is_green(client, session, device_key, public_key_b64):
    """Registered on LTE, comfortably above the -110 dBm line."""
    colour, state = await _colour_for(
        client, session, device_key, public_key_b64,
        label="green",
        registered=True, network_type="LTE", cells=6,
        signal={"rsrp_dbm": -85.0, "level": 4},
    )
    assert (colour, state) == ("green", "LTE_GOOD")


async def test_weak_lte_is_yellow(client, session, device_key, public_key_b64):
    """Still LTE, still registered, but below -110 dBm: data works and crawls.

    The boundary itself, not a comfortable margin, because this is the line the
    whole optimisation budget hangs on.
    """
    colour, state = await _colour_for(
        client, session, device_key, public_key_b64,
        label="yello",
        registered=True, network_type="LTE", cells=3,
        signal={"rsrp_dbm": -111.0, "level": 1},
    )
    assert (colour, state) == ("yellow", "LTE_WEAK")


async def test_registered_on_3g_only_is_orange(client, session, device_key, public_key_b64):
    """Calls and SMS work, data does not. A capacity upgrade, not a new site."""
    colour, state = await _colour_for(
        client, session, device_key, public_key_b64,
        label="orang",
        registered=True, network_type="UMTS", cells=4,
        signal={"rsrp_dbm": -95.0, "level": 3},
    )
    assert (colour, state) == ("orange", "REGISTERED_2G_3G")


async def test_cells_visible_but_unregistered_is_red_orange(
    client, session, device_key, public_key_b64
):
    """A tower is within earshot and cannot be attached to.

    Diagnostically the most valuable state on the map: the mast already exists,
    so the remedy is an upgrade or a repeater rather than capital for a new
    site. Recording it as "no network" would ask for a tower that is already
    standing.
    """
    colour, state = await _colour_for(
        client, session, device_key, public_key_b64,
        label="rdorg",
        registered=False, network_type=None, cells=2,
        signal={"rsrp_dbm": -125.0, "level": 0},
    )
    assert (colour, state) == ("red_orange", "CELLS_VISIBLE_UNREGISTERED")


async def test_nothing_on_the_air_is_red(client, session, device_key, public_key_b64):
    """No cell detected at all — the finding that justifies a new tower."""
    colour, state = await _colour_for(
        client, session, device_key, public_key_b64,
        label="red00",
        registered=False, network_type=None, cells=0,
        signal={"rsrp_dbm": None, "level": 0},
    )
    assert (colour, state) == ("red", "NO_CELL")


async def test_the_five_colours_are_all_different(
    client, session, device_key, public_key_b64
):
    """A map that paints two states the same colour cannot be read.

    Checked against the platform's own published palette rather than a list
    repeated here, so the two cannot drift apart.
    """
    from app.core.radio import STATE_COLOUR, RadioState

    colours = [STATE_COLOUR[state].value for state in RadioState]
    assert len(set(colours)) == len(colours) == 5, colours
    # Grey means "not measured" and must never be one of them.
    assert "grey" not in colours
