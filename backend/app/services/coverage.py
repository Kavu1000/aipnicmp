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

from datetime import datetime, timedelta, timezone
from typing import Any

import h3
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.operators import NETWORK_NAMES, normalise_mnc, operator_from_reported_name
from app.core.radio import STATE_COLOUR, RadioState
from app.models.cell import ObservedCell
from app.models.device import Device
from app.models.measurement import Measurement
from app.models.tile import H3Tile, H3TileOperator
from app.services.network import canonical_operator_column, has_operator_identity
from app.services.geo import h3_centroid
from app.services.validation import haversine_m

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


# The centre of the country, used to size a representative hexagon. See below.
LAO_CENTRE_LAT = 18.0
LAO_CENTRE_LON = 103.5


def tile_area_km2(resolution: int | None = None) -> float:
    """The area of one hexagon, as it actually is over Laos.

    ``h3.average_hexagon_area`` is a mean over the whole sphere, and H3 cells
    are not equal-area. At resolution 8 the global average is 0.737 km2, but
    across Laos the real cells run 0.815-0.858 km2 with a mean of 0.836 —
    measured over all 279,918 cells covering the country.

    Using the global figure understated every area and every share this module
    reports by 11.8%. That is the wrong direction for a platform whose whole
    argument rests on saying honestly how little has been measured: it made the
    pilot look smaller than it is, in a number quoted to policymakers.

    A single representative cell rather than a per-tile sum: the spread across
    the country is 5.1%, so a mid-country cell is within about 2.5% anywhere in
    Laos, against 11.8% before. Summing real areas per tile would be exact, but
    it would put a 280,000-row scan behind every dashboard request to remove an
    error smaller than the simplification already in the boundaries.
    """
    res = resolution or settings.h3_resolution
    return h3.cell_area(h3.latlng_to_cell(LAO_CENTRE_LAT, LAO_CENTRE_LON, res), unit="km^2")


async def coverage_summary(session: AsyncSession) -> dict[str, Any]:
    """Everything the header and the dashboard need, in one query set."""
    measurements = await session.scalar(select(func.count()).select_from(Measurement)) or 0
    # Devices that have actually contributed a reading, not devices that have
    # enrolled. Six phones were enrolled and two had ever sent anything — the
    # other four were the same two handsets after a reinstall, since a
    # reinstalled app cannot resume its old identity. Counting enrolments under
    # the heading "contributing devices" turned that into a fleet three times
    # its real size, on the figure a reader uses to judge how much evidence is
    # behind the map.
    devices = (
        await session.scalar(select(func.count(func.distinct(Measurement.device_id))))
    ) or 0
    enrolled = await session.scalar(select(func.count()).select_from(Device)) or 0
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
        "devices_enrolled": enrolled,
        "tiles": tiles,
        "no_service_measurements": no_service,
        # Four decimals, not one.
        #
        # A pilot measures well under a square kilometre, and rounding to 0.1
        # km2 there is a 6% error: 0.848 km2 became 0.8, which the dashboard
        # then showed as 80 ha instead of 85. The client decides how to display
        # this; the server's job is not to have thrown the answer away first.
        "measured_area_km2": round(measured_km2, 4),
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
            action: round(count * area, 4) for action, count in by_action.items()
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


async def network_catalogue(session: AsyncSession) -> list[dict[str, Any]]:
    """Every Lao network, measured or not.

    A filter that lists only the networks with data implies the others do not
    exist. They do — nobody has measured them, because a phone can only measure
    the network its own SIM is attached to, and every collector in the pilot
    carries the same one.

    That is a recruitment problem, not a coverage finding, and the difference
    matters: "Unitel has no coverage here" and "nobody has checked Unitel here"
    are opposite claims. Listing the unmeasured networks and saying plainly that
    they are unmeasured is the same discipline the map already applies to
    unmeasured ground.
    """
    rows = (
        await session.execute(
            select(H3TileOperator.operator_name, func.count()).group_by(
                H3TileOperator.operator_name
            )
        )
    ).all()
    measured = {name: count for name, count in rows if name}

    catalogue: list[dict[str, Any]] = []
    for (mcc, mnc), name in NETWORK_NAMES.items():
        tiles = measured.pop(name, 0)
        catalogue.append(
            {"operator": name, "mcc": mcc, "mnc": mnc, "tiles": tiles, "measured": tiles > 0}
        )

    # Anything measured that the table does not know about — an unrecognised
    # PLMN, or a reading that carried a name but no PLMN at all.
    catalogue.extend(
        {"operator": name, "mcc": None, "mnc": None, "tiles": count, "measured": True}
        for name, count in sorted(measured.items())
    )

    catalogue.sort(key=lambda row: (-row["tiles"], row["operator"]))
    return catalogue


def isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


"""How recently a phone must have uploaded to count as reporting.

Set well above the one-minute upload cadence so a single missed cycle — a
lost signal, a retry, a phone briefly in a lift — does not flip a working
collector to silent and back.
"""
REPORTING_WINDOW = timedelta(minutes=10)


#: Android API level to the version a person recognises.
#:
#: Only the levels the fleet has actually enrolled, plus room to grow. An
#: unmapped level shows as the raw number rather than a wrong version — being
#: told a phone runs "Android 30" is a smaller failure than being told it runs
#: Android 11 when it does not.
ANDROID_VERSIONS = {
    28: "9", 29: "10", 30: "11", 31: "12", 32: "12L",
    33: "13", 34: "14", 35: "15", 36: "16",
}


def android_version(api_level: int | None) -> str | None:
    if api_level is None:
        return None
    return ANDROID_VERSIONS.get(api_level, str(api_level))


async def reporting_capability(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """What each handset actually manages to report, per device.

    The specification that decides what a reading is worth. Two phones on the
    same road do not produce the same data: one reports signal strength on
    every reading and hears ten neighbouring cells, another reports it on
    seven readings in ten and hears three.

    Both differences reach the findings. A reading with no RSRP is classified
    pessimistically — the platform will not credit coverage it cannot verify —
    so a handset that withholds the number produces more weak hexagons than one
    that does not, on identical ground. And a handset that hears few neighbours
    starves the cell estimator, which needs five sightings of a cell across
    800 m before it can place anything.

    So this is not an inventory column. It is the confounder, made visible.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT device_id,
                       count(*) AS readings,
                       count(rsrp_dbm) AS with_rsrp,
                       count(sinr_db) AS with_sinr,
                       avg(cells_visible) AS cells_seen
                FROM measurements
                GROUP BY device_id
                """
            )
        )
    ).all()

    return {
        row.device_id: {
            "readings": row.readings,
            # Percentages rather than counts: the question is what share of
            # this phone's readings carry the figure, and a count only answers
            # that against a total the reader has to find elsewhere.
            "rsrp_pct": round(100 * row.with_rsrp / row.readings, 1) if row.readings else None,
            "sinr_pct": round(100 * row.with_sinr / row.readings, 1) if row.readings else None,
            "cells_seen": round(float(row.cells_seen), 1) if row.cells_seen is not None else None,
        }
        for row in rows
    }


async def collectors(session: AsyncSession) -> list[dict[str, Any]]:
    """The devices contributing measurements, most recently active first.

    Carries a *coarse* position: the hexagon a phone last reported from, at
    resolution 8 — about 740 m across — and never its GPS fix. This reverses an
    earlier decision that published no position at all, and the reasoning for
    that decision still holds, so the replacement is deliberately limited:

    * the hexagon centroid only, so the answer is "somewhere in this 0.74 km²",
      not "here";
    * the latest one only, never a history, so it cannot become a movement
      record. Yesterday's hexagon is not retrievable through this view;
    * exact coordinates never leave the server for this endpoint.

    That is enough to answer the operational question — is anyone collecting in
    Attapeu today, is a phone stuck in one place, is the fleet spread out or
    all in Vientiane — without turning a coverage platform into a way of
    watching the people carrying the phones. A collector's own movements are
    what the H3 aggregation exists to hide, and it would be a poor trade to
    hide them from the public map and hand them to the operations page.

    The network each phone reports on *is* included, and is equipment
    information in the same sense as the handset model. It also answers the
    question the network list raises and cannot itself resolve: three of the
    four Lao operators have no coverage data, and the reason is that no
    collector carries their SIM. Naming the networks the fleet is actually on
    turns that from a gap in the map into a recruitment list.

    Install ids are shortened for the same reason they are random in the first
    place: enough to tell two devices apart, not enough to be worth correlating.
    """
    rows = (
        await session.scalars(
            select(Device).order_by(Device.last_seen_at.desc().nullslast()).limit(200)
        )
    ).all()

    operator = canonical_operator_column()
    seen = (
        await session.execute(
            select(Measurement.device_id, operator, func.count())
            .where(has_operator_identity())
            .group_by(Measurement.device_id, operator)
            .order_by(func.count().desc())
        )
    ).all()

    # A phone can report more than one network — a dual-SIM handset, or one that
    # roamed. All of them are listed, busiest first, rather than picking a
    # winner and hiding the rest.
    networks: dict[str, list[str]] = {}
    for device_id, name, _count in seen:
        if name:
            networks.setdefault(device_id, []).append(name)

    # The hexagon each phone last reported from. Ordered oldest-first so the
    # newest reading overwrites, which settles the tie when a device has two
    # measurements sharing the same captured_at.
    last_cell: dict[str, tuple[str, datetime]] = {}
    last_serving: dict[str, tuple[str | None, str | None, int | None, int | None]] = {}
    for device_id, h3_index, captured_at, mcc, mnc, lac, cid in (
        await session.execute(
            select(
                Measurement.device_id,
                Measurement.h3_index,
                Measurement.captured_at,
                Measurement.mcc,
                Measurement.mnc,
                Measurement.serving_lac_tac,
                Measurement.serving_cid,
            )
            .where(Measurement.h3_index.is_not(None))
            .order_by(Measurement.captured_at.asc())
        )
    ).all():
        last_cell[device_id] = (h3_index, captured_at)
        last_serving[device_id] = (mcc, mnc, lac, cid)

    # The masts the platform has been able to place, keyed by identity. Only
    # the reliable ones: a link drawn to a cell estimated from one car park
    # would put a confident line on the map between two guesses.
    placed = {
        (cell.mcc, cell.mnc, cell.lac_tac, cell.cid): cell
        for cell in (
            await session.scalars(
                select(ObservedCell).where(ObservedCell.position_is_reliable.is_(True))
            )
        ).all()
    }

    capability = await reporting_capability(session)

    now = datetime.now(timezone.utc)

    out: list[dict[str, Any]] = []
    for device in rows:
        total = device.records_accepted + device.records_rejected
        cell = last_cell.get(device.install_id)
        position = None
        link = None
        if cell is not None:
            lat, lon = h3_centroid(cell[0])
            position = {
                "h3_index": cell[0],
                "lat": lat,
                "lon": lon,
                "resolution": settings.h3_resolution,
                "at": cell[1].isoformat(),
            }

            # The mast that was serving this phone, when the platform has
            # managed to place it. Distance is measured from the hexagon
            # centre, not the handset's fix, because the centre is all this
            # view ever publishes — so it inherits that coarseness and says so.
            serving = last_serving.get(device.install_id)
            if serving is not None:
                mast = placed.get(
                    (serving[0], normalise_mnc(serving[1]), serving[2], serving[3])
                )
                if mast is not None:
                    metres = haversine_m(lat, lon, mast.est_lat, mast.est_lon)
                    link = {
                        "lat": mast.est_lat,
                        "lon": mast.est_lon,
                        "operator": mast.operator_name,
                        "cell": f"{mast.mcc}-{mast.mnc}-{mast.lac_tac}-{mast.cid}",
                        "distance_m": round(metres),
                        # Both ends are approximate, so the distance is too.
                        # Half a hexagon plus the mast's own uncertainty is the
                        # least dishonest bound available.
                        "distance_uncertainty_m": round(
                            mast.uncertainty_m + tile_area_km2() ** 0.5 * 500
                        ),
                    }

        # "Reporting" rather than "online": the server only ever learns that a
        # phone uploaded, which is not the same as it being switched on now. A
        # collector in a dead zone is working exactly as intended and will look
        # silent from here until they reach coverage.
        last_seen = device.last_seen_at
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        reporting = last_seen is not None and (now - last_seen) <= REPORTING_WINDOW

        out.append(
            {
                "id": device.install_id[:16],
                "position": position,
                "serving_tower": link,
                "is_reporting": reporting,
                "silent_for_s": int((now - last_seen).total_seconds()) if last_seen else None,
                "model": device.model,
                "manufacturer": device.manufacturer,
                "android_version": android_version(device.android_api),
                # Empty for a phone that has enrolled but not yet uploaded a
                # reading with a network attached.
                "networks": networks.get(device.install_id, []),
                "app_version": device.app_version,
                "key_algorithm": device.key_algorithm,
                "trust_level": device.trust_level,
                "is_blocked": device.is_blocked,
                "is_simulated": device.install_id.startswith("sim-"),
                "enrolled_at": device.enrolled_at.isoformat() if device.enrolled_at else None,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "records_accepted": device.records_accepted,
                "records_rejected": device.records_rejected,
                # The number worth watching: a collector whose records are all
                # being refused looks identical to a healthy one by any other
                # measure, right up until the map stays empty.
                "rejection_rate_pct": round(device.records_rejected / total * 100, 1) if total else 0.0,
                # What this handset manages to report, which decides what its
                # readings are worth. See reporting_capability.
                "capability": capability.get(device.install_id),
            }
        )
    return out


async def roaming_summary(session: AsyncSession) -> dict[str, Any]:
    """Where a SIM's own operator is not the network carrying it.

    Two names travel with every reading. The PLMN says whose radio served the
    phone; the string the handset prints is the SIM's service provider, which
    follows the subscription. When they differ the phone is being carried by
    somebody else's network.

    That is a finding rather than an error. For the subscriber, their
    operator's coverage in that place *is* the host network's coverage, so a
    village served only through roaming is a competition question, not a tower
    question — and the remedy is a commercial agreement rather than capital.

    Reported names that match no known operator are ignored rather than
    guessed at. Inventing a roaming relationship between two named companies
    would be worse than reporting nothing.
    """
    rows = (
        await session.execute(
            select(
                Measurement.mcc,
                Measurement.mnc,
                Measurement.operator_name,
                func.count(),
                func.count(func.distinct(Measurement.h3_index)),
            )
            .where(Measurement.mcc.is_not(None), Measurement.operator_name.is_not(None))
            .group_by(Measurement.mcc, Measurement.mnc, Measurement.operator_name)
        )
    ).all()

    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    agreeing = 0
    unknown = 0

    for mcc, mnc, reported, count, hexagons in rows:
        serving = NETWORK_NAMES.get((mcc, normalise_mnc(mnc) or ""))
        sim = operator_from_reported_name(reported)

        if serving is None or sim is None:
            unknown += count
            continue
        if serving == sim:
            agreeing += count
            continue

        entry = pairs.setdefault(
            (sim, serving),
            {"sim_operator": sim, "served_by": serving, "measurements": 0, "hexagons": 0},
        )
        entry["measurements"] += count
        entry["hexagons"] += hexagons

    roaming = sorted(pairs.values(), key=lambda row: -row["measurements"])
    total = agreeing + sum(row["measurements"] for row in roaming)

    return {
        "pairs": roaming,
        "measurements_agreeing": agreeing,
        "measurements_roaming": sum(row["measurements"] for row in roaming),
        "measurements_unidentified": unknown,
        # The figure that says whether to believe any of this. A handful of
        # roaming readings is ordinary; most of the fleet apparently roaming
        # means the PLMN table is wrong, not that the country is.
        "roaming_share_pct": (
            round(sum(row["measurements"] for row in roaming) / total * 100, 1) if total else 0.0
        ),
    }


# How close two cells must be to count as the same mast.
#
# An operator puts three or more sectors on one structure, each broadcasting its
# own identity, so counting cells counts antennas rather than towers. 150 m is
# wider than any single structure and far tighter than the spacing between
# sites, so it separates masts without merging neighbours.
SAME_SITE_METRES = 150.0


def _cluster_sites(points: list[tuple[float, float]]) -> int:
    """How many distinct structures a set of cell positions represents."""
    taken: set[int] = set()
    sites = 0
    for index, (lat, lon) in enumerate(points):
        if index in taken:
            continue
        sites += 1
        taken.add(index)
        for other in range(index + 1, len(points)):
            if other in taken:
                continue
            if haversine_m(lat, lon, points[other][0], points[other][1]) <= SAME_SITE_METRES:
                taken.add(other)
    return sites


async def tower_summary(session: AsyncSession, area: str | None = None) -> dict[str, Any]:
    """Base stations per operator, for the country or one area.

    Three figures per operator, because they answer different questions and
    conflating them would overstate the network:

    * ``cells`` — distinct broadcast identities heard. The rawest count.
    * ``cells_placed`` — those the readings were spread widely enough to put a
      position on. Always fewer, and only these can be mapped or clustered.
    * ``sites`` — placed cells grouped by proximity, which is the closest this
      platform gets to counting masts. An operator running three sectors on one
      structure appears as three cells and one site, and it is the site that
      corresponds to a thing standing in a field.

    Every count is of what the fleet has *heard*, never of what an operator
    owns. A network is only present here where somebody drove carrying its SIM
    or within earshot of its cells, so these are lower bounds on a network and
    an upper bound on nothing.
    """
    query = select(ObservedCell)
    if area:
        query = query.where(
            (ObservedCell.adm1_code == area) | (ObservedCell.adm2_code == area)
        )
    cells = (await session.scalars(query)).all()

    by_operator: dict[str, dict[str, Any]] = {}
    for cell in cells:
        name = cell.operator_name or f"{cell.mcc}-{cell.mnc}"
        entry = by_operator.setdefault(
            name,
            {"operator": name, "cells": 0, "cells_placed": 0, "sites": 0, "_points": []},
        )
        entry["cells"] += 1
        if cell.position_is_reliable:
            entry["cells_placed"] += 1
            entry["_points"].append((cell.est_lat, cell.est_lon))

    operators = []
    for entry in by_operator.values():
        entry["sites"] = _cluster_sites(entry.pop("_points"))
        operators.append(entry)

    # Every Lao network listed, measured or not. A table showing only the ones
    # with towers in it would read as though the others have none, when it
    # means nobody has carried their SIM down this road.
    present = {row["operator"] for row in operators}
    for name in NETWORK_NAMES.values():
        if name not in present:
            operators.append({"operator": name, "cells": 0, "cells_placed": 0, "sites": 0})

    operators.sort(key=lambda row: (-row["sites"], -row["cells"], row["operator"]))
    return {
        "area": area,
        "operators": operators,
        "cells": sum(row["cells"] for row in operators),
        "sites": sum(row["sites"] for row in operators),
    }
