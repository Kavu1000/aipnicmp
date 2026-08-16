"""Store the SIM's own network beside the one serving it.

A handset's printed operator name is chosen by firmware, and the pilot fleet
showed ten of them contradicting the published MCC/MNC assignment on 98.7% of
readings — leaving no way to tell whether the phones were wrong or the table
was. The SIM's own PLMN is encoded on the card and settles it: equal to the
serving network means normal service, different means roaming.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("measurements", sa.Column("sim_mcc", sa.String(length=3), nullable=True))
    op.add_column("measurements", sa.Column("sim_mnc", sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column("measurements", "sim_mnc")
    op.drop_column("measurements", "sim_mcc")
