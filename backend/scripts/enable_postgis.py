"""Add the PostGIS geometry column to an existing database.

Run this once after PostGIS becomes available on the server. Migration 0002
does the same thing for fresh installs, but it will already be stamped on a
database created before PostGIS arrived, so it will not run again.

    python scripts/enable_postgis.py

Idempotent: safe to run repeatedly, and safe to run on a database that already
has the column.
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine

from app.core.config import settings
from app.db.postgis import add_geometry, geometry_column_exists, postgis_available


def main() -> int:
    engine = create_engine(settings.database_url_sync)

    with engine.begin() as connection:
        if not postgis_available(connection):
            print(
                "PostGIS is not available on this server.\n"
                "For the official Docker image, switch to postgis/postgis:16-3.4 "
                "(a drop-in superset of postgres:16); on a Debian host, install "
                "postgresql-16-postgis-3.",
                file=sys.stderr,
            )
            return 1

        already = geometry_column_exists(connection)
        add_geometry(connection)
        print(
            "geometry column already present; index ensured"
            if already
            else "added measurements.geom and its GiST index"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
