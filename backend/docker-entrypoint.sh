#!/bin/sh
# Container entrypoint.
#
# Migrations run here, before the API accepts a single request, but only when
# RUN_MIGRATIONS=true. Two reasons for the flag:
#
#   * scaling to more than one replica would otherwise have several containers
#     racing to run the same migration
#   * a schema change should be a deliberate act, not something that happens
#     because a container restarted at 3am
#
# Set it on one container (or run the stack's `migrate` service once), then
# leave it off.
set -e

if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "[entrypoint] applying database migrations"
    alembic upgrade head
    echo "[entrypoint] migrations up to date"
fi

if [ -z "${DATABASE_URL}" ]; then
    echo "[entrypoint] DATABASE_URL is not set — the API cannot start" >&2
    exit 1
fi

exec "$@"
