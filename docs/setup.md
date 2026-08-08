# Setup — database and server

## Current state (2026-08-08)

The database is **live and working**.

| | |
| --- | --- |
| Server | `db2.chax.site`, PostgreSQL **16.14** (Debian, stock `postgres:16` image) |
| Reached via | Cloudflare Tunnel — port 5432 is not exposed to the internet |
| Database | `aipnicmp` (created 2026-08-08; other databases on the server untouched) |
| Role | `aiadmin` — superuser |
| Schema | migrations `0001` and `0002` applied |
| Seeded | 750 simulated measurements, 124 H3 tiles |
| PostGIS | **not installed** — see below |

### Connecting

The tunnel must be running before anything can reach the database:

```bash
~/.cloudflared/cloudflared.exe access tcp --hostname db2.chax.site --url 127.0.0.1:55432
```

`backend/.env` points at `127.0.0.1:55432`. Leave the tunnel running in its own
terminal while working; nothing else is needed.

Note the password's `@` is percent-encoded as `%40` in the URLs. Unencoded, the
driver reads it as the start of the hostname and fails confusingly.

## PostGIS is optional, and currently absent

`db2.chax.site` runs the stock `postgres:16` image, which ships no PostGIS.
Rather than block on it, the schema was split:

- **Migration 0001** creates every table and index, and needs only stock
  PostgreSQL.
- **Migration 0002** adds `measurements.geom` — a generated
  `geography(Point, 4326)` column with a GiST index — **only if PostGIS is
  available**, and logs a warning otherwise.

Nothing in the platform needs PostGIS today. Coverage is aggregated by H3
hexagon id and the map queries a plain lat/lon range, so the pilot runs fully on
what is installed now.

**Where PostGIS will earn its place: Layer 4 site ranking.** Asking "which
unserved settlements fall within this tower's radius" wants real geodesic
distance and a spatial index, not an approximation in Python. Worth having
before that work starts; not worth blocking anything for now.

### Adding it later

Switch the image to `postgis/postgis:16-3.4` — a drop-in superset of
`postgres:16`, same major version, so the existing data directory is unaffected.
On a plain Debian host, `apt install postgresql-16-postgis-3` instead.

**Careful:** that server also hosts `ceit-ai-db`, `ceit-meet-db`,
`cha-website-db`, `ceit_ams`, `amai` and `IMIS`. An image change restarts the
whole instance, so it needs a maintenance window rather than a casual `docker
compose up -d`.

Then, once:

```bash
cd backend && .venv/Scripts/python scripts/enable_postgis.py
```

Idempotent, and safe to run repeatedly. Migration 0002 will already be stamped
on this database, which is exactly why the standalone script exists.

## Still needed from you

**A public HTTPS endpoint for the API.** Android 9+ blocks cleartext HTTP, so
the collector app cannot talk to the backend until it has a real certificate.
The same Cloudflare account already in use would serve this well — a tunnel to
the API host gives HTTPS with no certificate management at all.

**Redis**, when the Celery worker should take over the hourly tile rebuild.
Optional; the admin endpoint covers it for now.

## Decisions that unblock other tracks

1. **Which province for the pilot?** Sets the map's default viewport, the
   terrain tiles to download, and which routes matter. The simulator currently
   uses Route 13 North, Luang Prabang → Nong Khiaw, as a placeholder.
2. **Which operators** to seed (LTC, Unitel, ETL, Beeline) with their MCC/MNC
   pairs, so the dashboard can filter by network.
3. **Play Store or sideload for phase 1?** Sideloading to partner collectors
   avoids Google's background-location review entirely — weeks of delay, and the
   single largest schedule risk in the Android track.

## What is deliberately not collected

No phone numbers, IMEIs or accounts. The only device identifier is a random id
generated on first launch and discarded on uninstall.
