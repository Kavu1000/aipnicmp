"""Where the fleet has observed each base station.

Proposal 2.5(1) lists OpenCelliD as the source of tower positions. This is the
same information derived from the platform's own measurements instead: every
reading already records the cells the handset could see, so the fleet maps the
network it is measuring, and the picture sharpens with every drive rather than
with a subscription.

A row here is an *observation summary*, not a surveyed site. Whether its
position is worth believing is a separate column, and it is usually false.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column


class ObservedCell(Base):
    """One base station cell, as seen from the road."""

    __tablename__ = "observed_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The cell's identity, as the network broadcasts it.
    mcc: Mapped[str] = mapped_column(String(3))
    mnc: Mapped[str] = mapped_column(String(3))
    lac_tac: Mapped[int] = mapped_column(Integer)
    cid: Mapped[int] = mapped_column(Integer)
    operator_name: Mapped[str | None] = mapped_column(String(120), index=True)

    # Which province and district the cell was heard in. Assigned from the
    # estimated centre: coarse for drawing, ample for attribution, because a
    # district is tens of kilometres across and the estimate is good to one.
    adm1_code: Mapped[str | None] = mapped_column(String(32), index=True)
    adm2_code: Mapped[str | None] = mapped_column(String(32), index=True)

    observations: Mapped[int] = mapped_column(Integer)

    # The signal-weighted centre of where it was heard. Not the tower: without
    # observations spread around it, this is closer to the centre of the road
    # the collector drove than to the mast.
    est_lat: Mapped[float] = mapped_column(Float)
    est_lon: Mapped[float] = mapped_column(Float)

    # How far the observations spread, and therefore how much the estimate is
    # worth. A cell heard only from a 200 m stretch of one road cannot be
    # placed to better than the cell's own radius, whatever the arithmetic says.
    spread_m: Mapped[float] = mapped_column(Float)
    uncertainty_m: Mapped[float] = mapped_column(Float)

    # Set only when the geometry can actually support a position. Everything
    # downstream must check this rather than the coordinates, which are always
    # present and often meaningless.
    position_is_reliable: Mapped[bool] = mapped_column(Boolean, default=False)

    # The strongest reading, and where it was taken. This is the honest part:
    # wherever the mast is, the phone was near it when it heard this.
    best_rsrp_dbm: Mapped[float | None] = mapped_column(Float)
    best_lat: Mapped[float | None] = mapped_column(Float)
    best_lon: Mapped[float | None] = mapped_column(Float)

    first_seen_at: Mapped[datetime | None] = timestamp_column(nullable=True)
    last_seen_at: Mapped[datetime | None] = timestamp_column(nullable=True)
    updated_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    __table_args__ = (
        Index("ix_observed_cells_identity", "mcc", "mnc", "lac_tac", "cid", unique=True),
        Index("ix_observed_cells_reliable", "position_is_reliable"),
    )
