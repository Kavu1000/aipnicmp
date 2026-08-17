"""What one collector covered, and nothing else.

Every endpoint here is scoped to the handsets the calling account owns, and an
account owns nothing until a super admin says otherwise. That is the whole
router: there is no parameter for whose data to show, because a parameter is a
thing a client can change.

The hexagons are computed from this account's own measurements rather than read
from ``h3_tiles``. Those tiles are aggregated across every device that passed
through, so serving them to a collector would hand them readings taken by other
people — the exact thing the role exists to prevent, arriving through the door
marked "your own coverage".

That recomputation is affordable because one collector's history is small: the
busiest handset in this fleet has about 2,500 readings, against 3,000 for the
whole platform. If a single account ever reaches the point where this is slow,
the answer is a per-account aggregation table, not a shortcut through the
shared one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.radio import STATE_COLOUR, RadioState
from app.db.session import get_session
from app.models.device import Device
from app.models.measurement import Measurement
from app.services.auth import own_devices
from app.services.coverage import android_version, reporting_capability
from app.services.geo import h3_polygon_geojson

router = APIRouter(prefix="/mine", tags=["mine"])


def _median_state(states: list[str]) -> RadioState | None:
    """The same statistic the public map uses, so the two cannot disagree."""
    from app.core.radio import STATE_SCORE

    if not states:
        return None
    scores = sorted(STATE_SCORE[RadioState(s)] for s in states if s)
    if not scores:
        return None
    middle = scores[len(scores) // 2]
    return next(state for state, score in STATE_SCORE.items() if score == middle)


@router.get("/devices")
async def my_devices(
    devices: frozenset[str] = Depends(own_devices),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The handsets assigned to this account, and how they are behaving."""
    if not devices:
        return {"devices": []}

    rows = (
        await session.scalars(select(Device).where(Device.install_id.in_(devices)))
    ).all()
    capability = await reporting_capability(session)

    return {
        "devices": [
            {
                "id": device.install_id[:16],
                "model": device.model,
                "manufacturer": device.manufacturer,
                "android_version": android_version(device.android_api),
                "app_version": device.app_version,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "records_accepted": device.records_accepted,
                "records_rejected": device.records_rejected,
                "capability": capability.get(device.install_id),
            }
            for device in sorted(rows, key=lambda d: -(d.records_accepted or 0))
        ]
    }


@router.get("/summary")
async def my_summary(
    devices: frozenset[str] = Depends(own_devices),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """How much ground this account has covered, and how it came out."""
    if not devices:
        return {"measurements": 0, "hexagons": 0, "by_state": {}, "networks": [], "latest": None}

    rows = (
        await session.execute(
            select(
                Measurement.h3_index,
                Measurement.radio_state,
                Measurement.operator_name,
                Measurement.captured_at,
            ).where(Measurement.device_id.in_(devices))
        )
    ).all()

    per_hexagon: dict[str, list[str]] = {}
    by_state: dict[str, int] = {}
    networks: dict[str, int] = {}
    latest = None
    for h3_index, state, network, captured_at in rows:
        if h3_index and state:
            per_hexagon.setdefault(h3_index, []).append(state)
        if state:
            by_state[state] = by_state.get(state, 0) + 1
        if network:
            networks[network] = networks.get(network, 0) + 1
        if captured_at and (latest is None or captured_at > latest):
            latest = captured_at

    return {
        "measurements": len(rows),
        "hexagons": len(per_hexagon),
        "by_state": by_state,
        # The networks this account's own handsets were on. Not a view of any
        # operator's coverage — just which SIMs these phones carried.
        "networks": sorted(networks, key=networks.get, reverse=True),
        "latest": latest.isoformat() if latest else None,
    }


@router.get("/tiles")
async def my_tiles(
    devices: frozenset[str] = Depends(own_devices),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The ground this account personally covered, as hexagons.

    Built from this account's measurements alone. The shared tiles aggregate
    every device that passed through a hexagon, so a hexagon this collector
    drove once and somebody else drove forty times would arrive carrying the
    other person's forty readings.
    """
    if not devices:
        return {"type": "FeatureCollection", "features": []}

    rows = (
        await session.execute(
            select(
                Measurement.h3_index,
                Measurement.radio_state,
                func.count().label("readings"),
            )
            .where(Measurement.device_id.in_(devices), Measurement.h3_index.is_not(None))
            .group_by(Measurement.h3_index, Measurement.radio_state)
        )
    ).all()

    per_hexagon: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for h3_index, state, readings in rows:
        counts[h3_index] = counts.get(h3_index, 0) + readings
        if state:
            per_hexagon.setdefault(h3_index, []).extend([state] * readings)

    features = []
    for h3_index, states in per_hexagon.items():
        state = _median_state(states)
        if state is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": h3_polygon_geojson(h3_index),
                "properties": {
                    "h3": h3_index,
                    "state": state.value,
                    "colour": STATE_COLOUR[state].value,
                    "measurements": counts[h3_index],
                    # No device count and no timestamp. This account already
                    # knows both — they are its own — but the field names are
                    # the ones the public map withholds, and leaving them out
                    # keeps one shape for "a hexagon" across the platform.
                    "predicted": False,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}
