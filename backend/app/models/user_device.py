"""Which handsets a collector account may see the readings of.

Kept apart from ``devices`` on purpose. That table states that it holds
nothing identifying a person, and it is written by the handset itself at
enrolment; an account column there would make every enrolment record a
statement about somebody. The ownership lives here, on the account side,
where a super admin puts it and where deleting the account takes it away.

One person, several handsets. A reinstall cannot recover its hardware key, so
it enrols as a new device — this fleet has eleven enrolments for one model —
and a scheme allowing only one device per account would break the first time
somebody reinstalled.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserDevice(Base):
    """One handset, owned by one account."""

    __tablename__ = "user_devices"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    install_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.install_id", ondelete="CASCADE"), primary_key=True
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    #: Who opened this window onto somebody's movements.
    assigned_by: Mapped[str | None] = mapped_column(String(320))

    __table_args__ = (
        # A handset belongs to one person. Two accounts each believing the same
        # readings were theirs is not a display bug, it is two people shown a
        # third person's journey.
        Index("ix_user_devices_install", "install_id", unique=True),
    )
