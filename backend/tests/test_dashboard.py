"""The dashboard's numbers end up in front of a ministry, so they get tests.

The figure most worth guarding is the measured share of the country. Reporting
a pilot as if it covered Lao PDR would discredit the whole platform, and the
mistake would be a rounding decision, not a bug anyone would notice.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import RadioState
from app.services.aggregate import rebuild_tiles
from app.services.coverage import LAO_AREA_KM2, coverage_summary, priority_areas, tile_area_km2
from tests.conftest import BASE_LAT, make_record, sign_record
from tests.test_ingest_api import batch, enroll


def test_a_res_8_hexagon_is_under_a_square_kilometre():
    """If this changes, every area figure on the dashboard changes with it."""
    assert 0.7 < tile_area_km2(8) < 0.8


def test_the_country_area_is_the_published_figure():
    assert LAO_AREA_KM2 == 236_800


async def _seed(client: AsyncClient, device_key, public_key_b64: str, *, count: int = 8) -> None:
    await enroll(client, public_key_b64)
    records = []
    for i in range(count):
        dead = i >= count // 2
        records.append(
            sign_record(
                make_record(
                    record_id=f"rec-dash{i:05d}",
                    minutes_ago=90 - i * 5,
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
    assert response.json()["accepted"] == count, response.text


async def test_summary_reports_area_not_just_tile_counts(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    summary = await coverage_summary(session)

    assert summary["tiles"] > 0
    # A tile count alone invites the reader to assume national coverage.
    assert summary["measured_area_km2"] > 0
    expected = round(summary["tiles"] * tile_area_km2(), 1)
    assert summary["measured_area_km2"] == expected


async def test_the_measured_share_survives_rounding(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """At pilot scale the share is a small fraction of one percent. Rounded to a
    whole percent it would print as 0%, which is both wrong and discouraging."""
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    summary = await coverage_summary(session)
    assert summary["measured_share_pct"] > 0.0
    assert summary["measured_share_pct"] < 1.0


async def test_summary_groups_tiles_by_what_it_would_cost_to_fix(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The project's whole argument: a dead area needs a tower, a weak one needs
    an upgrade, and reporting them as one number throws that away."""
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    summary = await coverage_summary(session)
    actions = summary["by_action"]

    assert set(actions) == {"new_tower", "upgrade", "optimisation", "none"}
    assert actions["new_tower"] > 0  # the dead half of the journey
    assert actions["none"] > 0  # the covered half
    assert sum(actions.values()) == summary["tiles"]

    areas = summary["area_by_action_km2"]
    assert areas["new_tower"] > 0


async def test_summary_reports_bounds_so_the_map_can_frame_itself(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Without this the map opens on an empty country and looks broken."""
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    bounds = (await coverage_summary(session))["bounds"]
    assert bounds is not None
    assert bounds["min_lat"] <= bounds["max_lat"]
    assert bounds["min_lon"] <= bounds["max_lon"]
    assert BASE_LAT - 1 < bounds["min_lat"] < BASE_LAT + 1


async def test_bounds_are_absent_before_anything_is_measured(session: AsyncSession):
    summary = await coverage_summary(session)
    assert summary["bounds"] is None
    assert summary["tiles"] == 0
    assert summary["measured_area_km2"] == 0


async def test_priority_areas_rank_dead_zones_first(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    areas = await priority_areas(session, limit=10)
    assert areas, "a journey through a dead zone must produce priority areas"
    assert areas[0]["state"] == RadioState.NO_CELL.value
    assert areas[0]["action"] == "new_tower"
    assert areas[0]["rank"] == 1
    # Every entry must be somewhere a map can fly to.
    assert all(a["lat"] and a["lon"] for a in areas)


async def test_priority_areas_never_include_good_coverage(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    areas = await priority_areas(session, limit=100)
    assert all(a["state"] != RadioState.LTE_GOOD.value for a in areas)


async def test_priority_endpoint_says_the_list_is_measured_not_modelled(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A dashboard must not present measured dead zones as if a model had
    ranked tower sites — they are different claims with different authority."""
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    response = await client.get("/api/v1/dashboard/priority-areas")
    assert response.status_code == 200

    body = response.json()
    assert body["source"] == "measured"
    assert body["modelled_sites_available"] is False
    assert body["count"] > 0


async def test_operator_breakdown_and_filtered_tiles(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    names = (await client.get("/api/v1/dashboard/operator-names")).json()["operators"]
    assert "LTC" in names

    breakdown = (await client.get("/api/v1/dashboard/operators")).json()["operators"]
    assert breakdown
    ltc = next(row for row in breakdown if row["operator"] == "LTC")
    assert ltc["tiles"] > 0
    assert ltc["area_km2"] > 0
    assert 0 <= ltc["good_pct"] <= 100

    filtered = await client.get(
        "/api/v1/tiles",
        params={
            "min_lat": BASE_LAT - 1,
            "min_lon": 101.5,
            "max_lat": BASE_LAT + 1,
            "max_lon": 102.8,
            "operator": "LTC",
        },
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["operator"] == "LTC"
    assert body["features"]
    assert all(f["properties"]["operator"] == "LTC" for f in body["features"])


async def test_a_dead_zone_is_not_attributed_to_any_operator(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A reading with no network has no operator to blame. Bucketing those into
    'unknown' would put dead zones on some carrier's ledger."""
    await enroll(client, public_key_b64)
    record = sign_record(
        make_record(
            record_id="rec-nooperator1",
            registered=False,
            network_type=None,
            cells=0,
            signal={"rsrp_dbm": None, "level": 0},
            operator={"mcc": None, "mnc": None, "name": None},
        ),
        device_key,
    )
    assert (await client.post("/api/v1/measurements/batch", json=batch([record]))).json()["accepted"] == 1

    await rebuild_tiles(session)
    names = (await client.get("/api/v1/dashboard/operator-names")).json()["operators"]
    assert names == []


async def test_stats_and_dashboard_summary_cannot_disagree(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """They share an implementation precisely so the public map and the operator
    view never quote different figures for the same thing."""
    await _seed(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    stats = (await client.get("/api/v1/stats")).json()
    summary = (await client.get("/api/v1/dashboard/summary")).json()
    assert stats == summary
