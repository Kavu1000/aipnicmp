"""Administrative areas, and area codes on the tile tables

The map is read by people who think in provinces and districts, not hexagons.
This adds the places themselves, and stamps every tile with the areas it falls
in so that filtering the map by province is an indexed equality rather than a
point-in-polygon test on every request.

The geometry is stored as JSONB rather than a PostGIS geometry column on
purpose: PostGIS remains an optional upgrade for this platform (see
app/db/postgis.py), and area filtering must work without it. Membership is
resolved once, at tile rebuild time, in Python.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Postgres in production, plain JSON for the SQLite the test suite runs on.
BOUNDARY_JSON = sa.JSON().with_variant(JSONB, "postgresql")

TILE_TABLES = ("h3_tiles", "h3_tile_operators")
AREA_COLUMNS = ("adm1_code", "adm2_code", "adm3_code")


def upgrade() -> None:
    op.create_table(
        "admin_areas",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("name_en", sa.String(120), nullable=False),
        sa.Column("name_lo", sa.String(120)),
        sa.Column("parent_code", sa.String(32)),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("min_lat", sa.Float(), nullable=False),
        sa.Column("min_lon", sa.Float(), nullable=False),
        sa.Column("max_lat", sa.Float(), nullable=False),
        sa.Column("max_lon", sa.Float(), nullable=False),
        sa.Column("area_km2", sa.Float()),
        # NULL for a village published as a point rather than a polygon. The
        # platform will not invent an outline it was not given.
        sa.Column("boundary", BOUNDARY_JSON),
        sa.Column("boundary_points", sa.Integer()),
        sa.Column("radius_m", sa.Float()),
        sa.Column("source", sa.String(120)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_admin_areas_level", "admin_areas", ["level"])
    op.create_index("ix_admin_areas_parent_code", "admin_areas", ["parent_code"])
    # Drives the cascading selector: "the districts of this province".
    op.create_index("ix_admin_areas_level_parent", "admin_areas", ["level", "parent_code"])
    op.create_index("ix_admin_areas_level_name", "admin_areas", ["level", "name_en"])

    for table in TILE_TABLES:
        for column in AREA_COLUMNS:
            op.add_column(table, sa.Column(column, sa.String(32)))
            op.create_index(f"ix_{table}_{column}", table, [column])

    op.create_index(
        "ix_h3_tile_operators_adm2", "h3_tile_operators", ["adm2_code", "operator_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_h3_tile_operators_adm2", table_name="h3_tile_operators")

    for table in TILE_TABLES:
        for column in AREA_COLUMNS:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
            op.drop_column(table, column)

    op.drop_index("ix_admin_areas_level_name", table_name="admin_areas")
    op.drop_index("ix_admin_areas_level_parent", table_name="admin_areas")
    op.drop_index("ix_admin_areas_parent_code", table_name="admin_areas")
    op.drop_index("ix_admin_areas_level", table_name="admin_areas")
    op.drop_table("admin_areas")
