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

## 1. The repository

**https://github.com/tsabxyooj2018/aipnicmp** — private.

Private is the right default here. The code contains no credentials — that was
checked before the first push — but `docs/setup.md` and `scripts/init_db.py`
name the database host and the `aiadmin` username, which is free reconnaissance
for anyone who finds the repo. Make it public later, once those are
parameterised, if the project wants to publish its methodology.

## 2. CI builds the images

The workflow runs on every push to `main`. Watch it with:

```bash
gh run watch
```

Confirmed working. Each successful run publishes:

```
ghcr.io/tsabxyooj2018/aipnicmp-backend:latest   (also :main and :sha-<short>)
ghcr.io/tsabxyooj2018/aipnicmp-web:latest       (also :main and :sha-<short>)
```

and attaches the debug APK as the `coverage-collector-debug` artifact (~6.3 MB),
so a collector build is downloadable without any local Android toolchain.

Prefer a `:sha-` or `:v` tag over `:latest` on the server — it makes a rollback
a one-line change rather than a guess about which image is running.

**Because the repository is private, so are the packages.** Portainer needs a
pull secret; see step 4.

## 3. Create the stack in Portainer

Portainer → **Stacks** → **Add stack** → **Repository**, pointing at the GitHub
repo with compose path `docker-compose.yml`. Or choose **Web editor** and paste
the contents of that file.

Then fill in **Environment variables**. Portainer offers two modes:

- **Simple mode** — a `name` box and a `value` box per row, and an "add
  environment variable" button for the next one.
- **Advanced mode** — one textarea taking `KEY=value` lines. Far quicker for a
  stack this size; paste [portainer.env.example](portainer.env.example) and
  edit.

Four things Portainer will not warn you about:

- **No quotes.** The value is stored literally, so `"secret"` arrives as eight
  characters including the quote marks — and the password looks right in the UI
  while authentication fails.
- **No spaces around `=`.**
- **No trailing spaces.** Invisible, and part of the value.
- **A literal `$` must be doubled to `$$`**, since compose reads a single `$`
  as the start of a variable reference.



| Variable | Value | Notes |
| --- | --- | --- |
| `BACKEND_IMAGE` | *(optional)* | defaults to `ghcr.io/tsabxyooj2018/aipnicmp-backend:latest` |
| `WEB_IMAGE` | *(optional)* | defaults to `ghcr.io/tsabxyooj2018/aipnicmp-web:latest` |
| `DATABASE_URL` | `postgresql+asyncpg://aiadmin:PASSWORD@192.168.15.21:5432/aipnicmp` | `@` in the password **must** be `%40` |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://aiadmin:PASSWORD@192.168.15.21:5432/aipnicmp` | same database, sync driver, for Alembic |
| `CORS_ORIGINS` | `https://map.yourdomain.la` | comma-separated; no trailing slash |
| `JWT_SECRET` | 48 random bytes | `python -c "import secrets; print(secrets.token_urlsafe(48))"` — **also signs the sign-in sessions**, so anyone who learns it can mint a session for any account |
| `ADMIN_TOKEN` | another random string | empty keeps the admin endpoints closed |
| `GOOGLE_CLIENT_ID` | `…apps.googleusercontent.com` | OAuth **Web application** client id; public by design. No client secret is used |
| `SUPER_ADMIN_EMAILS` | `chaxiong@fe-nuol.edu.la` | comma-separated. Without at least one, **nobody can ever be approved** |
| `AUTH_ENABLED` | `true` | leave true; `false` serves the platform to anyone |
| `WEB_PORT` | `8090` | host port for nginx |

### Sign in with Google

Create the client in Google Cloud Console → **APIs & Services → Credentials →
Create credentials → OAuth client ID → Web application**, and add the site to
**Authorised JavaScript origins**:

```
https://aipn.chax.site
```

Add `http://localhost:5173` as well **only if somebody develops locally** — it
is the Vite dev server's address and has no part in the deployed site. Listing
it means any program on port 5173, on any machine, can ask Google for a token
issued to this client; the sign-in still needs the person's consent and a super
admin's approval, so the risk is small, but an unused origin is a door with no
purpose behind it. It can be added in one click later.

Origins are exact — scheme, host and port, no path and no trailing slash. A
missing origin is the usual cause of a sign-in button that renders and then
does nothing.

The addresses in `SUPER_ADMIN_EMAILS` become approved super admins on first
sign-in, and are restored to that on every sign-in. That is deliberate: it is
what makes losing access to every super admin account recoverable by editing
configuration instead of the database.

### The database host: 192.168.15.21

The stack does **not** include PostgreSQL. The database already exists and holds
real collected data; a compose file able to recreate it is a compose file able
to destroy it.

**From the production server, the database is reached directly at
`192.168.15.21:5432`** — it is on the same internal network. The Cloudflare
tunnel is *not* involved and must not appear in these URLs.

That tunnel exists only for development: a laptop outside that network cannot
reach `192.168.15.21`, so `cloudflared access tcp` forwards it to
`127.0.0.1:55432` locally. Two different paths to one database:

| Where | Host in the URL |
| --- | --- |
| Production containers | `192.168.15.21:5432` |
| Development laptop | `127.0.0.1:55432` (via `cloudflared access tcp`) |

Never `localhost` in a container — inside one, that means the container itself.

## 4. If the images are private

Portainer → **Registries** → **Add registry** → **Custom**:

- URL: `ghcr.io`
- Username: `tsabxyooj2018`
- Password: a personal access token with the **`read:packages`** scope

Create the token at GitHub → Settings → Developer settings → Personal access
tokens. `read:packages` alone is enough — it cannot push images or touch the
repository, so a leak from the server is limited to pulling what it could
already run.

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
the stack** with **Re-pull image** ticked. For a controlled release, pin the
full reference and change it deliberately:

```
BACKEND_IMAGE=ghcr.io/tsabxyooj2018/aipnicmp-backend:sha-497b81d
WEB_IMAGE=ghcr.io/tsabxyooj2018/aipnicmp-web:sha-497b81d
```

Rolling back is then editing those two lines back to the previous sha.

## If the stack fails to deploy

**`invalid reference format`** means Docker could not parse an image name.
Almost always an environment variable that resolved to empty, leaving a double
slash or a bare `:tag`. The image names now carry complete defaults, so the
stack deploys with no variables set at all — if you still see this, something
is overriding `BACKEND_IMAGE` or `WEB_IMAGE` with a malformed value.

**`manifest unknown` / `denied`** means the pull failed, not the parse. The
packages are private, so add the `ghcr.io` registry credential in step 4.

## Not yet done

- **The images have never been run.** CI builds them successfully, but nothing
  has yet started a container from one. The first `docker compose up` in
  Portainer is their first execution — most likely place for a problem is the
  entrypoint or a missing environment variable, and both report clearly in the
  container logs.
- No automatic redeploy on push. Portainer can poll the repository or accept a
  webhook; deliberately left manual so a deploy to a server collecting real
  field data stays a decision rather than a side effect.
