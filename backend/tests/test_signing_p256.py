"""ECDSA P-256 signatures — the algorithm real Android devices use.

The Android Keystore cannot hold an Ed25519 key. It *can* generate a P-256 key
inside the secure element, where the private half is not extractable even from a
rooted phone, which is a stronger guarantee than a software Ed25519 key would
give. These tests stand in for a handset by producing byte-identical output to
Java's ``Signature.getInstance("SHA256withECDSA")``:

* the public key is X.509 SubjectPublicKeyInfo DER, as ``PublicKey.getEncoded()``
  returns
* the signature is DER-encoded (r, s), as Java's ECDSA emits

If the app ever fails to verify against a live server, the divergence is in one
of those two encodings, and these tests pin both.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.measurement import Measurement
from app.schemas.measurement import MeasurementIn
from app.services.signing import KeyAlgorithm, canonical_message, load_public_key, verify_record
from tests.conftest import BASE_LAT, make_record

P256_INSTALL_ID = "install-p256-0123456789ab"


@pytest.fixture
def p256_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def p256_public_b64(p256_key: ec.EllipticCurvePrivateKey) -> str:
    """Exactly what Android's ``PublicKey.getEncoded()`` produces, base64-encoded."""
    der = p256_key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode()


def sign_p256(record: dict, key: ec.EllipticCurvePrivateKey) -> dict:
    parsed = MeasurementIn.model_validate(record)
    signature = key.sign(canonical_message(parsed), ec.ECDSA(hashes.SHA256()))
    return {**record, "signature": base64.b64encode(signature).decode()}


def test_p256_public_key_parses(p256_public_b64: str):
    assert load_public_key(p256_public_b64, KeyAlgorithm.ECDSA_P256) is not None


def test_p256_key_fits_the_column_width(p256_public_b64: str):
    """The devices.public_key column is 256 characters; a P-256 SPKI is 124."""
    assert len(p256_public_b64) <= 256


def test_a_p256_signature_verifies(p256_key, p256_public_b64: str):
    record = MeasurementIn.model_validate(sign_p256(make_record(), p256_key))
    assert verify_record(record, p256_public_b64, KeyAlgorithm.ECDSA_P256) is True


def test_tampering_still_breaks_a_p256_signature(p256_key, p256_public_b64: str):
    signed = sign_p256(make_record(), p256_key)
    moved = MeasurementIn.model_validate({**signed, "lat": BASE_LAT + 0.4})
    assert verify_record(moved, p256_public_b64, KeyAlgorithm.ECDSA_P256) is False


def test_a_key_from_another_curve_is_refused():
    """Accepting any curve would let a device enrol a weak one and still satisfy
    'the signature verified'."""
    other = ec.generate_private_key(ec.SECP192R1())
    der = other.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    assert load_public_key(base64.b64encode(der).decode(), KeyAlgorithm.ECDSA_P256) is None


def test_algorithms_are_not_interchangeable(p256_key, p256_public_b64: str, public_key_b64: str):
    """A P-256 key read as Ed25519 — or the reverse — must fail rather than
    accidentally pass some length check."""
    record = MeasurementIn.model_validate(sign_p256(make_record(), p256_key))
    assert verify_record(record, p256_public_b64, KeyAlgorithm.ED25519) is False
    assert verify_record(record, public_key_b64, KeyAlgorithm.ECDSA_P256) is False


def test_unknown_algorithm_never_verifies(p256_key, p256_public_b64: str):
    record = MeasurementIn.model_validate(sign_p256(make_record(), p256_key))
    assert verify_record(record, p256_public_b64, "rsa_2048") is False


def test_garbage_der_is_refused(p256_key):
    record = MeasurementIn.model_validate(sign_p256(make_record(), p256_key))
    assert verify_record(record, base64.b64encode(b"not a key").decode(), KeyAlgorithm.ECDSA_P256) is False


async def test_an_android_style_device_enrols_and_uploads(
    client: AsyncClient, session: AsyncSession, p256_key, p256_public_b64: str
):
    """The whole path a real handset will take."""
    enrolment = await client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {
                "install_id": P256_INSTALL_ID,
                "manufacturer": "samsung",
                "model": "SM-A125F",
                "android_api": 34,
                "app_version": "0.1.0",
            },
            "public_key": p256_public_b64,
            "key_algorithm": "ecdsa_p256",
            "hardware_backed": True,
        },
    )
    assert enrolment.status_code == 200, enrolment.text
    assert enrolment.json()["key_algorithm"] == "ecdsa_p256"

    stored = await session.scalar(select(Device).where(Device.install_id == P256_INSTALL_ID))
    assert stored is not None and stored.key_algorithm == "ecdsa_p256"

    records = [
        sign_p256(make_record(record_id=f"rec-p256{i:04d}", minutes_ago=40 - i * 5), p256_key)
        for i in range(4)
    ]
    upload = await client.post(
        "/api/v1/measurements/batch",
        json={
            "batch_id": "batch-p256-0001",
            "device": {"install_id": P256_INSTALL_ID},
            "records": records,
        },
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["accepted"] == 4
    assert upload.json()["rejected"] == []

    saved = (await session.scalars(select(Measurement))).all()
    assert len(saved) == 4
    assert all(m.signature_valid for m in saved)


async def test_a_p256_device_cannot_be_hijacked_by_an_ed25519_key(
    client: AsyncClient, p256_public_b64: str, public_key_b64: str
):
    """Re-enrolling with a different algorithm is still a key change, and must
    be refused for the same reason any key rotation is."""
    first = await client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {"install_id": P256_INSTALL_ID},
            "public_key": p256_public_b64,
            "key_algorithm": "ecdsa_p256",
        },
    )
    assert first.status_code == 200

    hijack = await client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {"install_id": P256_INSTALL_ID},
            "public_key": public_key_b64,
            "key_algorithm": "ed25519",
        },
    )
    assert hijack.status_code == 409


async def test_enrolment_rejects_a_key_that_does_not_match_its_algorithm(
    client: AsyncClient, public_key_b64: str
):
    response = await client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {"install_id": "install-mismatch-0123456"},
            "public_key": public_key_b64,  # an Ed25519 key…
            "key_algorithm": "ecdsa_p256",  # …declared as P-256
        },
    )
    assert response.status_code == 422
