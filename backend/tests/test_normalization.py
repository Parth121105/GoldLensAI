from datetime import date
from decimal import Decimal

import pytest

from app.normalization import (
    IncompatibleUnitsError,
    InvalidPriceError,
    NormalizationError,
    PriceField,
    RawQuote,
    UnverifiedSpecificationError,
    normalize,
)
from app.specs import SpecStatus

TRADE_DATE = date(2025, 10, 15)
SIX_DP = Decimal("0.000001")


def quote(symbol, price, expiry=date(2025, 10, 31), field=PriceField.CLOSE, **kw):
    return RawQuote(symbol, expiry, TRADE_DATE, Decimal(price), field, **kw)


# Hand-worked examples (see docs/methodology/normalization.md):
#   GOLDM      72000 per 10 g @995 -> 7200 /g @995 -> 7200 * 999/995 = 7228.944724 /g @999
#   GOLDTEN    72450 per 10 g @999 -> 7245 /g
#   GOLDGUINEA 57960 per 8 g  @999 -> 7245 /g
#   GOLDPETAL   7245 per 1 g  @999 -> 7245 /g
@pytest.mark.parametrize(
    ("symbol", "price", "expiry", "per_gram_basis", "per_gram_999"),
    [
        ("GOLDM", "72000", date(2025, 11, 5), "7200", "7228.944724"),
        ("GOLDTEN", "72450", date(2025, 10, 31), "7245", "7245"),
        ("GOLDGUINEA", "57960", date(2025, 10, 31), "7245", "7245"),
        ("GOLDPETAL", "7245", date(2025, 10, 31), "7245", "7245"),
    ],
)
def test_hand_worked_examples(symbol, price, expiry, per_gram_basis, per_gram_999):
    result = normalize(quote(symbol, price, expiry))

    assert result.inr_per_gram_at_basis == Decimal(per_gram_basis)
    assert result.inr_per_gram_999.quantize(SIX_DP) == Decimal(per_gram_999).quantize(SIX_DP)
    assert result.spec_status is SpecStatus.VERIFIED
    assert result.spec_version_id == VERSION_FOR_THESE_EXPIRIES[symbol]


# The specification PDFs that cover the expiries above (backend/data/raw/specs/).
VERSION_FOR_THESE_EXPIRIES = {
    "GOLDM": "GOLDM@MCX/TRD/456/2025",
    "GOLDTEN": "GOLDTEN@MCX/TRD/134/2025",
    "GOLDGUINEA": "GOLDGUINEA@MCX/TRD/650/2024",
    "GOLDPETAL": "GOLDPETAL@MCX/TRD/858/2024",
}


def test_equal_fine_gold_value_normalizes_to_equal_prices():
    # 71640 per 10 g at 995 = 7164 /g at 995 = 7192.8 /g at 999 = GOLDTEN 71928 per 10 g.
    gold_m = normalize(quote("GOLDM", "71640", date(2025, 11, 5)))
    gold_ten = normalize(quote("GOLDTEN", "71928"))

    assert gold_m.inr_per_gram_999 == gold_ten.inr_per_gram_999 == Decimal("7192.8")


@pytest.mark.parametrize("spot_995_per_10g", ["71640", "72000", "98765.43"])
def test_consistent_with_mcx_due_date_rate_formulas(spot_995_per_10g):
    """MCX/TRD/456/2025 derives each settlement price from one 995 spot per 10 g:

    GOLDTEN    DDR = S * 999/995                (Annexure 3)
    GOLDGUINEA DDR = S * 999/995 * 8/10         (Annexure 4)
    GOLDPETAL  DDR = S * 999/995 * 1/10         (Annexure 5, Mumbai spot)
    GOLDM      FSP = average of polled 995 spot (Annexure 2), i.e. S on a flat day

    Settlement prices built from the same spot must normalize to the same value.
    """
    s = Decimal(spot_995_per_10g)
    ddr = {
        "GOLDTEN": s * 999 / 995,
        "GOLDGUINEA": s * 999 / 995 * 8 / 10,
        "GOLDPETAL": s * 999 / 995 / 10,
        "GOLDM": s,
    }
    expiries = {"GOLDM": date(2025, 11, 5)}

    values = {
        symbol: normalize(
            quote(symbol, price, expiries.get(symbol, date(2025, 10, 31)), PriceField.SETTLEMENT)
        ).inr_per_gram_999.quantize(SIX_DP)
        for symbol, price in ddr.items()
    }

    assert len(set(values.values())) == 1
    assert values["GOLDTEN"] == (s / 10 * 999 / 995).quantize(SIX_DP)


def test_raw_quote_is_preserved_alongside_normalized_value():
    q = quote("GOLDGUINEA", "57960")
    result = normalize(q)

    assert result.raw is q
    assert result.raw.price == Decimal("57960")
    assert result.quotation_base_g == Decimal("8")


def test_formula_records_each_conversion():
    assert normalize(quote("GOLDM", "72000", date(2025, 11, 5))).formula == "72000 / 10 g * 999/995"
    assert normalize(quote("GOLDTEN", "72450")).formula == "72450 / 10 g (already 999 basis)"


def test_already_normalized_value_cannot_be_normalized_again():
    once = normalize(quote("GOLDM", "72000", date(2025, 11, 5)))

    with pytest.raises(TypeError):
        normalize(once)


@pytest.mark.parametrize(
    ("symbol", "tick"),
    [("GOLDTEN", "0.1"), ("GOLDGUINEA", "0.125"), ("GOLDPETAL", "1")],
)
def test_tick_size_in_comparison_units(symbol, tick):
    assert normalize(quote(symbol, "7245" if symbol == "GOLDPETAL" else "72450")).tick_inr_per_gram_999 == Decimal(tick)


def test_goldm_tick_size_includes_fineness_adjustment():
    result = normalize(quote("GOLDM", "72000", date(2025, 11, 5)))

    assert result.tick_inr_per_gram_999.quantize(SIX_DP) == Decimal("0.100402")


def test_declared_unit_matching_spec_is_accepted():
    result = normalize(quote("GOLDGUINEA", "57960", declared_quotation_base_g=Decimal("8")))

    assert result.inr_per_gram_at_basis == Decimal("7245")


def test_declared_unit_conflicting_with_spec_is_rejected():
    with pytest.raises(IncompatibleUnitsError, match="per 8 g"):
        normalize(quote("GOLDGUINEA", "57960", declared_quotation_base_g=Decimal("10")))


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_invalid_prices_are_rejected(price):
    with pytest.raises(InvalidPriceError):
        normalize(quote("GOLDTEN", price))


def test_unknown_instrument_is_rejected():
    with pytest.raises(NormalizationError, match="SILVER"):
        normalize(quote("SILVER", "88000"))


def test_unverified_specification_is_refused_by_default():
    with pytest.raises(UnverifiedSpecificationError, match="GOLDTEN"):
        normalize(quote("GOLDTEN", "72450", date(2027, 7, 30)))


def test_unverified_specification_can_be_assumed_explicitly_and_is_flagged():
    result = normalize(quote("GOLDTEN", "72450", date(2027, 7, 30)), allow_unverified=True)

    assert result.spec_status is SpecStatus.UNVERIFIED
    assert any(w.startswith("UNVERIFIED SPECIFICATION ASSUMED") for w in result.warnings)


def test_symbol_is_canonicalised_before_lookup():
    result = normalize(quote("  goldpetal ", "7245"))

    assert result.spec_version_id == "GOLDPETAL@MCX/TRD/858/2024"


def test_settlement_price_is_flagged_as_not_executable():
    result = normalize(quote("GOLDTEN", "72450", field=PriceField.SETTLEMENT))

    assert any("not an executable" in w for w in result.warnings)


def test_location_basis_difference_is_flagged_not_adjusted():
    petal = normalize(quote("GOLDPETAL", "7245"))
    ten = normalize(quote("GOLDTEN", "72450"))

    assert any("Ex-Mumbai" in w for w in petal.warnings)
    assert not any("Ex-" in w for w in ten.warnings)
    assert petal.inr_per_gram_999 == ten.inr_per_gram_999
