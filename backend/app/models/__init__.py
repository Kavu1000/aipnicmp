"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.device import Device
from app.models.measurement import CellObservation, IngestBatch, Measurement
from app.models.report import UserReport
from app.models.tile import CandidateSite, H3Tile

__all__ = [
    "Base",
    "CandidateSite",
    "CellObservation",
    "Device",
    "H3Tile",
    "IngestBatch",
    "Measurement",
    "UserReport",
]
