"""Per-hexagon predictors for the coverage model (proposal Layer 4).

One row per hexagon of Lao PDR, whether or not anyone has ever measured it.
That is the point: the model is trained on the hexagons that *have* been
measured and asked about the ones that have not, so the grid has to exist
independently of the measurements.

Every column here describes the ground, not the network. Nothing derived from
a measurement belongs in this table — mixing the two would leak the training
label into the features and produce a model that scores well and predicts
nothing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column


class HexFeature(Base):
    """The terrain, people and infrastructure of one hexagon."""

    __tablename__ = "hex_features"

    h3_index: Mapped[str] = mapped_column(String(20), primary_key=True)
    resolution: Mapped[int] = mapped_column(SmallInteger, index=True)

    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    # Cells are not equal-area; this is the real area of this hexagon, not a
    # national average. See coverage.tile_area_km2.
    area_km2: Mapped[float] = mapped_column(Float)

    # Which province and district it falls in, so the model can be trained,
    # evaluated and reported per area without a second point-in-polygon pass.
    adm1_code: Mapped[str | None] = mapped_column(String(32), index=True)
    adm2_code: Mapped[str | None] = mapped_column(String(32), index=True)

    # --- terrain -----------------------------------------------------------
    # Elevation drives line of sight, which drives coverage more than distance
    # does in a country that is mostly mountains.
    elevation_mean_m: Mapped[float | None] = mapped_column(Float)
    elevation_min_m: Mapped[float | None] = mapped_column(Float)
    elevation_max_m: Mapped[float | None] = mapped_column(Float)
    # Standard deviation of elevation within the hexagon: flat valley floor
    # versus broken ground, which a mean alone cannot distinguish.
    terrain_ruggedness_m: Mapped[float | None] = mapped_column(Float)

    # --- people ------------------------------------------------------------
    population: Mapped[float | None] = mapped_column(Float)
    # Built-up and cropland fractions separate a village from the fields around
    # it, which population density alone blurs at this hexagon size.
    built_up_fraction: Mapped[float | None] = mapped_column(Float)
    cropland_fraction: Mapped[float | None] = mapped_column(Float)
    forest_fraction: Mapped[float | None] = mapped_column(Float)

    # --- infrastructure ----------------------------------------------------
    # Distance to the nearest cell the platform has ever observed serving.
    # Derived from the fleet's own cell observations rather than a purchased
    # tower database, so it improves as collection continues.
    distance_to_observed_cell_km: Mapped[float | None] = mapped_column(Float)
    distance_to_road_km: Mapped[float | None] = mapped_column(Float)

    # Which feature builders have run. A partially built row is useful — the
    # model can be trained on the features that exist — but it must be visible
    # that the rest are missing rather than genuinely zero.
    sources: Mapped[str | None] = mapped_column(String(200))
    feature_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    updated_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    __table_args__ = (
        Index("ix_hex_features_adm1_adm2", "adm1_code", "adm2_code"),
        # The training join: every hexagon that has both features and a label.
        Index("ix_hex_features_res_pop", "resolution", "population"),
    )
