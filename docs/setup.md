# Setup — what the backend needs from the server and database

Everything here is what you provide; the code is already written against it.

## 1. PostgreSQL

**Required version:** PostgreSQL 14 or newer (the schema uses a
`GENERATED ALWAYS AS ... STORED` column, added in 12, and is otherwise plain).

**Required extension: PostGIS.** It must be *installed on the server*, and
created once in this database by a superuser:

```sql
CREATE DATABASE aipnicmp;
CREATE USER aipnicmp WITH PASSWORD 'a-strong-password';
GRANT ALL PRIVILEGES ON DATABASE aipnicmp TO aipnicmp;
\c aipnicmp
CREATE EXTENSION IF NOT EXISTS postgis;
GRANT ALL ON SCHEMA public TO aipnicmp;
```

The migration also tries `CREATE EXTENSION IF NOT EXISTS postgis`, which
succeeds silently if a superuser already ran it and fails clearly if PostGIS is
not installed on the server at all.

> **Note on the portable Postgres in `Documents/Crew/pgsql`:** it has no PostGIS
> extension. If that is the instance you intend to use, PostGIS has to be added
> to it (the PostGIS Windows bundle), or point the project at a different
> server.

**Send me:** host, port, database name, username, password. I only need them in
`backend/.env`, which is gitignored.

**TimescaleDB** is in the proposal for outage detection (Layer 4). It is not
needed yet — nothing in the current code depends on it. Worth deciding before
the anomaly-detection work starts.

## 2. Redis (optional for now)

Only needed when the Celery worker runs the hourly tile rebuild. Until then the
rebuild can be triggered by the admin endpoint. If you have Redis, send me the
URL; if not, nothing breaks.

## 3. Server

For the pilot the API needs very little: 2 vCPU / 4 GB is comfortable. What
matters more:

- **A public HTTPS endpoint.** Android 9+ blocks cleartext HTTP by default, and
  the whole upload path assumes TLS. A domain name with a Let's Encrypt
  certificate, or a reverse proxy that terminates TLS, is required before the
  app can talk to it from a real phone.
- **Outbound internet** if we later fetch SRTM/Sentinel-2 data on the server.
- **Disk**: measurements are small (~1 KB each with cell observations). A
  province-scale pilot is well under a gigabyte.

**Send me:** the hostname or IP, how you want me to deploy (systemd + nginx,
Docker, or you deploy from a build I hand over), and whether I have SSH access
or should produce a deployment package.

## 4. Decisions I need from you (not blocking today's work)

1. **Which province for the pilot?** It sets the map's default viewport, the
   terrain tiles we download, and which routes matter. The simulator currently
   uses Route 13 North, Luang Prabang → Nong Khiaw, as a placeholder.
2. **Which operators** to name in the data (LTC, Unitel, ETL, Beeline)? Their
   MCC/MNC pairs should be seeded so the dashboard can filter by network.
3. **Play Store or sideload for phase 1?** Sideloading to partner collectors
   (bus drivers, health workers) avoids the background-location policy review
   entirely and is much faster for a pilot. Play Store distribution needs a
   Console account and a declared justification for background location.

## 5. What I do not need and will not ask for

No API keys, no personal data, no production credentials for anything outside
this project. The system deliberately stores no phone numbers, IMEIs or
accounts — the only device identifier is a random id generated on first launch
and discarded on uninstall.
