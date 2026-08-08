from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.device import Device
from app.schemas.measurement import BatchResult, MeasurementBatch
from app.services.ingest import process_batch

router = APIRouter(prefix="/measurements", tags=["measurements"])


def _hash_ip(request: Request) -> str | None:
    """Salted hash of the client address.

    Enough to spot one source flooding the system; not enough to place anyone.
    The salt is the app's JWT secret, so the hashes are useless if the table
    leaks without the config.
    """
    client = request.client
    if client is None:
        return None
    return hashlib.sha256(f"{settings.jwt_secret}:{client.host}".encode()).hexdigest()


@router.post("/batch", response_model=BatchResult)
async def upload_batch(
    payload: MeasurementBatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BatchResult:
    """Accept a store-and-forward upload from a collector device.

    Returns 200 with a per-record breakdown even when some records fail, so the
    client knows exactly which ids to drop from its queue and which to retry.
    Failing the whole batch would make a device in a remote area retry forever.
    """
    if len(payload.records) > settings.max_batch_records:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"batch exceeds {settings.max_batch_records} records",
        )

    device = await session.scalar(
        select(Device).where(Device.install_id == payload.device.install_id)
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="device is not enrolled; call POST /devices/enroll first",
        )
    if device.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device is blocked")

    return await process_batch(session, payload, device, client_ip_hash=_hash_ip(request))
