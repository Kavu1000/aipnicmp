"""The upload contract between the Android collector and the ingestion layer.

Field names here are the wire format. Changing one is a breaking change for
every device already in the field, and devices in uncovered areas may hold
records for days before uploading, so old shapes must keep working. Add
fields; do not rename them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.radio import RadioState

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class DeviceInfo(BaseModel):
    """Identifies the installation, never the person.

    ``install_id`` is generated on first launch and thrown away on uninstall.
    It exists to rate-limit and to spot one device fabricating a whole province,
    not to follow anyone around.
    """

    model_config = ConfigDict(extra="forbid")

    install_id: str = Field(min_length=16, max_length=64)
    model: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)
    android_api: int | None = Field(default=None, ge=21, le=99)
    app_version: str | None = Field(default=None, max_length=32)


class OperatorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcc: str | None = Field(default=None, pattern=r"^\d{3}$")
    mnc: str | None = Field(default=None, pattern=r"^\d{2,3}$")
    name: str | None = Field(default=None, max_length=80)


class CellInfo(BaseModel):
    """One cell as seen by the modem.

    Cell identifiers are the anti-spoofing anchor of proposal 3.5: they are hard
    to fabricate plausibly, because a faked position implies a set of cells that
    other devices' records would contradict.
    """

    model_config = ConfigDict(extra="forbid")

    radio: Literal["GSM", "UMTS", "LTE", "NR", "CDMA"] | None = None
    mcc: str | None = Field(default=None, pattern=r"^\d{3}$")
    mnc: str | None = Field(default=None, pattern=r"^\d{2,3}$")
    cid: int | None = Field(default=None, ge=0)
    lac_tac: int | None = Field(default=None, ge=0)
    pci_psc: int | None = Field(default=None, ge=0)
    arfcn: int | None = Field(default=None, ge=0)
    rsrp_dbm: float | None = Field(default=None, ge=-160, le=0)
    is_registered: bool = False


class SignalSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rsrp_dbm: float | None = Field(default=None, ge=-160, le=0)
    rsrq_db: float | None = Field(default=None, ge=-50, le=10)
    sinr_db: float | None = Field(default=None, ge=-30, le=50)
    rssi_dbm: float | None = Field(default=None, ge=-160, le=0)
    # Android's coarse 0-4 bar level, the one metric every OEM exposes.
    level: int | None = Field(default=None, ge=0, le=4)


class ActiveTest(BaseModel):
    """Active results exist only where the internet was usable (proposal 2.3)."""

    model_config = ConfigDict(extra="forbid")

    download_kbps: float | None = Field(default=None, ge=0, le=10_000_000)
    upload_kbps: float | None = Field(default=None, ge=0, le=10_000_000)
    latency_ms: float | None = Field(default=None, ge=0, le=60_000)
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100)
    tested_at: datetime | None = None


class MeasurementIn(BaseModel):
    """A single measurement, signed on the device at the moment of capture."""

    model_config = ConfigDict(extra="forbid")

    client_record_id: str = Field(min_length=8, max_length=64)
    captured_at: datetime
    lat: Latitude
    lon: Longitude
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=10_000)
    altitude_m: float | None = Field(default=None, ge=-500, le=9_000)
    speed_mps: float | None = Field(default=None, ge=0, le=400)

    registered: bool
    network_type: str | None = Field(default=None, max_length=24)
    operator: OperatorInfo | None = None
    signal: SignalSample = Field(default_factory=SignalSample)
    serving_cell: CellInfo | None = None
    neighbor_cells: list[CellInfo] = Field(default_factory=list, max_length=32)
    active_test: ActiveTest | None = None
    # The SIM's own network. Differs from `operator` exactly when the phone
    # is roaming, which is the only reliable way to tell that apart from a
    # mislabelled PLMN table — a handset's printed name cannot.
    sim_operator: OperatorInfo | None = None

    # What the device itself concluded. Stored for comparison, never trusted:
    # the server's own classification is authoritative.
    radio_state_client: RadioState | None = None

    # Base64 Ed25519 signature over the canonical form of this record, produced
    # at capture time so that a record held for days cannot be rewritten before
    # upload.
    signature: str | None = Field(default=None, max_length=128)

    @field_validator("captured_at")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware (send UTC with a Z suffix)")
        return v

    @property
    def cells_visible(self) -> int:
        serving = 1 if self.serving_cell is not None else 0
        return serving + len(self.neighbor_cells)


class MeasurementBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=8, max_length=64)
    device: DeviceInfo
    uploaded_from_lat: Latitude | None = None
    uploaded_from_lon: Longitude | None = None
    records: list[MeasurementIn] = Field(min_length=1)


class RejectedRecord(BaseModel):
    client_record_id: str
    reason: str
    detail: str | None = None


class BatchResult(BaseModel):
    """Per-record outcome. A partly bad batch is still worth its good records —
    devices in remote areas may not get another upload window for days."""

    batch_id: str
    accepted: int
    duplicates: int
    rejected: list[RejectedRecord] = Field(default_factory=list)
