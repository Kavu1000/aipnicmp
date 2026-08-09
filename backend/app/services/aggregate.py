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

from sqlalchemy import String, and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.operators import NETWORK_NAMES
from app.core.radio import STATE_COLOUR, STATE_SCORE, RadioState, TileColour
from app.models.measurement import Measurement
from app.models.tile import H3Tile, H3TileOperator
from app.services.areas import AreaAssignment, AreaResolver, load_resolver
from app.services.geo import h3_centroid

SCORE_STATE = {score: state for state, score in STATE_SCORE.items()}

NO_AREAS = AreaAssignment()


def _padded_mnc():
    """MNC as two digits. One handset reports "1" where another reports "01".

    Concatenation is written with ``+`` on a String column, which SQLAlchemy
    renders as the ``||`` operator. ``concat()`` is a Postgres function and
    does not exist in the SQLite the tests run on.
    """
    return case(
        (func.length(Measurement.mnc) == 1, literal("0", String) + Measurement.mnc),
        else_=Measurement.mnc,
    )


def canonical_operator_column():
    """The operator's identity, as SQL, so grouping happens in the database.

    Resolved from MCC/MNC rather than from the name the handset reported —
    see app/core/operators.py for why one company otherwise appears as several.

    It has to be an expression rather than a Python pass because the aggregate
    it feeds counts *distinct devices*, and distinct counts cannot be summed
    back together after the fact: a collector seen under two spellings of one
    network is one collector, and folding the groups in Python would report two.
    """
    mnc = _padded_mnc()
    known = [
        (and_(Measurement.mcc == mcc, mnc == network_mnc), name)
        for (mcc, network_mnc), name in NETWORK_NAMES.items()
    ]
    return case(
        *known,
        # A network not in the table keeps its stable identity as a code, which
        # is honest and obviously not a company name.
        (
            and_(Measurement.mcc.is_not(None), mnc.is_not(None)),
            Measurement.mcc + literal("-", String) + mnc,
        ),
        else_=func.trim(Measurement.operator_name),
    )


def _has_operator_identity():
    """Something to attribute the reading to — a PLMN, or failing that a name.

    A reading with no network at all has neither, and is excluded: bucketing
    those into "unknown" would put dead zones on some carrier's ledger.
    """
    return or_(
        and_(Measurement.mcc.is_not(None), Measurement.mnc.is_not(None)),
        and_(
            Measurement.operator_name.is_not(None),
            func.trim(Measurement.operator_name) != "",
        ),
    )


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


class _AreaTagger:
    """Resolves each hexagon to its administrative areas, once.

    The combined and per-operator passes both need the answer for the same
    hexagons, and a point-in-polygon test is the most expensive thing in a
    rebuild, so results are memoised across both.

    When no boundaries have been imported this does nothing at all and every
    tile keeps a null area — the platform is fully usable before anyone loads a
    boundary file, it simply has no area filter yet.
    """

    def __init__(self, resolver: AreaResolver) -> None:
        self._resolver = resolver
        self._active = not resolver.is_empty
        self._cache: dict[str, AreaAssignment] = {}

    def of(self, h3_index: str, lat: float, lon: float) -> AreaAssignment:
        if not self._active:
            return NO_AREAS
        cached = self._cache.get(h3_index)
        if cached is None:
            cached = self._resolver.assign(lat, lon)
            self._cache[h3_index] = cached
        return cached


def _apply_areas(tile: H3Tile | H3TileOperator, areas: AreaAssignment) -> None:
    tile.adm1_code = areas.adm1
    tile.adm2_code = areas.adm2
    tile.adm3_code = areas.adm3


async def rebuild_tiles(session: AsyncSession, *, since: datetime | None = None) -> int:
    """Recompute every tile from the measurements. Returns the number written.

    A measured tile always overrides a predicted one: ``is_predicted`` is
    cleared here, so a single real reading immediately replaces the model's
    guess for that hexagon. A prediction must never outrank a measurement.
    """
    counts = await _state_counts(session, since)
    metrics = await _tile_metrics(session, since)
    tagger = _AreaTagger(await load_resolver(session))

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
        _apply_areas(tile, tagger.of(h3_index, lat, lon))
        tile.first_measured_at = row["first_measured_at"]
        tile.last_measured_at = row["last_measured_at"]
        tile.updated_at = datetime.now(timezone.utc)
        written += 1

    await session.flush()
    await _rebuild_operator_tiles(session, since, tagger)
    await session.commit()
    return written


async def _rebuild_operator_tiles(
    session: AsyncSession, since: datetime | None, tagger: _AreaTagger
) -> int:
    """The same hexagons again, split by operator.

    A village where one network works and three do not is a different finding
    from one where none do — the first is a competition and roaming question,
    the second is a tower question. The combined map cannot say which it is.

    Records with no operator identity are skipped rather than bucketed into
    "unknown": a reading with no network at all has no operator to attribute it
    to, and inventing one would put dead zones on some carrier's ledger.

    Operators are identified by MCC/MNC, not by the name the handset reported.
    Grouping by the reported name splits one company across several partial
    maps, because the string comes from the SIM or the firmware and they
    disagree — see app/core/operators.py.
    """
    operator = canonical_operator_column().label("operator_name")
    identified = (Measurement.h3_index.is_not(None), _has_operator_identity())

    state_query = (
        select(
            Measurement.h3_index,
            operator,
            Measurement.radio_state,
            func.count(),
        )
        .where(*identified)
        .group_by(Measurement.h3_index, operator, Measurement.radio_state)
    )
    metric_query = (
        select(
            Measurement.h3_index,
            operator,
            func.count().label("measurement_count"),
            func.count(func.distinct(Measurement.device_id)).label("device_count"),
            func.avg(Measurement.rsrp_dbm).label("avg_rsrp_dbm"),
            func.avg(Measurement.download_kbps).label("avg_download_kbps"),
            func.max(Measurement.captured_at).label("last_measured_at"),
        )
        .where(*identified)
        .group_by(Measurement.h3_index, operator)
    )
    if since is not None:
        state_query = state_query.where(Measurement.captured_at >= since)
        metric_query = metric_query.where(Measurement.captured_at >= since)

    counts: dict[tuple[str, str], dict[str, int]] = {}
    for h3_index, operator, state, count in (await session.execute(state_query)).all():
        counts.setdefault((h3_index, operator), {})[state] = count

    rows = (await session.execute(metric_query)).mappings().all()
    keys = [(row["h3_index"], row["operator_name"]) for row in rows]

    existing: dict[tuple[str, str], H3TileOperator] = {}
    if keys:
        found = await session.scalars(
            select(H3TileOperator).where(
                H3TileOperator.h3_index.in_({k[0] for k in keys}),
                H3TileOperator.operator_name.in_({k[1] for k in keys}),
            )
        )
        existing = {(t.h3_index, t.operator_name): t for t in found.all()}

    written = 0
    for row in rows:
        key = (row["h3_index"], row["operator_name"])
        tile_counts = counts.get(key, {})
        median = median_state(tile_counts)
        worst = worst_state(tile_counts)
        lat, lon = h3_centroid(row["h3_index"])

        tile = existing.get(key)
        if tile is None:
            tile = H3TileOperator(h3_index=key[0], operator_name=key[1])
            session.add(tile)

        tile.centroid_lat = lat
        tile.centroid_lon = lon
        tile.colour = (STATE_COLOUR[median] if median else TileColour.GREY).value
        tile.dominant_state = median.value if median else None
        tile.worst_state = worst.value if worst else None
        tile.measurement_count = row["measurement_count"]
        tile.device_count = row["device_count"]
        tile.avg_rsrp_dbm = row["avg_rsrp_dbm"]
        tile.avg_download_kbps = row["avg_download_kbps"]
        _apply_areas(tile, tagger.of(key[0], lat, lon))
        tile.last_measured_at = row["last_measured_at"]
        tile.updated_at = datetime.now(timezone.utc)
        written += 1

    if since is None:
        await _drop_stale_operator_tiles(session, set(keys))

    return written


async def _drop_stale_operator_tiles(
    session: AsyncSession, current: set[tuple[str, str]]
) -> int:
    """Remove operator tiles the measurements no longer support.

    Aggregation only ever wrote rows; nothing removed them. That was invisible
    until an operator's name changed — when the same company was recognised
    under a new name, the row under the old one stayed on the map forever, and
    the network filter offered both.

    Only on a full rebuild. An incremental run has deliberately looked at a
    slice of the measurements, so anything outside that slice is missing, not
    stale, and deleting it would erase the rest of the map.
    """
    existing = (await session.scalars(select(H3TileOperator))).all()
    dropped = 0
    for tile in existing:
        if (tile.h3_index, tile.operator_name) not in current:
            await session.delete(tile)
            dropped += 1
    return dropped
