"""Initial schema: devices, measurements, cells, tiles, sites, reports

Revision ID: 0001
Revises:
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS must be created by a superuser. If this fails, ask the DBA to run
    #   CREATE EXTENSION postgis;
    # once against this database and re-run the migration.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "devices",
        sa.Column("install_id", sa.String(64), primary_key=True),
        sa.Column("public_key", sa.String(128)),
        sa.Column("manufacturer", sa.String(120)),
        sa.Column("model", sa.String(120)),
        sa.Column("android_api", sa.Integer()),
        sa.Column("app_version", sa.String(32)),
        sa.Column("trust_level", sa.String(16), nullable=False, server_default="enrolled"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("records_accepted", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.BigInteger(), nullable=False, server_default="0"),
    )

    op.create_table(
        "ingest_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.install_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upload_lat", sa.Float()),
        sa.Column("upload_lon", sa.Float()),
        sa.Column("client_ip_hash", sa.String(64)),
        sa.UniqueConstraint("device_id", "batch_id", name="uq_ingest_batches_device_batch"),
    )
    op.create_index("ix_ingest_batches_batch_id", "ingest_batches", ["batch_id"])
    op.create_index("ix_ingest_batches_device_id", "ingest_batches", ["device_id"])

    op.create_table(
        "measurements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.install_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_pk", sa.BigInteger(), sa.ForeignKey("ingest_batches.id", ondelete="SET NULL")),
        sa.Column("client_record_id", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("upload_delay_s", sa.Integer()),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("gps_accuracy_m", sa.Float()),
        sa.Column("altitude_m", sa.Float()),
        sa.Column("speed_mps", sa.Float()),
        sa.Column("registered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("network_type", sa.String(24)),
        sa.Column("mcc", sa.String(3)),
        sa.Column("mnc", sa.String(3)),
        sa.Column("operator_name", sa.String(80)),
        sa.Column("rsrp_dbm", sa.Float()),
        sa.Column("rsrq_db", sa.Float()),
        sa.Column("sinr_db", sa.Float()),
        sa.Column("rssi_dbm", sa.Float()),
        sa.Column("signal_level", sa.SmallInteger()),
        sa.Column("serving_cid", sa.BigInteger()),
        sa.Column("serving_lac_tac", sa.Integer()),
        sa.Column("serving_pci", sa.Integer()),
        sa.Column("serving_arfcn", sa.Integer()),
        sa.Column("cells_visible", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("download_kbps", sa.Float()),
        sa.Column("upload_kbps", sa.Float()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("packet_loss_pct", sa.Float()),
        sa.Column("radio_state", sa.String(32), nullable=False),
        sa.Column("radio_state_client", sa.String(32)),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quality_flags", sa.String(255)),
        sa.Column("h3_index", sa.String(20)),
        sa.UniqueConstraint("device_id", "client_record_id", name="uq_measurements_device_record"),
    )
    op.create_index("ix_measurements_device_id", "measurements", ["device_id"])
    op.create_index("ix_measurements_captured_at", "measurements", ["captured_at"])
    op.create_index("ix_measurements_h3_index", "measurements", ["h3_index"])
    op.create_index("ix_measurements_radio_state", "measurements", ["radio_state"])
    op.create_index("ix_measurements_h3_captured", "measurements", ["h3_index", "captured_at"])
    op.create_index("ix_measurements_state_captured", "measurements", ["radio_state", "captured_at"])

    # Geometry is derived, never supplied: lat/lon are the single source of
    # truth and the column cannot drift out of step with them.
    op.execute(
        """
        ALTER TABLE measurements
        ADD COLUMN geom geography(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED
        """
    )
    op.execute("CREATE INDEX ix_measurements_geom ON measurements USING GIST (geom)")

    op.create_table(
        "cell_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "measurement_id",
            sa.BigInteger(),
            sa.ForeignKey("measurements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("radio", sa.String(8)),
        sa.Column("mcc", sa.String(3)),
        sa.Column("mnc", sa.String(3)),
        sa.Column("cid", sa.BigInteger()),
        sa.Column("lac_tac", sa.Integer()),
        sa.Column("pci_psc", sa.Integer()),
        sa.Column("arfcn", sa.Integer()),
        sa.Column("rsrp_dbm", sa.Float()),
        sa.Column("is_registered", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_cell_observations_measurement_id", "cell_observations", ["measurement_id"])
    op.create_index("ix_cell_observations_identity", "cell_observations", ["mcc", "mnc", "lac_tac", "cid"])

    op.create_table(
        "h3_tiles",
        sa.Column("h3_index", sa.String(20), primary_key=True),
        sa.Column("resolution", sa.SmallInteger(), nullable=False),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("colour", sa.String(16), nullable=False),
        sa.Column("state_score", sa.Float()),
        sa.Column("dominant_state", sa.String(32)),
        sa.Column("worst_state", sa.String(32)),
        sa.Column("measurement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rsrp_dbm", sa.Float()),
        sa.Column("avg_download_kbps", sa.Float()),
        sa.Column("avg_latency_ms", sa.Float()),
        sa.Column("is_predicted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("prediction_confidence", sa.Float()),
        sa.Column("first_measured_at", sa.DateTime(timezone=True)),
        sa.Column("last_measured_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_h3_tiles_resolution", "h3_tiles", ["resolution"])
    op.create_index("ix_h3_tiles_colour", "h3_tiles", ["colour"])
    op.create_index("ix_h3_tiles_res_colour", "h3_tiles", ["resolution", "colour"])
    # The map queries by viewport, which is a range scan on both coordinates.
    op.create_index("ix_h3_tiles_centroid", "h3_tiles", ["centroid_lat", "centroid_lon"])

    op.create_table(
        "candidate_sites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("h3_index", sa.String(20)),
        sa.Column("rank", sa.Integer()),
        sa.Column("score", sa.Float()),
        sa.Column("population_covered", sa.Integer()),
        sa.Column("unserved_population", sa.Integer()),
        sa.Column("tiles_improved", sa.Integer()),
        sa.Column("recommendation", sa.String(32)),
        sa.Column("has_grid_power", sa.Boolean()),
        sa.Column("province", sa.String(80)),
        sa.Column("district", sa.String(80)),
        sa.Column("model_version", sa.String(32)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_candidate_sites_rank", "candidate_sites", ["rank"])
    op.create_index("ix_candidate_sites_h3_index", "candidate_sites", ["h3_index"])
    op.create_index("ix_candidate_sites_province", "candidate_sites", ["province"])

    op.create_table(
        "user_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.install_id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("h3_index", sa.String(20)),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("operator_name", sa.String(80)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("forwarded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_reports_device_id", "user_reports", ["device_id"])
    op.create_index("ix_user_reports_created_at", "user_reports", ["created_at"])
    op.create_index("ix_user_reports_h3_index", "user_reports", ["h3_index"])
    op.create_index("ix_user_reports_category", "user_reports", ["category"])
    op.create_index("ix_user_reports_status", "user_reports", ["status"])


def downgrade() -> None:
    op.drop_table("user_reports")
    op.drop_table("candidate_sites")
    op.drop_table("h3_tiles")
    op.drop_table("cell_observations")
    op.drop_table("measurements")
    op.drop_table("ingest_batches")
    op.drop_table("devices")
    # postgis is left installed: other schemas in the same database may use it.
