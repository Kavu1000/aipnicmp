"""Estimate where each base station cell stands, from the fleet's own readings.

Every measurement records the cells the handset could see and how strongly, so
the network can be mapped from the road instead of bought from OpenCelliD as
proposal 2.5(1) assumed. The picture sharpens with each drive.

What this can and cannot do is the whole point of the file.

A phone measures signal strength, not direction. One reading says only that the
cell is somewhere within range: a disc, not a point. Overlapping many discs
taken from *different places* narrows it; taking a hundred readings from one
spot does not, however confident the arithmetic looks afterwards. So every
estimate is stored with the spread it came from, and marked unreliable unless
the readings were spread widely enough to have constrained anything.

    python -m scripts.estimate_cell_sites --dry-run
    python -m scripts.estimate_cell_sites
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math

from sqlalchemy import delete, text

from app.core.operators import canonical_operator
from app.db.session import SessionLocal
from app.services.areas import load_resolver
from app.models.cell import ObservedCell

log = logging.getLogger("cells")

# Observations needed before a cell is considered at all.
MIN_OBSERVATIONS = 5

# How far apart the readings must spread before a position means anything.
#
# A cell's own coverage is typically 1-5 km. Readings confined to less than this
# are all effectively from the same place as far as the geometry is concerned,
# and their weighted centre lands wherever the collector happened to drive
# rather than where the mast stands. 800 m is deliberately modest: enough to
# have moved meaningfully through the cell, not so strict that only a highway
# would ever qualify.
MIN_SPREAD_M = 800.0

EARTH_RADIUS_M = 6_371_008.8


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def weight_of(rsrp: float | None) -> float:
    """How much a reading pulls the estimate toward itself.

    Signal strength is the only clue to distance a handset offers, and a weak
    one: fading and obstruction move RSRP by tens of dB with no change in
    distance at all. So this leans gently. A reading 60 dB stronger counts for
    five times more, not a thousand times, because treating dB as a distance
    would be trusting a number that has not earned it.
    """
    if rsrp is None:
        return 1.0
    return 1.0 + 4.0 * max(0.0, min(1.0, (rsrp + 120.0) / 60.0))


def widest_separation(points: list[tuple]) -> float:
    """The distance between the two furthest-apart readings.

    Not the scatter about their own centre, which stays small however far the
    collector drove, and would call a cell heard along ten kilometres of road
    just as tightly clustered as one heard from a car park.
    """
    widest = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            widest = max(
                widest,
                metres_between(points[i][0], points[i][1], points[j][0], points[j][1]),
            )
    return widest


async def build(dry_run: bool = False) -> int:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT co.mcc, co.mnc, co.lac_tac, co.cid,
                           m.lat, m.lon, co.rsrp_dbm, m.captured_at
                    FROM cell_observations co
                    JOIN measurements m ON m.id = co.measurement_id
                    WHERE co.mcc IS NOT NULL
                      AND co.mnc IS NOT NULL
                      AND co.cid IS NOT NULL
                      AND co.lac_tac IS NOT NULL
                      AND co.lac_tac NOT IN (0, 65535)
                      AND co.cid > 100
                    """
                )
            )
        ).all()

    # The filter above drops placeholders rather than cells. Android reports an
    # unavailable identity as 0 or 65535 and a neighbour it can see but not
    # identify with a tiny index; left in, those merge dozens of real masts into
    # one fictional cell apparently heard across the whole country.
    grouped: dict[tuple, list] = {}
    for mcc, mnc, lac, cid, lat, lon, rsrp, at in rows:
        grouped.setdefault((mcc, mnc, lac, cid), []).append((lat, lon, rsrp, at))

    log.info("identified cells with any observation: %d", len(grouped))

    async with SessionLocal() as session:
        resolver = await load_resolver(session)

    estimates: list[ObservedCell] = []
    for (mcc, mnc, lac, cid), points in grouped.items():
        if len(points) < MIN_OBSERVATIONS:
            continue

        weights = [weight_of(p[2]) for p in points]
        total = sum(weights)
        est_lat = sum(p[0] * w for p, w in zip(points, weights)) / total
        est_lon = sum(p[1] * w for p, w in zip(points, weights)) / total

        spread = widest_separation(points)
        with_rsrp = [p for p in points if p[2] is not None]
        best = max(with_rsrp, key=lambda p: p[2]) if with_rsrp else None
        times = [p[3] for p in points if p[3] is not None]

        estimates.append(
            ObservedCell(
                mcc=mcc,
                mnc=mnc,
                lac_tac=lac,
                cid=cid,
                operator_name=canonical_operator(mcc, mnc, None),
                adm1_code=resolver.assign(est_lat, est_lon).adm1,
                adm2_code=resolver.assign(est_lat, est_lon).adm2,
                observations=len(points),
                est_lat=est_lat,
                est_lon=est_lon,
                spread_m=round(spread, 1),
                # Never better than the spread the readings came from. A
                # tighter figure would be inventing precision the geometry
                # cannot supply.
                uncertainty_m=round(max(spread / 2.0, 250.0), 1),
                position_is_reliable=spread >= MIN_SPREAD_M,
                best_rsrp_dbm=best[2] if best else None,
                best_lat=best[0] if best else None,
                best_lon=best[1] if best else None,
                first_seen_at=min(times) if times else None,
                last_seen_at=max(times) if times else None,
            )
        )

    reliable = [e for e in estimates if e.position_is_reliable]
    log.info("cells with %d+ observations: %d", MIN_OBSERVATIONS, len(estimates))
    log.info("of those, spread far enough to place: %d", len(reliable))

    for cell in sorted(estimates, key=lambda c: -c.observations)[:10]:
        verdict = "placed" if cell.position_is_reliable else "too tightly clustered"
        log.info(
            "  %s-%s-%s-%s  %d obs  spread %.0f m  best %s dBm  -> %s",
            cell.mcc,
            cell.mnc,
            cell.lac_tac,
            cell.cid,
            cell.observations,
            cell.spread_m,
            cell.best_rsrp_dbm,
            verdict,
        )

    if dry_run:
        return len(estimates)

    async with SessionLocal() as session:
        # Replaced wholesale rather than merged: every figure here is derived
        # from the whole measurement history, so a partial update would leave
        # rows describing a fleet that no longer exists.
        await session.execute(delete(ObservedCell))
        session.add_all(estimates)
        await session.commit()

    log.info("wrote %d cells (%d with a usable position)", len(estimates), len(reliable))
    return len(estimates)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(build(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
