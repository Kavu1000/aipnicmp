"""Device enrolment.

A device generates an Ed25519 keypair in the Android Keystore on first launch
and registers the public key here. The private key never leaves the device, so
a stolen server database cannot be used to forge measurements.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.measurement import DeviceInfo


class DeviceEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: DeviceInfo
    # Base64-encoded raw Ed25519 public key (32 bytes).
    public_key: str = Field(min_length=40, max_length=128)
    # Play Integrity token, verified server-side once a Play project exists.
    # Optional in phase 1 so the pilot can run with sideloaded builds.
    integrity_token: str | None = Field(default=None, max_length=8192)


class DeviceEnrollResponse(BaseModel):
    install_id: str
    enrolled_at: datetime
    trust_level: str
    signature_required: bool
