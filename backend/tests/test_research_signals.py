import statistics

import pytest

from app.research.config import ResearchConfig
from app.research.costs import CostModel
from app.research.pairs import build_pair_series
from app.research.signals import PointStatus, assess_series
from tests.synthetic_market import month_end, pair_market

OCT = month_end(2025, 10)
NOV = month_end(2025, 11)
CONFIG = ResearchConfig()
KNOWN_COSTS = CostModel.from_dict({
    name: {"bps_per_leg_side": 0.5, "source": "test"}
    for name in ("brokerage", "exchange_transaction_charges", "statutory_taxes_and_levies", "slippage")
})


def series_for(spread_fn, expiries=(OCT,)):
    return build_pair_series(pair_market(spread_fn, list(expiries)), CONFIG)


def wiggle(c, k):
    return [0.0, 3.0, -3.0, 2.0, -2.0][k % 5]


def test_baseline_uses_only_prior_points():
    (series,) = series_for(wiggle)
    assessed = assess_series(series, z_threshold=2.0, window=5, costs=CostModel())

    eligible = [a for a in assessed if a.point.eligible]
    a = eligible[7]
    prior = [e.point.spread_bps for e in eligible[2:7]]
    assert a.baseline_mean_bps == pytest.approx(statistics.fmean(prior))
    assert a.baseline_std_bps == pytest.approx(statistics.stdev(prior))


def test_changing_future_data_does_not_change_past_assessments():
    def spiky_future(c, k):
        return wiggle(c, k) + (500.0 if k >= 25 else 0.0)

    (base,) = series_for(wiggle)
    (changed,) = series_for(spiky_future)
    a = assess_series(base, z_threshold=2.0, window=5, costs=CostModel())
    b = assess_series(changed, z_threshold=2.0, window=5, costs=CostModel())

    for x, y in zip(a[:25], b[:25], strict=True):
        assert (x.status, x.z_score) == (y.status, y.z_score)


def test_first_points_have_insufficient_history():
    (series,) = series_for(wiggle)
    assessed = [a for a in assess_series(series, z_threshold=2.0, window=10, costs=CostModel())
                if a.point.eligible]

    assert all(a.status is PointStatus.INSUFFICIENT_HISTORY for a in assessed[:10])
    assert assessed[10].status is not PointStatus.INSUFFICIENT_HISTORY


def test_new_expiry_pair_starts_without_inherited_history():
    oct_series, nov_series = series_for(wiggle, (OCT, NOV))
    nov = [a for a in assess_series(nov_series, z_threshold=2.0, window=10, costs=CostModel())
           if a.point.eligible]

    # The Oct pair trades alongside, but the Nov baseline never borrows from it.
    assert nov[0].status is PointStatus.INSUFFICIENT_HISTORY
    assert nov[0].baseline_n == 0


def spike_at(k_spike, size):
    return lambda c, k: wiggle(c, k) + (size if k == k_spike else 0.0)


def status_at(spread_fn, k, costs):
    (series,) = series_for(spread_fn)
    assessed = assess_series(series, z_threshold=2.0, window=10, costs=costs)
    return next(a for a in assessed if a.point.trade_date == series.points[k].trade_date)


def test_spike_with_unknown_costs_is_statistical_anomaly_only():
    a = status_at(spike_at(20, 40.0), 20, CostModel())

    assert a.status is PointStatus.STATISTICAL_ANOMALY
    assert a.round_trip_cost_bps is None
    assert "Costs unknown" in a.notes[0]


def test_spike_exceeding_known_costs_is_cost_adjusted_candidate():
    a = status_at(spike_at(20, 40.0), 20, KNOWN_COSTS)

    assert a.status is PointStatus.COST_ADJUSTED_CANDIDATE
    assert a.round_trip_cost_bps == pytest.approx(8.0)
    assert a.net_edge_bps == pytest.approx(abs(a.deviation_bps) - 8.0)


def test_spike_below_known_costs_stays_statistical():
    expensive = CostModel.from_dict({
        name: {"bps_per_leg_side": 20.0, "source": "test"}
        for name in ("brokerage", "exchange_transaction_charges", "statutory_taxes_and_levies", "slippage")
    })
    a = status_at(spike_at(20, 40.0), 20, expensive)

    assert a.status is PointStatus.STATISTICAL_ANOMALY
    assert a.net_edge_bps < 0


def test_tiny_deviation_inside_tick_resolution_is_only_a_candidate():
    flat = lambda c, k: 0.0 if k != 20 else 1.0  # noqa: E731
    a = status_at(flat, 20, CostModel())

    # A flat baseline would be degenerate; GOLDPETAL rounding creates tiny noise instead.
    assert a.status in {PointStatus.CANDIDATE_ANOMALY, PointStatus.WITHIN_BASELINE,
                        PointStatus.DEGENERATE_BASELINE}
    assert a.status is not PointStatus.STATISTICAL_ANOMALY
