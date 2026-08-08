"""Keep why records were rejected

A rejected record is discarded by the device and never sent again, so without
this the only trace of lost data was a count. During a pilot that is the
difference between "the collector is working" and "every reading from that
phone is being thrown away for a reason nobody can see".

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingest_batches",
        sa.Column("rejection_summary", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ingest_batches", "rejection_summary")
