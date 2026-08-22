"""Filtering the map by province, district and village.

The geometry is hand-rolled (``app/services/polygon.py``), so it is tested
directly rather than trusted: a point-in-polygon bug would not crash anything,
it would quietly file a district's hexagons under its neighbour, and the map
would look entirely plausible while being wrong.

The other thing guarded here is the honesty rule the feature rests on. A
village published as a point must never come back looking like a surveyed
border, and an area measured by a single collector must not publish detail that
could identify whoever drove through it.
"""

from __future__ import annotations

import base64
import json
import math

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import AdminArea
from app.models.tile import H3Tile
from app.services.aggregate import rebuild_tiles
from app.services.polygon import (
    ShapeIndex,
    bbox_of,
    centroid_of,
    count_points,
    point_in_shape,
    shape_area_km2,
    shape_of,
    simplify,
)
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
from tests.test_ingest_api import batch, enroll

# The seeded journey runs north from BASE_LAT along one meridian, so the test
# areas are latitude bands: a province containing the lot, split into a
# southern and a northern district.
PROVINCE = "LA-TEST-P"
DISTRICT_SOUTH = "LA-TEST-D1"
DISTRICT_NORTH = "LA-TEST-D2"
VILLAGE = "LA-TEST-V1"

SPLIT_LAT = 19.95


def square(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


def area_row(
    code: str,
    level: int,
    name: str,
    *,
    parent: str | None = None,
    boundary: dict | None = None,
    lat: float = 0.0,
    lon: float = 0.0,
    radius_m: float | None = None,
) -> AdminArea:
    if boundary is not None:
        shape = shape_of(boundary)
        min_lon, min_lat, max_lon, max_lat = bbox_of(shape)
        lon, lat = centroid_of(shape)
    else:
        min_lon = max_lon = lon
        min_lat = max_lat = lat

    return AdminArea(
        code=code,
        level=level,
        name_en=name,
        name_lo=None,
        parent_code=parent,
        centroid_lat=lat,
        centroid_lon=lon,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
        area_km2=shape_area_km2(shape_of(boundary)) if boundary else None,
        boundary=boundary,
        radius_m=radius_m,
        source="test fixture",
    )


async def seed_areas(session: AsyncSession) -> None:
    """A country, one province, two districts, and a village with no polygon."""
    session.add_all(
        [
            area_row("LA-TEST", 0, "Lao PDR (test)", lat=20.0, lon=102.0),
            area_row(
                PROVINCE,
                1,
                "Test Province",
                parent="LA-TEST",
                boundary=square(101.5, 19.5, 102.8, 20.5),
            ),
            area_row(
                DISTRICT_SOUTH,
                2,
                "South District",
                parent=PROVINCE,
                boundary=square(101.5, 19.5, 102.8, SPLIT_LAT),
            ),
            area_row(
                DISTRICT_NORTH,
                2,
                "North District",
                parent=PROVINCE,
                boundary=square(101.5, SPLIT_LAT, 102.8, 20.5),
            ),
            # No polygon: exactly the case Lao village data actually presents.
            area_row(
                VILLAGE,
                3,
                "Test Village",
                parent=DISTRICT_SOUTH,
                lat=BASE_LAT,
                lon=BASE_LON,
                radius_m=3_000.0,
            ),
        ]
    )
    await session.flush()


async def seed_journey(
    client: AsyncClient, device_key: Ed25519PrivateKey, public_key_b64: str, *, count: int = 8
) -> None:
    """The same northbound journey the dashboard tests use, half of it dead."""
    await enroll(client, public_key_b64)
    records = []
    for i in range(count):
        dead = i >= count // 2
        records.append(
            sign_record(
                make_record(
                    record_id=f"rec-area{i:05d}",
                    minutes_ago=90 - i * 5,
                    lat=BASE_LAT + i * 0.02,
                    registered=not dead,
                    network_type=None if dead else "LTE",
                    cells=0 if dead else 3,
                    signal=(
                        {"rsrp_dbm": None, "level": 0}
                        if dead
                        else {"rsrp_dbm": -85.0, "level": 4}
                    ),
                ),
                device_key,
            )
        )
    response = await client.post("/api/v1/measurements/batch", json=batch(records))
    assert response.json()["accepted"] == count, response.text


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def test_a_point_inside_a_hole_is_outside_the_shape():
    """The case a naive even-odd implementation gets wrong, and the reason a
    lake in the middle of a district is not part of that district."""
    shape = [
        [
            [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)],
        ]
    ]
    assert point_in_shape(1.0, 1.0, shape)
    assert not point_in_shape(5.0, 5.0, shape)
    assert not point_in_shape(11.0, 5.0, shape)


def test_a_vertex_on_the_ray_is_not_counted_twice():
    """A point level with a vertex is the classic double-count, and it puts
    points outside shapes they are plainly inside."""
    diamond = [[[(0.0, 0.0), (5.0, 5.0), (10.0, 0.0), (5.0, -5.0), (0.0, 0.0)]]]
    assert point_in_shape(5.0, 0.0, diamond)
    assert not point_in_shape(-1.0, 0.0, diamond)


def test_area_of_a_one_degree_box_is_spherical_not_planar():
    """At 20°N a degree of longitude is about 105 km, not 111. A planar shoelace
    would overstate every province by several percent, and the figure is printed
    next to measured km²."""
    box = shape_of(square(102.0, 19.0, 103.0, 20.0))
    assert 11_000 < shape_area_km2(box) < 12_500


def test_simplify_thins_a_ring_but_keeps_its_shape():
    """A 400-vertex outline drawn at province scale carries detail nobody can
    see. It should lose most of its points and none of its form."""
    circle = [
        [
            (102.0 + 0.5 * math.cos(i / 400 * math.tau), 19.0 + 0.5 * math.sin(i / 400 * math.tau))
            for i in range(400)
        ]
    ]
    circle[0].append(circle[0][0])

    thinned = simplify([circle], 0.001)

    assert count_points(thinned) < count_points([circle]) / 2
    assert thinned[0][0][0] == thinned[0][0][-1], "a ring must stay closed"
    # Still recognisably the same disc, not a triangle.
    assert 0.7 < shape_area_km2(thinned) / shape_area_km2([circle]) <= 1.0


def test_simplify_refuses_to_collapse_a_small_island():
    """Better sent whole than sent as a triangle; the saving would be bytes."""
    island = [[(102.0, 19.0), (102.001, 19.0), (102.001, 19.001), (102.0, 19.001), (102.0, 19.0)]]
    assert simplify([island], 0.5) == [island]


def test_shape_index_finds_the_containing_area():
    index = ShapeIndex(
        [
            (code, shape_of(geometry), bbox_of(shape_of(geometry)))
            for code, geometry in (
                ("south", square(101.5, 19.5, 102.8, 19.95)),
                ("north", square(101.5, 19.95, 102.8, 20.5)),
            )
        ]
    )
    assert index.find(102.0, 19.7) == "south"
    assert index.find(102.0, 20.2) == "north"
    assert index.find(99.0, 19.7) is None


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------


def test_the_importer_reads_the_lowercase_cod_ab_convention(tmp_path):
    """COD-AB ships in two naming conventions and the current Lao release uses
    the lowercase one, where the Lao script lives in ``adm2_name1`` rather than
    a language-suffixed field. Reading only the uppercase form imported the
    whole country nameless."""
    from scripts.import_admin_areas import load_features

    path = tmp_path / "adm2.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "adm2_name": "Park Ou",
                            "adm2_name1": "ມ. ປາກອູ",
                            "adm2_pcode": "LA0604",
                            "adm1_pcode": "LA06",
                        },
                        "geometry": square(102.0, 20.0, 102.5, 20.5),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows, problems = load_features(
        path,
        2,
        simplify_deg=0.001,
        village_radius_m=2000,
        overrides={"name": None, "code": None, "parent": None},
    )

    assert problems == []
    assert len(rows) == 1
    assert rows[0].code == "LA0604"
    assert rows[0].name_en == "Park Ou"
    assert rows[0].name_lo == "ມ. ປາກອູ"
    assert rows[0].parent_code == "LA06"


def test_computed_area_matches_the_published_figure():
    """The importer computes its own km² rather than trusting the source, and
    the two must agree — this is what caught the spherical-vs-planar question.
    A degree box at Lao latitudes is ~11,600 km², not ~12,300."""
    box = shape_of(square(102.0, 19.0, 103.0, 20.0))
    assert abs(shape_area_km2(box) - 11_600) < 600


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


async def test_rebuild_stamps_every_tile_with_its_areas(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    tiles = (await session.scalars(select(H3Tile))).all()
    assert tiles

    assert all(tile.adm1_code == PROVINCE for tile in tiles)
    assert {tile.adm2_code for tile in tiles} == {DISTRICT_SOUTH, DISTRICT_NORTH}

    # The split is at 19.95, and the centroid decides — never the corner.
    for tile in tiles:
        expected = DISTRICT_SOUTH if tile.centroid_lat < SPLIT_LAT else DISTRICT_NORTH
        assert tile.adm2_code == expected


async def test_a_village_point_claims_only_the_hexagons_within_its_radius(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The village sits at the journey's start with a 3 km radius, so the far
    end of the drive must not be filed under it."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    tiles = (await session.scalars(select(H3Tile))).all()
    claimed = [tile for tile in tiles if tile.adm3_code == VILLAGE]

    assert claimed, "the hexagons at the village itself belong to it"
    assert len(claimed) < len(tiles), "a 3 km circle cannot swallow the whole journey"
    assert all(tile.centroid_lat < BASE_LAT + 0.05 for tile in claimed)


async def test_rebuild_works_before_any_boundaries_are_imported(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The platform must be fully usable with no boundary file loaded — it
    simply has no area filter yet."""
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    tiles = (await session.scalars(select(H3Tile))).all()
    assert tiles
    assert all(tile.adm1_code is None and tile.adm2_code is None for tile in tiles)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


async def test_areas_endpoint_walks_the_hierarchy(client: AsyncClient, session: AsyncSession):
    await seed_areas(session)

    root = (await client.get("/api/v1/areas")).json()
    assert [area["code"] for area in root["areas"]] == ["LA-TEST"]

    provinces = (await client.get("/api/v1/areas", params={"parent": "LA-TEST"})).json()
    assert [area["code"] for area in provinces["areas"]] == [PROVINCE]

    districts = (await client.get("/api/v1/areas", params={"parent": PROVINCE})).json()
    assert {area["code"] for area in districts["areas"]} == {DISTRICT_SOUTH, DISTRICT_NORTH}

    # A dropdown does not need polygons, and sending them would make the filter
    # slower than the map it filters.
    assert all("boundary" not in area for area in districts["areas"])


async def test_area_detail_carries_the_border_and_the_coverage(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get(f"/api/v1/areas/{DISTRICT_SOUTH}")).json()

    assert body["area"]["has_boundary"] is True
    assert body["area"]["boundary"]["type"] == "Polygon"
    assert body["coverage"]["tiles"] > 0
    assert 0 <= body["coverage"]["good_pct"] <= 100
    assert body["coverage"]["colour"] != "grey"


async def test_an_areas_state_and_its_colour_cannot_disagree(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A summary showing one state's name beside another state's swatch reads
    as a bug in the data, not in the page."""
    from app.core.radio import STATE_COLOUR, RadioState

    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    for code in ("LA-TEST", PROVINCE, DISTRICT_SOUTH, DISTRICT_NORTH):
        coverage = (await client.get(f"/api/v1/areas/{code}")).json()["coverage"]
        assert coverage["state"] is not None
        assert coverage["colour"] == STATE_COLOUR[RadioState(coverage["state"])].value


async def test_the_country_total_agrees_with_the_districts_inside_it(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The country has no column to group on, so its totals take a different
    path through the same function — and that path once counted every tile
    under a single state, reporting a half-dead country as fully covered."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    country = (await client.get("/api/v1/areas/LA-TEST")).json()["coverage"]
    districts = (await client.get(f"/api/v1/areas/{PROVINCE}/children")).json()["features"]

    combined: dict[str, int] = {}
    for feature in districts:
        for state, count in feature["properties"]["coverage"]["by_state"].items():
            combined[state] = combined.get(state, 0) + count

    assert country["by_state"] == combined
    assert country["tiles"] == sum(combined.values())
    # The seeded journey is half dead, so neither extreme is credible.
    assert 0 < country["good_pct"] < 100
    assert country["unusable_pct"] > 0


async def test_a_village_without_a_polygon_says_so(client: AsyncClient, session: AsyncSession):
    """It must be impossible to mistake a stated radius for a surveyed border."""
    await seed_areas(session)

    body = (await client.get(f"/api/v1/areas/{VILLAGE}")).json()
    assert body["area"]["has_boundary"] is False
    assert body["area"]["radius_m"] == 3_000.0
    assert "boundary" not in body["area"]


async def test_children_endpoint_returns_geometry_and_coverage_together(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """One request per zoom level: a national view is 18 shaded provinces, not
    300,000 hexagons."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get(f"/api/v1/areas/{PROVINCE}/children")).json()

    assert body["type"] == "FeatureCollection"
    assert body["level_name"] == "district"
    assert len(body["features"]) == 2
    for feature in body["features"]:
        assert feature["geometry"]["type"] == "Polygon"
        assert feature["properties"]["colour"] in {
            "green", "yellow", "orange", "red_orange", "red", "grey",
        }
        assert feature["properties"]["coverage"]["tiles"] > 0


async def test_a_barely_measured_area_says_how_barely(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """A district with one hexagon in it has a colour, and painting it as
    confidently as a fully surveyed one claims something the measurements do
    not. The client shades by this, so thin evidence looks thin."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get(f"/api/v1/areas/{PROVINCE}/children")).json()
    south = next(
        f for f in body["features"] if f["properties"]["code"] == DISTRICT_SOUTH
    )

    share = south["properties"]["measured_share_pct"]
    assert 0 < share < 100
    # It must agree with the two figures it is derived from, or the map and the
    # summary panel would tell different stories about the same district.
    coverage = south["properties"]["coverage"]
    expected = coverage["measured_area_km2"] / south["properties"]["area_km2"] * 100
    assert abs(share - expected) < 0.01


async def test_an_unmeasured_area_reports_no_share_rather_than_a_missing_one(
    client: AsyncClient, session: AsyncSession
):
    """Always a number, because the map interpolates opacity from it and a null
    would take the whole layer out."""
    await seed_areas(session)

    body = (await client.get(f"/api/v1/areas/{PROVINCE}/children")).json()
    assert all(f["properties"]["measured_share_pct"] == 0.0 for f in body["features"])


async def test_an_unmeasured_child_is_grey_not_quietly_shaded(
    client: AsyncClient, session: AsyncSession
):
    await seed_areas(session)

    body = (await client.get(f"/api/v1/areas/{PROVINCE}/children")).json()
    assert all(feature["properties"]["colour"] == "grey" for feature in body["features"])
    assert all(feature["properties"]["coverage"] is None for feature in body["features"])


async def test_a_village_child_is_a_point_feature(client: AsyncClient, session: AsyncSession):
    await seed_areas(session)

    body = (await client.get(f"/api/v1/areas/{DISTRICT_SOUTH}/children")).json()
    assert body["level_name"] == "village"
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["has_boundary"] is False
    assert feature["properties"]["radius_m"] == 3_000.0


async def test_a_tile_carries_the_centre_of_its_hexagon(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """So the map can offer directions to a place it is already drawing. The
    polygon is in the same response, so the centre is not a new disclosure —
    and it must be published with the colour rather than the detail, or a
    single-collector tile would lose it exactly where somebody most wants to go
    and look."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get("/api/v1/tiles", params={"area": DISTRICT_SOUTH})).json()
    for feature in body["features"]:
        properties = feature["properties"]
        assert properties["lat"] is not None and properties["lon"] is not None
        # Inside its own hexagon, not merely somewhere in Laos.
        ring = feature["geometry"]["coordinates"][0]
        lons = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        assert min(lons) <= properties["lon"] <= max(lons)
        assert min(lats) <= properties["lat"] <= max(lats)

    # Withheld detail must not take the location with it.
    assert any(f["properties"].get("low_confidence") for f in body["features"])


async def test_tiles_can_be_filtered_to_one_district(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    south = (await client.get("/api/v1/tiles", params={"area": DISTRICT_SOUTH})).json()
    north = (await client.get("/api/v1/tiles", params={"area": DISTRICT_NORTH})).json()
    province = (await client.get("/api/v1/tiles", params={"area": PROVINCE})).json()

    assert south["features"] and north["features"]
    assert south["area"]["name_en"] == "South District"
    assert len(south["features"]) + len(north["features"]) == len(province["features"])

    codes = {feature["properties"]["h3"] for feature in south["features"]}
    assert not codes & {feature["properties"]["h3"] for feature in north["features"]}


async def test_area_and_operator_filters_combine(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """"Can my customers get service in this district" is the operator question,
    and it needs both filters at once."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (
        await client.get(
            "/api/v1/tiles", params={"area": DISTRICT_SOUTH, "operator": "Lao Telecom"}
        )
    ).json()

    assert body["operator"] == "Lao Telecom"
    assert body["features"]
    assert all(
        feature["properties"]["operator"] == "Lao Telecom" for feature in body["features"]
    )


async def test_the_country_needs_no_bounding_box(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """Level 0 has no column to filter on; the request must still work."""
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    body = (await client.get("/api/v1/tiles", params={"area": "LA-TEST"})).json()
    assert body["features"]
    assert body["area"]["level"] == 0


async def test_tiles_still_require_an_area_or_a_bounding_box(client: AsyncClient):
    assert (await client.get("/api/v1/tiles")).status_code == 400


async def test_an_unknown_area_is_a_404_not_an_empty_map(client: AsyncClient):
    """Returning an empty FeatureCollection would say "measured, nothing here"
    about a place that does not exist."""
    assert (await client.get("/api/v1/tiles", params={"area": "NOPE"})).status_code == 404
    assert (await client.get("/api/v1/areas/NOPE")).status_code == 404


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


async def test_one_collector_does_not_publish_an_areas_detail(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    """The same rule a single hexagon follows, and it withholds *time*.

    One collector's journey through a district must not be reconstructable from
    the district's own page, and what would reconstruct it is the timestamp:
    an area plus a moment is a record of where somebody was and when. How many
    readings there were, and what they averaged to, place nobody — and the
    colour has already disclosed that a phone passed through.

    This test used to require the whole detail withheld. That withheld nothing
    further and cost every reader the evidence on 98% of the map, since almost
    every hexagon in the pilot rests on a single collector.
    """
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)

    coverage = (await client.get(f"/api/v1/areas/{DISTRICT_SOUTH}")).json()["coverage"]

    assert coverage["low_confidence"] is True
    # The field that would place the traveller at a moment.
    assert coverage["last_measured_at"] is None
    # The evidence behind the colour, which places nobody.
    assert coverage["measurements"] is not None and coverage["measurements"] > 0
    assert coverage["avg_rsrp_dbm"] is not None
    # The finding itself is not suppressed — that would blank out exactly the
    # remote places this project exists to reveal.
    assert coverage["tiles"] > 0
    assert coverage["colour"] != "grey"


async def test_a_second_collector_unlocks_the_detail(
    client: AsyncClient, session: AsyncSession, device_key, public_key_b64: str
):
    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)

    second_key = Ed25519PrivateKey.generate()
    second_public = base64.b64encode(
        second_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    install_id = "install-second00000001"

    await client.post(
        "/api/v1/devices/enroll",
        json={"device": {"install_id": install_id}, "public_key": second_public},
    )
    records = [
        sign_record(
            make_record(record_id=f"rec-second{i:05d}", minutes_ago=60 - i, lat=BASE_LAT + i * 0.01),
            second_key,
        )
        for i in range(3)
    ]
    response = await client.post(
        "/api/v1/measurements/batch",
        json={
            "batch_id": "batch-second001",
            "device": {"install_id": install_id},
            "records": records,
        },
    )
    assert response.json()["accepted"] == 3, response.text

    await rebuild_tiles(session)
    coverage = (await client.get(f"/api/v1/areas/{DISTRICT_SOUTH}")).json()["coverage"]

    assert coverage["devices"] >= 2
    assert coverage["low_confidence"] is False
    assert coverage["measurements"] is not None
