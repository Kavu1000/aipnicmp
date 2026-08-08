"""Create the project database and its PostGIS extension, idempotently.

Run once against a server where the role already exists:

    python scripts/init_db.py --host db2.chax.site --user aiadmin

The password is read from PGPASSWORD or prompted for, never passed on the
command line, where it would land in the shell history.

The script reports what it finds before it changes anything: server version,
whether the role can create databases and extensions, and whether PostGIS is
even available on the server. Those three answers determine whether the rest of
the setup can proceed, and finding out here is much cheaper than finding out
halfway through a migration.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import psycopg
from psycopg import sql


def connect(host: str, port: int, user: str, password: str, dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host, port=port, user=user, password=password, dbname=dbname, connect_timeout=15
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", required=True)
    parser.add_argument("--dbname", default="aipnicmp", help="database to create")
    parser.add_argument(
        "--maintenance-db",
        default="postgres",
        help="existing database to connect to while creating the new one",
    )
    args = parser.parse_args()

    password = os.environ.get("PGPASSWORD") or getpass.getpass(f"password for {args.user}: ")

    try:
        conn = connect(args.host, args.port, args.user, password, args.maintenance_db)
    except psycopg.OperationalError as error:
        print(f"cannot reach {args.host}:{args.port} — {error}", file=sys.stderr)
        return 1

    with conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            print(cur.fetchone()[0])

            cur.execute(
                "SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname = current_user"
            )
            row = cur.fetchone()
            is_super, can_create_db = (row if row else (False, False))
            print(f"role {args.user}: superuser={is_super} createdb={can_create_db}")

            cur.execute(
                "SELECT default_version FROM pg_available_extensions WHERE name = 'postgis'"
            )
            available = cur.fetchone()
            if available is None:
                print(
                    "PostGIS is NOT available on this server. It must be installed at the OS "
                    "level before this project's schema can be created.",
                    file=sys.stderr,
                )
                return 2
            print(f"postgis available: {available[0]}")

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.dbname,))
            if cur.fetchone():
                print(f"database {args.dbname} already exists — leaving it alone")
            else:
                if not (is_super or can_create_db):
                    print(f"role {args.user} may not create databases", file=sys.stderr)
                    return 3
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.dbname)))
                print(f"created database {args.dbname}")

    # PostGIS is created inside the target database, so this needs a second
    # connection. CREATE EXTENSION normally requires superuser.
    with connect(args.host, args.port, args.user, password, args.dbname) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            except psycopg.errors.InsufficientPrivilege:
                print(
                    f"role {args.user} may not create extensions. Ask a superuser to run:\n"
                    f"    \\c {args.dbname}\n    CREATE EXTENSION postgis;",
                    file=sys.stderr,
                )
                return 4
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
            print(f"postgis installed in {args.dbname}: {cur.fetchone()[0]}")

    print("\nnext: set DATABASE_URL / DATABASE_URL_SYNC in backend/.env, then")
    print("      python -m alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
