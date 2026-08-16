"""Put each observed cell in its province and district.

So the tower counts can be filtered the same way the coverage map is. Assigned
from the cell's estimated centre, which is coarse — but a district is tens of
kilometres across and the estimate is good to about one, so the attribution
holds even where the position is too rough to draw.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("observed_cells", sa.Column("adm1_code", sa.String(length=32), nullable=True))
    op.add_column("observed_cells", sa.Column("adm2_code", sa.String(length=32), nullable=True))
    op.create_index("ix_observed_cells_adm1", "observed_cells", ["adm1_code"])
    op.create_index("ix_observed_cells_adm2", "observed_cells", ["adm2_code"])


def downgrade() -> None:
    op.drop_column("observed_cells", "adm2_code")
    op.drop_column("observed_cells", "adm1_code")
