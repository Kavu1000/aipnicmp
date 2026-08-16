from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPk, timestamp_column


class IngestBatch(Base):
    """One upload. Kept so a bad batch can be traced and reversed wholesale."""

    __tablename__ = "ingest_batches"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.install_id", ondelete="CASCADE"), index=True)

    # Indexed because incremental aggregation asks "what arrived since?".
    # Capture time cannot answer that: a phone back from a dead zone brings
    # records hours older than the window being rebuilt.
    received_at: Mapped[datetime] = timestamp_column(server_default=func.now(), index=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)

    # Where the device was when it regained coverage and uploaded. Compared
    # against the measurement positions to check the journey was possible.
    upload_lat: Mapped[float | None] = mapped_column(Float)
    upload_lon: Mapped[float | None] = mapped_column(Float)

    # Salted hash, not the address itself — enough to rate-limit, not enough to
    # locate anyone.
    client_ip_hash: Mapped[str | None] = mapped_column(String(64))

    # Why records were refused, as "reason xN" pairs. A rejected record is
    # dropped by the device and never resent, so without this the only evidence
    # of lost data would be a count — and a collector silently discarding every
    # reading would look identical to one that is working.
    rejection_summary: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (UniqueConstraint("device_id", "batch_id", name="uq_ingest_batches_device_batch"),)


class Measurement(Base):
    """A single signal reading.

    Raw observations and the derived state are stored side by side: the raw
    fields are the evidence, the derived state is an interpretation that may be
    recomputed when thresholds change.

    ``geom`` is added by migration as a generated PostGIS column over
    (lon, lat), so the ORM never has to construct geometry and the coordinates
    have exactly one source of truth.
    """

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.install_id", ondelete="CASCADE"), index=True)
    batch_pk: Mapped[int | None] = mapped_column(BigIntPk, ForeignKey("ingest_batches.id", ondelete="SET NULL"))
    client_record_id: Mapped[str] = mapped_column(String(64))

    captured_at: Mapped[datetime] = timestamp_column(index=True)
    # Indexed because incremental aggregation asks "what arrived since?".
    # Capture time cannot answer that: a phone back from a dead zone brings
    # records hours older than the window being rebuilt.
    received_at: Mapped[datetime] = timestamp_column(server_default=func.now(), index=True)
    # How long the record sat on the device. A large value is normal here and is
    # exactly what store-and-forward is for; it is also the window in which
    # tampering would have to happen, so it is worth keeping visible.
    upload_delay_s: Mapped[int | None] = mapped_column(Integer)

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)

    registered: Mapped[bool] = mapped_column(Boolean, default=False)
    network_type: Mapped[str | None] = mapped_column(String(24))
    mcc: Mapped[str | None] = mapped_column(String(3))
    mnc: Mapped[str | None] = mapped_column(String(3))
    operator_name: Mapped[str | None] = mapped_column(String(80))
    # The SIM's home network, as encoded on the card, beside the network that
    # actually served the reading. Equal means ordinary service; different
    # means roaming — the one comparison that does not depend on the display
    # name a handset chose to print.
    sim_mcc: Mapped[str | None] = mapped_column(String(3))
    sim_mnc: Mapped[str | None] = mapped_column(String(3))

    rsrp_dbm: Mapped[float | None] = mapped_column(Float)
    rsrq_db: Mapped[float | None] = mapped_column(Float)
    sinr_db: Mapped[float | None] = mapped_column(Float)
    rssi_dbm: Mapped[float | None] = mapped_column(Float)
    signal_level: Mapped[int | None] = mapped_column(SmallInteger)

    serving_cid: Mapped[int | None] = mapped_column(BigInteger)
    serving_lac_tac: Mapped[int | None] = mapped_column(Integer)
    serving_pci: Mapped[int | None] = mapped_column(Integer)
    serving_arfcn: Mapped[int | None] = mapped_column(Integer)
    cells_visible: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Active test results, present only where the internet was usable.
    download_kbps: Mapped[float | None] = mapped_column(Float)
    upload_kbps: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float)

    # Server-derived; authoritative.
    radio_state: Mapped[str] = mapped_column(String(32), index=True)
    # Device-derived; kept only to detect clients drifting from server rules.
    radio_state_client: Mapped[str | None] = mapped_column(String(32))

    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    # Space-separated advisory flags (e.g. "coarse_gps stale_upload"). The record
    # is kept and the caveat travels with it, rather than being silently dropped.
    quality_flags: Mapped[str | None] = mapped_column(String(255))

    h3_index: Mapped[str | None] = mapped_column(String(20), index=True)

    batch = relationship("IngestBatch", lazy="noload")

    __table_args__ = (
        # Makes re-uploads idempotent: a device that never got our response can
        # safely send the same records again.
        UniqueConstraint("device_id", "client_record_id", name="uq_measurements_device_record"),
        Index("ix_measurements_h3_captured", "h3_index", "captured_at"),
        Index("ix_measurements_state_captured", "radio_state", "captured_at"),
    )


class CellObservation(Base):
    """Every cell the modem could see at one measurement.

    These are the anti-spoofing anchor of proposal 3.5. They are also the raw
    material for inferring tower positions where OpenCelliD has no entry.
    """

    __tablename__ = "cell_observations"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    measurement_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("measurements.id", ondelete="CASCADE"), index=True
    )

    radio: Mapped[str | None] = mapped_column(String(8))
    mcc: Mapped[str | None] = mapped_column(String(3))
    mnc: Mapped[str | None] = mapped_column(String(3))
    cid: Mapped[int | None] = mapped_column(BigInteger)
    lac_tac: Mapped[int | None] = mapped_column(Integer)
    pci_psc: Mapped[int | None] = mapped_column(Integer)
    arfcn: Mapped[int | None] = mapped_column(Integer)
    rsrp_dbm: Mapped[float | None] = mapped_column(Float)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("ix_cell_observations_identity", "mcc", "mnc", "lac_tac", "cid"),)
