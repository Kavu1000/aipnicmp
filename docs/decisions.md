# Design decisions

Choices that are not obvious from the code, with the reasoning that produced
them. Where a decision departs from the proposal, that is stated explicitly.

## 1. The server derives the radio state; the device's opinion is only recorded

The app sends what it observed — registration, network type, RSRP, visible cell
count — and the server decides which of the five states that means. The device's
own conclusion is stored in `radio_state_client` but never used.

Thresholds will be retuned as real Lao data arrives. If the state were decided
on the phone, retuning would mean shipping an app update and waiting months for
adoption, and old records would keep the old rule forever. Deriving it centrally
means the entire history can be reclassified in one job.

## 2. Signatures are made at capture time, over a fixed canonical string

Proposal 3.5 requires this, and the reason is worth restating: a record from an
uncovered area may sit on a phone for a fortnight. A signature applied at upload
would prove only that the file was intact by the time someone chose to send it —
which is exactly the window in which a forger would work.

The canonical string is pinned in `app/services/signing.py` and in a test that
asserts the exact field layout, because the Kotlin client must produce
byte-identical input. Adding a field means a `v2` canonical form; `v1` keeps
verifying for devices that have not updated.

## 3. Partial batches succeed

A batch containing bad records still stores its good ones, and the response says
per record what happened. Rejecting the whole upload would mean a device in a
remote area retries the same failing batch forever and its genuine readings are
never seen. This is a deliberate departure from the usual all-or-nothing
transaction: the data is irreplaceable and the upload window may not come again.

## 4. Two severities: reject versus flag

Rejection is reserved for records that are not evidence of anything — bad
signature, impossible coordinates, a physically impossible journey. Everything
else is stored with a flag: coarse GPS, a fortnight-long store-and-forward
delay, a missing accuracy figure.

The bias this avoids is specific. Weak-evidence records come
disproportionately from remote areas — worse GPS under canopy, longer offline
delays, older phones. Dropping them would quietly make the map cleanest exactly
where coverage is already good.

## 5. Only the later record of an impossible pair is rejected

A forger splicing a fake point into a genuine journey breaks the chain at the
insertion. Rejecting the earlier record would throw away real data and reward
the attack.

## 6. Trajectory checks ignore movements under 250 m

Below that, GPS noise dominates and a stationary phone appears to teleport. The
check would otherwise reject a bus stopped at a village — the exact situation
where the readings matter most.

## 7. Low-contributor tiles publish their colour but withhold their detail

Proposal 2.6 promises anonymised, aggregated data. The obvious implementation —
hide any tile with fewer than *k* contributing devices — would blank out
precisely the remote hexagons the project exists to reveal, since those are the
ones only one traveller ever crosses.

Instead, such tiles keep their colour and lose everything that could tie the
reading to one journey: device counts, measurement counts, timestamps. The
client sees `low_confidence: true`. The threshold is `TILE_MIN_DEVICES`.

**Residual risk, stated plainly:** a colour on a rarely travelled hexagon still
reveals that *someone* passed through it. For a coverage map this is judged
acceptable; if the project later carries anything more sensitive, revisit this.

## 8. Grey is rendered by the client, never stored

A hexagon with no measurement and no prediction is simply absent from the API
response. The server does not invent "unknown" rows. "Not yet measured" is the
absence of a claim, not a claim.

## 9. PostGIS is an upgrade, not a prerequisite

The proposal names PostGIS, and the target server turned out to run the stock
`postgres:16` image without it. Rather than block the pilot, the schema was
split: migration 0001 creates everything on plain PostgreSQL, and migration 0002
adds the geometry column only where PostGIS exists, warning otherwise.

This is possible because nothing in the platform needs PostGIS today. Coverage
is aggregated by H3 hexagon id and the map queries a lat/lon range. PostGIS
earns its place in Layer 4, where ranking tower sites means asking which
unserved settlements fall inside a radius — that wants real geodesic distance
and a GiST index, not an approximation in Python.

When it is added, `measurements.geom` is a generated column
(`GENERATED ALWAYS AS ... STORED`) over `lon`/`lat`, so the coordinates stay the
single source of truth and the geometry cannot drift out of step with them.
`scripts/enable_postgis.py` exists because migration 0002 will already be
stamped on a database created before PostGIS arrived.

## 10. Tile colour is the median state, and the worst state is kept beside it

The median resists a phone in a bag or a minute inside a concrete building. But
"usually fine, occasionally nothing at all" is a real finding for an operator,
so `worst_state` is stored and exposed alongside it rather than being averaged
away.

## 11. Numeric tile metrics are means, not medians

`avg_download_kbps` and `avg_latency_ms` are arithmetic means. The state median
is computed exactly, from per-state counts, which keeps a national rebuild to a
few thousand rows instead of a few million; true medians for the numeric columns
would need either `percentile_cont` (Postgres-only, untestable in the SQLite
suite) or a full row scan. Revisit if throughput outliers prove misleading.

## 12. Citizen reports never enter the tile statistics

Reports are subjective; measurements are instrument readings. Mixing them would
let a coordinated group of complainants outrank a genuinely unserved village.
Their value is corroboration: a red tile plus twenty reports is a stronger case
to an operator than either alone.

## 13. Enrolment will not rotate an existing device's key

Otherwise anyone who learned an `install_id` could register their own key and
sign whatever they liked under that identity. A device that loses its key enrols
as a new installation.

## 14. Admin endpoints are closed when unconfigured

An empty `ADMIN_TOKEN` locks the tile rebuild rather than opening it, so a
forgotten config fails safe.

## 15. Alembic reads the database URL directly, not through alembic.ini

`alembic.ini` is parsed by configparser with interpolation enabled, so writing
the URL into it makes any percent-encoded character in the password raise
"invalid interpolation syntax" before a single migration runs. Since a password
containing `@` *must* be percent-encoded, that is not an edge case. `env.py`
takes the URL straight from settings instead.

## 16. A hexagon belongs to the area its centroid falls in

At resolution 8 a hexagon is about 740 m across, so some straddle an
administrative border. The centroid decides, always. Assigning a tile to every
area it touches would double-count area totals, and splitting it proportionally
would invent a precision the measurements do not have.

The assignment is computed once, during the tile rebuild, and stored on the tile
as `adm1_code` / `adm2_code` / `adm3_code`. Filtering the map by province is
then an indexed equality rather than a geometry query on every pan — and it
works on a server with no PostGIS, consistent with decision 9.

## 17. Boundaries are stored as JSONB and tested in Python, not in PostGIS

Point-in-polygon, area and simplification are implemented in
`app/services/polygon.py` rather than delegated to GEOS. Four textbook
algorithms are a smaller commitment than a C library in every backend and worker
image, they run unchanged in the SQLite test suite, and they keep the area
filter working on a stock PostgreSQL server.

## 18. A village with no published boundary is a point, never an invented border

Lao province and district boundaries are published; village boundaries largely
are not — villages are recorded as points. Rather than carve a district into
village-shaped pieces, such a village is stored as its point with a stated
radius, `has_boundary` is false, and the map draws a dashed circle captioned as
an approximation.

A fabricated border on a national coverage map is the same class of error as
presenting a prediction as a measurement, and it is refused for the same reason.

## 19. A country or province view is shaded child areas, not hexagons

Lao PDR at resolution 8 is roughly 300,000 hexagons, each smaller than a pixel
at national zoom. The map therefore draws provinces shaded by their coverage at
country level and districts at province level, dropping to hexagons at district
and village. This is also the view a ministry actually reads.

## 20. An operator is identified by its MCC/MNC, never by its reported name

`TelephonyManager.getNetworkOperatorName()` returns a display string chosen by
the SIM, the network or the firmware, and the three disagree. The pilot database
showed the cost directly: 124 tiles filed under `LTC` and 1 under `LAO TELECOM`
— one company, appearing twice in the network filter with its coverage split
between the two entries.

Identity therefore comes from the MCC/MNC pair the device already sends, and the
display name from a table in `app/core/operators.py`. An unrecognised PLMN is
shown as its code (`457-05`), which is honest and obviously not a company name;
a reading with no PLMN falls back to whatever it called itself; a reading with
no network at all still has no operator.

The grouping happens in SQL rather than in Python because the aggregate counts
*distinct devices*, and distinct counts cannot be summed back together
afterwards — one collector seen under two spellings is one collector.

## 21. A full rebuild removes operator tiles the measurements no longer support

Aggregation only ever wrote rows. Nothing removed them, which was invisible
until an operator's name changed: the row under the old name stayed on the map
permanently and the network filter kept offering it.

Only on a full rebuild. An incremental run has deliberately looked at a slice of
the measurements, so anything outside that slice is missing rather than stale,
and deleting it would erase the rest of the map. `h3_tiles` is deliberately not
cleaned the same way — it also carries model predictions, which are not derived
from the measurement table.

## 22. Google proves identity; a super admin grants access

Signing in with Google establishes that an address belongs to whoever presented
it, and nothing more. A new account is therefore created `pending` and can read
nothing until a super admin approves it.

An allowlist checked at sign-in would be the same idea with the decision moved
into a config file, and everyone who needed access would wait for a redeploy.
The one thing configuration *does* decide is `SUPER_ADMIN_EMAILS`, because the
first super admin cannot approve themselves into existence — and keeping it in
configuration is what makes losing every super admin account recoverable.

Two rules stop the platform locking itself: nobody may decide about their own
account, and the last approved super admin cannot be demoted or rejected.

## 23. The session is a cookie this platform signs, not Google's token

Google's id token is evidence of a sign-in at one moment, not a session, and it
carries claims this application has no reason to keep. The server verifies it
once and issues its own short-lived JWT in an httpOnly, SameSite=Lax cookie —
httpOnly because any XSS bug would otherwise hand over the session.

The role and the approval are read from the database on every request rather
than baked into the token, so revoking somebody takes effect immediately
instead of whenever their token happens to expire.

The audience check on the Google token is the load-bearing one: without it, a
token minted for *any* Google application would verify here, and anyone able to
register their own app could sign in as anyone.

## 24. The collector endpoints are never gated

Enrolment and upload stay open, because a phone has no Google account and
authenticates instead with a device signature over every record. Gating them
would have stopped the Android fleet silently the moment sign-in was switched
on, and the map would simply have stopped growing.

Health checks stay open for the same reason: a load balancer cannot sign in
either. `/stats` does not — it is coverage data that happens to live beside
them.

## 25. A collector's position is published as a hexagon, never as a path

Asked twice, and settled the same way both times: the fleet view shows where
each phone **last** reported, snapped to its H3 hexagon — about 740 m across —
and nothing else. No history, no trail, never the GPS fix the handset recorded.

Every ingredient for full movement tracking is already on the server. Each
measurement carries exact coordinates, a timestamp and the device id, so a path
per collector is a query away rather than a feature to build. It is withheld
because it can be, not because it is hard.

Three reasons it stays withheld.

The proposal commits to it in writing, twice — 2.6 and 3.5 both say location
data is anonymised and aggregated into grid tiles before any display. A live
per-person path is the opposite of that sentence, in a document being judged.

The people carrying these phones are teachers, health workers, drivers and
provincial staff. A coarse position answers an operational question — is anyone
collecting in Attapeu today, is a phone sitting still — without answering where
somebody went after work. The first is fleet management; the second is
surveillance, and the difference is not a slider.

And it would not work where it matters anyway. In a dead zone there is no live
position at all: records queue on the handset and arrive in a burst hours
later, so a trail would fill itself in retroactively across exactly the places
this project exists to find.

If it is ever revisited, the conditions are known: admin-only, today's
hexagons only, deleted nightly, disclosed to every collector, and 2.6 amended
first.

## Open questions

- **Play Integrity**: device attestation is accepted but not yet verified
  server-side; it needs a Play Console project. Until then `trust_level` is
  advisory.
- **PostGIS on db2.chax.site**: absent today. Needed before Layer 4 site
  ranking; see `docs/setup.md` for how to add it and why it needs a maintenance
  window.
- **Role-based access** (public / operator / ministry, proposal 3.5) needs an
  identity provider decision. The single admin token is a placeholder.
- **H3 resolution**: currently 8 (~0.7 km² hexes). The right value depends on
  measurement density in the pilot province and should be revisited with real
  data before the public map launches.
- **Village boundary data**: settled for now — COD-AB for Lao PDR publishes
  ADM0-2 only, so the pilot has country, province and district. No village
  source exists to import; the point-and-radius handling of decision 18 stays in
  place for the day one does.
