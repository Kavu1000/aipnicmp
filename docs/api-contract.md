# API contract

Base path `/api/v1`. Interactive documentation at `/docs` when the server runs.

The upload contract is the one part of this system that is genuinely hard to
change: devices in uncovered areas may hold records for days, so a phone running
last month's build must still be able to upload. **Add fields; never rename or
remove them.**

## POST /devices/enroll

Called once on first launch. The device generates an Ed25519 keypair in the
Android Keystore and registers the public key.

```json
{
  "device": {
    "install_id": "a1b2c3d4e5f60718293a4b5c",
    "manufacturer": "samsung",
    "model": "SM-A125F",
    "android_api": 34,
    "app_version": "0.1.0"
  },
  "public_key": "base64 of the raw 32-byte Ed25519 public key",
  "integrity_token": "optional Play Integrity token"
}
```

`install_id` is generated on the device, at least 16 characters, and must not be
derived from any hardware identifier. Re-enrolling with the same id is allowed
but **will not rotate the key** — that returns `409`.

## POST /measurements/batch

The store-and-forward upload.

```json
{
  "batch_id": "unique per upload attempt",
  "device": { "install_id": "a1b2c3d4e5f60718293a4b5c" },
  "uploaded_from_lat": 20.568,
  "uploaded_from_lon": 102.642,
  "records": [ { "…": "see below" } ]
}
```

One record:

```json
{
  "client_record_id": "unique per record, stable across retries",
  "captured_at": "2026-08-08T04:31:07Z",
  "lat": 19.884500,
  "lon": 102.135000,
  "gps_accuracy_m": 8.0,
  "altitude_m": 305.0,
  "speed_mps": 14.2,

  "registered": true,
  "network_type": "LTE",
  "operator": { "mcc": "457", "mnc": "01", "name": "LTC" },

  "signal": { "rsrp_dbm": -95.0, "rsrq_db": -11.0, "sinr_db": 8.0, "level": 3 },

  "serving_cell": {
    "radio": "LTE", "mcc": "457", "mnc": "01",
    "cid": 12345, "lac_tac": 4001, "pci_psc": 271, "arfcn": 1650,
    "is_registered": true
  },
  "neighbor_cells": [ { "radio": "LTE", "pci_psc": 143, "rsrp_dbm": -108.0 } ],

  "active_test": { "download_kbps": 8400.0, "upload_kbps": 2100.0, "latency_ms": 48.0 },

  "signature": "base64 Ed25519 signature — see below"
}
```

Notes that matter:

- `captured_at` **must** be timezone-aware UTC ending in `Z`.
- A no-service reading is `registered: false`, `network_type: null`,
  `serving_cell: null`, `neighbor_cells: []`, `signal.rsrp_dbm: null`. This is a
  valid, valuable record — not an error.
- `active_test` may only be present when `registered` is true. A speed test
  without a data connection is impossible and the record is rejected.
- Omit a field rather than sending a fabricated zero. `rsrp_dbm: 0` would mean a
  physically impossible signal; `null` means "this device did not report it".

### Response

`200` even when some records fail, with a per-record breakdown:

```json
{
  "batch_id": "…",
  "accepted": 197,
  "duplicates": 0,
  "rejected": [
    { "client_record_id": "…", "reason": "bad_signature", "detail": "signature missing or does not verify" }
  ]
}
```

The client should drop accepted and duplicate ids from its queue. Rejected ids
should also be dropped — every rejection reason is permanent, so retrying them
only wastes a scarce upload window.

Rejection reasons: `out_of_area`, `future_timestamp`, `too_old`,
`gps_inaccurate`, `implausible_rsrp`, `inconsistent_state`, `bad_signature`,
`impossible_trajectory`.

Other statuses: `401` device not enrolled, `403` device blocked, `413` batch
over `MAX_BATCH_RECORDS`, `422` malformed payload.

## The signature

Ed25519 over this exact UTF-8 string, fields joined by `|`:

```
v1|<client_record_id>|<captured_at>|<lat>|<lon>|<registered>|<network_type>|<rsrp>|<cells_visible>
```

| Field | Format |
| --- | --- |
| `captured_at` | `2026-08-08T04:31:07Z` — UTC, whole seconds, `Z` suffix |
| `lat`, `lon` | exactly 6 decimal places, never scientific notation |
| `registered` | `1` or `0` |
| `network_type` | uppercase name, or empty string when null |
| `rsrp` | exactly 1 decimal place, or empty string when null |
| `cells_visible` | integer: serving cell (0 or 1) plus neighbour count |

Signed **at the moment of capture**, not at upload. Kotlin must produce
byte-identical input; `backend/tests/test_signing.py` pins the exact layout, and
`backend/scripts/simulate_journey.py` contains a standalone reference
implementation.

## GET /tiles

Public coverage map for a viewport. Returns GeoJSON.

```
GET /tiles?min_lat=19.8&min_lon=102.0&max_lat=20.7&max_lon=102.8&include_predicted=true
```

Each feature is one H3 hexagon. `colour` is one of `green`, `yellow`, `orange`,
`red_orange`, `red`. Tiles resting on fewer than `TILE_MIN_DEVICES` contributors
carry `low_confidence: true` and omit counts and timestamps. Tiles with no data
at all are absent from the response — the client renders "not measured" itself.

The viewport may not span more than 6 degrees per side.

`operator` takes a canonical network name, not the string a handset reported.
Networks are identified by MCC/MNC (`457-01` is `Lao Telecom`, whether the
device called it `LTC` or `LAO TELECOM`); `GET /dashboard/operator-names` lists
exactly the values this parameter accepts.

`area` replaces the bounding box entirely — an area bounds its own query:

```
GET /tiles?area=LA0601&operator=LTC
```

The response then carries an `area` block naming what was filtered to. An area
holding more than 20,000 tiles is refused with 400 rather than truncated: a
partial map that looks complete is worse than a stated refusal. Use
`/areas/{code}/children` for those.

## Authentication

The map, areas, dashboard, reports and sites endpoints require an approved
account: 401 without a session, 403 with a reason when the account exists but
is not yet approved. The session is an httpOnly cookie, so send requests with
credentials.

`/devices/enroll`, `/measurements/batch` and `/health` are never gated — a
collector phone and a load balancer have no account to sign in with.
`/admin/rebuild-tiles` keeps its separate `X-Admin-Token`.

```
GET  /auth/session          # who is signed in, plus the Google client id
POST /auth/google           # {"credential": "<Google id token>"} -> session cookie
POST /auth/logout
```

`GET /auth/session` is always 200: nobody being signed in is the application's
normal first state, not an error.

Super admins only:

```
GET  /users
POST /users/{id}/decision   # {"status": "approved" | "rejected" | "pending"}
POST /users/{id}/role       # {"role": "super_admin" | "admin"}
```

Both refuse a decision about your own account, and refuse to remove the last
approved super admin.

## GET /areas

The administrative hierarchy — country, province, district, village — without
geometry, one level at a time. This is what the map's cascading filter reads.

```
GET /areas                  # the root: the country
GET /areas?parent=LA06      # its districts
GET /areas?q=nambak         # name search
```

## GET /areas/{code}

One area's border and what has been measured inside it. Accepts `operator`.

`has_boundary: false` means the area is a point with a stated `radius_m`, not a
polygon — the normal case for Lao villages, whose boundaries are unpublished.
Clients must render that as a circle labelled as an approximation, never as a
border. `coverage: null` means nothing has been measured there; it does not
mean coverage is zero.

Area coverage follows the same privacy rule as a single hexagon: `colour`,
`state` and the percentages are always published, while `measurements`,
`avg_rsrp_dbm`, `avg_download_kbps` and `last_measured_at` are withheld — set to
null, with `low_confidence: true` — when fewer than `TILE_MIN_DEVICES` distinct
devices contributed. `state` is the area's median hexagon and always matches
`colour`.

## GET /areas/{code}/children

Every child area with its geometry *and* its coverage, as one FeatureCollection
— the choropleth a national or provincial view is drawn from. A child published
as a point comes back as a `Point` feature. Accepts `operator`.

## POST /reports

Citizen problem report (proposal 2.6). `category` is one of `no_service`,
`slow`, `unstable`, `cannot_call`, `other`.

## GET /sites

The ranked tower-site list. Empty until the Layer 4 site-ranking model runs.

## GET /stats, /health, /health/db

Headline numbers, liveness, and a database check that also reports the installed
PostGIS version.

## POST /admin/rebuild-tiles

Recomputes every H3 tile from the measurements. Requires the `X-Admin-Token`
header. Closed entirely when `ADMIN_TOKEN` is unset.
