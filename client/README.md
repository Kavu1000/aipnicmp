# Public client — the coverage map, with its own sign-in

A separate app from `../web` (the admin dashboard) on purpose: this is what
a visitor sees — the landing page, the live map, the methodology note, and
an optional Google sign-in — served from its own build, its own container,
and its own subdomain (`map.chax.site` in production; see `docs/deploy.md`).

It shares nothing with `../web` at runtime except the backend API. At build
time it shares nothing at all — `src/MapView.tsx`, `Legend.tsx`,
`coverage.ts`, `geo.ts`, `i18n.ts`, `Login.tsx` and friends are copies of
`../web`'s files, not imports of them, so this app can be built, deployed
and broken independently of the dashboard. If the map's rendering or the
sign-in flow changes in one, change it in the other in the same commit.

## Pages

| Path | What it shows | Needs a session? |
| --- | --- | --- |
| `/` | Landing page — hero, live stats, a live map preview, how it works | No |
| `/map` | The full public map | No |
| `/method` | How a reading becomes a colour on the map | No |
| `/signin`, `/pending` | Google sign-in | No — this *is* how you get one |

**Signing in changes nothing you can see.** Every page here, before or after
sign-in, calls only `/api/v1/public/*` and `/api/v1/auth/*` — never a
per-network breakdown, a mast position, a device count, or anything else
that resolves to one person's movement. See `backend/app/api/v1/public.py`
for exactly what that boundary is, and `src/App.tsx`'s note for why nothing
here is gated on it. The full, role-gated view — operators, government,
collector fleet ops — lives only in `../web`, behind its own approval flow.

So what does signing in *do*? Right now: nothing but put a name in the
header instead of a "Sign in" button. It exists because the platform's
account system is shared with `../web` (same backend, same `users` table),
and having it here is what a future member-only feature would build on —
not because anything today needs it.

## Run it

```bash
npm install
npm run dev        # http://localhost:5175
```

Needs the backend running (`../backend`, see its README) — the dev server
proxies `/api` to it, same pattern as `../web`. Override with
`VITE_API_TARGET` if the API runs somewhere other than `127.0.0.1:8000`.

Google sign-in needs `GOOGLE_CLIENT_ID` set on the *backend* (`../backend/.env`)
with `http://localhost:5175` (and `:5173` for `../web`) listed under that
OAuth client's **Authorized JavaScript origins** in Google Cloud Console.
Without it, `/signin` renders and explains that Google sign-in is not
configured — not a broken button, an honest one.

## Deploying alongside `../web`

Wired into `docker-compose.yml` as the `client` service — its own image
(`aipnicmp-client`), its own host port (`CLIENT_PORT`, default `8091`), same
`api` upstream. Two subdomains, not one path-based nginx: `aipn.chax.site`
stays `../web`, `map.chax.site` is this app. See `docs/deploy.md` for the
Portainer variables and the Google Cloud Console origin to add.
