"""Aggregation of measurement points into H3 tiles.

Nothing individual is ever published. This is the step that turns a trail of
one person's journey into a statement about a place (proposal 2.4).

Runs as a background job rather than on write: aggregation is cheap to redo and
expensive to get wrong, and re-running it is how thresholds get retuned.

The tile colour comes from the *median* state, computed from per-state counts
rather than from every row, so a national rebuild moves a few thousand rows
instead of a few million.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.radio import STATE_COLOUR, STATE_SCORE, RadioState, TileColour
from app.models.measurement import Measurement
from app.models.tile import H3Tile
from app.services.geo import h3_centroid

SCORE_STATE = {score: state for state, score in STATE_SCORE.items()}


def median_state(counts: dict[str, int]) -> RadioState | None:
    """Median state given how many measurements fell into each state.

    The median resists outliers in a way the mean cannot: a phone in a bag or a
    minute spent inside a concrete building should not turn a working area red,
    and one lucky reading beside a window should not turn a dead area green.
    """
    total = sum(counts.values())
    if total == 0:
        return None

    target = total // 2
    seen = 0
    for score in sorted(SCORE_STATE):
        state = SCORE_STATE[score]
        seen += counts.get(state.value, 0)
        if seen > target:
            return state
    return SCORE_STATE[max(SCORE_STATE)]


def worst_state(counts: dict[str, int]) -> RadioState | None:
    """The worst state ever seen in this tile.

    Kept alongside the median because "usually fine, but sometimes nothing at
    all" is a real and actionable finding for an operator, and a median alone
    hides it.
    """
    present = [SCORE_STATE[STATE_SCORE[state]] for state in RadioState if counts.get(state.value)]
    if not present:
        return None
    return min(present, key=lambda state: STATE_SCORE[state])


async def _state_counts(session: AsyncSession, since: datetime | None) -> dict[str, dict[str, int]]:
    query = (
        select(Measurement.h3_index, Measurement.radio_state, func.count())
        .where(Measurement.h3_index.is_not(None))
        .group_by(Measurement.h3_index, Measurement.radio_state)
    )
    if since is not None:
        query = query.where(Measurement.captured_at >= since)

    counts: dict[str, dict[str, int]] = {}
    for h3_index, state, count in (await session.execute(query)).all():
        counts.setdefault(h3_index, {})[state] = count
    return counts


async def _tile_metrics(session: AsyncSession, since: datetime | None):
    query = (
        select(
            Measurement.h3_index,
            func.count().label("measurement_count"),
            func.count(func.distinct(Measurement.device_id)).label("device_count"),
            func.avg(Measurement.rsrp_dbm).label("avg_rsrp_dbm"),
            func.avg(Measurement.download_kbps).label("avg_download_kbps"),
            func.avg(Measurement.latency_ms).label("avg_latency_ms"),
            func.min(Measurement.captured_at).label("first_measured_at"),
            func.max(Measurement.captured_at).label("last_measured_at"),
        )
        .where(Measurement.h3_index.is_not(None))
        .group_by(Measurement.h3_index)
    )
    if since is not None:
        query = query.where(Measurement.captured_at >= since)
    return (await session.execute(query)).mappings().all()


async def rebuild_tiles(session: AsyncSession, *, since: datetime | None = None) -> int:
    """Recompute every tile from the measurements. Returns the number written.

    A measured tile always overrides a predicted one: ``is_predicted`` is
    cleared here, so a single real reading immediately replaces the model's
    guess for that hexagon. A prediction must never outrank a measurement.
    """
    counts = await _state_counts(session, since)
    metrics = await _tile_metrics(session, since)

    existing = {
        tile.h3_index: tile
        for tile in (
            await session.scalars(
                select(H3Tile).where(H3Tile.h3_index.in_([m["h3_index"] for m in metrics]))
            )
        ).all()
    } if metrics else {}

    written = 0
    for row in metrics:
        h3_index = row["h3_index"]
        tile_counts = counts.get(h3_index, {})
        median = median_state(tile_counts)
        worst = worst_state(tile_counts)
        lat, lon = h3_centroid(h3_index)

        tile = existing.get(h3_index)
        if tile is None:
            tile = H3Tile(h3_index=h3_index)
            session.add(tile)

        tile.resolution = settings.h3_resolution
        tile.centroid_lat = lat
        tile.centroid_lon = lon
        tile.colour = (STATE_COLOUR[median] if median else TileColour.GREY).value
        tile.state_score = float(STATE_SCORE[median]) if median else None
        tile.dominant_state = median.value if median else None
        tile.worst_state = worst.value if worst else None
        tile.measurement_count = row["measurement_count"]
        tile.device_count = row["device_count"]
        tile.avg_rsrp_dbm = row["avg_rsrp_dbm"]
        tile.avg_download_kbps = row["avg_download_kbps"]
        tile.avg_latency_ms = row["avg_latency_ms"]
        tile.is_predicted = False
        tile.prediction_confidence = None
        tile.first_measured_at = row["first_measured_at"]
        tile.last_measured_at = row["last_measured_at"]
        tile.updated_at = datetime.now(timezone.utc)
        written += 1

    await session.commit()
    return written
