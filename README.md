# AI-PNICMP

**AI-Powered National Internet Coverage Mapping Platform — Lao PDR**

A crowdsourced map of where the internet actually works, built from real signal
measurements taken on ordinary Android phones instead of operator coverage
claims. Full specification: [docs/proposal.md](docs/proposal.md).

The idea the system turns on: **measuring the signal and using the internet are
two different things.** A phone's modem keeps scanning for base stations whether
or not any data flows, and GPS needs no network at all. So the app can record a
reading in a place with no service, hold it, and upload when the user returns to
coverage. Places with *no signal at all* become the most valuable data in the
system rather than blank gaps on the map.

## Repository layout

| Path | Contents | Status |
| --- | --- | --- |
| `backend/` | FastAPI ingestion + map API, PostGIS schema, H3 aggregation (Layers 2, 3, 5) | working, 64 tests passing |
| `android/` | Kotlin collector app (Layer 1) | not started; constraints documented |
| `ml/` | Coverage prediction, satellite CV, site ranking (Layer 4) | not started |
| `web/` | MapLibre public coverage map (Layer 5) | working; operator dashboard not started |
| `docs/` | Proposal, architecture figures, API contract, decisions | written |

## Quick start (backend)

```bash
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt
```

Copy `backend/.env.example` to `backend/.env` and fill in the database URL, then:

```bash
cd backend && .venv/Scripts/python -m alembic upgrade head
```

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload
```

Interactive API docs are then at http://127.0.0.1:8000/docs.

### Seeing it work without a phone

`scripts/simulate_journey.py` plays a collector device driving Route 13 North,
signing every record with a real Ed25519 key and speaking the real wire
protocol. It produces all five radio states, including a genuine dead stretch.

```bash
cd backend && .venv/Scripts/python scripts/simulate_journey.py --points 300 --seed 7
```

Then aggregate into map tiles and fetch the GeoJSON:

```bash
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://127.0.0.1:8000/api/v1/admin/rebuild-tiles
```

Simulated devices all carry an `install_id` beginning `sim-`, so they can be
deleted wholesale before real collection starts.

### Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

The suite runs against in-memory SQLite and needs no database. Two things it
cannot cover — the PostGIS generated geometry column and the migration itself —
are verified by running the migration against the real database.

## The five radio states

The classification is the project's policy argument in code. A binary
"signal / no signal" map cannot tell a ministry where to spend money; this can.

| State | Meaning | Colour | Implied remedy |
| --- | --- | --- | --- |
| `NO_CELL` | Nothing on the air at all | red | **New tower** — capital spend |
| `CELLS_VISIBLE_UNREGISTERED` | Tower visible, too weak to attach | red-orange | Upgrade or repeater |
| `REGISTERED_2G_3G` | Calls and SMS work, data does not | orange | Data capacity upgrade |
| `LTE_WEAK` | Data works but slow (RSRP < −110 dBm) | yellow | Optimisation |
| `LTE_GOOD` | Normal service | green | None |

The server derives the state from raw fields rather than trusting the device, so
thresholds can be retuned and the whole history reclassified without shipping an
app update.

## Design decisions worth knowing

See [docs/decisions.md](docs/decisions.md). The ones that shape everything else:

- **Records are signed at capture, not at upload.** A record may sit on a phone
  for days; a signature made at upload would prove only that nobody edited the
  file after they decided to send it.
- **A bad record never costs a device its whole batch.** A phone in a remote
  area may not get another upload window for days.
- **Flag, don't drop, weak evidence.** Discarding coarse-GPS or long-delayed
  records would bias the map towards places that already have coverage.
- **Predictions never outrank measurements.** One real reading immediately
  replaces the model's guess for that hexagon.
