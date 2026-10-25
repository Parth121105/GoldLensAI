from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.parsing import (
    DateOrder,
    DateOrderConflictError,
    ParseError,
    infer_date_order,
    parse_date,
    parse_decimal,
    parse_int,
)
from app.instruments import canonical_symbol, is_supported


@pytest.mark.parametrize(
    "text",
    ["15-Oct-2025", "15OCT2025", "15 Oct 2025", "15/Oct/2025", "2025-10-15", "20251015",
     "2025-10-15T00:00:00", " \"15-OCT-2025\" "],
)
def test_unambiguous_date_formats(text):
    assert parse_date(text) == date(2025, 10, 15)


def test_numeric_date_requires_known_order():
    with pytest.raises(ParseError, match="Ambiguous"):
        parse_date("05/11/2025")


def test_numeric_date_respects_order():
    assert parse_date("05/11/2025", DateOrder.DMY) == date(2025, 11, 5)
    assert parse_date("05/11/2025", DateOrder.MDY) == date(2025, 5, 11)


@pytest.mark.parametrize("text", ["31/02/2025", "garbage", "15-Oct-25", "15-Oct-1925", ""])
def test_invalid_dates_raise(text):
    with pytest.raises(ParseError):
        parse_date(text, DateOrder.DMY)


def test_infer_date_order():
    assert infer_date_order(["15/10/2025", "05/11/2025"]) is DateOrder.DMY
    assert infer_date_order(["10/15/2025", "11/05/2025"]) is DateOrder.MDY
    assert infer_date_order(["05/11/2025", "15-Oct-2025"]) is None


def test_infer_date_order_conflict():
    with pytest.raises(DateOrderConflictError):
        infer_date_order(["15/10/2025", "10/15/2025"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [("72,000.50", Decimal("72000.50")), (" 7245 ", Decimal("7245")), ("-5", Decimal("-5")),
     ("", None), ("-", None), ("NA", None), ("NaN", None), (None, None)],
)
def test_parse_decimal(text, expected):
    assert parse_decimal(text) == expected


@pytest.mark.parametrize("text", ["abc", "1.2.3", "inf", "-Infinity"])
def test_parse_decimal_rejects_non_numbers(text):
    with pytest.raises(ParseError):
        parse_decimal(text)


def test_parse_int():
    assert parse_int("1,200") == 1200
    assert parse_int("12.0") == 12
    with pytest.raises(ParseError):
        parse_int("12.5")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("GOLDM", "GOLDM"), ("  goldm  ", "GOLDM"), ('"GOLDTEN"', "GOLDTEN"),
     ("GOLD GUINEA", "GOLDGUINEA"), ("GOLDPTL", "GOLDPETAL"), ("SILVER", "SILVER")],
)
def test_canonical_symbol(raw, expected):
    assert canonical_symbol(raw) == expected


def test_only_the_four_gold_contracts_are_supported():
    assert is_supported("GOLDPETAL")
    assert not is_supported("GOLD")
    assert not is_supported("SILVER")
