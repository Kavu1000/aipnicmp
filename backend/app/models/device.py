from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column


class Device(Base):
    """One app installation.

    Deliberately holds nothing that identifies a person — no account, no phone
    number, no IMEI. Proposal 2.6 promises anonymised data, and the cheapest way
    to keep that promise is never to collect the identifying field in the first
    place.
    """

    __tablename__ = "devices"

    install_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Base64 raw Ed25519 public key. Records are verified against this.
    public_key: Mapped[str | None] = mapped_column(String(128))

    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    android_api: Mapped[int | None] = mapped_column(Integer)
    app_version: Mapped[str | None] = mapped_column(String(32))

    # untrusted -> enrolled -> attested -> partner
    # "partner" marks the regular collectors of proposal 2.3 (bus drivers,
    # health workers): their records carry the pilot, so they are rate-limited
    # more generously.
    trust_level: Mapped[str] = mapped_column(String(16), default="enrolled", server_default="enrolled")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    enrolled_at: Mapped[datetime] = timestamp_column(server_default=func.now())
    last_seen_at: Mapped[datetime | None] = timestamp_column()

    records_accepted: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    records_rejected: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
