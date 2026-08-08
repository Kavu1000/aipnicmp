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

## 9. Geometry is a generated column, not an ORM field

`measurements.geom` is derived by PostGIS from `lon`/`lat`
(`GENERATED ALWAYS AS ... STORED`). The coordinates have exactly one source of
truth and the geometry cannot drift out of step with them. It also keeps the ORM
free of a spatial type, so the test suite runs on SQLite with no SpatiaLite.

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

## Open questions

- **Play Integrity**: device attestation is accepted but not yet verified
  server-side; it needs a Play Console project. Until then `trust_level` is
  advisory.
- **Role-based access** (public / operator / ministry, proposal 3.5) needs an
  identity provider decision. The single admin token is a placeholder.
- **H3 resolution**: currently 8 (~0.7 km² hexes). The right value depends on
  measurement density in the pilot province and should be revisited with real
  data before the public map launches.
