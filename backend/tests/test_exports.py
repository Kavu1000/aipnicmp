"""Downloads, and the caveats that have to travel with them.

An export is the one place where a mistake is permanent. A file on somebody's
disk cannot be corrected, un-shared, or annotated later — whatever it says when
it leaves is what it says forever, in a slide deck nobody here will see. So
these tests guard two things: that the scoping holds, and that a reader who has
only the archive still knows what the numbers do not mean.
"""

from __future__ import annotations

import codecs
import csv
import io
import json
import zipfile

from app.services.aggregate import rebuild_tiles
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll


async def _measure(client, session, device_key, public_key_b64, *, count=6):
    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(
                record_id=f"rec-exp{i:04d}",
                minutes_ago=90 - i,
                lat=BASE_LAT + i * 0.01,
                lon=BASE_LON,
            ),
            device_key,
        )
        for i in range(count)
    ]
    assert (
        await client.post(
            "/api/v1/measurements/batch", json=batch(records, batch_id="batch-export")
        )
    ).json()["accepted"] == count
    await rebuild_tiles(session)


async def test_the_bundle_carries_the_manifest_with_the_data(
    client, session, device_key, public_key_b64
):
    """The caveats and the numbers travel in one file or they separate."""
    await _measure(client, session, device_key, public_key_b64)

    response = await client.get("/api/v1/exports/bundle.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(archive.namelist()) == {
        "MANIFEST.txt",
        "tiles.geojson",
        "tiles.csv",
        "areas.csv",
        "cells.geojson",
        "weak-areas.csv",
    }

    manifest = archive.read("MANIFEST.txt").decode()
    # The four things a reader with only this file must not get wrong.
    assert "Absent does not mean no coverage" in manifest
    assert "coverage radius" in manifest
    assert "not where a mast stands" in manifest
    assert "median state" in manifest
    # And enough provenance to tell two exports apart a year later.
    assert "Generated:" in manifest
    assert "Export version:" in manifest
    # The caveat that decides whether any money should move: these readings
    # were taken inside a car, and the car costs more decibels than the median
    # shortfall the file reports.
    assert "inside moving vehicles" in manifest
    assert "before committing money" in manifest


async def test_the_hexagons_carry_geometry_and_a_join_key(
    client, session, device_key, public_key_b64
):
    """GeoJSON so it opens in QGIS; h3_index so it joins to anything else."""
    await _measure(client, session, device_key, public_key_b64)

    body = (await client.get("/api/v1/exports/tiles.geojson")).json()
    assert body["type"] == "FeatureCollection"
    assert body["features"], "the fixture should have produced hexagons"

    for feature in body["features"]:
        assert feature["geometry"]["type"] == "Polygon"
        # A closed ring of seven points: six corners, first repeated last.
        assert len(feature["geometry"]["coordinates"][0]) >= 6
        properties = feature["properties"]
        assert properties["h3_index"]
        assert properties["colour"]
        assert properties["measurements"] >= 1

    csv_response = await client.get("/api/v1/exports/tiles.csv")
    # The byte-order mark Excel needs to read UTF-8 on Windows. Asserted here
    # because it is invisible in every viewer that matters and would be dropped
    # by a well-meaning refactor.
    assert csv_response.content.startswith(codecs.BOM_UTF8)
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert len(rows) == len(body["features"])
    assert "h3_index" in rows[0] and "worst_state" in rows[0]


async def test_an_export_never_carries_a_predicted_hexagon(
    client, session, device_key, public_key_b64
):
    """A modelled tile beside a measured one is indistinguishable in a
    spreadsheet the moment somebody hides a column, and the file outlives the
    conversation that would have explained it."""
    from sqlalchemy import select

    from app.models.tile import H3Tile

    await _measure(client, session, device_key, public_key_b64)

    real = (await session.scalars(select(H3Tile))).all()
    assert real
    invented = H3Tile(
        h3_index="88d8a0c001fffff",
        resolution=8,
        centroid_lat=BASE_LAT + 1.0,
        centroid_lon=BASE_LON + 1.0,
        colour="green",
        dominant_state="LTE_GOOD",
        measurement_count=0,
        device_count=0,
        is_predicted=True,
        prediction_confidence=0.9,
    )
    session.add(invented)
    await session.commit()

    body = (await client.get("/api/v1/exports/tiles.geojson")).json()
    assert invented.h3_index not in {f["properties"]["h3_index"] for f in body["features"]}


async def test_every_export_goes_through_the_scope_dependency():
    """The scoping that matters most, because a file cannot be recalled.

    Asserted against the routes themselves rather than a request, so an
    endpoint added here later without ``enforce_scope`` fails this test instead
    of shipping a download that ignores the operator role — the same omission
    that already happened once on /cells.
    """
    from app.api.v1 import exports
    from app.services.auth import enforce_scope

    routes = [route for route in exports.router.routes if getattr(route, "path", "")]
    assert routes, "the export router should have routes"

    for route in routes:
        dependencies = [
            dependency.call for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        ]
        assert enforce_scope in dependencies, f"{route.path} is not scoped"


async def test_an_operator_account_cannot_export_another_network(
    client, session, device_key, public_key_b64
):
    """Asking for somebody else's network is refused, never quietly swapped.

    A silent substitution would put a file on disk that does not hold what its
    filename says, which is worse than an error.
    """
    import pytest
    from fastapi import HTTPException

    from app.services.auth import enforce_scope

    assert await enforce_scope(operator="Unitel", scope="Unitel") == "Unitel"
    with pytest.raises(HTTPException) as refused:
        await enforce_scope(operator="Lao Telecom", scope="Unitel")
    assert refused.value.status_code == 403


async def test_the_area_table_counts_by_state(client, session, device_key, public_key_b64):
    """The row a budget is argued from, so the columns must be the five states."""
    from sqlalchemy import select, update

    from app.models.area import AdminArea
    from app.models.tile import H3Tile

    await _measure(client, session, device_key, public_key_b64)

    # The test database carries no administrative areas, so the hexagons are
    # stamped here — without a province to belong to there is nothing for this
    # table to group by, and the export would be empty for reasons that have
    # nothing to do with what is under test.
    session.add(
        AdminArea(
            code="LA11", level=1, name_en="Bolikhamxai", name_lo="ບໍລິຄຳໄຊ",
            centroid_lat=BASE_LAT, centroid_lon=BASE_LON,
            min_lat=BASE_LAT - 1, min_lon=BASE_LON - 1,
            max_lat=BASE_LAT + 1, max_lon=BASE_LON + 1,
        )
    )
    await session.execute(update(H3Tile).values(adm1_code="LA11"))
    await session.commit()
    assert (await session.scalars(select(H3Tile))).all()

    areas = await client.get("/api/v1/exports/areas.csv")
    # Every district name in this file is in Lao script, and Excel on Windows
    # renders it as mojibake without the mark.
    assert areas.content.startswith(codecs.BOM_UTF8)
    rows = list(csv.DictReader(io.StringIO(areas.content.decode("utf-8-sig"))))
    assert rows, "a province with measured hexagons should produce a row"
    assert any(ord(c) > 0x0E00 for c in rows[0]["name_lo"] or ""), "Lao name should survive"
    assert set(rows[0]) >= {
        "code", "level", "name_en", "hexagons_measured",
        "good", "weak", "calls_only", "unusable", "no_network",
    }
    for row in rows:
        counted = sum(
            int(row[key]) for key in ("good", "weak", "calls_only", "unusable", "no_network")
        )
        assert counted == int(row["hexagons_measured"]), row


async def test_cells_say_what_they_are_in_the_manifest(
    client, session, device_key, public_key_b64
):
    """The single most misread figure in the platform, in the file that lasts."""
    await _measure(client, session, device_key, public_key_b64)
    body = (await client.get("/api/v1/exports/cells.geojson")).json()
    assert body["type"] == "FeatureCollection"

    archive = zipfile.ZipFile(io.BytesIO((await client.get("/api/v1/exports/bundle.zip")).content))
    geo = json.loads(archive.read("cells.geojson"))
    assert geo["type"] == "FeatureCollection"
    assert "uncertainty_m is the" in archive.read("MANIFEST.txt").decode()


async def test_weak_areas_rank_by_people_times_shortfall(
    client, session, device_key, public_key_b64
):
    """A planner reads the top of this list, so the top has to be the right rows.

    Neither figure alone orders it correctly: a village three decibels under
    matters more than empty ground fifteen under, and the product is what says
    so.
    """
    from sqlalchemy import select, update

    from app.models.features import HexFeature
    from app.models.tile import H3Tile
    from app.services.export import weak_area_rows

    await enroll(client, public_key_b64)

    # Two hexagons far enough apart to stay separate, both weak — and sent as
    # two batches, because five kilometres between consecutive readings inside
    # one upload is exactly what the trajectory check rejects, and rightly.
    async def drive(tag: str, *, lat: float, rsrp: float) -> None:
        records = [
            sign_record(
                make_record(
                    record_id=f"rec-{tag}{i:04d}",
                    minutes_ago=90 - i,
                    lat=lat,
                    lon=BASE_LON,
                    registered=True,
                    network_type="LTE",
                    cells=3,
                    signal={"rsrp_dbm": rsrp, "level": 1},
                ),
                device_key,
            )
            for i in range(3)
        ]
        response = await client.post(
            "/api/v1/measurements/batch", json=batch(records, batch_id=f"batch-{tag}")
        )
        assert response.json()["accepted"] == 3, response.text

    # One barely under the line, one far under.
    await drive("weakA", lat=BASE_LAT, rsrp=-112.0)
    await drive("weakB", lat=BASE_LAT + 0.05, rsrp=-125.0)
    await rebuild_tiles(session)

    tiles = (await session.scalars(select(H3Tile))).all()
    assert len(tiles) == 2
    barely = min(tiles, key=lambda t: abs(t.avg_rsrp_dbm + 112.0))
    deeply = next(t for t in tiles if t.h3_index != barely.h3_index)

    # The barely-weak hexagon is a village; the deeply-weak one is empty.
    session.add_all(
        [
            HexFeature(
                h3_index=barely.h3_index, resolution=8,
                centroid_lat=barely.centroid_lat, centroid_lon=barely.centroid_lon,
                area_km2=0.84, population=2000.0, terrain_ruggedness_m=4.0,
                elevation_mean_m=180.0,
            ),
            HexFeature(
                h3_index=deeply.h3_index, resolution=8,
                centroid_lat=deeply.centroid_lat, centroid_lon=deeply.centroid_lon,
                area_km2=0.84, population=10.0, terrain_ruggedness_m=50.0,
                elevation_mean_m=400.0,
            ),
        ]
    )
    await session.execute(update(H3Tile).values(is_predicted=False))
    await session.commit()

    rows = await weak_area_rows(session)
    assert [row["h3_index"] for row in rows] == [barely.h3_index, deeply.h3_index]
    assert rows[0]["rank"] == 1
    assert rows[0]["shortfall_band"] == "under_5db"
    assert rows[1]["shortfall_band"] == "over_10db"
    # The deeply-weak one is further under and still ranked second, which is
    # the whole point of weighting by population.
    assert rows[1]["shortfall_db"] > rows[0]["shortfall_db"]
    assert rows[0]["people_times_shortfall"] > rows[1]["people_times_shortfall"]


async def test_only_weak_hexagons_appear_in_the_weak_list(
    client, session, device_key, public_key_b64
):
    """A good hexagon in a remediation list sends somebody to a working tower."""
    from app.services.export import weak_area_rows

    await _measure(client, session, device_key, public_key_b64)
    rows = await weak_area_rows(session)
    assert rows == [], "the default fixture is good coverage and must not appear"
