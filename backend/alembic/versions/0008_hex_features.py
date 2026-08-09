"""The per-hexagon feature grid for the coverage model (Layer 4).

One row per hexagon of the country, independent of whether anyone has measured
it — that is what lets a model trained on measured hexagons be asked about the
rest.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hex_features",
        sa.Column("h3_index", sa.String(length=20), primary_key=True),
        sa.Column("resolution", sa.SmallInteger(), nullable=False),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("adm1_code", sa.String(length=32), nullable=True),
        sa.Column("adm2_code", sa.String(length=32), nullable=True),
        sa.Column("elevation_mean_m", sa.Float(), nullable=True),
        sa.Column("elevation_min_m", sa.Float(), nullable=True),
        sa.Column("elevation_max_m", sa.Float(), nullable=True),
        sa.Column("terrain_ruggedness_m", sa.Float(), nullable=True),
        sa.Column("population", sa.Float(), nullable=True),
        sa.Column("built_up_fraction", sa.Float(), nullable=True),
        sa.Column("cropland_fraction", sa.Float(), nullable=True),
        sa.Column("forest_fraction", sa.Float(), nullable=True),
        sa.Column("distance_to_observed_cell_km", sa.Float(), nullable=True),
        sa.Column("distance_to_road_km", sa.Float(), nullable=True),
        sa.Column("sources", sa.String(length=200), nullable=True),
        sa.Column("feature_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_hex_features_resolution", "hex_features", ["resolution"])
    op.create_index("ix_hex_features_adm1_code", "hex_features", ["adm1_code"])
    op.create_index("ix_hex_features_adm2_code", "hex_features", ["adm2_code"])
    op.create_index("ix_hex_features_adm1_adm2", "hex_features", ["adm1_code", "adm2_code"])
    op.create_index("ix_hex_features_res_pop", "hex_features", ["resolution", "population"])


def downgrade() -> None:
    op.drop_table("hex_features")
