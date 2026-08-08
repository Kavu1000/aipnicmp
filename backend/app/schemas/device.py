"""Device enrolment.

A device generates a signing keypair on first launch and registers the public
key here. The private key never leaves the device, so a stolen server database
cannot be used to forge measurements.

Android devices use ``ecdsa_p256``: the Keystore can generate that key inside
the secure element, where the private half is not extractable even on a rooted
phone. It cannot hold an Ed25519 key at all, which is why the platform speaks
both algorithms rather than picking the tidier one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.measurement import DeviceInfo

KeyAlgorithmName = Literal["ed25519", "ecdsa_p256"]


class DeviceEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: DeviceInfo

    # Base64. Raw 32 bytes for ed25519; X.509 SubjectPublicKeyInfo DER for
    # ecdsa_p256 — exactly what Java's PublicKey.getEncoded() returns.
    public_key: str = Field(min_length=40, max_length=256)

    # Defaults to ed25519 so the simulator and older clients keep working
    # unchanged. Android clients must send ecdsa_p256 explicitly.
    key_algorithm: KeyAlgorithmName = "ed25519"

    # True when the key was generated inside the secure element. Recorded rather
    # than trusted — a client can claim anything — but useful for judging how
    # much weight a device's records deserve once Play Integrity is verified.
    hardware_backed: bool = False

    # Play Integrity token, verified server-side once a Play project exists.
    # Optional in phase 1 so the pilot can run with sideloaded builds.
    integrity_token: str | None = Field(default=None, max_length=8192)


class DeviceEnrollResponse(BaseModel):
    install_id: str
    enrolled_at: datetime
    trust_level: str
    key_algorithm: str
    signature_required: bool
