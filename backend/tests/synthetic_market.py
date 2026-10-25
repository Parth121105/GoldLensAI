"""SYNTHETIC market generator for research-engine tests. NOT MARKET DATA.

Builds GOLDTEN / GOLDPETAL observations whose normalized spread follows a
function chosen by the test, so each test knows the right answer in advance.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from app.ingestion.models import Observation, RowProvenance

SYNTHETIC_FILE = "SYNTHETIC_generated.csv"
BASE_PER_GRAM = 7245.0

# spread_bps(contract_index, day_index_within_contract) -> GOLDTEN vs GOLDPETAL spread in bps
SpreadFn = Callable[[int, int], float]


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def observation(
    symbol: str, expiry: date, trade_date: date, close: Decimal, volume: int | None = 10, line: int = 0
) -> Observation:
    return Observation(
        trade_date=trade_date,
        symbol=symbol,
        raw_symbol=symbol,
        expiry=expiry,
        open=close,
        high=close,
        low=close,
        close=close,
        previous_close=None,
        settlement=None,
        volume=volume,
        value=None,
        open_interest=None,
        traded=None if volume is None else volume > 0,
        provenance=RowProvenance(SYNTHETIC_FILE, "0" * 64, line, "synthetic"),
    )


def pair_market(
    spread_fn: SpreadFn,
    expiries: list[date],
    listing_days: int = 60,
) -> list[Observation]:
    """One GOLDTEN and one GOLDPETAL contract per expiry, each trading for ``listing_days``."""
    out = []
    for c, expiry in enumerate(expiries):
        days = business_days(expiry - timedelta(days=listing_days), expiry)
        for k, d in enumerate(days):
            per_gram = BASE_PER_GRAM * (1 + 0.0002 * c)
            ten = Decimal(round(per_gram * 10))
            petal = Decimal(round(float(ten) / 10 * math.exp(-spread_fn(c, k) / 10_000)))
            out.append(observation("GOLDTEN", expiry, d, ten))
            out.append(observation("GOLDPETAL", expiry, d, petal))
    return out


def verified_expiries() -> list[date]:
    """Month-end expiries Aug 2025 - Jun 2026, all inside the verified specification window."""
    months = [(2025, m) for m in range(8, 13)] + [(2026, m) for m in range(1, 7)]
    return [month_end(y, m) for y, m in months]
