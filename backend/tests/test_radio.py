"""The five-state classification is the proposal's policy argument in code,
so each state gets an explicit test."""

from __future__ import annotations

import pytest

from app.core.radio import RadioState, TileColour, aggregate_colour, classify


def test_no_cell_when_nothing_on_the_air():
    state = classify(registered=False, network_type=None, cells_visible=0, rsrp_dbm=None)
    assert state is RadioState.NO_CELL


def test_cells_visible_but_unregistered():
    """The diagnostically important middle case: a tower exists but cannot be
    used from here, which is an upgrade problem rather than a new-site problem."""
    state = classify(registered=False, network_type="LTE", cells_visible=2, rsrp_dbm=-125.0)
    assert state is RadioState.CELLS_VISIBLE_UNREGISTERED


@pytest.mark.parametrize("network", ["GSM", "EDGE", "UMTS", "HSPA"])
def test_narrowband_is_calls_and_sms_only(network: str):
    state = classify(registered=True, network_type=network, cells_visible=1, rsrp_dbm=-90.0)
    assert state is RadioState.REGISTERED_2G_3G


def test_lte_weak_below_threshold():
    state = classify(registered=True, network_type="LTE", cells_visible=1, rsrp_dbm=-111.0)
    assert state is RadioState.LTE_WEAK


def test_lte_good_at_threshold():
    """-110 dBm is stated in the proposal as the boundary; the boundary itself
    counts as usable."""
    state = classify(registered=True, network_type="LTE", cells_visible=1, rsrp_dbm=-110.0)
    assert state is RadioState.LTE_GOOD


def test_nr_counts_as_broadband():
    state = classify(registered=True, network_type="NR", cells_visible=1, rsrp_dbm=-80.0)
    assert state is RadioState.LTE_GOOD


def test_falls_back_to_sinr_when_rsrp_missing():
    weak = classify(registered=True, network_type="LTE", cells_visible=1, rsrp_dbm=None, sinr_db=-5.0)
    good = classify(registered=True, network_type="LTE", cells_visible=1, rsrp_dbm=None, sinr_db=12.0)
    assert weak is RadioState.LTE_WEAK
    assert good is RadioState.LTE_GOOD


def test_unknown_metrics_assume_the_pessimistic_side():
    """Overstating coverage is the failure that costs a village its tower."""
    state = classify(registered=True, network_type="LTE", cells_visible=1, rsrp_dbm=None, sinr_db=None)
    assert state is RadioState.LTE_WEAK


def test_unknown_network_type_is_not_credited_as_broadband():
    state = classify(registered=True, network_type="SOMETHING_NEW", cells_visible=1, rsrp_dbm=-70.0)
    assert state is RadioState.REGISTERED_2G_3G


def test_empty_tile_is_grey():
    assert aggregate_colour([]) is TileColour.GREY


def test_tile_colour_uses_the_median_not_the_extreme():
    """One reading from inside a building must not turn a working area red."""
    states = [
        RadioState.LTE_GOOD,
        RadioState.LTE_GOOD,
        RadioState.LTE_GOOD,
        RadioState.NO_CELL,
        RadioState.LTE_GOOD,
    ]
    assert aggregate_colour(states) is TileColour.GREEN


def test_genuinely_dead_area_stays_red():
    assert aggregate_colour([RadioState.NO_CELL] * 5) is TileColour.RED
