from datetime import date
from decimal import Decimal

import pytest

from app.specs import SpecStatus, UnknownInstrumentError, default_registry
from app.specs.registry import LastTradingDayRule

registry = default_registry()

# Expected values transcribed by hand from MCX/TRD/456/2025, Annexures 2-5.
EXPECTED = {
    "GOLDM": ("100", "10", 995, "Ex-Ahmedabad", ((2025, 9), (2026, 7))),
    "GOLDTEN": ("10", "10", 999, "Ex-Ahmedabad", ((2025, 8), (2026, 6))),
    "GOLDGUINEA": ("8", "8", 999, "Ex-Ahmedabad", ((2025, 8), (2026, 6))),
    "GOLDPETAL": ("1", "1", 999, "Ex-Mumbai", ((2025, 8), (2026, 6))),
}


def test_all_four_instruments_have_a_specification():
    assert registry.symbols == set(EXPECTED)


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_specification_matches_circular(symbol):
    unit, base, fineness, location, (lo, hi) = EXPECTED[symbol]
    (spec,) = registry.versions(symbol)

    assert spec.verification is SpecStatus.VERIFIED
    assert spec.trading_unit_g == Decimal(unit)
    assert spec.quotation_base_g == Decimal(base)
    assert spec.price_basis_fineness == fineness
    assert spec.tick_size_inr == Decimal("1")
    assert spec.price_quote_location == location
    assert (spec.expiry_from, spec.expiry_to) == (lo, hi)


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_every_specification_cites_a_retrievable_source(symbol):
    (spec,) = registry.versions(symbol)

    assert spec.sources
    assert spec.expiry_from <= spec.expiry_to
    for citation in spec.sources:
        assert citation.source.issued_on
        assert citation.source.retrieved_from.startswith("https://")
        assert citation.location
    assert spec.price_basis_evidence


def test_resolve_inside_verified_window():
    resolution = registry.resolve("GOLDTEN", date(2025, 10, 31))

    assert resolution.status is SpecStatus.VERIFIED
    assert resolution.spec.version_id == "GOLDTEN@MCX/TRD/456/2025"


@pytest.mark.parametrize(
    ("symbol", "expiry"),
    [("GOLDTEN", date(2025, 4, 30)), ("GOLDM", date(2026, 8, 5)), ("GOLDPETAL", date(2019, 1, 31))],
)
def test_resolve_outside_window_is_unverified(symbol, expiry):
    resolution = registry.resolve(symbol, expiry)

    assert resolution.status is SpecStatus.UNVERIFIED
    assert "No verified specification" in resolution.reason


def test_resolve_unknown_symbol_raises():
    with pytest.raises(UnknownInstrumentError):
        registry.resolve("SILVER", date(2025, 12, 5))


def test_goldten_listing_date_recorded():
    assert registry.listings["GOLDTEN"].first_trading_date == date(2025, 4, 1)


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (date(2025, 11, 5), True),  # nominal 5th
        (date(2025, 10, 3), True),  # 5 Oct 2025 is a Sunday: rolled back to Friday
        (date(2025, 11, 25), False),
        (date(2025, 11, 6), False),  # after the nominal day
    ],
)
def test_day_of_month_rule(expiry, expected):
    assert LastTradingDayRule("day_of_month", 5).is_consistent(expiry) is expected


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (date(2025, 10, 31), True),
        (date(2025, 11, 28), True),  # 30 Nov 2025 is a Sunday
        (date(2024, 2, 29), True),  # leap year
        (date(2025, 11, 20), False),
    ],
)
def test_last_calendar_day_rule(expiry, expected):
    assert LastTradingDayRule("last_calendar_day").is_consistent(expiry) is expected
