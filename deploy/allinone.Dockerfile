# syntax=docker/dockerfile:1.7
#
# The public site and the API in one container.
#
# Not how this platform is meant to run. `docker-compose.yml` puts the API,
# the dashboard and the public site in separate containers, which is right:
# they scale differently, they are rebuilt on different days, and a crash in
# one should not take the others with it. This image exists because a hosting
# plan can cap how many containers a project may have at once, and one
# container that works beats three that cannot be provisioned.
#
# What it is *not* is a second copy of the application. Both halves are built
# from the same sources as their own images — the same client/, the same
# backend/ — so nothing here can drift from what the compose deployment runs.
# The only thing this file invents is the arrangement.
#
# Built from the repository root, because it needs both halves:
#   docker build -f deploy/allinone.Dockerfile .

# ---- the site ------------------------------------------------------------
FROM node:22-alpine AS site

WORKDIR /build

COPY client/package.json client/package-lock.json ./
RUN npm ci

COPY client/ ./

# Vite folds these into the bundle at build time; see client/Dockerfile for
# why they are arguments rather than runtime configuration, and
# client/src/auth/firebase.ts for why they are not secrets.
ARG VITE_FIREBASE_API_KEY=""
ARG VITE_FIREBASE_AUTH_DOMAIN=""
ARG VITE_FIREBASE_PROJECT_ID=""
ARG VITE_FIREBASE_APP_ID=""
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID

RUN npm run build

# ---- the API's dependencies ---------------------------------------------
FROM python:3.12-slim AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---- runtime -------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=wheels /opt/venv /opt/venv

WORKDIR /app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts

COPY --from=site /build/dist /usr/share/nginx/html
COPY deploy/allinone.nginx.conf /etc/nginx/sites-available/default
COPY deploy/allinone-entrypoint.sh /usr/local/bin/allinone-entrypoint.sh
RUN chmod +x /usr/local/bin/allinone-entrypoint.sh

# Root, unlike backend/Dockerfile's unprivileged user: nginx binds port 80 and
# writes its pid and logs under /var. Worth naming because it is a real step
# down from the image this replaces, and a reason to prefer the compose
# deployment wherever the container budget allows it.

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz && curl -fsS http://127.0.0.1/api/v1/health || exit 1

CMD ["allinone-entrypoint.sh"]
