"""What the cell-site estimator may and may not claim.

These pin the honesty of the figure, not its arithmetic. The estimator is a
signal-weighted centroid of the places a cell was heard, and measured against
the fleet's own data it lands a median 104 m from the nearest reading, with the
readings running a median 11:1 along the route against across it. It finds the
middle of a drive. Splitting one cell's readings by time puts the two halves a
median 2,079 m apart.

So the danger here is not a wrong number, it is a number that looks surer than
it is: a tight radius on a map is read as a surveyed mast, and a ministry does
not send a survey team to check.
"""

from __future__ import annotations

import math

from scripts.estimate_cell_sites import (
    MIN_SPREAD_M,
    metres_between,
    weight_of,
    widest_separation,
)


def _uncertainty(spread: float) -> float:
    """The published figure, kept in step with the script by the test below."""
    return round(max(spread, 500.0), 1)


def test_uncertainty_covers_the_whole_stretch_not_half_of_it():
    """Half the spread failed 45 of 55 cells against a split-half check.

    The tightest-spread cells are the ones whose estimate moves furthest when
    the evidence changes, so halving made the figure worst exactly where it
    was most needed. The full spread covered all 55.
    """
    for spread in (900.0, 2_000.0, 8_264.0, 16_380.0):
        assert _uncertainty(spread) >= spread

    # And never a confident-looking figure for a cell heard along a short hop.
    assert _uncertainty(0.0) == 500.0


def test_the_estimate_never_escapes_the_readings_it_averages():
    """The reason this cannot locate a mast, stated as a test.

    A weighted centroid lies inside the convex hull of its inputs. A mast two
    kilometres off the highway is therefore unreachable by this method however
    many times the road is driven, which is why the label says "where the cell
    was heard" and not "base station".
    """
    # A road running north, with the true mast far to the east of all of it.
    readings = [(18.0 + i * 0.01, 102.6, -100.0) for i in range(6)]
    weights = [weight_of(r[2]) for r in readings]
    total = sum(weights)
    est_lat = sum(r[0] * w for r, w in zip(readings, weights)) / total
    est_lon = sum(r[1] * w for r, w in zip(readings, weights)) / total

    # Within the readings' own bounds, give or take the rounding of averaging
    # identical values — a millimetre, against the kilometres at issue here.
    lons = [r[1] for r in readings]
    assert min(lons) - 1e-9 <= est_lon <= max(lons) + 1e-9
    # Dead on the road: not one metre east, whatever the mast is really doing.
    assert math.isclose(est_lon, 102.6, abs_tol=1e-9)

    # The point is wrong by two kilometres while sitting exactly on the data.
    mast_east_of_the_road = metres_between(est_lat, est_lon, est_lat, 102.62)
    assert mast_east_of_the_road > 2_000

    # Whether the published circle happens to contain that mast depends only on
    # how far the collector drove, not on anything the readings know about the
    # offset. A long drive covers it by luck; a short one does not cover it at
    # all. That is why the label refuses to call this a base station, rather
    # than leaning on the circle to make the claim safe.
    long_drive = _uncertainty(widest_separation(readings))
    short_hop = _uncertainty(widest_separation(readings[:2]))
    assert long_drive > mast_east_of_the_road
    assert short_hop < mast_east_of_the_road


def test_a_cell_heard_from_one_place_is_never_published():
    """Readings from a car park do not become a position by being numerous."""
    parked = [(18.0, 102.6, -90.0)] * 30
    assert widest_separation(parked) < MIN_SPREAD_M

    drove = [(18.0 + i * 0.005, 102.6, -90.0) for i in range(6)]
    assert widest_separation(drove) >= MIN_SPREAD_M


def test_the_script_publishes_the_figure_these_tests_describe():
    """Guards against the formula drifting away from the calibration above."""
    import inspect

    from scripts import estimate_cell_sites

    source = inspect.getsource(estimate_cell_sites.build)
    assert "uncertainty_m=round(max(spread, 500.0), 1)" in source, (
        "the uncertainty formula changed; re-run the split-half calibration "
        "before accepting a smaller figure"
    )


def test_weighting_leans_gently_on_signal_strength():
    """RSRP is a poor distance proxy and must not be trusted like one."""
    assert weight_of(-120.0) == 1.0
    assert weight_of(-60.0) == 5.0
    # A 60 dB difference is worth five times, not a thousand times.
    assert weight_of(-60.0) / weight_of(-120.0) == 5.0
    assert weight_of(None) == 1.0
