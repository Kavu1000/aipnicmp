from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPk, timestamp_column


class UserReport(Base):
    """A citizen's report of slow or unusable internet (proposal 2.6).

    Reports are subjective where measurements are objective, so they are stored
    apart and never mixed into the tile statistics. Their value is corroboration:
    a red tile plus twenty reports is a stronger case to an operator than either
    on its own.
    """

    __tablename__ = "user_reports"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.install_id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = timestamp_column(server_default=func.now(), index=True)
    occurred_at: Mapped[datetime | None] = timestamp_column()

    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    h3_index: Mapped[str | None] = mapped_column(String(20), index=True)

    # no_service | slow | unstable | cannot_call | other
    category: Mapped[str] = mapped_column(String(32), index=True)
    operator_name: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)

    # new | forwarded | acknowledged | resolved
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new", index=True)
    forwarded_at: Mapped[datetime | None] = timestamp_column()
