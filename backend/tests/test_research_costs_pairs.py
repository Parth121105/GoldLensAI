import math
from datetime import date
from decimal import Decimal

import pytest

from app.research.config import ResearchConfig
from app.research.costs import CostModel
from app.research.pairs import ComparisonType, build_pair_series
from tests.synthetic_market import month_end, observation, pair_market

OCT = month_end(2025, 10)
NOV = month_end(2025, 11)


# --- Costs: unknown is never zero -------------------------------------------------


def test_costs_start_unknown():
    model = CostModel()

    assert model.round_trip_bps() is None
    assert set(model.unknown_components) == {
        "brokerage", "exchange_transaction_charges", "statutory_taxes_and_levies", "slippage",
    }


def test_partially_known_costs_are_still_unknown():
    model = CostModel().with_component("brokerage", 1.0, "broker tariff")

    assert model.round_trip_bps() is None
    assert "brokerage" not in model.unknown_components


def test_round_trip_is_four_leg_sides():
    model = CostModel.from_dict({
        "brokerage": {"bps_per_leg_side": 1.0, "source": "broker", "as_of": "2026-10-01"},
        "exchange_transaction_charges": {"bps_per_leg_side": 0.25},
        "statutory_taxes_and_levies": {"bps_per_leg_side": 0.5},
        "slippage": {"bps_per_leg_side": 0.25},
    })

    assert model.round_trip_bps() == pytest.approx(8.0)


def test_explicit_zero_is_allowed_and_labelled_as_assumption():
    model = CostModel().with_component("slippage", 0.0)
    (slippage,) = [c for c in model.components if c.name == "slippage"]

    assert slippage.known
    assert "user assumption" in slippage.label


def test_negative_cost_rejected():
    with pytest.raises(ValueError):
        CostModel().with_component("brokerage", -1.0)


# --- Pair construction ---------------------------------------------------------------


def test_spread_on_normalized_basis():
    # GOLDTEN 72450 per 10 g = 7245 /g; GOLDPETAL 7245 /g -> spread 0.
    d = date(2025, 10, 1)
    obs = [observation("GOLDTEN", OCT, d, Decimal("72450")), observation("GOLDPETAL", OCT, d, Decimal("7245"))]
    (series,) = build_pair_series(obs, ResearchConfig())

    assert series.points[0].spread_bps == pytest.approx(0.0)
    assert series.comparison_type is ComparisonType.SAME_EXPIRY


def test_goldm_995_basis_is_adjusted_before_spread():
    # GOLDM 71640 per 10 g @995 = 7192.8 /g @999 = GOLDTEN 71928 per 10 g.
    d = date(2025, 10, 1)
    goldm_expiry = date(2025, 11, 5)
    obs = [observation("GOLDM", goldm_expiry, d, Decimal("71640")),
           observation("GOLDTEN", OCT, d, Decimal("71928"))]
    (series,) = build_pair_series(obs, ResearchConfig())

    assert series.points[0].spread_bps == pytest.approx(0.0, abs=1e-9)
    assert series.comparison_type is ComparisonType.CROSS_EXPIRY
    assert series.expiry_gap_days == 5


def test_expiries_too_far_apart_are_not_paired():
    d = date(2025, 10, 1)
    obs = [observation("GOLDTEN", OCT, d, Decimal("72450")),
           observation("GOLDPETAL", NOV, d, Decimal("7245"))]

    assert build_pair_series(obs, ResearchConfig(max_expiry_gap_days=10)) == []


def test_each_series_is_one_fixed_contract_pair_never_spliced():
    obs = pair_market(lambda c, k: 0.0, [OCT, NOV])
    series = build_pair_series(obs, ResearchConfig())

    assert [s.pair_id for s in series] == [
        f"GOLDTEN-{OCT}|GOLDPETAL-{OCT}", f"GOLDTEN-{NOV}|GOLDPETAL-{NOV}",
    ]
    for s in series:
        assert {p.leg_a.contract_id for p in s.points} == {s.contract_a}
        assert {p.leg_b.contract_id for p in s.points} == {s.contract_b}


def test_missing_leg_dates_are_recorded_not_filled():
    obs = pair_market(lambda c, k: 0.0, [OCT])
    gap_day = date(2025, 10, 15)
    obs = [o for o in obs if not (o.symbol == "GOLDPETAL" and o.trade_date == gap_day)]
    (series,) = build_pair_series(obs, ResearchConfig())

    assert gap_day not in {p.trade_date for p in series.points}
    assert series.dates_missing_b == [gap_day]


@pytest.mark.parametrize(
    ("volume", "code"), [(None, "volume_unknown"), (0, "volume_below_min")],
)
def test_liquidity_unknown_or_zero_is_ineligible(volume, code):
    d = date(2025, 10, 1)
    obs = [observation("GOLDTEN", OCT, d, Decimal("72450"), volume=volume),
           observation("GOLDPETAL", OCT, d, Decimal("7245"))]
    (series,) = build_pair_series(obs, ResearchConfig())

    assert not series.points[0].eligible
    assert code in series.points[0].ineligible_codes


def test_dates_near_expiry_are_ineligible():
    d = date(2025, 10, 27)  # 4 days before 31 Oct
    obs = [observation("GOLDTEN", OCT, d, Decimal("72450")), observation("GOLDPETAL", OCT, d, Decimal("7245"))]
    (series,) = build_pair_series(obs, ResearchConfig(lifecycle_buffer_days=7))

    assert series.points[0].ineligible_codes == ("lifecycle_buffer",)


def test_unverified_specification_is_ineligible_unless_allowed():
    expiry = month_end(2025, 6)  # before the verified window
    d = date(2025, 6, 2)
    obs = [observation("GOLDTEN", expiry, d, Decimal("72450")),
           observation("GOLDPETAL", expiry, d, Decimal("7245"))]

    (strict,) = build_pair_series(obs, ResearchConfig())
    (lenient,) = build_pair_series(obs, ResearchConfig(allow_unverified_specs=True))

    assert "unverified_spec" in strict.points[0].ineligible_codes
    assert lenient.points[0].eligible


def test_resolution_reflects_tick_sizes():
    d = date(2025, 10, 1)
    obs = [observation("GOLDTEN", OCT, d, Decimal("72450")), observation("GOLDPETAL", OCT, d, Decimal("7245"))]
    (series,) = build_pair_series(obs, ResearchConfig())

    expected = 10_000 * (0.1 / 7245 + 1 / 7245)
    assert series.points[0].resolution_bps == pytest.approx(expected)
    assert math.isclose(series.points[0].resolution_bps, 1.518, rel_tol=1e-3)
