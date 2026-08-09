from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import RadioState
from app.models.measurement import Measurement
from app.models.tile import H3Tile, H3TileOperator
from app.services.aggregate import median_state, rebuild_tiles, worst_state
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll


def test_median_of_a_uniform_tile():
    counts = {RadioState.LTE_GOOD.value: 10}
    assert median_state(counts) is RadioState.LTE_GOOD


def test_median_ignores_a_single_outlier():
    counts = {RadioState.LTE_GOOD.value: 9, RadioState.NO_CELL.value: 1}
    assert median_state(counts) is RadioState.LTE_GOOD


def test_a_mostly_dead_tile_reads_as_dead():
    counts = {RadioState.NO_CELL.value: 8, RadioState.LTE_GOOD.value: 2}
    assert median_state(counts) is RadioState.NO_CELL


def test_worst_state_surfaces_the_dropout_the_median_hides():
    """"Usually fine, but sometimes nothing at all" is actionable for an
    operator, and the median alone would conceal it."""
    counts = {RadioState.LTE_GOOD.value: 20, RadioState.NO_CELL.value: 1}
    assert median_state(counts) is RadioState.LTE_GOOD
    assert worst_state(counts) is RadioState.NO_CELL


def test_empty_counts_have_no_state():
    assert median_state({}) is None
    assert worst_state({}) is None


async def _upload_journey(client: AsyncClient, device_key, public_key_b64: str) -> None:
    await enroll(client, public_key_b64)
    records = []
    for i in range(6):
        # First half in coverage, second half in a dead zone — the shape of a
        # real drive out of a town.
        dead = i >= 3
        records.append(
            sign_record(
                make_record(
                    record_id=f"rec-agg{i:05d}",
                    minutes_ago=60 - i * 5,
                    lat=BASE_LAT + i * 0.02,
                    registered=not dead,
                    network_type=None if dead else "LTE",
                    cells=0 if dead else 3,
                    signal={"rsrp_dbm": None, "level": 0} if dead else {"rsrp_dbm": -85.0, "level": 4},
                ),
                device_key,
            )
        )
    response = await client.post("/api/v1/measurements/batch", json=batch(records))
    assert response.json()["accepted"] == 6, response.text


async def test_rebuild_produces_tiles_of_both_colours(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _upload_journey(client, device_key, public_key_b64)

    written = await rebuild_tiles(session)
    assert written > 0

    tiles = (await session.scalars(select(H3Tile))).all()
    colours = {tile.colour for tile in tiles}
    assert "green" in colours
    assert "red" in colours
    assert all(tile.is_predicted is False for tile in tiles)
    assert all(tile.measurement_count >= 1 for tile in tiles)


async def test_rebuild_is_idempotent(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Aggregation is a pure function of the measurements, so running it twice
    must not double any count."""
    await _upload_journey(client, device_key, public_key_b64)

    first = await rebuild_tiles(session)
    counts_before = {
        tile.h3_index: tile.measurement_count for tile in (await session.scalars(select(H3Tile))).all()
    }
    second = await rebuild_tiles(session)
    counts_after = {
        tile.h3_index: tile.measurement_count for tile in (await session.scalars(select(H3Tile))).all()
    }

    assert first == second
    assert counts_before == counts_after


async def test_an_incremental_rebuild_agrees_with_a_full_one(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The guarantee that lets aggregation run every minute.

    ``since`` may narrow which hexagons are revisited. It must never narrow
    what they are built from, so the two runs have to be indistinguishable.
    """
    await enroll(client, public_key_b64)

    # A well-measured hexagon: twenty good readings in one place.
    early = [
        sign_record(
            make_record(record_id=f"rec-inc-a{i:04d}", minutes_ago=120 - i, lat=BASE_LAT),
            device_key,
        )
        for i in range(20)
    ]
    assert (await client.post("/api/v1/measurements/batch", json=batch(early, batch_id="batch-inc-a"))).json()["accepted"] == 20
    await rebuild_tiles(session)

    tile = (await session.scalars(select(H3Tile))).one()
    index, before_colour, before_first = tile.h3_index, tile.colour, tile.first_measured_at
    assert tile.measurement_count == 20

    # One dead reading arrives in the same hexagon a moment later.
    boundary = datetime.now(timezone.utc) - timedelta(minutes=5)
    late = [
        sign_record(
            make_record(
                record_id="rec-inc-b0000",
                minutes_ago=1,
                lat=BASE_LAT,
                registered=False,
                network_type=None,
                cells=0,
                signal={"rsrp_dbm": None, "level": 0},
            ),
            device_key,
        )
    ]
    assert (await client.post("/api/v1/measurements/batch", json=batch(late, batch_id="batch-inc-b"))).json()["accepted"] == 1

    await rebuild_tiles(session, since=boundary)

    tile = (await session.scalars(select(H3Tile))).one()
    # The lifetime history, not the slice: this read 1 before the fix.
    assert tile.measurement_count == 21
    assert tile.first_measured_at == before_first
    # Twenty good readings still outvote one dead one.
    assert tile.colour == before_colour
    incremental = {
        c: getattr(tile, c) for c in ("colour", "measurement_count", "dominant_state", "worst_state")
    }

    await rebuild_tiles(session)
    tile = (await session.scalars(select(H3Tile))).one()
    assert tile.h3_index == index
    assert {
        c: getattr(tile, c) for c in ("colour", "measurement_count", "dominant_state", "worst_state")
    } == incremental


async def test_an_incremental_rebuild_leaves_untouched_hexagons_alone(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A quiet hexagon must survive a run that only looked at a busy one —
    the reason the stale-tile cleanup is confined to full rebuilds."""
    await _upload_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)
    before = {t.h3_index: t.measurement_count for t in (await session.scalars(select(H3Tile))).all()}
    assert len(before) > 1

    await rebuild_tiles(session, since=datetime.now(timezone.utc) + timedelta(minutes=1))

    after = {t.h3_index: t.measurement_count for t in (await session.scalars(select(H3Tile))).all()}
    assert after == before


async def test_deleting_the_measurements_takes_their_tiles_off_the_map(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A hexagon with nothing behind it must not keep showing coverage.

    Rebuilding only ever visited hexagons that still had measurements, so
    deleting readings left their tiles in place, unchanged and still coloured.
    That went unnoticed until the simulated pilot data was cleared out and the
    map carried on reporting measured coverage across the country.
    """
    await _upload_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)
    assert (await session.scalars(select(H3Tile))).all()

    await session.execute(delete(Measurement))
    await session.commit()

    await rebuild_tiles(session)
    assert (await session.scalars(select(H3Tile))).all() == []
    assert (await session.scalars(select(H3TileOperator))).all() == []


async def test_a_prediction_survives_a_rebuild_that_finds_no_measurements(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Predicted tiles have no measurements by definition, so the cleanup above
    must not treat them as leftovers and erase the modelled layer."""
    session.add(
        H3Tile(
            h3_index="8a2a1072b59ffff",
            resolution=8,
            centroid_lat=BASE_LAT,
            centroid_lon=BASE_LON,
            colour="amber",
            is_predicted=True,
            prediction_confidence=0.6,
            measurement_count=0,
            device_count=0,
        )
    )
    await session.commit()

    await rebuild_tiles(session)

    surviving = (await session.scalars(select(H3Tile))).all()
    assert [tile.h3_index for tile in surviving] == ["8a2a1072b59ffff"]


async def test_map_endpoint_returns_geojson_hexagons(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _upload_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    response = await client.get(
        "/api/v1/tiles",
        params={"min_lat": BASE_LAT - 1, "min_lon": BASE_LON - 1, "max_lat": BASE_LAT + 1, "max_lon": BASE_LON + 1},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]

    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    # A closed hexagon ring: six vertices plus the repeated first point.
    assert len(feature["geometry"]["coordinates"][0]) == 7


async def test_single_contributor_tiles_publish_colour_but_withhold_detail(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The privacy rule of proposal 2.6, and the deliberate limit on it: a tile
    resting on one traveller still shows its colour, because blanking it would
    erase exactly the remote places this project exists to reveal."""
    await _upload_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    response = await client.get(
        "/api/v1/tiles",
        params={"min_lat": BASE_LAT - 1, "min_lon": BASE_LON - 1, "max_lat": BASE_LAT + 1, "max_lon": BASE_LON + 1},
    )
    properties = [f["properties"] for f in response.json()["features"]]

    assert all(p["colour"] for p in properties)
    assert all(p.get("low_confidence") is True for p in properties)
    assert all("devices" not in p for p in properties)
    assert all("last_measured_at" not in p for p in properties)


async def test_oversized_viewport_is_refused(client: AsyncClient):
    response = await client.get(
        "/api/v1/tiles", params={"min_lat": 13.0, "min_lon": 100.0, "max_lat": 23.0, "max_lon": 108.0}
    )
    assert response.status_code == 400


async def test_admin_rebuild_is_closed_without_a_token(client: AsyncClient):
    response = await client.post("/api/v1/admin/rebuild-tiles")
    assert response.status_code == 401
