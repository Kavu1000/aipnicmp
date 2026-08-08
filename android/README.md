# Android collector — Layer 1

Not built yet. This file records what the app must do and the platform
constraints that will shape it, so the design work is not redone later.

## What it does

1. Enrol once: generate an Ed25519 keypair in the Android Keystore, register the
   public key at `POST /devices/enroll`.
2. Sample the radio and GPS on a rule of **one record per 100 m or per 60 s**,
   whichever comes first.
3. Sign each record at the moment of capture and write it to SQLite.
4. Upload queued records via `WorkManager` with a `NetworkType.CONNECTED`
   constraint, in batches, when coverage returns.
5. Drop accepted, duplicate and rejected ids from the queue on a `200`.

Full wire format: [../docs/api-contract.md](../docs/api-contract.md).

## Platform constraints that change the design

These are not incidental. Each one has bitten similar projects.

### Background sampling is throttled

`TelephonyManager.getAllCellInfo()` is rate-limited from Android 10 (API 29): an
app in the background receives **cached** results, not a fresh scan. A plain
background service therefore cannot honour the 100 m / 60 s sampling rule.

What this forces:

- a **foreground service** with `foregroundServiceType="location"`, and a
  persistent notification the user can see
- `ACCESS_FINE_LOCATION` **and** `ACCESS_BACKGROUND_LOCATION`, requested
  separately and in the right order (fine first, background afterwards, from a
  rationale screen — Android 11+ will not show the background prompt otherwise)
- `requestCellInfoUpdate()` for an explicit fresh reading where available
  (API 29+), rather than relying on `getAllCellInfo()` alone

### Play Store distribution needs a background-location declaration

Publishing an app that requests `ACCESS_BACKGROUND_LOCATION` requires a written
justification and a video demonstration, reviewed by Google, and the review can
take weeks. **For a pilot with partner collectors — bus drivers, health workers,
provincial staff, teachers — sideloading avoids this entirely.** Decide which
route before building the release pipeline; it changes the timeline more than
any code decision here.

### Signal fields vary by manufacturer

`CellSignalStrengthLte.getRsrp()` needs API 26+; RSRQ and SINR are inconsistent
across OEMs and some devices return `Integer.MAX_VALUE` for "unknown". Send
`null` for anything the device did not genuinely report — never a zero, which
the server would read as a physically impossible signal. The backend already
falls back from RSRP to SINR to a pessimistic default.

### GPS works with no network; A-GPS only makes the first fix faster

This is the assumption the whole project rests on, and it holds. But the *first*
fix in a dead zone can take a minute or more without assistance data, so the app
should keep location updates warm rather than starting cold at each sample.

### Battery

Passive radio reads are cheap; the GPS fix is not. Use
`FusedLocationProviderClient` with a balanced-power interval, and only run an
active speed test when the device is registered on LTE/NR, on unmetered
connections or under an explicit user setting — the proposal's two-tier design
already assumes active tests are rare.

## Signing, precisely

The canonical string is defined in
[../docs/api-contract.md](../docs/api-contract.md#the-signature) and pinned by
`backend/tests/test_signing.py`. Kotlin must produce byte-identical UTF-8. The
two traps:

- Format floats with `Locale.ROOT` — a Lao or French locale renders `19,884500`
  and every signature silently fails to verify.
- Never let a float reach scientific notation. Use
  `String.format(Locale.ROOT, "%.6f", value)`.

A working reference implementation of the canonical form is in
`backend/scripts/simulate_journey.py`.
