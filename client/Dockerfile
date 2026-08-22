# syntax=docker/dockerfile:1.7
# Cloned from ../web/Dockerfile — same build/runtime split, different image.

# ---- builder -------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API base stays relative — nginx proxies /api to the backend inside the
# Docker network (see nginx.conf), so this one image works in development,
# on the pilot server and anywhere else without a rebuild. No other build
# arg is needed: this app signs in through its own /signin, never by
# pointing at another app (see src/App.tsx's note).
# Firebase Authentication's configuration, which Vite folds into the bundle at
# build time rather than reading at runtime — so unlike API_UPSTREAM below,
# these have to arrive here, as build arguments, and a rebuild is what changes
# them. Public by design: they identify the project to Google and are readable
# in the shipped JavaScript. Left empty, the app keeps the Google button
# instead (see src/auth/firebase.ts).
ARG VITE_FIREBASE_API_KEY=""
ARG VITE_FIREBASE_AUTH_DOMAIN=""
ARG VITE_FIREBASE_PROJECT_ID=""
ARG VITE_FIREBASE_APP_ID=""
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID

RUN npm run build

# ---- runtime -------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Defaults describe the compose deployment: the API is a sibling container
# called `api`, reached by Docker's own resolver, and it answers to whatever
# host the browser asked for. A deployment where the API lives elsewhere sets
# all three (see docs/deploy.md).
ENV API_UPSTREAM=http://api:8000
ENV API_HOST="\$host"
ENV DNS_RESOLVER=127.0.0.11

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
