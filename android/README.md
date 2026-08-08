# Android collector — Layer 1

The app that turns this project from an architecture into evidence. It measures
mobile signal wherever the phone travels, holds readings taken where there is no
network, and uploads them when coverage returns.

**Status:** compiles and its unit tests pass. Debug APK 7.4 MB, release
(R8-minified) 2.5 MB. It has not yet run on a physical handset — everything
below the compiler is still unproven.

## Building

No Android Studio required. A portable JDK and SDK live under
`~/android-toolchain`; see [TOOLCHAIN.md](TOOLCHAIN.md) to recreate them.

```bash
cd android && ./build.sh
```

That runs the tests and produces `app/build/outputs/apk/debug/app-debug.apk`.
Android Studio also works — open `android/` and let it sync.

### The tests matter more than they look

```bash
cd android && ./build.sh test
```

Six plain JVM tests, no device needed, checking the single most dangerous piece
of the system: that the canonical string this app signs matches the one the
server verifies, byte for byte. The expected values are pinned against
`backend/tests/test_signing.py`, and both sides were confirmed to produce
identical output for the same five inputs — including the locale and rounding
traps.

If those fail, **stop**. Every record the app produced would be rejected as
`bad_signature`, with no other symptom, because the records themselves look
perfectly well-formed.

## Pointing it at a server

`app/build.gradle.kts` sets `API_BASE_URL` per build type:

| Build | Default | Use |
| --- | --- | --- |
| debug | `http://10.0.2.2:8000` | Emulator talking to a backend on this machine |
| release | `https://api.chax.site` | The pilot server — **change this to the real hostname** |

The address can also be overridden at runtime via `CollectorPrefs.apiBaseUrl`,
so a pilot that moves hosts does not need a rebuild.

**A real phone needs HTTPS.** Android 9+ blocks cleartext HTTP by default, so a
debug build on a physical handset cannot reach a plain `http://` backend. Put
the API behind TLS — a Cloudflare tunnel to the API host is the least-effort
route, and the account is already in use for the database.

## What it does

1. **Enrol once.** Generates an ECDSA P-256 keypair in the Android Keystore and
   registers the public key. Enrolment happens *before* the first recording,
   never during: a record signed by a key the server has not seen is rejected
   permanently, and it cannot be re-signed later.
2. **Sample** on the rule from proposal 2.3 — one record per 100 m or per 60
   seconds, whichever comes first.
3. **Sign at capture**, then write to a local SQLite queue.
4. **Upload** in batches of 250 via WorkManager, constrained to
   `NetworkType.CONNECTED`.
5. **Drop** every id the server has ruled on — accepted, duplicate *or*
   rejected. Rejection reasons are all permanent, so retrying them would block
   the queue behind rows that can never succeed.

## Decisions worth knowing

### The key is P-256, not Ed25519

The server was Ed25519-only until this app was written. **The Android Keystore
cannot hold an Ed25519 signing key**, so the only way to keep Ed25519 would have
been a software key — which a rooted phone can copy out, making the capture-time
signature worthless exactly where forgery matters. A hardware-backed P-256 key
whose private half never leaves the secure element is the stronger guarantee, so
the server learned P-256 instead. It still speaks both.

### Collection runs in a foreground service

From Android 10, `getAllCellInfo()` is throttled for background apps and returns
**cached** results. A plain background service would report stale readings that
look perfectly valid — the worst kind of failure for this project. A foreground
service with a visible notification is the only way to sample honestly from a
pocket.

### The queue drops the newest records when full, not the oldest

Counter-intuitive and deliberate. The oldest queued records are the ones nearest
the server's 30-day cutoff, so discarding them wastes the evidence that has
waited longest — and a phone this far behind is deep in a dead zone, which is
the case worth protecting. Cap is 20,000 records, roughly 20 MB.

### Views and plain SQLite, not Compose and Room

Both of those bring compiler plugins or annotation processors. Since this code
ships without ever having been compiled, every removable build dependency is one
less thing that can fail on a machine I cannot see. The UI is a status screen and
one button; it does not need more.

## Platform constraints that shaped this

- **Background location** (`ACCESS_BACKGROUND_LOCATION`) is requested
  separately, after fine location, from an explanation dialog. Android 11+ will
  not show the prompt otherwise, and refusing it means recording stops whenever
  the screen turns off.
- **Play Store distribution** of an app requesting background location requires
  a written justification and a video, reviewed by Google, taking weeks.
  **Sideloading to partner collectors avoids this entirely** and is the
  recommended route for the pilot.
- **Signal fields vary by OEM.** `getRsrp()` needs API 26+ (hence `minSdk 26`);
  RSRQ and SINR are inconsistent and some devices return `Integer.MAX_VALUE` for
  "unknown". Those become `null` on the wire, never a zero — the server would
  read `rsrp: 0` as a physically impossible signal.
- **GPS works with no network.** A-GPS only speeds up the first fix, which is
  why location updates are kept warm rather than started cold at each sample.

## The first real drive

1. Build, install on a phone with a Lao SIM, grant location **all the time**.
2. Press **Start recording** and drive a road that leaves coverage.
3. Watch "Waiting to send" climb while offline — those are the records nothing
   else can produce.
4. Return to coverage. The queue should drain on its own; **Try uploading now**
   forces it.
5. Confirm on the server:

```bash
curl https://YOUR_API/api/v1/stats
```

Then rebuild the tiles and look at the map. The moment real readings replace the
simulated ones, the project stops being a demonstration.

## Not built yet

- Active speed tests (download/upload/latency). The wire format and the server
  already accept them; the app never populates `active_test`. Passive sampling
  was the priority because it works everywhere, including where nothing else
  does.
- The problem-reporting form (`POST /reports`).
- Lao translation. Strings are all in `res/values/strings.xml`; a `values-lo/`
  copy is all that is needed.
