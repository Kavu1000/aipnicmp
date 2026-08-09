"""Headline figures for the map and the operator dashboard.

Two principles run through this module.

**Say how little is measured.** A coverage map that reports "124 areas" invites
the reader to assume national coverage. Reporting 91 km², and that this is
0.04% of Lao PDR, is both honest and a stronger argument: it says plainly that
the map is a pilot and that more collectors would extend it.

**Say what it would cost to fix.** The five radio states map onto three very
different budget lines, and that mapping is the project's whole policy claim.
An area no tower reaches needs capital investment; an area with a tower that
cannot be attached to needs an upgrade. Reporting them as one "bad coverage"
number would throw away the distinction the platform exists to make.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import h3
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.radio import STATE_COLOUR, RadioState
from app.models.device import Device
from app.models.measurement import Measurement
from app.models.tile import H3Tile, H3TileOperator

# CIA World Factbook / UN figure for Lao PDR.
LAO_AREA_KM2 = 236_800

# What each state implies for spending. The wording is deliberately the same as
# the map legend, so the dashboard and the public map cannot drift apart.
INVESTMENT_ACTION: dict[RadioState, str] = {
    RadioState.NO_CELL: "new_tower",
    RadioState.CELLS_VISIBLE_UNREGISTERED: "upgrade",
    RadioState.REGISTERED_2G_3G: "upgrade",
    RadioState.LTE_WEAK: "optimisation",
    RadioState.LTE_GOOD: "none",
}


def tile_area_km2(resolution: int | None = None) -> float:
    return h3.average_hexagon_area(resolution or settings.h3_resolution, unit="km^2")


async def coverage_summary(session: AsyncSession) -> dict[str, Any]:
    """Everything the header and the dashboard need, in one query set."""
    measurements = await session.scalar(select(func.count()).select_from(Measurement)) or 0
    devices = await session.scalar(select(func.count()).select_from(Device)) or 0
    latest = await session.scalar(select(func.max(Measurement.captured_at)))
    generated_at = await session.scalar(select(func.max(H3Tile.updated_at)))

    state_rows = (
        await session.execute(
            select(H3Tile.dominant_state, func.count()).group_by(H3Tile.dominant_state)
        )
    ).all()
    by_state = {state: count for state, count in state_rows if state}
    tiles = sum(by_state.values())

    area = tile_area_km2()
    measured_km2 = tiles * area

    # Grouped by what it would take to fix, not by how bad it looks.
    by_action: dict[str, int] = {"new_tower": 0, "upgrade": 0, "optimisation": 0, "none": 0}
    for state_name, count in by_state.items():
        try:
            action = INVESTMENT_ACTION[RadioState(state_name)]
        except ValueError:
            continue
        by_action[action] += count

    bounds = (
        await session.execute(
            select(
                func.min(H3Tile.centroid_lat),
                func.min(H3Tile.centroid_lon),
                func.max(H3Tile.centroid_lat),
                func.max(H3Tile.centroid_lon),
            )
        )
    ).one()

    no_service = (
        await session.scalar(
            select(func.count())
            .select_from(Measurement)
            .where(Measurement.radio_state == RadioState.NO_CELL.value)
        )
        or 0
    )

    return {
        "measurements": measurements,
        "devices": devices,
        "tiles": tiles,
        "no_service_measurements": no_service,
        "measured_area_km2": round(measured_km2, 1),
        "country_area_km2": LAO_AREA_KM2,
        # Deliberately not rounded to a whole percent: at pilot scale that
        # would read as "0%", which is both wrong and discouraging.
        "measured_share_pct": round(measured_km2 / LAO_AREA_KM2 * 100, 4),
        "tile_area_km2": round(area, 3),
        "h3_resolution": settings.h3_resolution,
        "latest_measurement_at": latest.isoformat() if latest else None,
        "tiles_updated_at": generated_at.isoformat() if generated_at else None,
        "by_state": by_state,
        "by_action": by_action,
        "area_by_action_km2": {
            action: round(count * area, 1) for action, count in by_action.items()
        },
        "bounds": (
            {
                "min_lat": bounds[0],
                "min_lon": bounds[1],
                "max_lat": bounds[2],
                "max_lon": bounds[3],
            }
            if bounds[0] is not None
            else None
        ),
    }


async def operator_breakdown(session: AsyncSession) -> list[dict[str, Any]]:
    """Per-operator coverage, worst first.

    Sorted by the share of their measured area that is unusable, because that is
    the number an operator has to answer for — not the raw tile count, which
    only says where collectors happened to travel.
    """
    rows = (
        await session.execute(
            select(
                H3TileOperator.operator_name,
                H3TileOperator.dominant_state,
                func.count(),
                func.avg(H3TileOperator.avg_rsrp_dbm),
            ).group_by(H3TileOperator.operator_name, H3TileOperator.dominant_state)
        )
    ).all()

    operators: dict[str, dict[str, Any]] = {}
    for name, state, count, avg_rsrp in rows:
        entry = operators.setdefault(
            name, {"operator": name, "tiles": 0, "by_state": {}, "rsrp_sum": 0.0, "rsrp_n": 0}
        )
        entry["tiles"] += count
        if state:
            entry["by_state"][state] = count
        if avg_rsrp is not None:
            entry["rsrp_sum"] += avg_rsrp * count
            entry["rsrp_n"] += count

    area = tile_area_km2()
    result = []
    for entry in operators.values():
        by_state = entry["by_state"]
        usable = by_state.get(RadioState.LTE_GOOD.value, 0)
        unusable = by_state.get(RadioState.NO_CELL.value, 0) + by_state.get(
            RadioState.CELLS_VISIBLE_UNREGISTERED.value, 0
        )
        tiles = entry["tiles"]
        result.append(
            {
                "operator": entry["operator"],
                "tiles": tiles,
                "area_km2": round(tiles * area, 1),
                "by_state": by_state,
                "good_pct": round(usable / tiles * 100, 1) if tiles else 0.0,
                "unusable_pct": round(unusable / tiles * 100, 1) if tiles else 0.0,
                "avg_rsrp_dbm": (
                    round(entry["rsrp_sum"] / entry["rsrp_n"], 1) if entry["rsrp_n"] else None
                ),
            }
        )

    result.sort(key=lambda row: row["unusable_pct"], reverse=True)
    return result


async def priority_areas(session: AsyncSession, limit: int = 25) -> list[dict[str, Any]]:
    """Measured dead zones, ranked — an actionable list with no model involved.

    The ranked *tower sites* of proposal 2.5(3) need population and terrain data
    that the pilot does not yet have. This is the honest interim: places where
    the platform has actually recorded no service, ordered by how much evidence
    supports the finding.

    Ranking by measurement count rather than by severity alone is deliberate. A
    tile seen once might be a phone in a bag; a tile seen forty times, by
    several devices, is a fact about the place.
    """
    ranked_states = [
        RadioState.NO_CELL.value,
        RadioState.CELLS_VISIBLE_UNREGISTERED.value,
        RadioState.REGISTERED_2G_3G.value,
    ]

    rows = (
        await session.scalars(
            select(H3Tile)
            .where(H3Tile.dominant_state.in_(ranked_states), H3Tile.is_predicted.is_(False))
            .order_by(
                H3Tile.state_score.asc(),
                H3Tile.measurement_count.desc(),
                H3Tile.device_count.desc(),
            )
            .limit(limit)
        )
    ).all()

    area = tile_area_km2()
    out = []
    for index, tile in enumerate(rows, start=1):
        state = RadioState(tile.dominant_state) if tile.dominant_state else None
        out.append(
            {
                "rank": index,
                "h3": tile.h3_index,
                "lat": tile.centroid_lat,
                "lon": tile.centroid_lon,
                "state": tile.dominant_state,
                "colour": STATE_COLOUR[state].value if state else "grey",
                "action": INVESTMENT_ACTION[state] if state else None,
                "measurements": tile.measurement_count,
                "devices": tile.device_count,
                "area_km2": round(area, 3),
                "avg_rsrp_dbm": tile.avg_rsrp_dbm,
                "last_measured_at": (
                    tile.last_measured_at.isoformat() if tile.last_measured_at else None
                ),
            }
        )
    return out


async def known_operators(session: AsyncSession) -> list[str]:
    rows = await session.scalars(
        select(H3TileOperator.operator_name)
        .distinct()
        .order_by(H3TileOperator.operator_name.asc())
    )
    return list(rows.all())


def isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
