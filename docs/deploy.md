# Deploying with GitHub Actions and Portainer

GitHub builds the container images; Portainer pulls and runs them. Nothing is
built on the server.

```
push to main ──► GitHub Actions ──► ghcr.io/OWNER/aipnicmp-backend:latest
                  (tests first)      ghcr.io/OWNER/aipnicmp-web:latest
                                              │
                                              ▼
                                     Portainer stack pulls and runs
```

## What gets built

| Image | Contents | Size |
| --- | --- | --- |
| `aipnicmp-backend` | FastAPI + Alembic + Celery, Python 3.12-slim, non-root | ~250 MB |
| `aipnicmp-web` | The map, built to static files and served by nginx | ~60 MB |

The Android APK is built by the same workflow and attached to each run as an
artifact, so a collector build is always downloadable without a local toolchain.

Both images are pushed only after the backend tests, the migration round-trip,
the web typecheck and the Android unit tests have passed. A broken canonical
signing string can therefore never reach the server.

## 1. Push the repository

```bash
gh repo create aipnicmp --private --source=. --remote=origin --push
```

**Private is the right default.** The code contains no credentials — that was
checked — but `docs/setup.md` and `scripts/init_db.py` name the database host
and the `aiadmin` username, which is free reconnaissance for anyone who finds
the repo. Make it public later, once those are parameterised, if the project
wants to publish its methodology.

## 2. Let CI build the images

The workflow runs on every push to `main`. Watch it with:

```bash
gh run watch
```

Images land at `ghcr.io/<owner>/aipnicmp-backend:latest` and `-web:latest`.

**GHCR packages are private by default.** Either make them public (GitHub →
your profile → Packages → each package → Package settings → Change visibility),
or give Portainer a pull secret — see step 4.

## 3. Create the stack in Portainer

Portainer → **Stacks** → **Add stack** → **Repository**, pointing at the GitHub
repo with compose path `docker-compose.yml`. Or choose **Web editor** and paste
the contents of that file.

Then fill in **Environment variables**:

| Variable | Value | Notes |
| --- | --- | --- |
| `IMAGE_OWNER` | your GitHub username | lowercase; GHCR paths are case-sensitive |
| `IMAGE_TAG` | `latest` | or a `v1.2.3` tag for a pinned deploy |
| `DATABASE_URL` | `postgresql+asyncpg://aiadmin:PASSWORD@db2:5432/aipnicmp` | `@` in the password **must** be `%40` |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://aiadmin:PASSWORD@db2:5432/aipnicmp` | same database, sync driver, for Alembic |
| `CORS_ORIGINS` | `https://map.yourdomain.la` | comma-separated; no trailing slash |
| `JWT_SECRET` | 48 random bytes | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_TOKEN` | another random string | empty keeps the admin endpoints closed |
| `WEB_PORT` | `8090` | host port for nginx |

### The database host inside Docker

The stack does **not** include PostgreSQL. The database already exists and holds
real collected data; a compose file able to recreate it is a compose file able
to destroy it.

If Postgres runs as a container on the same Docker host, put both on the same
network and use its **service or container name** as the host — not
`localhost`, which inside a container means the container itself. If it is on
another machine, use its address and make sure the stack can reach it.

## 4. If the images are private

Portainer → **Registries** → **Add registry** → **Custom**:

- URL: `ghcr.io`
- Username: your GitHub username
- Password: a personal access token with `read:packages`

Then pick that registry when deploying the stack.

## 5. Order of startup

`migrate` runs first, applies Alembic migrations, and exits. Portainer shows it
as **exited (0)** — that is success, not a crash. `api` waits for it to finish
before starting, so the schema is never half-applied under a live API.

Only `web` publishes a host port. `api` is reachable solely from inside the
Docker network, through nginx, because the only thing that should face the
internet is something terminating TLS.

## 6. TLS is not optional

Android 9+ refuses cleartext HTTP, so **the collector app cannot upload to a
plain `http://` server**. Put one of these in front of `WEB_PORT`:

- a Cloudflare tunnel to `http://localhost:8090` — no certificate management,
  and the account is already in use for the database
- nginx or Traefik with a Let's Encrypt certificate

Then set the app's server address to that HTTPS hostname.

## 7. Verify

```bash
curl https://YOUR_HOST/api/v1/health/db
```

Expect `{"status":"ok","postgis":"not installed"}` — PostGIS being absent is
expected and documented in [setup.md](setup.md).

```bash
curl https://YOUR_HOST/api/v1/stats
```

Then open `https://YOUR_HOST/` for the map.

## Updating

Push to `main`, wait for the workflow, then Portainer → the stack → **Update
the stack** with **Re-pull image** ticked. For a controlled release, push a tag
(`git tag v0.2.0 && git push --tags`) and set `IMAGE_TAG` to that version, so a
rollback is just changing the variable back.

## Not yet done

- **Image builds are untested locally.** There is no Docker on the development
  machine, so the first real build of these Dockerfiles happens in CI. Expect to
  fix something on the first run; the workflow will say what.
- No automatic redeploy on push. Portainer can poll the repository or accept a
  webhook; deliberately left manual so a deploy to a server collecting real
  field data stays a decision rather than a side effect.
