"""One network, one entry on the map.

``getNetworkOperatorName()`` returns whatever the SIM, the network or the
firmware says, and the three disagree. The pilot database showed the cost of
trusting it: 124 tiles filed under "LTC" and 1 under "LAO TELECOM", the same
company appearing twice in the network filter with its coverage split between
the two.

These tests pin the identity to MCC/MNC instead, and pin the cleanup that stops
the old name lingering on the map after the fix.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.operators import NETWORK_NAMES, canonical_operator, normalise_mnc
from app.models.tile import H3TileOperator
from app.services.aggregate import rebuild_tiles
from tests.conftest import BASE_LAT, make_record, sign_record
from tests.test_ingest_api import batch, enroll


def test_the_lao_networks_are_identified_by_plmn():
    """These names are printed on a public map and in operator reports, so a
    wrong entry mislabels a company rather than failing quietly."""
    assert NETWORK_NAMES[("457", "01")] == "Lao Telecom"
    assert NETWORK_NAMES[("457", "02")] == "ETL"
    assert NETWORK_NAMES[("457", "03")] == "Unitel"
    assert NETWORK_NAMES[("457", "08")] == "Tplus"


def test_every_spelling_of_one_network_resolves_to_one_name():
    for reported in ("LTC", "LAO TELECOM", "Lao Telecommunications", "", None):
        assert canonical_operator("457", "01", reported) == "Lao Telecom"


def test_a_single_digit_mnc_is_the_same_network_as_its_padded_form():
    assert canonical_operator("457", "1", "LTC") == canonical_operator("457", "01", "LTC")
    assert normalise_mnc("1") == "01"
    assert normalise_mnc("01") == "01"
    assert normalise_mnc("") is None


def test_an_unknown_network_keeps_its_identity_as_a_code():
    """Obviously a code rather than a company name, and stable enough to group
    on — better than inventing a label for a PLMN nobody has mapped."""
    assert canonical_operator("457", "05", "Something New") == "457-05"


def test_a_network_with_no_plmn_falls_back_to_what_it_called_itself():
    assert canonical_operator(None, None, "  Village WiFi  ") == "Village WiFi"


def test_a_reading_with_no_network_has_no_operator():
    """Bucketing these into "unknown" would put dead zones on a carrier's
    ledger."""
    assert canonical_operator(None, None, None) is None
    assert canonical_operator(None, None, "   ") is None


async def _seed_two_spellings(
    client: AsyncClient, device_key, public_key_b64: str
) -> None:
    """The same SIM, reported under two different names — the pilot's bug."""
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(
                record_id=f"rec-op{i:05d}",
                minutes_ago=60 - i,
                lat=BASE_LAT + i * 0.01,
                operator={
                    "mcc": "457",
                    "mnc": "01",
                    "name": "LTC" if i % 2 else "LAO TELECOM",
                },
            ),
            device_key,
        )
        for i in range(6)
    ]
    response = await client.post("/api/v1/measurements/batch", json=batch(records))
    assert response.json()["accepted"] == 6, response.text


async def test_two_reported_names_for_one_sim_are_one_operator(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _seed_two_spellings(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    names = (await client.get("/api/v1/dashboard/operator-names")).json()["operators"]
    assert names == ["Lao Telecom"]

    breakdown = (await client.get("/api/v1/dashboard/operators")).json()["operators"]
    assert len(breakdown) == 1
    # Split across two names, this operator's coverage was two partial maps.
    assert breakdown[0]["operator"] == "Lao Telecom"
    assert breakdown[0]["tiles"] > 0


async def test_a_renamed_operator_does_not_linger_on_the_map(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Aggregation only ever wrote rows. A tile written under an old name stayed
    on the map for good, and the network filter kept offering it."""
    await _seed_two_spellings(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    stale = H3TileOperator(
        h3_index=(await session.scalars(select(H3TileOperator.h3_index))).first(),
        operator_name="LAO TELECOM",
        centroid_lat=BASE_LAT,
        centroid_lon=102.135,
        colour="green",
        measurement_count=1,
        device_count=1,
    )
    session.add(stale)
    await session.commit()

    assert "LAO TELECOM" in (
        await client.get("/api/v1/dashboard/operator-names")
    ).json()["operators"]

    await rebuild_tiles(session)

    names = (await client.get("/api/v1/dashboard/operator-names")).json()["operators"]
    assert names == ["Lao Telecom"]


async def test_unmeasured_networks_are_listed_as_unmeasured_not_omitted(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A filter listing only the networks with data implies the others have no
    coverage. What it actually means is that no collector carries their SIM."""
    await _seed_two_spellings(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get("/api/v1/dashboard/operator-names")).json()

    # Only the values the operator filter will actually accept.
    assert body["operators"] == ["Lao Telecom"]

    catalogue = {row["operator"]: row for row in body["networks"]}
    assert set(catalogue) == {"Lao Telecom", "ETL", "Unitel", "Tplus"}

    assert catalogue["Lao Telecom"]["measured"] is True
    assert catalogue["Lao Telecom"]["tiles"] > 0

    for name in ("ETL", "Unitel", "Tplus"):
        assert catalogue[name]["measured"] is False
        # Zero tiles, not zero coverage — the distinction the UI has to keep.
        assert catalogue[name]["tiles"] == 0
        assert catalogue[name]["mcc"] == "457"


async def test_an_unrecognised_network_still_appears_in_the_catalogue(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await enroll(client, public_key_b64)
    record = sign_record(
        make_record(
            record_id="rec-unknown0001",
            operator={"mcc": "457", "mnc": "05", "name": "Something New"},
        ),
        device_key,
    )
    assert (
        await client.post("/api/v1/measurements/batch", json=batch([record]))
    ).json()["accepted"] == 1

    await rebuild_tiles(session)
    body = (await client.get("/api/v1/dashboard/operator-names")).json()

    assert "457-05" in body["operators"]
    unknown = next(row for row in body["networks"] if row["operator"] == "457-05")
    assert unknown["measured"] is True


async def test_the_collector_list_names_each_phones_network(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Three of the four Lao networks have no coverage data because no
    collector carries their SIM. Naming what the fleet is actually on turns
    that from a gap in the map into a recruitment list."""
    await _seed_two_spellings(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    fleet = (await client.get("/api/v1/dashboard/collectors")).json()["collectors"]
    assert fleet

    # Both reported spellings were one SIM, so one network — not two.
    assert fleet[0]["networks"] == ["Lao Telecom"]

    # Still no position of any kind: that is what the hexagons exist to hide.
    assert not {"lat", "lon", "h3"} & set(fleet[0])


async def test_a_phone_that_has_not_reported_yet_lists_no_network(
    client: AsyncClient, session: AsyncSession, public_key_b64: str
):
    """Empty means "has not sent a reading with a network attached", which is
    not the same as "has no network"."""
    await enroll(client, public_key_b64)

    fleet = (await client.get("/api/v1/dashboard/collectors")).json()["collectors"]
    assert fleet[0]["networks"] == []


async def test_an_incremental_rebuild_does_not_delete_the_rest_of_the_map(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """An incremental run has deliberately looked at a slice of the
    measurements. Everything outside that slice is missing, not stale."""
    await _seed_two_spellings(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    before = len((await session.scalars(select(H3TileOperator))).all())
    assert before > 1

    from datetime import datetime, timedelta, timezone

    await rebuild_tiles(session, since=datetime.now(timezone.utc) - timedelta(minutes=2))

    after = len((await session.scalars(select(H3TileOperator))).all())
    assert after == before
