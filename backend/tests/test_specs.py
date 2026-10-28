from datetime import date
from decimal import Decimal

import pytest

from app.specs import SpecStatus, UnknownInstrumentError, default_registry
from app.specs.registry import LastTradingDayRule

registry = default_registry()

# Transcribed by hand from the official MCX contract specification PDFs in backend/data/raw/specs/.
# symbol: (trading unit g, quote base g, fineness, location, [(version id, from, to, tender days, making Rs)])
EXPECTED = {
    "GOLD": ("1000", "10", 995, "Ex-Ahmedabad", [
        ("GOLD@MCX/TRD/086/2025", (2026, 2), (2026, 6), 5, None),
        ("GOLD@MCX/TRD/383/2025", (2026, 8), (2026, 12), 3, None),
        ("GOLD@MCX/PMT/375/2026", (2027, 2), (2027, 12), 3, None),
    ]),
    "GOLDM": ("100", "10", 995, "Ex-Ahmedabad", [
        ("GOLDM@MCX/TRD/456/2025", (2025, 9), (2026, 4), 3, None),
        ("GOLDM@MCX/TRD/041/2026", (2026, 5), (2026, 7), 3, None),
        ("GOLDM@MCX/PMT/375/2026", (2026, 8), (2027, 7), 3, None),
    ]),
    "GOLDTEN": ("10", "10", 999, "Ex-Ahmedabad", [
        ("GOLDTEN@MCX/TRD/134/2025", (2025, 4), (2025, 10), 5, "300"),
        ("GOLDTEN@MCX/TRD/456/2025", (2025, 11), (2026, 6), 3, "300"),
        ("GOLDTEN@MCX/PMT/375/2026", (2026, 7), (2027, 6), 3, "300"),
    ]),
    "GOLDGUINEA": ("8", "8", 999, "Ex-Ahmedabad", [
        ("GOLDGUINEA@MCX/TRD/650/2024", (2025, 1), (2025, 11), 5, "200"),
        ("GOLDGUINEA@MCX/TRD/456/2025", (2025, 12), (2026, 6), 3, "200"),
        ("GOLDGUINEA@MCX/PMT/375/2026", (2026, 7), (2027, 6), 3, "200"),
    ]),
    "GOLDPETAL": ("1", "1", 999, "Ex-Mumbai", [
        ("GOLDPETAL@MCX/TRD/858/2024", (2025, 4), (2025, 11), 5, "100"),
        ("GOLDPETAL@MCX/TRD/456/2025", (2025, 12), (2026, 6), 3, "100"),
        ("GOLDPETAL@MCX/PMT/375/2026", (2026, 7), (2027, 6), 3, "100"),
    ]),
}


def test_every_contract_has_specifications():
    assert registry.symbols == set(EXPECTED)


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_specifications_match_the_pdfs(symbol):
    unit, base, fineness, location, versions = EXPECTED[symbol]
    specs = registry.versions(symbol)

    assert [s.version_id for s in specs] == [v[0] for v in versions]
    for spec, (_, lo, hi, tender_days, making) in zip(specs, versions, strict=True):
        assert spec.verification is SpecStatus.VERIFIED
        assert spec.trading_unit_g == Decimal(unit)
        assert spec.quotation_base_g == Decimal(base)
        assert spec.price_basis_fineness == fineness
        assert spec.tick_size_inr == Decimal("1")
        assert spec.price_quote_location == location
        assert (spec.expiry_from, spec.expiry_to) == (lo, hi)
        assert spec.tender_period.trading_days == tender_days
        assert (str(spec.making_charge.inr) if spec.making_charge else None) == making
        assert spec.contract_start_text and spec.delivery_settlement


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_versions_do_not_overlap_and_lie_inside_their_launch_calendar(symbol):
    specs = registry.versions(symbol)
    for earlier, later in zip(specs, specs[1:]):
        assert earlier.expiry_to < later.expiry_from
    for spec in specs:
        # A version may also govern earlier-listed expiries from its "onwards" month,
        # but never expiries its launch calendar does not reach.
        assert spec.expiry_to <= max(m.expiry for m in spec.launch_calendar)


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_every_specification_cites_an_official_pdf(symbol):
    for spec in registry.versions(symbol):
        assert spec.sources
        for citation in spec.sources:
            assert citation.source.issued_on
            assert citation.source.retrieved_from.startswith("backend/data/raw/specs/")
            assert citation.source.retrieved_from.endswith(".pdf")
            assert "MCX/" in citation.source.retrieval_notes
            assert citation.location
        assert spec.price_basis_evidence


def test_uncovered_expiry_ranges_are_listed():
    assert set(registry.uncovered) == set(EXPECTED)


@pytest.mark.parametrize(
    ("symbol", "expiry", "version"),
    [
        ("GOLDTEN", date(2025, 10, 31), "GOLDTEN@MCX/TRD/134/2025"),
        ("GOLDTEN", date(2026, 10, 30), "GOLDTEN@MCX/PMT/375/2026"),
        ("GOLDM", date(2026, 11, 5), "GOLDM@MCX/PMT/375/2026"),
        ("GOLDM", date(2026, 6, 5), "GOLDM@MCX/TRD/041/2026"),
        ("GOLDPETAL", date(2027, 3, 31), "GOLDPETAL@MCX/PMT/375/2026"),
    ],
)
def test_resolve_inside_verified_window(symbol, expiry, version):
    resolution = registry.resolve(symbol, expiry)

    assert resolution.status is SpecStatus.VERIFIED
    assert resolution.spec.version_id == version


@pytest.mark.parametrize(
    ("symbol", "expiry"),
    [("GOLDTEN", date(2027, 7, 30)), ("GOLDM", date(2025, 8, 5)), ("GOLDPETAL", date(2019, 1, 31))],
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
