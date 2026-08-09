"""Administrative areas: country, province, district, village.

The map is read by people who think in places, not in hexagons. A provincial
officer asks about Oudomxay; a district office asks about its own district.
This table is what lets the platform answer in those terms, and what lets the
public map draw the border of the area being asked about.

Two things are deliberate.

**Boundaries are optional.** Province and district polygons for Lao PDR are
published; village polygons largely are not — villages are usually recorded as
points. Rather than invent an outline by carving up a district, a village
without a polygon is stored as its point and a stated radius, and the client is
told which it received (``has_boundary``). Drawing a fabricated border around
someone's village on a national coverage map would be exactly the kind of
confident falsehood the rest of this system refuses to produce.

**Codes come from the source, not from us.** ``code`` holds the publisher's
identifier (a COD-AB PCODE, a GADM GID). Renaming a district — which happens —
then leaves the joins intact, and a re-import updates rather than duplicates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, Index, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column

# JSONB on Postgres, plain JSON on the SQLite used by the tests.
BoundaryJson = JSON().with_variant(JSONB, "postgresql")

LEVEL_COUNTRY = 0
LEVEL_PROVINCE = 1
LEVEL_DISTRICT = 2
LEVEL_VILLAGE = 3

LEVEL_NAMES: dict[int, str] = {
    LEVEL_COUNTRY: "country",
    LEVEL_PROVINCE: "province",
    LEVEL_DISTRICT: "district",
    LEVEL_VILLAGE: "village",
}

# The column on the tile tables that carries each level's code. Level 0 has no
# column: every tile in the database is in the country, so a column saying so
# would be a constant.
LEVEL_TILE_COLUMN: dict[int, str] = {
    LEVEL_PROVINCE: "adm1_code",
    LEVEL_DISTRICT: "adm2_code",
    LEVEL_VILLAGE: "adm3_code",
}


class AdminArea(Base):
    """One administrative unit at any level."""

    __tablename__ = "admin_areas"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(SmallInteger, index=True)

    name_en: Mapped[str] = mapped_column(String(120))
    # Nullable because a source may not carry Lao script. The UI falls back to
    # the English name rather than showing an empty row.
    name_lo: Mapped[str | None] = mapped_column(String(120))

    parent_code: Mapped[str | None] = mapped_column(String(32), index=True)

    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)

    # Stored so the client can frame the area without ever parsing the polygon,
    # and so tile queries can be bounded before any point-in-polygon work.
    min_lat: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)

    area_km2: Mapped[float | None] = mapped_column(Float)

    # Simplified GeoJSON geometry, or NULL for a point-only village.
    boundary: Mapped[dict[str, Any] | None] = mapped_column(BoundaryJson)
    boundary_points: Mapped[int | None] = mapped_column(Integer)
    # Only meaningful when boundary is NULL: how far around the point the
    # platform is willing to call "this village" when selecting hexagons.
    radius_m: Mapped[float | None] = mapped_column(Float)

    # Where the geometry came from, carried to the client. A map that shades a
    # province should be able to say who drew that province.
    source: Mapped[str | None] = mapped_column(String(120))

    updated_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    __table_args__ = (
        Index("ix_admin_areas_level_parent", "level", "parent_code"),
        Index("ix_admin_areas_level_name", "level", "name_en"),
    )

    @property
    def has_boundary(self) -> bool:
        return self.boundary is not None
