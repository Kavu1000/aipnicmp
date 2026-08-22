"""Load administrative boundaries into ``admin_areas``.

    python scripts/import_admin_areas.py \
        --country lao_adm0.geojson \
        --provinces lao_adm1.geojson \
        --districts lao_adm2.geojson \
        --source "COD-AB, Lao Statistics Bureau"

Reads GeoJSON — the format every publisher of Lao boundaries offers — and
recognises the property conventions of the three sources anyone is realistically
going to use:

* **COD-AB / HDX** (``ADM1_EN``, ``ADM1_LO``, ``ADM1_PCODE``, ``ADM0_PCODE``)
* **GADM** (``NAME_1``, ``GID_1``, ``GID_0``)
* **OSM exports** (``name``, ``name:lo``, ``admin_level``)

Anything else can be mapped with ``--name-field`` and friends rather than by
editing this file.

Three decisions worth knowing about:

**Villages may be points.** Lao village boundaries are largely unpublished;
villages are recorded as points. A Point feature is stored as a point with a
radius, and the map draws a circle labelled as such. This script will not
manufacture a village outline by carving up its district — a fabricated border
on a national coverage map is worse than an honest circle.

**Parents are resolved geometrically when the file does not say.** COD-AB
carries the parent PCODE on every row; other sources often do not. Where it is
missing, the child's centroid is tested against the already-imported parents,
which is exact for every case except a centroid falling outside its own
concave parent — reported at the end rather than silently guessed.

**Outlines are simplified.** Full-resolution district boundaries run to tens of
megabytes, and the map draws them at a scale where the detail is invisible. The
default tolerance is about 100 m; ``--simplify 0`` keeps the source geometry.

Run ``--dry-run`` first: it reports exactly what would be written, including
every unresolved parent, without touching the database.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.area import (  # noqa: E402
    LEVEL_COUNTRY,
    LEVEL_DISTRICT,
    LEVEL_PROVINCE,
    LEVEL_VILLAGE,
    AdminArea,
)
from app.services.areas import DEFAULT_VILLAGE_RADIUS_M  # noqa: E402
from app.services.polygon import (  # noqa: E402
    ShapeIndex,
    bbox_of,
    centroid_of,
    count_points,
    shape_area_km2,
    shape_of,
    simplify,
    to_geojson,
)

# ~100 m at Lao latitudes. Small enough that a border still looks like itself
# at the zoom where a district fills the screen.
DEFAULT_SIMPLIFY_DEG = 0.001

LEVEL_ARGUMENTS = {
    LEVEL_COUNTRY: "country",
    LEVEL_PROVINCE: "provinces",
    LEVEL_DISTRICT: "districts",
    LEVEL_VILLAGE: "villages",
}

# Property names to try, in order, for each level. First hit wins.
#
# COD-AB ships in two naming conventions depending on vintage — the uppercase
# ADM1_EN form and the lowercase adm1_name form, the latter putting the local
# script in adm1_name1 rather than a language-suffixed field. The current Lao
# release uses the lowercase one. Both are listed rather than making the caller
# discover which they have and pass --name-field.
NAME_FIELDS = {
    LEVEL_COUNTRY: ("ADM0_EN", "adm0_name", "NAME_0", "COUNTRY", "name", "NAME"),
    LEVEL_PROVINCE: ("ADM1_EN", "adm1_name", "NAME_1", "PROVINCE", "name", "NAME"),
    LEVEL_DISTRICT: ("ADM2_EN", "adm2_name", "NAME_2", "DISTRICT", "name", "NAME"),
    LEVEL_VILLAGE: ("ADM3_EN", "adm3_name", "NAME_3", "VILLAGE", "name", "NAME"),
}
LAO_NAME_FIELDS = {
    LEVEL_COUNTRY: ("ADM0_LO", "ADM0_LAO", "adm0_name1", "name:lo", "NL_NAME_0"),
    LEVEL_PROVINCE: ("ADM1_LO", "ADM1_LAO", "adm1_name1", "name:lo", "NL_NAME_1"),
    LEVEL_DISTRICT: ("ADM2_LO", "ADM2_LAO", "adm2_name1", "name:lo", "NL_NAME_2"),
    LEVEL_VILLAGE: ("ADM3_LO", "ADM3_LAO", "adm3_name1", "name:lo", "NL_NAME_3"),
}
CODE_FIELDS = {
    LEVEL_COUNTRY: ("ADM0_PCODE", "adm0_pcode", "GID_0", "ISO3", "pcode"),
    LEVEL_PROVINCE: ("ADM1_PCODE", "adm1_pcode", "GID_1", "pcode"),
    LEVEL_DISTRICT: ("ADM2_PCODE", "adm2_pcode", "GID_2", "pcode"),
    LEVEL_VILLAGE: ("ADM3_PCODE", "adm3_pcode", "GID_3", "pcode"),
}
PARENT_CODE_FIELDS = {
    LEVEL_PROVINCE: ("ADM0_PCODE", "adm0_pcode", "GID_0"),
    LEVEL_DISTRICT: ("ADM1_PCODE", "adm1_pcode", "GID_1"),
    LEVEL_VILLAGE: ("ADM2_PCODE", "adm2_pcode", "GID_2"),
}


@dataclass
class Loaded:
    """One area, ready to be written."""

    code: str
    level: int
    name_en: str
    name_lo: str | None
    parent_code: str | None
    centroid_lat: float
    centroid_lon: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    area_km2: float | None
    boundary: dict[str, Any] | None
    boundary_points: int | None
    radius_m: float | None


@dataclass
class Report:
    written: int = 0
    updated: int = 0
    points_only: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _first(properties: dict[str, Any], candidates: Iterable[str]) -> str | None:
    for key in candidates:
        value = properties.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _fallback_code(level: int, name: str, parent: str | None) -> str:
    """A stable code for a source that publishes none.

    Derived from the parent and the name so that re-importing the same file
    updates the same rows instead of duplicating them. Truncated to fit the
    column; collisions inside one parent would need two identically named
    districts, which the reports at the end would surface.
    """
    slug = "".join(char for char in name.upper() if char.isalnum())[:20]
    return f"{parent or 'LA'}-{level}-{slug}"[:32]


def load_features(
    path: Path,
    level: int,
    *,
    simplify_deg: float,
    village_radius_m: float,
    overrides: dict[str, str | None],
) -> tuple[list[Loaded], list[str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    features = document.get("features") if document.get("type") == "FeatureCollection" else [document]
    if not features:
        return [], [f"{path.name}: no features"]

    loaded: list[Loaded] = []
    problems: list[str] = []

    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}

        name = (
            _first(properties, [overrides["name"]] if overrides.get("name") else [])
            or _first(properties, NAME_FIELDS[level])
        )
        if not name:
            problems.append(f"{path.name}#{index}: no name property")
            continue

        parent_code = _first(properties, PARENT_CODE_FIELDS.get(level, ()))
        if overrides.get("parent"):
            parent_code = _first(properties, [overrides["parent"]]) or parent_code

        code = (
            _first(properties, [overrides["code"]] if overrides.get("code") else [])
            or _first(properties, CODE_FIELDS[level])
            or _fallback_code(level, name, parent_code)
        )
        name_lo = _first(properties, LAO_NAME_FIELDS[level])

        kind = geometry.get("type")
        if kind == "Point":
            lon, lat = (float(value) for value in geometry["coordinates"][:2])
            loaded.append(
                Loaded(
                    code=code,
                    level=level,
                    name_en=name,
                    name_lo=name_lo,
                    parent_code=parent_code,
                    centroid_lat=lat,
                    centroid_lon=lon,
                    # A point's "extent" is its circle, so the map has something
                    # to frame when the village is selected.
                    min_lat=lat,
                    min_lon=lon,
                    max_lat=lat,
                    max_lon=lon,
                    area_km2=None,
                    boundary=None,
                    boundary_points=None,
                    radius_m=village_radius_m,
                )
            )
            continue

        try:
            shape = shape_of(geometry)
        except ValueError as error:
            problems.append(f"{path.name}#{index} ({name}): {error}")
            continue

        thinned = simplify(shape, simplify_deg)
        min_lon, min_lat, max_lon, max_lat = bbox_of(thinned)
        lon, lat = centroid_of(thinned)

        loaded.append(
            Loaded(
                code=code,
                level=level,
                name_en=name,
                name_lo=name_lo,
                parent_code=parent_code,
                centroid_lat=lat,
                centroid_lon=lon,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
                area_km2=shape_area_km2(thinned),
                boundary=to_geojson(thinned),
                boundary_points=count_points(thinned),
                radius_m=None,
            )
        )

    return loaded, problems


def resolve_parents(children: list[Loaded], parents: list[Loaded]) -> list[str]:
    """Fill in missing parent codes by locating each child's centroid.

    Returns the names of children that could not be placed, which is a real
    finding rather than an error: a boundary file that leaves districts outside
    every province is telling you the two files do not belong together.
    """
    if not parents:
        return [child.name_en for child in children if child.parent_code is None]

    index = ShapeIndex(
        (parent.code, shape_of(parent.boundary), bbox_of(shape_of(parent.boundary)))
        for parent in parents
        if parent.boundary is not None
    )

    unresolved: list[str] = []
    for child in children:
        if child.parent_code:
            continue
        found = index.find(child.centroid_lon, child.centroid_lat)
        if found is None:
            unresolved.append(child.name_en)
        else:
            child.parent_code = found
    return unresolved


def synthesise_country(provinces: list[Loaded], code: str, name: str) -> Loaded:
    """A country row derived from its provinces, with no boundary of its own.

    Only the extent is computed, never an outline: merging polygons correctly is
    real work, and a national border assembled by this script would be a claim
    the source never made. The client outlines provinces, not the country, so
    nothing is lost.
    """
    return Loaded(
        code=code,
        level=LEVEL_COUNTRY,
        name_en=name,
        name_lo=None,
        parent_code=None,
        centroid_lat=sum(p.centroid_lat for p in provinces) / len(provinces),
        centroid_lon=sum(p.centroid_lon for p in provinces) / len(provinces),
        min_lat=min(p.min_lat for p in provinces),
        min_lon=min(p.min_lon for p in provinces),
        max_lat=max(p.max_lat for p in provinces),
        max_lon=max(p.max_lon for p in provinces),
        area_km2=sum(p.area_km2 or 0.0 for p in provinces) or None,
        boundary=None,
        boundary_points=None,
        radius_m=None,
    )


def write(session: Session, rows: list[Loaded], source: str | None, report: Report) -> None:
    existing = {
        area.code: area
        for area in session.scalars(
            select(AdminArea).where(AdminArea.code.in_([row.code for row in rows]))
        ).all()
    }

    for row in rows:
        area = existing.get(row.code)
        if area is None:
            area = AdminArea(code=row.code)
            session.add(area)
            report.written += 1
        else:
            report.updated += 1

        area.level = row.level
        area.name_en = row.name_en
        area.name_lo = row.name_lo
        area.parent_code = row.parent_code
        area.centroid_lat = row.centroid_lat
        area.centroid_lon = row.centroid_lon
        area.min_lat = row.min_lat
        area.min_lon = row.min_lon
        area.max_lat = row.max_lat
        area.max_lon = row.max_lon
        area.area_km2 = row.area_km2
        area.boundary = row.boundary
        area.boundary_points = row.boundary_points
        area.radius_m = row.radius_m
        area.source = source


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--country", type=Path, help="ADM0 GeoJSON")
    parser.add_argument("--provinces", type=Path, help="ADM1 GeoJSON")
    parser.add_argument("--districts", type=Path, help="ADM2 GeoJSON")
    parser.add_argument("--villages", type=Path, help="ADM3 GeoJSON (polygons or points)")
    parser.add_argument(
        "--simplify",
        type=float,
        default=DEFAULT_SIMPLIFY_DEG,
        help=f"Douglas-Peucker tolerance in degrees (default {DEFAULT_SIMPLIFY_DEG}; 0 disables)",
    )
    parser.add_argument(
        "--village-radius",
        type=float,
        default=DEFAULT_VILLAGE_RADIUS_M,
        help="metres around a village point that count as that village",
    )
    parser.add_argument("--source", help='attribution, e.g. "COD-AB, Lao Statistics Bureau"')
    parser.add_argument("--country-code", default="LA")
    parser.add_argument("--country-name", default="Lao PDR")
    parser.add_argument("--name-field", help="override the English name property")
    parser.add_argument("--code-field", help="override the code property")
    parser.add_argument("--parent-field", help="override the parent code property")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    overrides = {"name": args.name_field, "code": args.code_field, "parent": args.parent_field}

    by_level: dict[int, list[Loaded]] = {}
    problems: list[str] = []

    for level, argument in LEVEL_ARGUMENTS.items():
        path: Path | None = getattr(args, argument)
        if path is None:
            continue
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            return 1
        rows, issues = load_features(
            path,
            level,
            simplify_deg=args.simplify,
            village_radius_m=args.village_radius,
            overrides=overrides,
        )
        by_level[level] = rows
        problems.extend(issues)
        print(f"{argument}: {len(rows)} features from {path.name}")

    if not by_level:
        parser.error("give at least one of --country, --provinces, --districts, --villages")

    if LEVEL_COUNTRY not in by_level and LEVEL_PROVINCE in by_level:
        by_level[LEVEL_COUNTRY] = [
            synthesise_country(by_level[LEVEL_PROVINCE], args.country_code, args.country_name)
        ]
        print(f"country: synthesised {args.country_name} from provinces (extent only, no border)")

    report = Report()

    # Every province belongs to the country, whether or not the file said so.
    country = by_level.get(LEVEL_COUNTRY)
    if country:
        for province in by_level.get(LEVEL_PROVINCE, []):
            province.parent_code = province.parent_code or country[0].code

    for level, parent_level in ((LEVEL_DISTRICT, LEVEL_PROVINCE), (LEVEL_VILLAGE, LEVEL_DISTRICT)):
        if level in by_level:
            report.orphans.extend(
                resolve_parents(by_level[level], by_level.get(parent_level, []))
            )

    report.points_only = [
        row.name_en for row in by_level.get(LEVEL_VILLAGE, []) if row.boundary is None
    ]
    report.skipped = problems

    ordered = [row for level in sorted(by_level) for row in by_level[level]]

    if args.dry_run:
        print(f"\n-- dry run: {len(ordered)} areas would be written --")
    else:
        engine = create_engine(settings.database_url_sync, future=True)
        with Session(engine) as session:
            write(session, ordered, args.source, report)
            session.commit()
        engine.dispose()
        print(f"\nwrote {report.written} new, updated {report.updated}")

    if report.points_only:
        print(
            f"\n{len(report.points_only)} villages have no polygon and are stored as points "
            f"with a {args.village_radius:.0f} m radius. The map labels them as such."
        )
    if report.orphans:
        print(f"\n{len(report.orphans)} areas could not be placed inside a parent:", file=sys.stderr)
        for name in report.orphans[:20]:
            print(f"  - {name}", file=sys.stderr)
        if len(report.orphans) > 20:
            print(f"  … and {len(report.orphans) - 20} more", file=sys.stderr)
    if report.skipped:
        print(f"\n{len(report.skipped)} features skipped:", file=sys.stderr)
        for issue in report.skipped[:20]:
            print(f"  - {issue}", file=sys.stderr)

    if not args.dry_run:
        print("\nnext: rebuild the tiles so they carry their area codes")
        print("      curl -X POST -H \"X-Admin-Token: $ADMIN_TOKEN\" .../api/v1/admin/rebuild-tiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
