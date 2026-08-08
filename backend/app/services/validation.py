"""Record validation and the anti-spoofing checks of proposal 3.5.

The threat is specific and worth naming: without these checks, anyone could
submit false data to make their own area look underserved and jump the
investment queue. That makes validation a fairness mechanism, not just hygiene.

Two severities are used deliberately:

* **Reject** — the record is not evidence of anything (bad signature, impossible
  coordinates, physically impossible journey).
* **Flag** — the record is probably fine but carries a caveat (coarse GPS, an
  unusually long store-and-forward delay). Flagged records are stored and the
  caveat travels with them, because discarding weak evidence from remote areas
  would bias the map towards exactly the places that already have coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.radio import is_plausible_rsrp
from app.schemas.measurement import MeasurementBatch, MeasurementIn
from app.services.geo import haversine_m, in_lao_bbox
from app.services.signing import verify_record

# Devices with a slightly wrong clock are common; a few minutes of drift is not
# evidence of fraud.
CLOCK_SKEW_TOLERANCE = timedelta(minutes=10)

# Below this distance, GPS noise dominates and any implied speed is meaningless.
TRAJECTORY_MIN_DISTANCE_M = 250.0

# Flag, not reject, past this delay: a fortnight in a village with no coverage
# is a plausible story, and it is the story the whole system exists to capture.
LONG_DELAY_FLAG_DAYS = 14


class Rejection(Exception):
    """Raised with a machine-readable reason so the client can log it usefully."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass
class ValidationOutcome:
    signature_valid: bool = False
    flags: list[str] = field(default_factory=list)

    @property
    def flag_string(self) -> str | None:
        return " ".join(sorted(set(self.flags))) or None


def validate_record(
    record: MeasurementIn,
    *,
    public_key: str | None,
    now: datetime | None = None,
) -> ValidationOutcome:
    """Check one record in isolation. Raises `Rejection` if it cannot be used."""
    now = now or datetime.now(timezone.utc)
    outcome = ValidationOutcome()

    if not in_lao_bbox(record.lat, record.lon):
        raise Rejection("out_of_area", f"({record.lat:.4f}, {record.lon:.4f}) is outside the survey area")

    if record.captured_at > now + CLOCK_SKEW_TOLERANCE:
        raise Rejection("future_timestamp", "captured_at is in the future")

    age = now - record.captured_at
    if age > timedelta(days=settings.max_record_age_days):
        raise Rejection("too_old", f"captured {age.days} days ago")
    if age > timedelta(days=LONG_DELAY_FLAG_DAYS):
        outcome.flags.append("long_store_and_forward")

    if record.gps_accuracy_m is not None:
        if record.gps_accuracy_m > settings.max_gps_accuracy_m:
            raise Rejection("gps_inaccurate", f"accuracy {record.gps_accuracy_m:.0f} m")
        if record.gps_accuracy_m > 30:
            outcome.flags.append("coarse_gps")
    else:
        # No accuracy figure usually means a coarse network-derived fix, which
        # is the one thing that cannot be true in an area with no network.
        outcome.flags.append("no_gps_accuracy")

    rsrp = record.signal.rsrp_dbm
    if rsrp is not None and not is_plausible_rsrp(rsrp):
        raise Rejection("implausible_rsrp", f"{rsrp} dBm is outside the physical range")

    # A device claiming to be registered while seeing no cells at all is
    # describing something that cannot happen.
    if record.registered and record.cells_visible == 0:
        raise Rejection("inconsistent_state", "registered but no cells visible")

    # Active test results from a device that was not registered are impossible:
    # a speed test needs a working data connection.
    if record.active_test is not None and not record.registered:
        raise Rejection("inconsistent_state", "active test result without registration")

    outcome.signature_valid = verify_record(record, public_key)
    if not outcome.signature_valid:
        if settings.require_record_signature:
            raise Rejection("bad_signature", "signature missing or does not verify")
        outcome.flags.append("unsigned")

    return outcome


def check_trajectory(batch: MeasurementBatch) -> dict[str, Rejection]:
    """Check that the journey described by a batch is physically possible.

    Returns rejections keyed by ``client_record_id`` rather than raising, so one
    impossible jump does not cost a device its entire upload.

    Only the *later* of an impossible pair is rejected. A forger who splices a
    fake point into a real journey breaks the chain at the point of insertion;
    dropping the earlier record would throw away genuine data instead.
    """
    rejections: dict[str, Rejection] = {}
    ordered = sorted(batch.records, key=lambda r: r.captured_at)

    previous: MeasurementIn | None = None
    for record in ordered:
        if previous is not None:
            distance = haversine_m(previous.lat, previous.lon, record.lat, record.lon)
            elapsed = (record.captured_at - previous.captured_at).total_seconds()

            if distance >= TRAJECTORY_MIN_DISTANCE_M:
                if elapsed <= 0:
                    rejections[record.client_record_id] = Rejection(
                        "impossible_trajectory",
                        f"{distance:.0f} m apart with no time between readings",
                    )
                    continue
                speed = distance / elapsed
                if speed > settings.max_plausible_speed_mps:
                    rejections[record.client_record_id] = Rejection(
                        "impossible_trajectory",
                        f"implies {speed:.0f} m/s between consecutive readings",
                    )
                    continue
        previous = record

    return rejections


def check_upload_origin(batch: MeasurementBatch, *, received_at: datetime) -> list[str]:
    """Compare the upload position against the last measurement.

    Advisory only. The gap between capture and upload is the defining feature of
    store-and-forward, and an honest device that stayed offline for a week will
    look strange by construction. This produces a flag for review, never a
    rejection.
    """
    if batch.uploaded_from_lat is None or batch.uploaded_from_lon is None:
        return []

    latest = max(batch.records, key=lambda r: r.captured_at)
    distance = haversine_m(latest.lat, latest.lon, batch.uploaded_from_lat, batch.uploaded_from_lon)
    elapsed = (received_at - latest.captured_at).total_seconds()

    if elapsed <= 0:
        return ["upload_before_capture"]
    if distance / elapsed > settings.max_plausible_speed_mps:
        return ["implausible_upload_origin"]
    return []
