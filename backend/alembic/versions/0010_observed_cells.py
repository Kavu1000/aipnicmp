"""Where the fleet has observed each base station cell.

Derived from the platform's own cell observations rather than bought in, so
the picture improves with every drive. A row is an observation summary; whether
its position can be believed is a column of its own.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observed_cells",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mcc", sa.String(length=3), nullable=False),
        sa.Column("mnc", sa.String(length=3), nullable=False),
        sa.Column("lac_tac", sa.Integer(), nullable=False),
        sa.Column("cid", sa.Integer(), nullable=False),
        sa.Column("operator_name", sa.String(length=120), nullable=True),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("est_lat", sa.Float(), nullable=False),
        sa.Column("est_lon", sa.Float(), nullable=False),
        sa.Column("spread_m", sa.Float(), nullable=False),
        sa.Column("uncertainty_m", sa.Float(), nullable=False),
        sa.Column("position_is_reliable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("best_rsrp_dbm", sa.Float(), nullable=True),
        sa.Column("best_lat", sa.Float(), nullable=True),
        sa.Column("best_lon", sa.Float(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_observed_cells_identity", "observed_cells",
        ["mcc", "mnc", "lac_tac", "cid"], unique=True,
    )
    op.create_index("ix_observed_cells_operator_name", "observed_cells", ["operator_name"])
    op.create_index("ix_observed_cells_reliable", "observed_cells", ["position_is_reliable"])


def downgrade() -> None:
    op.drop_table("observed_cells")
