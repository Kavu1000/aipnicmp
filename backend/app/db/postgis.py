"""Optional PostGIS geometry for the measurements table.

The platform does not need PostGIS to run. Coverage is aggregated by H3 hexagon
id and the map queries a lat/lon range, so a stock PostgreSQL server serves the
whole pilot.

PostGIS earns its place later, in Layer 4: ranking tower sites means asking
"which unserved settlements fall within this radius", and doing that with real
geodesic distance and a GiST index is far better than approximating it in
Python.

So the geometry column is treated as an upgrade rather than a prerequisite.
This module is the single implementation, called both by migration 0002 (for
servers that already have PostGIS) and by ``scripts/enable_postgis.py`` (for
servers where it arrives later).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

GEOMETRY_COLUMN = "geom"
GEOMETRY_INDEX = "ix_measurements_geom"


def postgis_available(connection: Connection) -> bool:
    """True when the server *could* create the extension."""
    return bool(
        connection.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
        ).scalar()
    )


def postgis_installed(connection: Connection) -> bool:
    """True when the extension exists in this database."""
    return bool(
        connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
        ).scalar()
    )


def geometry_column_exists(connection: Connection) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'measurements' AND column_name = :column"
            ),
            {"column": GEOMETRY_COLUMN},
        ).scalar()
    )


def add_geometry(connection: Connection) -> bool:
    """Add the generated geometry column and its index. Returns False when
    PostGIS is unavailable, so callers can report rather than fail.

    The column is ``GENERATED ALWAYS AS ... STORED`` over (lon, lat): the
    coordinates remain the single source of truth and the geometry cannot drift
    out of step with them, which a trigger-maintained column eventually would.
    """
    if not postgis_available(connection):
        return False

    connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    if not geometry_column_exists(connection):
        connection.execute(
            text(
                f"""
                ALTER TABLE measurements
                ADD COLUMN {GEOMETRY_COLUMN} geography(Point, 4326)
                GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED
                """
            )
        )

    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS {GEOMETRY_INDEX} "
            f"ON measurements USING GIST ({GEOMETRY_COLUMN})"
        )
    )
    return True


def drop_geometry(connection: Connection) -> None:
    connection.execute(text(f"DROP INDEX IF EXISTS {GEOMETRY_INDEX}"))
    connection.execute(text(f"ALTER TABLE measurements DROP COLUMN IF EXISTS {GEOMETRY_COLUMN}"))
