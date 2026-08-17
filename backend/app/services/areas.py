"""Placing hexagons inside administrative areas, and summarising coverage there.

Two jobs live here.

**Assignment** happens once per rebuild: every tile centroid is resolved to a
province, district and village, and the codes are stored on the tile. Doing it
here rather than at query time is what keeps "show me Oudomxay" an indexed
lookup on a server with no PostGIS.

**Summary** is the dashboard side of the same idea: coverage totals for one
area, or for every child of one area at once — the second being what a
choropleth of 18 provinces needs in a single request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import settings
from app.core.radio import STATE_COLOUR, STATE_SCORE, RadioState, TileColour
from app.models.area import (
    LEVEL_COUNTRY,
    LEVEL_DISTRICT,
    LEVEL_PROVINCE,
    LEVEL_TILE_COLUMN,
    LEVEL_VILLAGE,
    AdminArea,
)
from app.models.measurement import Measurement
from app.models.tile import H3Tile, H3TileOperator
from app.services.coverage import INVESTMENT_ACTION, tile_area_km2
from app.services.geo import haversine_m
from app.services.polygon import ShapeIndex, bbox_of, shape_of
from app.services.network import canonical_operator_column, has_operator_identity

# How far from a village point the platform is willing to say "this is that
# village", when no polygon was published. Deliberately modest: a Lao village
# is a settlement, not a district, and a generous radius would quietly swallow
# the countryside between two of them.
DEFAULT_VILLAGE_RADIUS_M = 2_000.0


@dataclass(frozen=True)
class AreaAssignment:
    """The areas one point falls in. Any level may be unknown."""

    adm1: str | None = None
    adm2: str | None = None
    adm3: str | None = None


class _PointIndex:
    """Villages published as points rather than polygons.

    Answers "which village is this, if any" by nearest point inside that
    village's own stated radius. Restricting candidates to the district already
    resolved from real polygons stops a village just across the district line
    from claiming a hexagon that is not in it.
    """

    CELL_DEGREES = 0.5

    def __init__(self, entries: Iterable[tuple[str, float, float, float, str | None]]) -> None:
        self._grid: dict[tuple[int, int], list[tuple[str, float, float, float, str | None]]] = {}
        self._count = 0
        for entry in entries:
            _, lon, lat, radius_m, _ = entry
            self._count += 1
            # A point can be reached from a neighbouring bucket when its radius
            # crosses the line, so it is filed in every bucket its circle spans.
            span = radius_m / 111_320.0
            for x in self._cell_range(lon - span, lon + span):
                for y in self._cell_range(lat - span, lat + span):
                    self._grid.setdefault((x, y), []).append(entry)

    @classmethod
    def _cell_range(cls, low: float, high: float) -> range:
        return range(int(low // cls.CELL_DEGREES), int(high // cls.CELL_DEGREES) + 1)

    def __len__(self) -> int:
        return self._count

    def find(self, lon: float, lat: float, *, parent: str | None) -> str | None:
        bucket = self._grid.get(
            (int(lon // self.CELL_DEGREES), int(lat // self.CELL_DEGREES)), ()
        )
        best: tuple[float, str] | None = None
        for code, point_lon, point_lat, radius_m, parent_code in bucket:
            if parent is not None and parent_code is not None and parent_code != parent:
                continue
            distance = haversine_m(lat, lon, point_lat, point_lon)
            if distance <= radius_m and (best is None or distance < best[0]):
                best = (distance, code)
        return best[1] if best is not None else None


class AreaResolver:
    """An in-memory snapshot of the boundary table, built once per rebuild."""

    def __init__(
        self,
        *,
        provinces: ShapeIndex,
        districts: ShapeIndex,
        villages: ShapeIndex,
        village_points: _PointIndex,
        parents: dict[str, str | None],
    ) -> None:
        self._provinces = provinces
        self._districts = districts
        self._villages = villages
        self._village_points = village_points
        self._parents = parents

    @property
    def is_empty(self) -> bool:
        """True when no boundaries have been imported.

        The rebuild checks this and skips assignment entirely, so the platform
        runs perfectly well before anyone has loaded a boundary file — the map
        simply has no area filter until they do.
        """
        return not (
            len(self._provinces) or len(self._districts) or len(self._villages)
            or len(self._village_points)
        )

    def assign(self, lat: float, lon: float) -> AreaAssignment:
        """Resolve one point to its areas.

        Each level is decided by its own geometry, because that geometry is the
        authority for that level. Where a level has no geometry loaded, the
        parent chain of a deeper match fills it in — so importing districts
        alone still yields a usable province filter.
        """
        province = self._provinces.find(lon, lat)
        district = self._districts.find(lon, lat)
        village = self._villages.find(lon, lat)
        if village is None:
            village = self._village_points.find(lon, lat, parent=district)

        if district is None and village is not None:
            district = self._parents.get(village)
        if province is None and district is not None:
            province = self._parents.get(district)

        return AreaAssignment(adm1=province, adm2=district, adm3=village)


async def load_resolver(session: AsyncSession) -> AreaResolver:
    """Read every area into indexes suitable for point lookup."""
    areas = (await session.scalars(select(AdminArea))).all()

    shapes: dict[int, list[tuple[str, Any, Any]]] = {
        LEVEL_PROVINCE: [],
        LEVEL_DISTRICT: [],
        LEVEL_VILLAGE: [],
    }
    points: list[tuple[str, float, float, float, str | None]] = []
    parents: dict[str, str | None] = {}

    for area in areas:
        parents[area.code] = area.parent_code
        if area.level not in shapes:
            continue

        if area.boundary is not None:
            shape = shape_of(area.boundary)
            shapes[area.level].append((area.code, shape, bbox_of(shape)))
        elif area.level == LEVEL_VILLAGE:
            points.append(
                (
                    area.code,
                    area.centroid_lon,
                    area.centroid_lat,
                    area.radius_m or DEFAULT_VILLAGE_RADIUS_M,
                    area.parent_code,
                )
            )

    return AreaResolver(
        provinces=ShapeIndex(shapes[LEVEL_PROVINCE]),
        districts=ShapeIndex(shapes[LEVEL_DISTRICT]),
        villages=ShapeIndex(shapes[LEVEL_VILLAGE]),
        village_points=_PointIndex(points),
        parents=parents,
    )


def tile_column(level: int, *, operator: bool = False) -> InstrumentedAttribute | None:
    """The tile column carrying this level's code, or None for the country.

    Level 0 has no column because every tile in the database is in the country;
    storing that would be storing a constant.
    """
    model = H3TileOperator if operator else H3Tile
    name = LEVEL_TILE_COLUMN.get(level)
    return getattr(model, name) if name else None


async def area_or_none(session: AsyncSession, code: str) -> AdminArea | None:
    return await session.scalar(select(AdminArea).where(AdminArea.code == code))


async def children_of(
    session: AsyncSession, code: str | None, *, level: int | None = None
) -> Sequence[AdminArea]:
    query = select(AdminArea)
    if code is None:
        query = query.where(AdminArea.parent_code.is_(None))
    else:
        query = query.where(AdminArea.parent_code == code)
    if level is not None:
        query = query.where(AdminArea.level == level)
    return (await session.scalars(query.order_by(AdminArea.name_en.asc()))).all()


def _restrict(query: Select, column: InstrumentedAttribute | None, codes: Sequence[str] | None):
    if column is None or codes is None:
        return query
    return query.where(column.in_(codes))


async def coverage_by_area(
    session: AsyncSession,
    *,
    level: int,
    codes: Sequence[str] | None = None,
    operator: str | None = None,
) -> dict[str | None, dict[str, Any]]:
    """Coverage totals grouped by area code.

    Returns a mapping keyed by area code, or by ``None`` when summarising the
    country as a whole — level 0 has no column to group on, and grouping by a
    constant is not portable SQL.

    The device count is genuinely distinct, taken from the measurements rather
    than by summing per-tile counts: a collector who drove through forty
    hexagons is one collector, and the number is used to decide whether an
    area's detail may be published at all.
    """
    model = H3TileOperator if operator else H3Tile
    column = tile_column(level, operator=bool(operator))
    grouped = column is not None

    def base(query: Select) -> Select:
        query = _restrict(query, column, codes)
        if operator:
            query = query.where(H3TileOperator.operator_name == operator)
        else:
            # Predictions colour the map but must never be counted as evidence
            # in a total presented to a ministry.
            query = query.where(H3Tile.is_predicted.is_(False))
        return query

    # Grouped by state always — the area code is an *extra* grouping, added
    # below. Without this, the ungrouped country query counts every tile under
    # whichever state the database happened to return first, and the national
    # figure silently disagrees with the provinces that make it up.
    state_query = select(model.dominant_state, func.count()).group_by(model.dominant_state)
    metric_query = select(
        func.count().label("tiles"),
        func.sum(model.measurement_count).label("measurements"),
        func.avg(model.avg_rsrp_dbm).label("avg_rsrp_dbm"),
        func.avg(model.avg_download_kbps).label("avg_download_kbps"),
        func.max(model.last_measured_at).label("last_measured_at"),
    )
    device_query = (
        select(func.count(func.distinct(Measurement.device_id)).label("devices"))
        .select_from(Measurement)
        .join(model, model.h3_index == Measurement.h3_index)
    )
    if operator:
        # Canonical identity, not the string the handset reported. Every other
        # query in the project resolves an operator through MCC/MNC, because
        # one SIM comes back as "LTC" on one phone and "LAO TELECOM" on the
        # next. Matching the raw name here meant a province filtered by "Lao
        # Telecom" counted zero contributing devices while still reporting the
        # area those devices had measured — a panel contradicting itself.
        device_query = device_query.where(
            canonical_operator_column() == operator, has_operator_identity()
        )

    if grouped:
        state_query = state_query.add_columns(column).group_by(column)
        metric_query = metric_query.add_columns(column).group_by(column)
        device_query = device_query.add_columns(column).group_by(column)

    states: dict[str | None, dict[str, int]] = {}
    for row in (await session.execute(base(state_query))).all():
        state, count = row[0], row[1]
        key = row[2] if grouped else None
        if state:
            states.setdefault(key, {})[state] = count

    devices: dict[str | None, int] = {}
    for row in (await session.execute(base(device_query))).all():
        devices[row[1] if grouped else None] = row[0] or 0

    area_km2 = tile_area_km2()
    out: dict[str | None, dict[str, Any]] = {}

    for row in (await session.execute(base(metric_query))).mappings().all():
        key = row[column.key] if grouped else None
        tiles = row["tiles"] or 0
        if tiles == 0:
            continue

        by_state = states.get(key, {})
        by_action = {"new_tower": 0, "upgrade": 0, "optimisation": 0, "none": 0}
        for state_name, count in by_state.items():
            try:
                by_action[INVESTMENT_ACTION[RadioState(state_name)]] += count
            except ValueError:
                continue

        good = by_state.get(RadioState.LTE_GOOD.value, 0)
        unusable = by_state.get(RadioState.NO_CELL.value, 0) + by_state.get(
            RadioState.CELLS_VISIBLE_UNREGISTERED.value, 0
        )
        device_count = devices.get(key, 0)
        detailed = device_count >= settings.tile_min_devices
        state = _summary_state(by_state)

        out[key] = {
            "tiles": tiles,
            "devices": device_count,
            "measured_area_km2": round(tiles * area_km2, 4),
            "by_state": by_state,
            "by_action": by_action,
            "good_pct": round(good / tiles * 100, 1),
            "unusable_pct": round(unusable / tiles * 100, 1),
            # State and colour come from the same median so a summary can never
            # show one state's name beside another state's colour.
            "state": state.value if state else None,
            "colour": (STATE_COLOUR[state] if state else TileColour.GREY).value,
            # Same split as a single hexagon: how much evidence and what it
            # averaged to are always published, because neither places anybody
            # at a time. Only the timestamp waits for enough contributors.
            "low_confidence": not detailed,
            "measurements": row["measurements"],
            "avg_rsrp_dbm": (
                round(row["avg_rsrp_dbm"], 1) if row["avg_rsrp_dbm"] is not None else None
            ),
            "avg_download_kbps": (
                round(row["avg_download_kbps"], 1)
                if row["avg_download_kbps"] is not None
                else None
            ),
            "last_measured_at": (
                row["last_measured_at"].isoformat()
                if detailed and row["last_measured_at"]
                else None
            ),
        }

    return out


def _summary_state(by_state: dict[str, int]) -> RadioState | None:
    """One state for a whole area: its median hexagon.

    The median again, for the same reason it decides a single tile: a province
    should not be judged by one dead valley, nor by its capital.

    Deliberately not the most common state. A province that is 47% dead and 38%
    weak would be labelled "no network at all" by a plurality rule while its
    median — and therefore its colour — said otherwise, and the summary would
    contradict itself in a single line.
    """
    total = sum(by_state.values())
    if total == 0:
        return None

    target = total // 2
    seen = 0
    for state in sorted(RadioState, key=lambda s: STATE_SCORE[s]):
        seen += by_state.get(state.value, 0)
        if seen > target:
            return state
    return None


def area_payload(area: AdminArea, *, include_boundary: bool) -> dict[str, Any]:
    """The wire form of an area. Boundary omitted where it would be wasted."""
    payload: dict[str, Any] = {
        "code": area.code,
        "level": area.level,
        "name_en": area.name_en,
        "name_lo": area.name_lo,
        "parent_code": area.parent_code,
        "centroid": {"lat": area.centroid_lat, "lon": area.centroid_lon},
        "bounds": {
            "min_lat": area.min_lat,
            "min_lon": area.min_lon,
            "max_lat": area.max_lat,
            "max_lon": area.max_lon,
        },
        "area_km2": round(area.area_km2, 1) if area.area_km2 else None,
        # The client draws a border when this is true and a stated-radius circle
        # when it is false. It must never present the second as the first.
        "has_boundary": area.has_boundary,
        "radius_m": area.radius_m if not area.has_boundary else None,
        "source": area.source,
    }
    if include_boundary and area.boundary is not None:
        payload["boundary"] = area.boundary
    return payload


LEVEL_ORDER = (LEVEL_COUNTRY, LEVEL_PROVINCE, LEVEL_DISTRICT, LEVEL_VILLAGE)
