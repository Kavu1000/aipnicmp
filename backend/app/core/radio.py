"""Radio-state domain model.

The proposal's central policy argument rests on a five-state classification
rather than a binary "signal / no signal", because the states imply different
remedies: an area no tower reaches needs a new site, whereas an area with a
tower but a weak signal may only need an upgrade or a repeater.

The client reports what it observed; the server derives the state. Keeping the
derivation here means thresholds can be retuned and history reclassified
without asking every device to update.
"""

from __future__ import annotations

from enum import StrEnum

# Proposal 2.3: "RSRP below -110 dBm" marks the boundary between usable-but-slow
# and normal service. The unusable boundary is where LTE attach typically fails.
RSRP_GOOD_DBM = -110.0
RSRP_FLOOR_DBM = -140.0
RSRP_CEIL_DBM = -44.0

# SINR fallback, used when the device does not expose RSRP (varies by OEM).
SINR_GOOD_DB = 0.0

BROADBAND_TYPES = {"LTE", "LTE_CA", "NR", "NR_NSA", "IWLAN"}
NARROWBAND_TYPES = {"GPRS", "EDGE", "GSM", "CDMA", "UMTS", "HSPA", "HSPAP", "HSDPA", "HSUPA", "TD_SCDMA", "EVDO"}


class RadioState(StrEnum):
    """The five states of proposal 2.3, in ascending order of service quality."""

    NO_CELL = "NO_CELL"
    """No cell detected at all — no network reaches this area, a new tower is required."""

    CELLS_VISIBLE_UNREGISTERED = "CELLS_VISIBLE_UNREGISTERED"
    """Cells visible but registration fails — too weak to use, emergency calls only."""

    REGISTERED_2G_3G = "REGISTERED_2G_3G"
    """Calls and SMS work, data does not."""

    LTE_WEAK = "LTE_WEAK"
    """Data works but is slow (RSRP below -110 dBm)."""

    LTE_GOOD = "LTE_GOOD"
    """Normal usable service."""


class TileColour(StrEnum):
    """Map colours. GREY means not yet measured — it is a tile state, never a record state."""

    RED = "red"
    RED_ORANGE = "red_orange"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    GREY = "grey"


STATE_COLOUR: dict[RadioState, TileColour] = {
    RadioState.NO_CELL: TileColour.RED,
    RadioState.CELLS_VISIBLE_UNREGISTERED: TileColour.RED_ORANGE,
    RadioState.REGISTERED_2G_3G: TileColour.ORANGE,
    RadioState.LTE_WEAK: TileColour.YELLOW,
    RadioState.LTE_GOOD: TileColour.GREEN,
}

# Ordinal score per state, used to average a tile down to one colour.
STATE_SCORE: dict[RadioState, int] = {
    RadioState.NO_CELL: 0,
    RadioState.CELLS_VISIBLE_UNREGISTERED: 1,
    RadioState.REGISTERED_2G_3G: 2,
    RadioState.LTE_WEAK: 3,
    RadioState.LTE_GOOD: 4,
}

SCORE_STATE: dict[int, RadioState] = {score: state for state, score in STATE_SCORE.items()}


def classify(
    *,
    registered: bool,
    network_type: str | None,
    cells_visible: int,
    rsrp_dbm: float | None,
    sinr_db: float | None = None,
) -> RadioState:
    """Derive the authoritative radio state from raw device observations.

    ``cells_visible`` counts every cell the modem could see, serving and
    neighbour alike. A device that is not registered but can still see cells is
    the diagnostically interesting case: the tower exists, it just cannot be
    used from here.
    """
    if cells_visible <= 0:
        # Nothing on the air at all. This is the finding that justifies capital
        # spend on a new site, so it must not be conflated with "not measured".
        return RadioState.NO_CELL

    if not registered:
        return RadioState.CELLS_VISIBLE_UNREGISTERED

    normalised = (network_type or "").upper().replace("-", "_")
    if normalised not in BROADBAND_TYPES:
        # Includes the narrowband types and anything unrecognised: if the device
        # cannot tell us it has broadband, we do not credit it with broadband.
        return RadioState.REGISTERED_2G_3G

    if rsrp_dbm is not None:
        return RadioState.LTE_GOOD if rsrp_dbm >= RSRP_GOOD_DBM else RadioState.LTE_WEAK

    if sinr_db is not None:
        return RadioState.LTE_GOOD if sinr_db >= SINR_GOOD_DB else RadioState.LTE_WEAK

    # Registered on LTE but the OEM exposed no usable signal metric. Assume the
    # pessimistic side: overstating coverage is the failure mode that costs a
    # village its tower.
    return RadioState.LTE_WEAK


def colour_for(state: RadioState) -> TileColour:
    return STATE_COLOUR[state]


def aggregate_colour(states: list[RadioState]) -> TileColour:
    """Reduce the states observed in one tile to a single map colour.

    Uses the median rather than the mean so that a handful of anomalous
    readings — a phone in a bag, a moment inside a building — cannot flip a
    tile's colour on their own.
    """
    if not states:
        return TileColour.GREY
    scores = sorted(STATE_SCORE[s] for s in states)
    median = scores[len(scores) // 2]
    return STATE_COLOUR[SCORE_STATE[median]]


def is_plausible_rsrp(rsrp_dbm: float) -> bool:
    return RSRP_FLOOR_DBM <= rsrp_dbm <= RSRP_CEIL_DBM
