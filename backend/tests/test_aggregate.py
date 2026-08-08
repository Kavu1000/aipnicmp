from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import RadioState
from app.models.tile import H3Tile
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
