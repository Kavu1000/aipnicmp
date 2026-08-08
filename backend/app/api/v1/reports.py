from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.report import UserReport
from app.services.geo import to_h3

router = APIRouter(prefix="/reports", tags=["reports"])

ReportCategory = Literal["no_service", "slow", "unstable", "cannot_call", "other"]


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    install_id: str | None = Field(default=None, max_length=64)
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    category: ReportCategory
    operator_name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None


class ReportOut(BaseModel):
    id: int
    status: str
    h3_index: str | None


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    payload: ReportIn,
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    """File a citizen report of poor service (proposal 2.6).

    Reports are stored separately from measurements and never feed the tile
    statistics: one is a subjective account, the other an instrument reading.
    Mixing them would let a coordinated group of complainants outrank a
    genuinely unserved village.
    """
    report = UserReport(
        device_id=payload.install_id,
        lat=payload.lat,
        lon=payload.lon,
        h3_index=to_h3(payload.lat, payload.lon, settings.h3_resolution),
        category=payload.category,
        operator_name=payload.operator_name,
        description=payload.description,
        occurred_at=payload.occurred_at,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)

    return ReportOut(id=report.id, status=report.status, h3_index=report.h3_index)
