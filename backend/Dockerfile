# syntax=docker/dockerfile:1.7

# ---- builder -------------------------------------------------------------
# Wheels are built once here so the runtime image carries no compiler.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Only needed if a dependency has no manylinux wheel; harmless when they all do.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---- runtime -------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is here for the container healthcheck, not for the application.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 aipnicmp

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=aipnicmp:aipnicmp alembic.ini ./
COPY --chown=aipnicmp:aipnicmp alembic ./alembic
COPY --chown=aipnicmp:aipnicmp app ./app
COPY --chown=aipnicmp:aipnicmp scripts ./scripts
COPY --chown=aipnicmp:aipnicmp docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Runs unprivileged: this container accepts uploads from the public internet.
USER aipnicmp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
