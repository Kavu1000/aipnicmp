"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.area import AdminArea
from app.models.device import Device
from app.models.measurement import CellObservation, IngestBatch, Measurement
from app.models.report import UserReport
from app.models.tile import CandidateSite, H3Tile, H3TileOperator

__all__ = [
    "AdminArea",
    "Base",
    "CandidateSite",
    "CellObservation",
    "Device",
    "H3Tile",
    "H3TileOperator",
    "IngestBatch",
    "Measurement",
    "UserReport",
]
