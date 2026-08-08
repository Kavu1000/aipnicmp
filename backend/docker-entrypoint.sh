#!/bin/sh
# Container entrypoint.
#
# Configuration is checked before anything is attempted, so a missing variable
# says which one rather than surfacing as a connection error thirty lines into
# an Alembic stack trace. Passwords are never echoed.
set -e

fail() {
    echo "" >&2
    echo "[entrypoint] $1" >&2
    echo "" >&2
    exit 1
}

# Strip credentials so a URL can be shown in logs safely:
# postgresql+asyncpg://user:secret@host:5432/db  ->  postgresql+asyncpg://***@host:5432/db
redact() {
    echo "$1" | sed -E 's#(://)[^@/]*@#\1***@#'
}

if [ -z "${DATABASE_URL}" ]; then
    fail "DATABASE_URL is not set.
  Set it on this service, for example:
    DATABASE_URL=postgresql+asyncpg://user:pass@dbhost:5432/aipnicmp
  An '@' inside the password must be percent-encoded as %40."
fi

# Alembic uses the sync driver. Missing, it silently falls back to the
# localhost default and fails to connect — inside a container, localhost is the
# container itself, which is never where the database lives.
if [ "${RUN_MIGRATIONS}" = "true" ] && [ -z "${DATABASE_URL_SYNC}" ]; then
    fail "RUN_MIGRATIONS=true but DATABASE_URL_SYNC is not set.
  Migrations use the synchronous driver. Set the same database with psycopg:
    DATABASE_URL_SYNC=postgresql+psycopg://user:pass@dbhost:5432/aipnicmp"
fi

case "${DATABASE_URL}" in
    postgresql+asyncpg://*) ;;
    postgres://*|postgresql://*)
        fail "DATABASE_URL must name the async driver for the API:
    postgresql+asyncpg://...
  (currently: $(redact "${DATABASE_URL}"))" ;;
    *) fail "DATABASE_URL does not look like a PostgreSQL URL:
    $(redact "${DATABASE_URL}")" ;;
esac

echo "[entrypoint] database: $(redact "${DATABASE_URL}")"

# A stack often starts before the database accepts connections. Waiting beats
# a crash loop, and the message says plainly what is being waited for.
python - <<'PY' || fail "Could not reach the database. Check the host is
  correct and reachable from inside this container: 'localhost' here means the
  container itself, so a database elsewhere on the Docker host must be named by
  its service or container name, on a network this stack can see."
import os, re, socket, sys, time

url = os.environ["DATABASE_URL"]
match = re.search(r"@([^/:@]+)(?::(\d+))?/", url)
if not match:
    print("[entrypoint] could not parse a host from DATABASE_URL", file=sys.stderr)
    sys.exit(1)

host, port = match.group(1), int(match.group(2) or 5432)
deadline = time.time() + 60

while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"[entrypoint] {host}:{port} is accepting connections")
            sys.exit(0)
    except OSError as error:
        print(f"[entrypoint] waiting for {host}:{port} ({error.__class__.__name__})")
        time.sleep(3)

print(f"[entrypoint] gave up waiting for {host}:{port}", file=sys.stderr)
sys.exit(1)
PY

# Migrations run before the API accepts a request, but only when asked. Two
# reasons for the flag: more than one replica would otherwise race on the same
# migration, and a schema change should be a deliberate act rather than
# something that happens because a container restarted at 3am.
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "[entrypoint] applying database migrations"
    alembic upgrade head
    echo "[entrypoint] migrations up to date"
fi

exec "$@"
