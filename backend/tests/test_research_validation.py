import random
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.models import ImportReport, ImportResult
from app.research import CostModel, MixedDataError, ResearchConfig, Verdict, run_research
from app.research.engine import merge_observations
from app.research.pairs import build_pair_series
from app.research.validation import Event, _in_window, validate_symbol_pair
from tests.synthetic_market import month_end, observation, pair_market, verified_expiries

COST_NAMES = ("brokerage", "exchange_transaction_charges", "statutory_taxes_and_levies", "slippage")


def costs(bps_per_leg_side):
    return CostModel.from_dict({n: {"bps_per_leg_side": bps_per_leg_side, "source": "test"}
                                for n in COST_NAMES})


BASE = ResearchConfig(horizon=1, baseline_windows=(5, 10), min_events=8, n_folds=3)


def noise(c, k):
    return random.Random(c * 1000 + k).uniform(-2.0, 2.0)


def reverting(c, k):
    """Every 7th observation jumps 30 bps and is back to noise the next day."""
    return noise(c, k) + (30.0 if k % 7 == 6 else 0.0)


def persistent(c, k):
    """Every 7th observation the level steps 30 bps and stays there."""
    return noise(c, k) + 30.0 * ((k + 1) // 7)


def validate(spread_fn, config=BASE, expiries=None):
    obs = pair_market(spread_fn, expiries or verified_expiries())
    series = build_pair_series(obs, config)
    return validate_symbol_pair(series, config), obs


def test_reverting_spread_with_known_small_costs_is_validated():
    result, _ = validate(reverting, replace(BASE, costs=costs(0.5)))

    assert result.verdict is Verdict.HISTORICALLY_VALIDATED
    assert result.final.signals.n >= BASE.min_events
    assert result.final.signals.mean_net_bps > 0
    assert "independent verification" in result.reasons[-1]


def test_reverting_spread_with_unknown_costs_cannot_be_validated():
    result, _ = validate(reverting)

    assert result.verdict is Verdict.GROSS_ONLY_COSTS_UNKNOWN
    assert result.final.signals.mean_net_bps is None


def test_reverting_spread_with_high_costs_fails_after_costs():
    result, _ = validate(reverting, replace(BASE, costs=costs(10.0)))

    assert result.verdict is Verdict.NOT_SUPPORTED_AFTER_COSTS


def test_persistent_shifts_do_not_support_reversion():
    result, _ = validate(persistent, replace(BASE, costs=costs(0.5)))

    assert result.verdict in {Verdict.NOT_SUPPORTED, Verdict.INSUFFICIENT_DATA}
    assert result.verdict is not Verdict.HISTORICALLY_VALIDATED


def test_short_history_reports_insufficient_data():
    result, _ = validate(reverting, expiries=[month_end(2025, 10)])

    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert result.reasons


def test_windows_are_chronological_and_holdout_is_last():
    result, _ = validate(reverting)

    assert result.development[1] < result.holdout[0]
    for fold in result.folds:
        assert fold.train[1] < fold.test[0]
        assert fold.test[1] <= result.development[1]
    assert result.final.train == result.development
    assert result.final.test == result.holdout


def test_holdout_data_cannot_influence_parameter_choice():
    """Rewrite every holdout observation; folds and the selected parameters must not change."""
    config = replace(BASE, costs=costs(0.5))
    original, obs = validate(reverting, config)
    holdout_start = original.holdout[0]

    rng = random.Random(7)
    altered = [
        replace(o, close=o.close + Decimal(rng.randint(-40, 40))) if o.symbol == "GOLDPETAL"
        and o.trade_date >= holdout_start else o
        for o in obs
    ]
    again = validate_symbol_pair(build_pair_series(altered, config), config)

    assert again.final.params == original.final.params
    assert again.final.train_signals == original.final.train_signals
    assert again.folds == original.folds
    assert again.final.signals != original.final.signals  # the holdout itself did change


def test_events_straddling_a_window_boundary_are_purged():
    e = Event("p", date(2025, 10, 30), date(2025, 11, 3), 10.0, 5.0, None)
    window = (date(2025, 10, 1), date(2025, 10, 31))

    assert _in_window([e], window) == []
    assert _in_window([e], (date(2025, 10, 1), date(2025, 11, 3))) == [e]


def test_signal_events_do_not_overlap():
    config = replace(BASE, horizon=3)
    obs = pair_market(reverting, verified_expiries())
    series = build_pair_series(obs, config)
    from app.research.validation import _events

    signals = _events(series, (1.5, 5), config).signals
    by_pair = {}
    for e in sorted(signals, key=lambda e: e.trade_date):
        last = by_pair.get(e.pair_id)
        assert last is None or e.trade_date > last.outcome_date
        by_pair[e.pair_id] = e


def test_missing_observations_are_skipped_not_filled():
    obs = pair_market(reverting, verified_expiries())
    dropped = {date(2025, 10, 15), date(2025, 12, 10)}
    obs = [o for o in obs if not (o.symbol == "GOLDPETAL" and o.trade_date in dropped)]
    series = build_pair_series(obs, BASE)

    assert all(p.trade_date not in dropped for s in series for p in s.points)
    assert sum(len(s.dates_missing_b) for s in series) >= len(dropped)
    validate_symbol_pair(series, BASE)  # runs without filling gaps


# --- Engine -----------------------------------------------------------------------


def import_result(observations, name, synthetic):
    report = ImportReport(
        source_file=name, source_sha256="0" * 64, size_bytes=0, imported_at=None,
        layout_id="synthetic", layout_verified_against_real_file=False, units={},
        date_order=None, synthetic=synthetic,
    )
    return ImportResult(observations, report)


def test_synthetic_and_real_files_cannot_be_mixed():
    obs = pair_market(noise, [month_end(2025, 10)])
    with pytest.raises(MixedDataError):
        run_research([import_result(obs, "SYNTHETIC_a.csv", True), import_result(obs, "real.csv", False)])


def test_engine_report_is_labelled_synthetic():
    obs = pair_market(reverting, verified_expiries())
    report = run_research([import_result(obs, "SYNTHETIC_a.csv", True)], BASE)

    assert report.synthetic is True
    assert [v.symbol_pair for v in report.validations] == ["GOLDTEN/GOLDPETAL"]
    assert report.coverage[0].eligible_dates > 0


def test_conflicting_observations_across_files_are_dropped():
    d, expiry = date(2025, 10, 1), month_end(2025, 10)
    a = observation("GOLDTEN", expiry, d, Decimal("72450"))
    b = observation("GOLDTEN", expiry, d, Decimal("72460"))
    merged, conflicts = merge_observations([import_result([a], "x.csv", False),
                                            import_result([b], "y.csv", False)])

    assert merged == []
    assert "files disagree" in conflicts[0]


def test_identical_observations_across_files_are_kept_once():
    d, expiry = date(2025, 10, 1), month_end(2025, 10)
    a = observation("GOLDTEN", expiry, d, Decimal("72450"))
    merged, conflicts = merge_observations([import_result([a], "x.csv", False),
                                            import_result([a], "y.csv", False)])

    assert merged == [a]
    assert conflicts == []
