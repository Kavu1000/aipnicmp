from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.schemas.measurement import MeasurementBatch, MeasurementIn
from app.services.validation import Rejection, check_trajectory, validate_record
from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record


def _validated(record_dict: dict, key: Ed25519PrivateKey, public_key_b64: str):
    record = MeasurementIn.model_validate(sign_record(record_dict, key))
    return validate_record(record, public_key=public_key_b64)


def test_a_good_record_passes(device_key, public_key_b64):
    outcome = _validated(make_record(), device_key, public_key_b64)
    assert outcome.signature_valid is True
    assert outcome.flag_string is None


def test_no_service_record_is_accepted(device_key, public_key_b64):
    """The whole point of store-and-forward: a reading with no network at all is
    valid evidence, not a malformed record."""
    outcome = _validated(
        make_record(registered=False, network_type=None, rsrp=None, cells=0,
                    signal={"rsrp_dbm": None, "level": 0}),
        device_key,
        public_key_b64,
    )
    assert outcome.signature_valid is True


def test_position_outside_the_survey_area_is_rejected(device_key, public_key_b64):
    with pytest.raises(Rejection) as excinfo:
        _validated(make_record(lat=48.85, lon=2.35), device_key, public_key_b64)
    assert excinfo.value.reason == "out_of_area"


def test_future_timestamp_is_rejected(device_key, public_key_b64):
    with pytest.raises(Rejection) as excinfo:
        _validated(make_record(minutes_ago=-120), device_key, public_key_b64)
    assert excinfo.value.reason == "future_timestamp"


def test_registered_with_no_cells_is_rejected(device_key, public_key_b64):
    """Physically impossible, so it indicates a fabricated record."""
    with pytest.raises(Rejection) as excinfo:
        _validated(make_record(registered=True, cells=0), device_key, public_key_b64)
    assert excinfo.value.reason == "inconsistent_state"


def test_speed_test_without_registration_is_rejected(device_key, public_key_b64):
    with pytest.raises(Rejection) as excinfo:
        _validated(
            make_record(
                registered=False,
                cells=2,
                active_test={"download_kbps": 5000.0, "latency_ms": 40.0},
            ),
            device_key,
            public_key_b64,
        )
    assert excinfo.value.reason == "inconsistent_state"


def test_useless_gps_is_rejected_but_merely_coarse_gps_is_flagged(device_key, public_key_b64):
    with pytest.raises(Rejection) as excinfo:
        _validated(make_record(gps_accuracy_m=400.0), device_key, public_key_b64)
    assert excinfo.value.reason == "gps_inaccurate"

    outcome = _validated(make_record(gps_accuracy_m=55.0), device_key, public_key_b64)
    assert "coarse_gps" in outcome.flags


def test_long_offline_delay_is_flagged_not_rejected(device_key, public_key_b64):
    """Three weeks in a village with no coverage is the system working, not a
    device misbehaving."""
    outcome = _validated(make_record(minutes_ago=21 * 24 * 60), device_key, public_key_b64)
    assert "long_store_and_forward" in outcome.flags


def test_ancient_record_is_rejected(device_key, public_key_b64):
    with pytest.raises(Rejection) as excinfo:
        _validated(make_record(minutes_ago=60 * 24 * 60), device_key, public_key_b64)
    assert excinfo.value.reason == "too_old"


def test_unsigned_record_is_rejected_when_signatures_are_required(public_key_b64):
    record = MeasurementIn.model_validate(make_record())
    with pytest.raises(Rejection) as excinfo:
        validate_record(record, public_key=public_key_b64)
    assert excinfo.value.reason == "bad_signature"


def _batch(records: list[dict]) -> MeasurementBatch:
    return MeasurementBatch.model_validate(
        {
            "batch_id": "batch-0001",
            "device": {"install_id": "install-0123456789abcdef"},
            "records": records,
        }
    )


def test_a_normal_journey_passes_the_trajectory_check():
    """A bus travelling Route 13: a few km between readings a few minutes apart."""
    records = [
        make_record(record_id=f"rec-{i:08d}", minutes_ago=60 - i * 5, lat=BASE_LAT + i * 0.02)
        for i in range(6)
    ]
    assert check_trajectory(_batch(records)) == {}


def test_a_teleporting_record_is_rejected():
    """The forgery this check exists to catch: a record spliced in from a
    province the device could not have reached."""
    records = [
        make_record(record_id="rec-00000001", minutes_ago=40, lat=BASE_LAT, lon=BASE_LON),
        make_record(record_id="rec-00000002", minutes_ago=39, lat=14.5, lon=105.8),
        make_record(record_id="rec-00000003", minutes_ago=38, lat=BASE_LAT + 0.01, lon=BASE_LON),
    ]
    rejections = check_trajectory(_batch(records))
    assert "rec-00000002" in rejections
    assert rejections["rec-00000002"].reason == "impossible_trajectory"


def test_gps_jitter_while_stationary_is_not_treated_as_movement():
    """Consecutive readings a few metres apart imply an absurd speed if taken
    literally; below the noise floor the check must stay silent."""
    now = datetime.now(timezone.utc)
    records = []
    for i in range(4):
        captured = now - timedelta(seconds=120 - i)
        records.append(
            make_record(
                record_id=f"rec-{i:08d}",
                lat=BASE_LAT + i * 0.00005,
                lon=BASE_LON,
                **{"captured_at": captured.replace(microsecond=0).isoformat().replace("+00:00", "Z")},
            )
        )
    assert check_trajectory(_batch(records)) == {}


def test_only_the_later_of_an_impossible_pair_is_dropped():
    """A forger splicing into a real journey breaks the chain at the insertion
    point; the genuine earlier reading must survive."""
    records = [
        make_record(record_id="rec-good-01", minutes_ago=30, lat=BASE_LAT, lon=BASE_LON),
        make_record(record_id="rec-bad-001", minutes_ago=29, lat=15.0, lon=105.0),
    ]
    rejections = check_trajectory(_batch(records))
    assert set(rejections) == {"rec-bad-001"}
