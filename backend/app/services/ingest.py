"""Batch ingestion: the write path from phone to PostGIS."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.radio import classify
from app.models.device import Device
from app.models.measurement import CellObservation, IngestBatch, Measurement
from app.schemas.measurement import (
    BatchResult,
    MeasurementBatch,
    MeasurementIn,
    RejectedRecord,
)
from app.services.geo import to_h3
from app.services.validation import (
    Rejection,
    check_trajectory,
    check_upload_origin,
    validate_record,
)


async def _existing_record_ids(session: AsyncSession, device_id: str, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    result = await session.execute(
        select(Measurement.client_record_id).where(
            Measurement.device_id == device_id,
            Measurement.client_record_id.in_(ids),
        )
    )
    return set(result.scalars().all())


def _build_measurement(
    record: MeasurementIn,
    *,
    device_id: str,
    batch_pk: int,
    received_at: datetime,
    signature_valid: bool,
    flags: str | None,
) -> Measurement:
    state = classify(
        registered=record.registered,
        network_type=record.network_type,
        cells_visible=record.cells_visible,
        rsrp_dbm=record.signal.rsrp_dbm,
        sinr_db=record.signal.sinr_db,
    )
    serving = record.serving_cell
    active = record.active_test

    return Measurement(
        device_id=device_id,
        batch_pk=batch_pk,
        client_record_id=record.client_record_id,
        captured_at=record.captured_at,
        received_at=received_at,
        upload_delay_s=int((received_at - record.captured_at).total_seconds()),
        lat=record.lat,
        lon=record.lon,
        gps_accuracy_m=record.gps_accuracy_m,
        altitude_m=record.altitude_m,
        speed_mps=record.speed_mps,
        registered=record.registered,
        network_type=(record.network_type or None),
        mcc=record.operator.mcc if record.operator else None,
        mnc=record.operator.mnc if record.operator else None,
        operator_name=record.operator.name if record.operator else None,
        rsrp_dbm=record.signal.rsrp_dbm,
        rsrq_db=record.signal.rsrq_db,
        sinr_db=record.signal.sinr_db,
        rssi_dbm=record.signal.rssi_dbm,
        signal_level=record.signal.level,
        serving_cid=serving.cid if serving else None,
        serving_lac_tac=serving.lac_tac if serving else None,
        serving_pci=serving.pci_psc if serving else None,
        serving_arfcn=serving.arfcn if serving else None,
        cells_visible=record.cells_visible,
        download_kbps=active.download_kbps if active else None,
        upload_kbps=active.upload_kbps if active else None,
        latency_ms=active.latency_ms if active else None,
        packet_loss_pct=active.packet_loss_pct if active else None,
        radio_state=state.value,
        radio_state_client=record.radio_state_client.value if record.radio_state_client else None,
        signature_valid=signature_valid,
        quality_flags=flags,
        h3_index=to_h3(record.lat, record.lon, settings.h3_resolution),
    )


def _cell_rows(record: MeasurementIn) -> list[CellObservation]:
    rows: list[CellObservation] = []
    cells = list(record.neighbor_cells)
    if record.serving_cell is not None:
        cells.append(record.serving_cell)
    for cell in cells:
        rows.append(
            CellObservation(
                radio=cell.radio,
                mcc=cell.mcc,
                mnc=cell.mnc,
                cid=cell.cid,
                lac_tac=cell.lac_tac,
                pci_psc=cell.pci_psc,
                arfcn=cell.arfcn,
                rsrp_dbm=cell.rsrp_dbm,
                is_registered=cell.is_registered,
            )
        )
    return rows


async def process_batch(
    session: AsyncSession,
    batch: MeasurementBatch,
    device: Device,
    *,
    client_ip_hash: str | None = None,
) -> BatchResult:
    """Validate and store one upload.

    Records are judged individually. A device that has been offline for a week
    may never get a second upload window, so a batch containing some bad records
    still yields its good ones.
    """
    received_at = datetime.now(timezone.utc)

    batch_row = IngestBatch(
        batch_id=batch.batch_id,
        device_id=device.install_id,
        received_at=received_at,
        record_count=len(batch.records),
        upload_lat=batch.uploaded_from_lat,
        upload_lon=batch.uploaded_from_lon,
        client_ip_hash=client_ip_hash,
    )
    session.add(batch_row)
    await session.flush()

    trajectory_rejections = check_trajectory(batch)
    batch_flags = check_upload_origin(batch, received_at=received_at)
    already_stored = await _existing_record_ids(
        session, device.install_id, [r.client_record_id for r in batch.records]
    )

    accepted = 0
    duplicates = 0
    rejected: list[RejectedRecord] = []
    seen_in_batch: set[str] = set()

    for record in batch.records:
        if record.client_record_id in already_stored or record.client_record_id in seen_in_batch:
            duplicates += 1
            continue
        seen_in_batch.add(record.client_record_id)

        trajectory_problem = trajectory_rejections.get(record.client_record_id)
        if trajectory_problem is not None:
            rejected.append(
                RejectedRecord(
                    client_record_id=record.client_record_id,
                    reason=trajectory_problem.reason,
                    detail=trajectory_problem.detail,
                )
            )
            continue

        try:
            outcome = validate_record(record, public_key=device.public_key, now=received_at)
        except Rejection as problem:
            rejected.append(
                RejectedRecord(
                    client_record_id=record.client_record_id,
                    reason=problem.reason,
                    detail=problem.detail,
                )
            )
            continue

        outcome.flags.extend(batch_flags)
        measurement = _build_measurement(
            record,
            device_id=device.install_id,
            batch_pk=batch_row.id,
            received_at=received_at,
            signature_valid=outcome.signature_valid,
            flags=outcome.flag_string,
        )
        session.add(measurement)
        await session.flush()

        for cell_row in _cell_rows(record):
            cell_row.measurement_id = measurement.id
            session.add(cell_row)

        accepted += 1

    batch_row.accepted_count = accepted
    batch_row.rejected_count = len(rejected)

    await session.execute(
        update(Device)
        .where(Device.install_id == device.install_id)
        .values(
            last_seen_at=received_at,
            records_accepted=Device.records_accepted + accepted,
            records_rejected=Device.records_rejected + len(rejected),
        )
    )
    await session.commit()

    return BatchResult(
        batch_id=batch.batch_id,
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
    )
