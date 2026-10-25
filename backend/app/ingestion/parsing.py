"""Strict parsers for dates and numbers found in Bhavcopy files.

Nothing here guesses: a value that cannot be read unambiguously raises an error
that the importer records as a rejection reason.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

MISSING_TOKENS = frozenset({"", "-", "--", "NA", "N/A", "NULL", "NAN", "NONE"})

# Formats with a 4-digit year and a month name or a year-first order are unambiguous.
_UNAMBIGUOUS_FORMATS = ("%d-%b-%Y", "%d%b%Y", "%d %b %Y", "%d/%b/%Y", "%Y-%m-%d", "%Y%m%d")
_FOUR_DIGIT_YEAR = re.compile(r"(?<!\d)\d{4}(?!\d)")
_COMPACT_YMD = re.compile(r"^\d{8}$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_ISO_WITH_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]\d{1,2}:\d{2}")

MIN_YEAR, MAX_YEAR = 2000, 2100


class DateOrder(StrEnum):
    DMY = "DMY"
    MDY = "MDY"


class ParseError(ValueError):
    pass


class DateOrderConflictError(ParseError):
    pass


def is_missing(value: str | None) -> bool:
    return value is None or value.strip().strip('"').upper() in MISSING_TOKENS


def parse_date(value: str, order: DateOrder | None = None) -> date:
    text = value.strip().strip('"')
    if m := _ISO_WITH_TIME.match(text):
        text = m.group(1)

    if m := _NUMERIC_DATE.match(text):
        if order is None:
            raise ParseError(f"Ambiguous numeric date {value!r}: day/month order unknown")
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        day, month = (a, b) if order is DateOrder.DMY else (b, a)
        try:
            parsed = date(year, month, day)
        except ValueError as exc:
            raise ParseError(f"Invalid date {value!r} for order {order}: {exc}") from exc
        return _check_year(parsed, value)

    if not (_FOUR_DIGIT_YEAR.search(text) or _COMPACT_YMD.match(text)):
        raise ParseError(f"Unrecognised date {value!r}: a 4-digit year is required")
    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            return _check_year(datetime.strptime(text, fmt).date(), value)
        except ValueError:
            continue
    raise ParseError(f"Unrecognised date {value!r}")


def infer_date_order(values: Iterable[str]) -> DateOrder | None:
    """Infer day/month order from numeric dates where one part exceeds 12.

    Returns None when no value decides it. Raises if the evidence conflicts.
    """
    day_first = month_first = False
    for value in values:
        m = _NUMERIC_DATE.match(value.strip().strip('"'))
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        day_first |= a > 12
        month_first |= b > 12
    if day_first and month_first:
        raise DateOrderConflictError("File mixes day-first and month-first numeric dates")
    if day_first:
        return DateOrder.DMY
    if month_first:
        return DateOrder.MDY
    return None


def has_numeric_dates(values: Iterable[str]) -> bool:
    return any(_NUMERIC_DATE.match(v.strip().strip('"')) for v in values)


def parse_decimal(value: str | None) -> Decimal | None:
    if is_missing(value):
        return None
    assert value is not None
    text = value.strip().strip('"').replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"Not a number: {value!r}") from exc
    if not number.is_finite():
        raise ParseError(f"Not a finite number: {value!r}")
    return number


def parse_int(value: str | None) -> int | None:
    number = parse_decimal(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise ParseError(f"Expected a whole number, got {value!r}")
    return int(number)


def _check_year(parsed: date, original: str) -> date:
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ParseError(f"Implausible year in date {original!r}")
    return parsed
