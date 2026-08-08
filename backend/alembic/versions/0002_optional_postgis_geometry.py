"""Add the PostGIS geometry column where PostGIS is available

Skips silently on servers without PostGIS. Run `scripts/enable_postgis.py`
after installing it to add the column to an existing database — this migration
will already be stamped and will not run a second time.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08
"""
from __future__ import annotations

import logging

from alembic import op

from app.db.postgis import add_geometry

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    if add_geometry(op.get_bind()):
        log.info("PostGIS geometry column added to measurements")
    else:
        log.warning(
            "PostGIS is not available on this server — skipping the geometry column. "
            "The platform runs without it; run scripts/enable_postgis.py once PostGIS "
            "is installed."
        )


def downgrade() -> None:
    from app.db.postgis import drop_geometry

    drop_geometry(op.get_bind())
