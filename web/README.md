# Public coverage map — Layer 5

React + MapLibre GL. Renders the H3 coverage tiles served by the backend.

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so the backend needs no
CORS exception. Override with `VITE_API_TARGET` if the API runs elsewhere.

To see anything, the backend must have data:

```bash
cd ../backend && .venv/Scripts/python scripts/simulate_journey.py --points 400 --seed 11
```

…then rebuild the tiles (`POST /api/v1/admin/rebuild-tiles`).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_TARGET` | `http://127.0.0.1:8000` | Dev-server proxy target |
| `VITE_API_BASE` | `/api/v1` | API base path used by the client |
| `VITE_MAP_STYLE` | OpenFreeMap positron | Basemap style URL |

The basemap default is [OpenFreeMap](https://openfreemap.org), which needs no API
key or account — one less credential to manage for a pilot. Swap in MapTiler or a
self-hosted style later by setting `VITE_MAP_STYLE`; nothing else changes.

## Things that are deliberate

**The data does not wait for the basemap.** Coverage is fetched the moment the
map is constructed, and if the style CDN cannot be reached within 8 seconds the
map falls back to a plain background and keeps drawing hexagons. A coverage map
for rural Laos that goes blank when a CDN is unreachable would be a poor joke.

**Three visual tiers of confidence.** Measured tiles are solid with a white
edge; tiles resting on too few devices are faded; predicted tiles are faded
*and* dashed. A prediction must never carry the visual authority of a
measurement.

**Unmeasured areas are simply absent.** The server returns nothing for them and
the map draws nothing. "Not measured" is the absence of a claim, not a grey
claim.

**The legend names the remedy, not just the colour.** Red means a new tower and
capital spend; red-orange means an upgrade or a repeater. That distinction is
the project's whole argument, so it belongs in the legend rather than in a
footnote.

**The viewport is clamped to the API's 6-degree limit.** Zoomed out to the whole
country, the client requests the centre of the view rather than letting the
request fail.

## Not built yet

- Operator/ministry dashboard (the ranked tower-site list; `GET /sites` is
  wired in `api.ts` but has no UI)
- Problem-reporting form (`POST /reports`)
- Lao translation — the layout already uses a Lao-capable font stack
