# syntax=docker/dockerfile:1.7

# ---- builder -------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API base stays relative on purpose. nginx proxies /api to the backend
# inside the Docker network, so this one image works in development, on the
# pilot server and anywhere else without a rebuild.
RUN npm run build

# ---- runtime -------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Where nginx forwards /api. Overridable so the web container can point at a
# backend outside this stack.
ENV API_UPSTREAM=http://api:8000

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
