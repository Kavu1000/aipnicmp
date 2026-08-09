"""Index measurements.received_at for incremental aggregation.

Aggregation moved from an hourly full rebuild to a one-minute incremental
pass, which asks for the hexagons touched by records that *arrived* since the
last run. Without this index that question is a sequential scan of the whole
measurement table, once a minute, forever.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_measurements_received_at", "measurements", ["received_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_measurements_received_at", table_name="measurements")
