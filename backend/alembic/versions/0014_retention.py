"""Mark measurements whose exact position has been aged out.

Every reading carries a GPS fix taken every ten seconds while a collector was
moving, which together is a record of where a person went. The map has never
published that — it aggregates to hexagons — but the database held it
indefinitely, which is a different promise from the one the platform makes.

The column records when a row's coordinates were replaced by the centre of the
hexagon they already belonged to. Nullable, because most rows have not been.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "measurements",
        sa.Column("coarsened_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The sweep asks for old rows that have not been done yet, which is this
    # pair; without the index it is a full scan of the measurement table daily.
    op.create_index(
        "ix_measurements_coarsened",
        "measurements",
        ["coarsened_at", "captured_at"],
    )


def downgrade() -> None:
    # Only the marker goes. The precision it records the loss of is not
    # recoverable, and a downgrade must not pretend otherwise.
    op.drop_index("ix_measurements_coarsened", table_name="measurements")
    op.drop_column("measurements", "coarsened_at")
