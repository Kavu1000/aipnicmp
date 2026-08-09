"""Aggregate tiles per operator as well as overall

The public map asks "can anyone get service here?". An operator asks "can my
customers get service here?" — and a village where one network works and three
do not is a different finding from one where none do. The combined view cannot
express that, so operators get their own aggregation.

Separate table rather than a column on h3_tiles: the combined row is the one
the public map reads on every request, and it should not have to filter or
de-duplicate to find it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "h3_tile_operators",
        sa.Column("h3_index", sa.String(20), primary_key=True),
        sa.Column("operator_name", sa.String(80), primary_key=True),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("colour", sa.String(16), nullable=False),
        sa.Column("dominant_state", sa.String(32)),
        sa.Column("worst_state", sa.String(32)),
        sa.Column("measurement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rsrp_dbm", sa.Float()),
        sa.Column("avg_download_kbps", sa.Float()),
        sa.Column("last_measured_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_h3_tile_operators_colour", "h3_tile_operators", ["colour"])
    op.create_index("ix_h3_tile_operators_operator", "h3_tile_operators", ["operator_name", "colour"])
    # The map queries by viewport, which is a range scan on both coordinates.
    op.create_index(
        "ix_h3_tile_operators_centroid", "h3_tile_operators", ["centroid_lat", "centroid_lon"]
    )


def downgrade() -> None:
    op.drop_table("h3_tile_operators")
