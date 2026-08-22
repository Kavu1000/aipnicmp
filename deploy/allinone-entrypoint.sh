#!/bin/bash
# Start the API, then the site in front of it.
#
# Two processes in one container, which is the compromise this whole image is:
# `wait -n` is what keeps it honest. Without it, uvicorn could die and nginx
# would carry on serving a site whose every request fails — a container that
# looks healthy and answers nothing. With it, either process exiting takes the
# container down, and the platform restarts it.
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[entrypoint] DATABASE_URL is not set" >&2
    exit 1
fi

# Off by default, exactly as in backend/docker-entrypoint.sh: a schema change
# should be a deliberate act rather than something a 3am restart performs.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] applying database migrations"
    alembic upgrade head
fi

echo "[entrypoint] starting the API on 127.0.0.1:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
api=$!

echo "[entrypoint] starting nginx on :80"
nginx -g 'daemon off;' &
web=$!

wait -n "$api" "$web"
echo "[entrypoint] a process exited; stopping the container" >&2
exit 1
