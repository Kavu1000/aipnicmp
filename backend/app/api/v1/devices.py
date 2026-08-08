from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.device import Device
from app.schemas.device import DeviceEnrollRequest, DeviceEnrollResponse
from app.services.signing import load_public_key

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/enroll", response_model=DeviceEnrollResponse)
async def enroll_device(
    payload: DeviceEnrollRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviceEnrollResponse:
    """Register an installation and its capture-time signing key.

    Re-enrolment with the same ``install_id`` is allowed but never rotates the
    key: if it did, anyone who learned an install id could replace the key and
    then sign whatever they liked. A device that loses its key must enrol as a
    new installation.
    """
    if load_public_key(payload.public_key) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="public_key must be a base64-encoded 32-byte Ed25519 key",
        )

    install_id = payload.device.install_id
    existing = await session.scalar(select(Device).where(Device.install_id == install_id))

    if existing is not None:
        if existing.is_blocked:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device is blocked")
        if existing.public_key and existing.public_key != payload.public_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="this install_id is already enrolled with a different key",
            )
        existing.public_key = payload.public_key
        existing.app_version = payload.device.app_version or existing.app_version
        existing.last_seen_at = datetime.now(timezone.utc)
        await session.commit()
        return DeviceEnrollResponse(
            install_id=existing.install_id,
            enrolled_at=existing.enrolled_at,
            trust_level=existing.trust_level,
            signature_required=True,
        )

    device = Device(
        install_id=install_id,
        public_key=payload.public_key,
        manufacturer=payload.device.manufacturer,
        model=payload.device.model,
        android_api=payload.device.android_api,
        app_version=payload.device.app_version,
        # Play Integrity is verified in a later phase; until then an enrolled
        # device is trusted only as far as its signature chain goes.
        trust_level="attested" if payload.integrity_token else "enrolled",
        enrolled_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
    )
    session.add(device)
    await session.commit()

    return DeviceEnrollResponse(
        install_id=device.install_id,
        enrolled_at=device.enrolled_at,
        trust_level=device.trust_level,
        signature_required=True,
    )
