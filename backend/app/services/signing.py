"""Ed25519 record signatures.

Proposal 3.5 requires each record to be signed *at capture time*, not at upload.
Records from uncovered areas may sit on a phone for days, and a signature made
at upload would prove only that the file was intact by the time someone chose
to send it.

The canonical string below is the contract with the Android client. Both sides
must produce byte-identical input, so it is defined here in painful detail and
mirrored in `android/README.md`.
"""

from __future__ import annotations

import base64
import binascii
from datetime import timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.schemas.measurement import MeasurementIn

CANONICAL_VERSION = "v1"


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

    Only fields that a forger would want to change are covered. Adding a field
    later means a ``v2`` canonical form; the server keeps verifying ``v1`` for
    devices that have not updated.
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


def load_public_key(public_key_b64: str) -> Ed25519PublicKey | None:
    """Accept a raw 32-byte Ed25519 key, base64-encoded."""
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) != 32:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(raw)
    except ValueError:
        return None


def verify_record(record: MeasurementIn, public_key_b64: str | None) -> bool:
    """True only when the signature demonstrably matches. Any missing piece,
    malformed key or bad encoding is a failure, never a pass."""
    if not record.signature or not public_key_b64:
        return False

    key = load_public_key(public_key_b64)
    if key is None:
        return False

    try:
        signature = base64.b64decode(record.signature, validate=True)
    except (binascii.Error, ValueError):
        return False

    try:
        key.verify(signature, canonical_message(record))
    except InvalidSignature:
        return False
    return True
