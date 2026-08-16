"""Coverage data as files somebody can open somewhere else.

The platform's own screens carry a lot of care about what each number means —
that a cell point is not a mast, that an uncertainty is a lower bound, that a
pale district is unmeasured rather than poor. None of that survives a download.
A CSV of hexagons becomes a national coverage statistic in somebody else's
slide deck, with every caveat stripped by the act of exporting.

So every export here ships with a manifest: when it was generated, what filter
produced it, how many rows it holds, and what the platform declines to claim.
The bundle puts them in one file so the two cannot be separated by accident.

Hexagons are keyed by their H3 index, which is the point of using H3 at all —
anyone can join this against their own data on that column without a spatial
operation, on any machine, in any tool.

Raw measurements are deliberately absent. They are a GPS fix every ten seconds
for each collector, which is the personal trace the retention sweep exists to
age out; publishing them as a download would undo that in one click.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import RSRP_GOOD_DBM, RadioState
from app.models.area import AdminArea
from app.models.cell import ObservedCell
from app.models.features import HexFeature
from app.models.tile import H3Tile, H3TileOperator
from app.services.geo import h3_polygon_geojson, haversine_m

#: Bumped when a column is added, removed or given a new meaning, so a file
#: found on somebody's disk in a year can be matched to what produced it.
EXPORT_VERSION = 1

TILE_COLUMNS = [
    "h3_index",
    "centroid_lat",
    "centroid_lon",
    "colour",
    "state",
    "worst_state",
    "measurements",
    "devices",
    "avg_rsrp_dbm",
    "avg_download_kbps",
    "adm1_code",
    "adm2_code",
    "adm3_code",
    "last_measured_at",
]

CELL_COLUMNS = [
    "cell",
    "operator",
    "est_lat",
    "est_lon",
    "uncertainty_m",
    "spread_m",
    "observations",
    "best_rsrp_dbm",
    "first_seen_at",
    "last_seen_at",
]

AREA_COLUMNS = [
    "code",
    "level",
    "name_en",
    "name_lo",
    "hexagons_measured",
    "measurements",
    "good",
    "weak",
    "calls_only",
    "unusable",
    "no_network",
]

WEAK_AREA_COLUMNS = [
    "rank",
    "h3_index",
    "centroid_lat",
    "centroid_lon",
    "province",
    "district",
    "avg_rsrp_dbm",
    "shortfall_db",
    "shortfall_band",
    "population",
    "people_times_shortfall",
    "measurements",
    "devices",
    "distance_to_nearest_cell_m",
    "terrain_ruggedness_m",
    "elevation_mean_m",
]


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


#: Excel on Windows reads a CSV in the system codepage unless the file opens
#: with a byte-order mark, and Lao script comes out as mojibake when it does.
#: Every district name in areas.csv is in Lao, and a spreadsheet of unreadable
#: place names is a spreadsheet nobody uses. JSON never gets this — a leading
#: BOM is not valid JSON and parsers are right to reject it.
UTF8_BOM = "﻿"


def _csv(columns: list[str], rows: Iterable[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return UTF8_BOM + buffer.getvalue()


async def tile_rows(
    session: AsyncSession, *, operator: str | None = None, area: str | None = None
) -> list[dict[str, Any]]:
    """Measured hexagons, optionally for one network and one area.

    Predicted hexagons are excluded. An export is what somebody will treat as
    ground truth once it is on their disk, and a modelled tile in the same file
    as a measured one is indistinguishable the moment the `predicted` column is
    dropped by a spreadsheet — which is exactly what happens.
    """
    if operator:
        query = select(H3TileOperator).where(
            H3TileOperator.operator_name == operator,
            H3TileOperator.measurement_count > 0,
        )
        if area:
            query = query.where(
                (H3TileOperator.adm1_code == area)
                | (H3TileOperator.adm2_code == area)
                | (H3TileOperator.adm3_code == area)
            )
    else:
        query = select(H3Tile).where(
            H3Tile.measurement_count > 0, H3Tile.is_predicted.is_(False)
        )
        if area:
            query = query.where(
                (H3Tile.adm1_code == area)
                | (H3Tile.adm2_code == area)
                | (H3Tile.adm3_code == area)
            )

    tiles = (await session.scalars(query.order_by("h3_index"))).all()
    return [
        {
            "h3_index": tile.h3_index,
            "centroid_lat": round(tile.centroid_lat, 6),
            "centroid_lon": round(tile.centroid_lon, 6),
            "colour": tile.colour,
            "state": tile.dominant_state,
            "worst_state": tile.worst_state,
            "measurements": tile.measurement_count,
            "devices": tile.device_count,
            "avg_rsrp_dbm": tile.avg_rsrp_dbm,
            "avg_download_kbps": tile.avg_download_kbps,
            "adm1_code": tile.adm1_code,
            "adm2_code": tile.adm2_code,
            "adm3_code": tile.adm3_code,
            "last_measured_at": _iso(getattr(tile, "last_measured_at", None)),
        }
        for tile in tiles
    ]


async def cell_rows(
    session: AsyncSession, *, operator: str | None = None
) -> list[dict[str, Any]]:
    """Observed cells that were spread widely enough to be given a position."""
    query = select(ObservedCell).where(ObservedCell.position_is_reliable.is_(True))
    if operator:
        query = query.where(ObservedCell.operator_name == operator)

    return [
        {
            "cell": f"{cell.mcc}-{cell.mnc}-{cell.lac_tac}-{cell.cid}",
            "operator": cell.operator_name,
            "est_lat": round(cell.est_lat, 6),
            "est_lon": round(cell.est_lon, 6),
            "uncertainty_m": cell.uncertainty_m,
            "spread_m": cell.spread_m,
            "observations": cell.observations,
            "best_rsrp_dbm": cell.best_rsrp_dbm,
            "first_seen_at": _iso(cell.first_seen_at),
            "last_seen_at": _iso(cell.last_seen_at),
        }
        for cell in (await session.scalars(query.order_by(ObservedCell.operator_name))).all()
    ]


async def area_rows(
    session: AsyncSession, *, operator: str | None = None
) -> list[dict[str, Any]]:
    """One row per province and district, counted from the measured hexagons."""
    names = {
        area.code: area
        for area in (await session.scalars(select(AdminArea).where(AdminArea.level <= 2))).all()
    }
    tiles = await tile_rows(session, operator=operator)

    tally: dict[str, dict[str, Any]] = {}
    for tile in tiles:
        for code in (tile["adm1_code"], tile["adm2_code"]):
            if not code or code not in names:
                continue
            entry = tally.setdefault(
                code,
                {
                    "code": code,
                    "level": names[code].level,
                    "name_en": names[code].name_en,
                    "name_lo": names[code].name_lo,
                    "hexagons_measured": 0,
                    "measurements": 0,
                    "good": 0,
                    "weak": 0,
                    "calls_only": 0,
                    "unusable": 0,
                    "no_network": 0,
                },
            )
            entry["hexagons_measured"] += 1
            entry["measurements"] += tile["measurements"]
            key = {
                RadioState.LTE_GOOD.value: "good",
                RadioState.LTE_WEAK.value: "weak",
                RadioState.REGISTERED_2G_3G.value: "calls_only",
                RadioState.CELLS_VISIBLE_UNREGISTERED.value: "unusable",
                RadioState.NO_CELL.value: "no_network",
            }.get(tile["state"] or "")
            if key:
                entry[key] += 1

    return sorted(tally.values(), key=lambda row: (row["level"], row["code"]))


async def weak_area_rows(
    session: AsyncSession, *, operator: str | None = None
) -> list[dict[str, Any]]:
    """Weak-4G hexagons ranked by how many people the shortfall affects.

    Registered on LTE and below the good line: the state whose remedy is
    optimisation rather than construction. Ranked by population times decibels
    short, because a village three decibels under is worth more attention than
    empty ground fifteen under, and neither figure alone says that.

    The columns are evidence, not a prescription. ``shortfall_band`` groups the
    rows by how far under they are because that is what separates a remedy
    costing nothing from one costing a mast — but which remedy applies depends
    on antenna tilts and bands that only the operator holds, so this file
    stops at saying where and how much.
    """
    table = H3TileOperator if operator else H3Tile
    query = select(table).where(
        table.dominant_state == RadioState.LTE_WEAK.value,
        table.measurement_count > 0,
        table.avg_rsrp_dbm.is_not(None),
    )
    if operator:
        query = query.where(H3TileOperator.operator_name == operator)
    else:
        query = query.where(H3Tile.is_predicted.is_(False))

    tiles = (await session.scalars(query)).all()
    if not tiles:
        return []

    features = {
        row.h3_index: row
        for row in (
            await session.execute(
                select(
                    HexFeature.h3_index,
                    HexFeature.population,
                    HexFeature.terrain_ruggedness_m,
                    HexFeature.elevation_mean_m,
                ).where(HexFeature.h3_index.in_([tile.h3_index for tile in tiles]))
            )
        ).all()
    }
    names = {
        area.code: area.name_en
        for area in (await session.scalars(select(AdminArea).where(AdminArea.level <= 2))).all()
    }
    cells = (
        await session.execute(
            select(ObservedCell.est_lat, ObservedCell.est_lon).where(
                ObservedCell.position_is_reliable.is_(True)
            )
        )
    ).all()

    rows: list[dict[str, Any]] = []
    for tile in tiles:
        shortfall = round(RSRP_GOOD_DBM - tile.avg_rsrp_dbm, 1)
        feature = features.get(tile.h3_index)
        population = round(feature.population) if feature and feature.population else 0
        nearest = min(
            (
                haversine_m(tile.centroid_lat, tile.centroid_lon, cell.est_lat, cell.est_lon)
                for cell in cells
            ),
            default=None,
        )
        rows.append(
            {
                "h3_index": tile.h3_index,
                "centroid_lat": round(tile.centroid_lat, 6),
                "centroid_lon": round(tile.centroid_lon, 6),
                "province": names.get(tile.adm1_code or "", ""),
                "district": names.get(tile.adm2_code or "", ""),
                # Not in WEAK_AREA_COLUMNS, so they never reach the CSV. They
                # are here so an area filter can be applied after ranking
                # rather than before it, which is what keeps a rank number
                # meaning the same thing in every view.
                "adm1_code": tile.adm1_code,
                "adm2_code": tile.adm2_code,
                "adm3_code": tile.adm3_code,
                "avg_rsrp_dbm": round(tile.avg_rsrp_dbm, 1),
                "shortfall_db": shortfall,
                # Grouped by what the size of the gap implies, not by a guess
                # at the cause. Under 5 dB is inside the noise a vehicle body
                # adds; over 10 dB is not.
                "shortfall_band": (
                    "under_5db" if shortfall <= 5 else "5_to_10db" if shortfall <= 10 else "over_10db"
                ),
                "population": population,
                "people_times_shortfall": round(population * shortfall),
                "measurements": tile.measurement_count,
                "devices": tile.device_count,
                "distance_to_nearest_cell_m": round(nearest) if nearest is not None else "",
                "terrain_ruggedness_m": (
                    round(feature.terrain_ruggedness_m, 1)
                    if feature and feature.terrain_ruggedness_m is not None
                    else ""
                ),
                "elevation_mean_m": (
                    round(feature.elevation_mean_m)
                    if feature and feature.elevation_mean_m is not None
                    else ""
                ),
            }
        )

    rows.sort(key=lambda row: -row["people_times_shortfall"])
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def tiles_geojson(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Hexagons as polygons, so this opens in QGIS without a join step."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": h3_polygon_geojson(row["h3_index"]),
                "properties": row,
            }
            for row in rows
        ],
    }


def cells_geojson(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["est_lon"], row["est_lat"]]},
                "properties": row,
            }
            for row in rows
        ],
    }


def manifest(
    *,
    generated_at: datetime,
    operator: str | None,
    area: str | None,
    counts: dict[str, int],
) -> str:
    """What produced this file, and what it must not be read as saying.

    Written into every bundle because the caveats are the part most easily
    lost. A reader who has only this text file and the CSVs beside it should
    still know that a blank area is unmeasured rather than uncovered, and that
    a cell point is not a mast.
    """
    scope = operator or "all networks"
    where = area or "whole country"
    lines = [
        "AI-PNICMP — coverage export",
        "=" * 60,
        "",
        f"Generated:        {generated_at.isoformat()}",
        f"Export version:   {EXPORT_VERSION}",
        f"Networks:         {scope}",
        f"Area:             {where}",
        "",
        "Rows",
        "-" * 60,
    ]
    lines += [f"  {name:<24} {count}" for name, count in counts.items()]
    lines += [
        "",
        "Files",
        "-" * 60,
        "  tiles.geojson     measured hexagons as polygons (for QGIS)",
        "  tiles.csv         the same rows, without geometry (for a spreadsheet)",
        "  areas.csv         one row per province and district",
        "  cells.geojson     observed cells that could be given a position",
        "  weak-areas.csv    weak-4G hexagons, ranked by people times decibels",
        "",
        "Joining this to your own data",
        "-" * 60,
        "  Every hexagon row carries h3_index, an H3 resolution-8 cell (about",
        "  0.84 km2 at Lao latitudes). It is a stable text key: two exports of",
        "  the same ground use the same index, and you can join on it without",
        "  any spatial operation.",
        "",
        "What this data does not claim",
        "-" * 60,
        "  1. Coverage where nothing was measured. Hexagons absent from this",
        "     export were not visited. Absent does not mean no coverage.",
        "  2. How far any tower reaches. No figure here is a coverage radius.",
        "  3. Base station positions. Rows in cells.geojson are the centre of",
        "     where a cell was heard, not where a mast stands: readings taken",
        "     along a road place the point on the road. uncertainty_m is the",
        "     spread of those readings and is a lower bound — a mast standing",
        "     off to one side of the route is invisible to the method.",
        "  4. What an operator owns. These are cells collectors have heard.",
        "  5. A national statistic. Shares are computed over measured hexagons",
        "     only. See the coverage figures in the platform for how much of",
        "     the country that currently is.",
        "",
        "",
        "Before acting on weak-areas.csv",
        "-" * 60,
        "  These readings were taken on phones inside moving vehicles. A vehicle",
        "  body costs roughly 6-10 dB, which is larger than the median shortfall",
        "  in this file — so a hexagon a few decibels under the line may already",
        "  be adequate for somebody standing outside, and the figure describes",
        "  the car as much as the coverage.",
        "",
        "  Measure inside and outside the vehicle at a sample of these places",
        "  before committing money to any of them. shortfall_band groups the",
        "  rows by size of gap for that reason: under_5db is inside the range a",
        "  vehicle body alone can explain.",
        "",
        "  The file says where and how much. It does not say why, and the remedy",
        "  turns entirely on why: antenna tilt and azimuth, band, terrain",
        "  shadowing and site position are what separate a fix costing nothing",
        "  from one costing a mast. The operator holds all four; this platform",
        "  holds none of them.",
        "",
        "  A hexagon's colour is the median state of every reading ever taken",
        "  inside it, not the worst; worst_state is a separate column.",
        "  Predicted hexagons are excluded from this export entirely.",
        "",
        "  The full method is in web/src/content/METHOD.md in the repository,",
        "  and on the Method page of the platform.",
        "",
    ]
    return "\n".join(lines)


async def bundle(
    session: AsyncSession, *, operator: str | None = None, area: str | None = None
) -> bytes:
    """Every file above plus the manifest, in one archive.

    One file rather than four downloads, so the manifest cannot be the one
    nobody bothered to fetch.
    """
    generated_at = datetime.now(timezone.utc)
    tiles = await tile_rows(session, operator=operator, area=area)
    cells = await cell_rows(session, operator=operator)
    areas = await area_rows(session, operator=operator)
    weak = await weak_area_rows(session, operator=operator)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "MANIFEST.txt",
            manifest(
                generated_at=generated_at,
                operator=operator,
                area=area,
                counts={
                    "hexagons": len(tiles),
                    "areas": len(areas),
                    "observed cells": len(cells),
                    "weak-4G hexagons": len(weak),
                },
            ),
        )
        archive.writestr("tiles.geojson", json.dumps(tiles_geojson(tiles)))
        archive.writestr("tiles.csv", _csv(TILE_COLUMNS, tiles))
        archive.writestr("areas.csv", _csv(AREA_COLUMNS, areas))
        archive.writestr("cells.geojson", json.dumps(cells_geojson(cells)))
        archive.writestr("weak-areas.csv", _csv(WEAK_AREA_COLUMNS, weak))

    return buffer.getvalue()


def tiles_csv(rows: list[dict[str, Any]]) -> str:
    return _csv(TILE_COLUMNS, rows)


def areas_csv(rows: list[dict[str, Any]]) -> str:
    return _csv(AREA_COLUMNS, rows)


def weak_areas_csv(rows: list[dict[str, Any]]) -> str:
    return _csv(WEAK_AREA_COLUMNS, rows)
