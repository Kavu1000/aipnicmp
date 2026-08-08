"""Record signatures.

Proposal 3.5 requires each record to be signed *at capture time*, not at upload.
Records from uncovered areas may sit on a phone for days, and a signature made
at upload would prove only that the file was intact by the time someone chose
to send it.

Two algorithms are supported, and the reason is worth stating plainly:

* ``ecdsa_p256`` — what real Android devices use. The Android Keystore cannot
  hold an Ed25519 key, but it can hold a hardware-backed P-256 key whose private
  half never leaves the secure element. That is a *stronger* guarantee than a
  software Ed25519 key, which a rooted phone could simply copy out — and an
  extractable key defeats the entire point of signing at capture.
* ``ed25519`` — used by the simulator and the test suite, and available to any
  future client that can hold such a key safely.

The canonical message is identical for both, so the wire contract does not fork.
"""

from __future__ import annotations

import base64
import binascii
from datetime import timezone
from enum import StrEnum

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from app.schemas.measurement import MeasurementIn

CANONICAL_VERSION = "v1"


class KeyAlgorithm(StrEnum):
    ED25519 = "ed25519"
    ECDSA_P256 = "ecdsa_p256"


def _fmt_float(value: float | None, places: int) -> str:
    """Fixed decimal places, or empty for absent. Never scientific notation —
    Kotlin and Python disagree about when to use it."""
    if value is None:
        return ""
    return f"{value:.{places}f}"


def canonical_message(record: MeasurementIn) -> bytes:
    """The exact bytes a device signs.

    Format (UTF-8, fields joined by ``|``)::

        v1|<client_record_id>|<captured_at>|<lat>|<lon>|<registered>|
        <network_type>|<rsrp>|<cells_visible>

    where:

    * ``captured_at`` is UTC ISO-8601 to whole seconds with a ``Z`` suffix,
      e.g. ``2026-08-08T04:31:07Z``
    * ``lat`` and ``lon`` carry exactly 6 decimal places (~0.1 m — finer than
      any phone's GPS, so no real precision is lost)
    * ``registered`` is ``1`` or ``0``
    * ``network_type`` is the uppercase name, or empty
    * ``rsrp`` carries exactly 1 decimal place, or empty when unavailable
    * ``cells_visible`` is the integer count of serving plus neighbour cells

    Only fields a forger would want to change are covered. Adding a field later
    means a ``v2`` canonical form; the server keeps verifying ``v1`` for devices
    that have not updated.
    """
    captured = record.captured_at.astimezone(timezone.utc).replace(microsecond=0)
    parts = [
        CANONICAL_VERSION,
        record.client_record_id,
        captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
        _fmt_float(record.lat, 6),
        _fmt_float(record.lon, 6),
        "1" if record.registered else "0",
        (record.network_type or "").upper(),
        _fmt_float(record.signal.rsrp_dbm, 1),
        str(record.cells_visible),
    ]
    return "|".join(parts).encode("utf-8")


def _decode(value: str) -> bytes | None:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


def load_public_key(public_key_b64: str, algorithm: str = KeyAlgorithm.ED25519) -> object | None:
    """Parse an enrolled public key, or None if it is not a usable key of that type.

    * ``ed25519`` expects the raw 32-byte key, base64-encoded.
    * ``ecdsa_p256`` expects X.509 SubjectPublicKeyInfo DER, base64-encoded —
      exactly what Java's ``PublicKey.getEncoded()`` returns.
    """
    raw = _decode(public_key_b64)
    if raw is None:
        return None

    if algorithm == KeyAlgorithm.ED25519:
        if len(raw) != 32:
            return None
        try:
            return Ed25519PublicKey.from_public_bytes(raw)
        except ValueError:
            return None

    if algorithm == KeyAlgorithm.ECDSA_P256:
        try:
            key = load_der_public_key(raw)
        except (ValueError, UnsupportedAlgorithm):
            return None
        # Pinning the curve matters: accepting any curve would let a device
        # enrol a weak one and still satisfy "the signature verified".
        if not isinstance(key, ec.EllipticCurvePublicKey):
            return None
        if not isinstance(key.curve, ec.SECP256R1):
            return None
        return key

    return None


def verify_record(
    record: MeasurementIn,
    public_key_b64: str | None,
    algorithm: str = KeyAlgorithm.ED25519,
) -> bool:
    """True only when the signature demonstrably matches. Any missing piece,
    malformed key, unknown algorithm or bad encoding is a failure, never a pass."""
    if not record.signature or not public_key_b64:
        return False

    key = load_public_key(public_key_b64, algorithm)
    if key is None:
        return False

    signature = _decode(record.signature)
    if signature is None:
        return False

    message = canonical_message(record)

    try:
        if isinstance(key, Ed25519PublicKey):
            key.verify(signature, message)
        elif isinstance(key, ec.EllipticCurvePublicKey):
            # Java's "SHA256withECDSA" emits a DER-encoded (r, s) pair, which is
            # what this expects.
            key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        else:
            return False
    except InvalidSignature:
        return False
    except ValueError:
        # Malformed DER from a broken or hostile client.
        return False
    return True
