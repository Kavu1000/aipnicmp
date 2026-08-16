"""Age exact GPS fixes down to the hexagon they already belong to.

A collector's readings are a position every ten seconds for as long as they were
moving. Individually that is a coverage measurement; together it is a record of
where a person went, who they visited and when they were at home. The map has
never published it — every public view aggregates to hexagons — but the database
held it indefinitely, and "we do not show it" is a weaker promise than "we do
not keep it".

So after a while the coordinates are replaced by the centre of the hexagon they
were already assigned to. Nothing the platform publishes changes: tiles are
built from ``h3_index``, and the centre of a hexagon is still inside that same
hexagon. What is lost is the ability to reconstruct a route, which is the point.

This is irreversible by design. It runs on a schedule rather than on request so
that it happens without anyone having to remember, and it is deliberately
narrow: it does not delete rows, and it does not touch signal, timing, cell
identity or anything else the coverage findings rest on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.measurement import Measurement
from app.services.geo import h3_centroid

log = logging.getLogger(__name__)

#: Rows per pass. Large enough to finish in a few sweeps, small enough that the
#: statement never holds a long write lock on the busiest table.
BATCH_SIZE = 5_000


async def coarsen_old_fixes(
    session: AsyncSession,
    *,
    older_than_days: int | None = None,
    now: datetime | None = None,
    limit: int = BATCH_SIZE,
) -> int:
    """Replace exact coordinates older than the retention window.

    Returns the number of readings coarsened. Rows without an ``h3_index`` are
    left alone: there is no hexagon to fall back to, and inventing a position
    would be worse than keeping the true one.
    """
    days = settings.retention_precise_days if older_than_days is None else older_than_days
    if days <= 0:
        # Configured to keep exact fixes. Not an error, but it should be a
        # visible decision rather than a silent default.
        log.info("retention disabled (retention_precise_days=%s)", days)
        return 0

    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=days)

    rows = (
        await session.execute(
            select(Measurement.id, Measurement.h3_index)
            .where(
                Measurement.coarsened_at.is_(None),
                Measurement.captured_at < cutoff,
                Measurement.h3_index.is_not(None),
            )
            .order_by(Measurement.captured_at)
            .limit(limit)
        )
    ).all()

    if not rows:
        return 0

    # Grouped by hexagon so the centroid is computed once per hexagon rather
    # than once per reading — a long drive puts hundreds of readings in each.
    by_hexagon: dict[str, list[int]] = {}
    for row_id, h3_index in rows:
        by_hexagon.setdefault(h3_index, []).append(row_id)

    for h3_index, ids in by_hexagon.items():
        lat, lon = h3_centroid(h3_index)
        await session.execute(
            update(Measurement)
            .where(Measurement.id.in_(ids))
            .values(
                lat=lat,
                lon=lon,
                # The accuracy of a fix that is no longer a fix would be a
                # fiction, and a convincing one at three metres.
                gps_accuracy_m=None,
                coarsened_at=moment,
            )
        )

    await session.commit()
    log.info(
        "coarsened %d readings older than %d days across %d hexagons",
        len(rows),
        days,
        len(by_hexagon),
    )
    return len(rows)


async def retention_status(session: AsyncSession) -> dict[str, object]:
    """What is held, what has been aged out, and what is due.

    Exposed so the answer to "what do you keep?" is a query rather than a claim.
    """
    days = settings.retention_precise_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 0))

    total = await session.scalar(select(func.count()).select_from(Measurement)) or 0
    coarsened = (
        await session.scalar(
            select(func.count())
            .select_from(Measurement)
            .where(Measurement.coarsened_at.is_not(None))
        )
        or 0
    )
    due = (
        await session.scalar(
            select(func.count())
            .select_from(Measurement)
            .where(
                Measurement.coarsened_at.is_(None),
                Measurement.captured_at < cutoff,
                Measurement.h3_index.is_not(None),
            )
        )
        or 0
    )
    oldest_precise = await session.scalar(
        select(func.min(Measurement.captured_at)).where(Measurement.coarsened_at.is_(None))
    )

    return {
        "retention_precise_days": days,
        "measurements": total,
        "exact_fix_held": total - coarsened,
        "coarsened_to_hexagon": coarsened,
        "due_next_sweep": due,
        "oldest_exact_fix": oldest_precise.isoformat() if oldest_precise else None,
    }
