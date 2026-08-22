"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.area import AdminArea
from app.models.device import Device
from app.models.user_device import UserDevice
from app.models.measurement import CellObservation, IngestBatch, Measurement
from app.models.report import UserReport
from app.models.cell import ObservedCell
from app.models.features import HexFeature
from app.models.tile import CandidateSite, H3Tile, H3TileOperator
from app.models.user import User

__all__ = [
    "AdminArea",
    "Base",
    "CandidateSite",
    "CellObservation",
    "Device",
    "UserDevice",
    "HexFeature",
    "ObservedCell",
    "H3Tile",
    "H3TileOperator",
    "IngestBatch",
    "Measurement",
    "User",
    "UserReport",
]
