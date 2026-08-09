from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column


class H3Tile(Base):
    """The public map's unit of truth, across all operators.

    Individual points are never published. Aggregating to a hexagon serves two
    purposes at once (proposal 2.4): it stops the map from revealing where any
    one person travelled, and it makes a national map legible.
    """

    __tablename__ = "h3_tiles"

    h3_index: Mapped[str] = mapped_column(String(20), primary_key=True)
    resolution: Mapped[int] = mapped_column(SmallInteger, index=True)

    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)

    colour: Mapped[str] = mapped_column(String(16), index=True)
    state_score: Mapped[float | None] = mapped_column(Float)
    dominant_state: Mapped[str | None] = mapped_column(String(32))
    worst_state: Mapped[str | None] = mapped_column(String(32))

    measurement_count: Mapped[int] = mapped_column(Integer, default=0)
    device_count: Mapped[int] = mapped_column(Integer, default=0)

    avg_rsrp_dbm: Mapped[float | None] = mapped_column(Float)
    avg_download_kbps: Mapped[float | None] = mapped_column(Float)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float)

    # True when no measurement exists and the value came from the model of
    # proposal 2.5(1). The map must never present a prediction as a measurement,
    # so this flag is carried all the way to the client.
    is_predicted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    prediction_confidence: Mapped[float | None] = mapped_column(Float)

    first_measured_at: Mapped[datetime | None] = timestamp_column()
    last_measured_at: Mapped[datetime | None] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    __table_args__ = (Index("ix_h3_tiles_res_colour", "resolution", "colour"),)


class H3TileOperator(Base):
    """The same hexagons, split by network operator.

    Kept in a separate table rather than as a column on `h3_tiles` because the
    two answer different questions and are read at different times. The public
    map asks "can anyone get service here?", which is the combined view; an
    operator asks "can *my* customers get service here?", which is this one.

    Collapsing them into one table would force every public map request to
    filter or de-duplicate, and would make the combined row — the one that
    matters most — just another special case.
    """

    __tablename__ = "h3_tile_operators"

    h3_index: Mapped[str] = mapped_column(String(20), primary_key=True)
    operator_name: Mapped[str] = mapped_column(String(80), primary_key=True)

    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)

    colour: Mapped[str] = mapped_column(String(16), index=True)
    dominant_state: Mapped[str | None] = mapped_column(String(32))
    worst_state: Mapped[str | None] = mapped_column(String(32))

    measurement_count: Mapped[int] = mapped_column(Integer, default=0)
    device_count: Mapped[int] = mapped_column(Integer, default=0)

    avg_rsrp_dbm: Mapped[float | None] = mapped_column(Float)
    avg_download_kbps: Mapped[float | None] = mapped_column(Float)

    last_measured_at: Mapped[datetime | None] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    __table_args__ = (Index("ix_h3_tile_operators_operator", "operator_name", "colour"),)


class CandidateSite(Base):
    """A ranked tower site — the deliverable operators and the ministry act on.

    ``population_covered`` is the objective of the facility-location problem in
    proposal 2.5(3): the sites that reach the most unserved people per tower.
    """

    __tablename__ = "candidate_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    h3_index: Mapped[str | None] = mapped_column(String(20), index=True)

    rank: Mapped[int | None] = mapped_column(Integer, index=True)
    score: Mapped[float | None] = mapped_column(Float)
    population_covered: Mapped[int | None] = mapped_column(Integer)
    unserved_population: Mapped[int | None] = mapped_column(Integer)
    tiles_improved: Mapped[int | None] = mapped_column(Integer)

    # Distinguishes "needs a new tower" from "needs an upgrade" — the cost
    # difference the proposal builds its policy argument on.
    recommendation: Mapped[str | None] = mapped_column(String(32))
    has_grid_power: Mapped[bool | None] = mapped_column(Boolean)

    province: Mapped[str | None] = mapped_column(String(80), index=True)
    district: Mapped[str | None] = mapped_column(String(80))

    model_version: Mapped[str | None] = mapped_column(String(32))
    generated_at: Mapped[datetime] = timestamp_column(server_default=func.now())
