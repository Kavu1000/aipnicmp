"""Hexagons whose service changed between one visit and the next.

The one question this platform can answer well today. Everything else it might
predict extrapolates from 299 measured hexagons to a country of 279,925; this
compares a hexagon against *itself*, so it extrapolates nothing and needs no
national coverage to be trustworthy.

It is also the finding with the shortest path to an action. A hexagon that read
green last week and red today is either an outage somebody can be told about or
a measurement problem somebody should look at, and both are worth knowing
within a day rather than at the end of a survey.

Deliberately not a model. The comparison is a median of readings before against
a median of readings after, which is the same statistic the map already
publishes — so a change reported here is visible on the map for the same reason,
and can be checked by eye. A learned anomaly score would be harder to argue
with and no more correct at this scale.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import STATE_SCORE, RadioState, aggregate_colour
from app.models.measurement import Measurement

#: Readings needed on each side before a change is reported.
#:
#: One reading either side is a coin toss: a phone momentarily on the far edge
#: of a hexagon, or a handover caught mid-flight, will differ from its
#: neighbour for reasons that have nothing to do with the network. Three is
#: enough for the median to mean something without demanding a survey.
MIN_READINGS_EACH_SIDE = 3


def _median_state(states: list[RadioState]) -> RadioState:
    scores = sorted(STATE_SCORE[state] for state in states)
    middle = scores[len(scores) // 2]
    return next(state for state, score in STATE_SCORE.items() if score == middle)


async def detect_changes(
    session: AsyncSession,
    *,
    window_days: int = 7,
    now: datetime | None = None,
    min_readings: int = MIN_READINGS_EACH_SIDE,
) -> list[dict[str, Any]]:
    """Compare each hexagon's recent readings against its earlier ones.

    Returns one entry per hexagon that moved, worst first, with the counts
    behind both sides so a reader can judge how much evidence there is rather
    than being handed a verdict.

    Only hexagons measured on *both* sides appear. A hexagon visited once and
    never again has not changed; it is simply old, which is a different finding
    and belongs to the freshness figures.
    """
    moment = now or datetime.now(timezone.utc)
    boundary = moment - timedelta(days=window_days)

    rows = (
        await session.execute(
            select(
                Measurement.h3_index,
                Measurement.radio_state,
                Measurement.captured_at,
                Measurement.lat,
                Measurement.lon,
            ).where(Measurement.h3_index.is_not(None))
        )
    ).all()

    before: dict[str, list[RadioState]] = {}
    after: dict[str, list[RadioState]] = {}
    where: dict[str, tuple[float, float]] = {}

    for h3_index, state, captured_at, lat, lon in rows:
        if state is None:
            continue
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        bucket = after if captured_at >= boundary else before
        bucket.setdefault(h3_index, []).append(RadioState(state))
        where.setdefault(h3_index, (lat, lon))

    found: list[dict[str, Any]] = []
    for h3_index, recent in after.items():
        earlier = before.get(h3_index, [])
        if len(recent) < min_readings or len(earlier) < min_readings:
            continue

        was, is_now = _median_state(earlier), _median_state(recent)
        if was == is_now:
            continue

        # Positive means it got worse, which is the direction that needs
        # somebody told. Signed rather than absolute so a recovery is not
        # reported as a fault.
        drop = STATE_SCORE[was] - STATE_SCORE[is_now]
        lat, lon = where[h3_index]
        found.append(
            {
                "h3_index": h3_index,
                "lat": lat,
                "lon": lon,
                "was": was.value,
                "is_now": is_now.value,
                "colour_was": aggregate_colour([was]).value,
                "colour_now": aggregate_colour([is_now]).value,
                "direction": "worse" if drop > 0 else "better",
                "steps": abs(drop),
                "readings_before": len(earlier),
                "readings_after": len(recent),
                "since": boundary.isoformat(),
            }
        )

    # Worst first, then by weight of evidence: a two-step drop seen ten times
    # is a more useful thing to be shown than a one-step drop seen three.
    found.sort(
        key=lambda item: (
            item["direction"] != "worse",
            -item["steps"],
            -(item["readings_before"] + item["readings_after"]),
        )
    )
    return found
