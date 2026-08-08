from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.schemas.measurement import MeasurementIn
from app.services.signing import canonical_message, verify_record
from tests.conftest import make_record, sign_record


def test_canonical_message_is_exactly_specified():
    """Android must reproduce these bytes exactly. Pinning the string here means
    a change to the format cannot slip through unnoticed."""
    record = MeasurementIn.model_validate(
        make_record(record_id="rec-abc12345", lat=19.884500, lon=102.135000, rsrp=-95.0, cells=3)
    )
    message = canonical_message(record).decode()
    fields = message.split("|")

    assert fields[0] == "v1"
    assert fields[1] == "rec-abc12345"
    assert fields[2].endswith("Z") and len(fields[2]) == 20
    assert fields[3] == "19.884500"
    assert fields[4] == "102.135000"
    assert fields[5] == "1"
    assert fields[6] == "LTE"
    assert fields[7] == "-95.0"
    assert fields[8] == "3"


def test_missing_rsrp_is_an_empty_field_not_a_zero():
    """A zero would read as a physically impossible -0 dBm signal."""
    record = MeasurementIn.model_validate(
        make_record(rsrp=None, **{"signal": {"rsrp_dbm": None, "sinr_db": 5.0}})
    )
    assert canonical_message(record).decode().split("|")[7] == ""


def test_valid_signature_verifies(device_key: Ed25519PrivateKey, public_key_b64: str):
    signed = sign_record(make_record(), device_key)
    record = MeasurementIn.model_validate(signed)
    assert verify_record(record, public_key_b64) is True


def test_tampering_with_position_breaks_the_signature(
    device_key: Ed25519PrivateKey, public_key_b64: str
):
    """The attack the signature exists to stop: moving a genuine 'no service'
    reading to a different village while it sits in the upload queue."""
    signed = sign_record(make_record(), device_key)
    moved = MeasurementIn.model_validate({**signed, "lat": 18.5000})
    assert verify_record(moved, public_key_b64) is False


def test_tampering_with_signal_breaks_the_signature(
    device_key: Ed25519PrivateKey, public_key_b64: str
):
    signed = sign_record(make_record(rsrp=-95.0), device_key)
    weakened = MeasurementIn.model_validate(
        {**signed, "signal": {**signed["signal"], "rsrp_dbm": -135.0}}
    )
    assert verify_record(weakened, public_key_b64) is False


def test_another_devices_key_does_not_verify(device_key: Ed25519PrivateKey):
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    other = Ed25519PrivateKey.generate()
    other_pub = base64.b64encode(
        other.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()

    record = MeasurementIn.model_validate(sign_record(make_record(), device_key))
    assert verify_record(record, other_pub) is False


def test_missing_signature_never_passes(public_key_b64: str):
    record = MeasurementIn.model_validate(make_record())
    assert verify_record(record, public_key_b64) is False


def test_malformed_key_never_passes(device_key: Ed25519PrivateKey):
    record = MeasurementIn.model_validate(sign_record(make_record(), device_key))
    assert verify_record(record, "not-base64!!") is False
    assert verify_record(record, base64.b64encode(b"too short").decode()) is False
