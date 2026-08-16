# How this platform decides what it shows

AI-PNICMP maps internet coverage in Lao PDR from measurements taken on ordinary
phones, including in places where there is no signal at all. This note explains
how a reading becomes a colour on the map, what each figure means, and — at
least as importantly — what the platform does not claim.

It is written so that a reader deciding where to spend money can judge how much
weight the map deserves.

---

## 1. What a phone records

A collector's handset takes a reading every ten seconds while it is moving. Each
reading carries the time, the GPS position and its accuracy, the network the
phone was registered on, the signal strength, and every cell tower the handset
could hear at that moment — whether or not it was attached to any of them.

Readings are taken whether or not there is coverage. **A place with no signal
produces a reading that says so.** This is the point of the platform: an absence
of data and an absence of coverage are different findings, and commercial
coverage maps rarely distinguish them.

### Trust

Every reading is signed on the handset at the moment of capture, using an
ECDSA P-256 key generated inside the phone's hardware keystore. The private key
cannot leave the device or be backed up.

The signature covers a fixed canonical string — version, record id, timestamp,
latitude, longitude, registration state, network type, signal strength, and cell
count — so a reading cannot be altered in transit or after the fact without
breaking it. The server verifies each signature against the key the device
enrolled with, and stores whether verification succeeded alongside the reading.

A consequence worth stating: a reinstalled app cannot recover its key, so it
must enrol as a new device. Enrolments with no readings are usually the same
handset after a reinstall, and are kept rather than deleted.

### Store and forward

A phone in a dead zone cannot upload. Readings are signed, queued on the device,
and sent when coverage returns — which may be hours later. The signature was made
at capture, so a delayed reading is no less trustworthy than an immediate one.

Uploads more than **14 days** after capture are flagged, not rejected. The
platform also records where a batch was uploaded from, which is generally not
where it was collected.

---

## 2. From a reading to a colour

Each reading is classified into exactly one of five states.

| State | Meaning | What it asks for |
|---|---|---|
| 🟢 **LTE_GOOD** | Registered on LTE at −110 dBm or stronger | Nothing |
| 🟡 **LTE_WEAK** | Registered on LTE below −110 dBm | Optimisation |
| 🟠 **REGISTERED_2G_3G** | Calls and SMS work, data does not | Data capacity upgrade |
| 🔴🟠 **CELLS_VISIBLE_UNREGISTERED** | A tower is audible but cannot be attached to | Upgrade or repeater — **no new tower needed** |
| 🔴 **NO_CELL** | Nothing on the air at all | New tower — capital investment |

Two decisions in that table carry most of the platform's value.

**Separating "a tower is there but unusable" from "there is no tower."** These
look identical to a user — the phone does not work either way — and they cost
very different amounts to fix. Recording an unusable-but-present tower as "no
network" asks for capital to build a mast that is already standing.

**Failing pessimistic.** Where a handset registers on LTE but its manufacturer
exposes no usable signal metric, the reading is recorded as weak rather than
good. Overstating coverage is the failure that costs a village its tower, so the
platform errs the other way.

Where a phone reports signal-to-noise but not strength, SINR ≥ 0 dB is used
instead of the −110 dBm line. Implausible readings (outside −140 to −44 dBm) are
discarded rather than believed.

---

## 3. From readings to the map

Readings are grouped into **H3 hexagons at resolution 8** — about 0.84 km² each
at Lao latitudes. A hexagon is coloured by the **median** state of every reading
ever taken inside it.

Median, not worst and not average:

- **Not worst**, because a single momentary dropout would paint a working area
  red and send money to the wrong place.
- **Not average**, because these are ordered categories, not numbers. The mean
  of "no network" and "good service" is not "calls only".

The worst state seen in each hexagon is stored separately and available, so a
reader specifically looking for dropouts can find them without that view
becoming the default.

Hexagons are also what protects collectors: the map never publishes a phone's
track, only the hexagons it passed through.

**Unmeasured areas are left blank.** The map claims nothing about them. A blank
area does not mean no coverage; it means nobody has been there yet. Provinces
and districts shaded faintly are shaded that way because little of them has been
measured — pale means little evidence, not poor coverage.

### What is rejected

- Readings implying a jump of more than 250 m between consecutive fixes at an
  impossible speed
- Readings claiming registration with zero cells visible — internally
  contradictory
- Signature failures, recorded and counted per device

Each record is judged individually. A device that has been offline for a week
may never get a second upload window, so a batch containing some bad records
still yields its good ones.

---

## 4. Where the cell towers on the map come from — and what they are not

The map shows points for cells the collectors have heard. **These are not
surveyed base station positions, and the platform does not claim they are.**

Each point is the signal-weighted centre of everywhere that cell was heard. A
phone measures signal strength, not direction, so one reading places a cell
somewhere within range — a disc, not a point. Overlapping discs taken from
different places narrows it; a hundred readings from one spot does not.

A cell is placed only if it was heard at least **5 times** across a spread of at
least **800 m**. Cells heard from a single stationary location are never placed,
however many readings they have.

### The honest limitation

Measured against the platform's own data:

- Estimates sit a **median 104 m** from the nearest reading — they land on the
  road the collector drove, because a weighted centroid cannot leave the cloud
  of points it averages.
- The readings themselves run a median **11:1** along the route against across
  it. The across-road direction — exactly where a mast's offset from the road
  lies — is not constrained at all.
- Splitting one cell's readings by time and estimating from each half
  independently places the same cell a median **2,079 m apart** (worst 8,295 m).

So this finds the centre of the stretch of road each cell was heard along. That
is a real and useful thing — it says which cells exist, whose they are, and
roughly where their coverage falls — and it is not a tower location.

### Uncertainty

Each point carries an uncertainty equal to the **full spread of the readings it
came from**, floored at 500 m. This figure is calibrated, not chosen: against
the split-half test above, half the spread covered only 10 of 55 cells, while
the full spread covers 55 of 55.

It remains a lower bound. It bounds the along-road error, which is the only one
the readings can see. A mast standing off to one side of the route is invisible
to this method entirely.

On the map, the pale circle around each point **is this uncertainty, not
coverage.** A wider circle means a less certain position. Points whose
uncertainty exceeds 2 km are drawn faint, and should be read as "somewhere along
this stretch" rather than as a place.

Distances from a phone to its serving cell are shown with their error bar, or
suppressed entirely where the error bar exceeds the distance.

---

## 5. Which network a reading belongs to

Networks are identified by the MCC/MNC broadcast by the network itself, never by
the name a handset displays — handset names are inconsistent between
manufacturers and can reflect a roaming partner rather than the serving network.

**Open question.** The published Lao allocation used by this platform is
457-01 Lao Telecom, 457-02 ETL, 457-03 Unitel, 457-08 Tplus. The handsets in the
current fleet consistently disagree for the first two: 1,427 readings report
457-02 as Lao Telecom and 202 report 457-01 as ETL. This has not been resolved,
and until it is, per-operator figures should be treated as provisional. The
tiebreak is a direct check of one SIM's number against its reported MCC/MNC.

Roaming detection is implemented and deliberately not exposed for the same
reason.

---

## 6. Who can see what

Three roles. Super administrators and administrators see everything. **Operator
accounts see only their own network** — its coverage, its cells, its summaries —
enforced on the server for every endpoint that touches map data, not in the
browser. An operator account cannot widen its own scope by editing a request.

Areas with no network at all are visible to every operator, since they belong to
no one and are the finding that matters most.

---

## 7. What this platform does not claim

- **It does not claim coverage where nothing has been measured.** Blank is blank.
- **It does not know how far any tower reaches.** No circle, ring or animation on
  the map represents coverage radius.
- **It does not locate base stations.** See §4.
- **It does not report what an operator owns**, only what collectors have heard.
- **It does not show live phone positions**, only the last hexagon a phone
  reported from.

---

## 8. Current state of the evidence

As of 17 August 2026:

| | |
|---|---|
| Measurements | 1,860 |
| Contributing phones | 10 |
| Hexagons measured | 286 (≈240 km²) |
| Provinces touched | 2 of 18 |
| Period | 9–16 August 2026 |

This is approximately **0.1% of the country**, along one highway corridor
through Vientiane Capital and Bolikhamxai. The methods above are built to scale
and have been exercised end to end; the coverage is a pilot.

Two consequences a reader should carry:

1. Per-province and national percentages are computed over what has been
   measured. They are not national coverage statistics.
2. Because collection has followed one road, cell position estimates are weakly
   constrained (§4). Driving routes that approach masts from more than one
   direction is what would improve them — not a change in method.

Upload speed is not yet measured; download speed is recorded on a subset of
readings only.
