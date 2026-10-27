"""SYNTHETIC demonstration dataset. NOT MARKET DATA.

Generates a deterministic CSV in the legacy Bhavcopy layout so the full
pipeline (importer -> normalization -> research) can be demonstrated without
real MCX files. Every price is invented. The file name starts with
``SYNTHETIC_`` so the importer, the API and the UI label it as synthetic.

Built-in behaviour (so the demo exercises different outcomes):
  * GOLDPETAL: small noise plus a one-day price dip every few days, which
    reverses the next day. Pairs involving GOLDPETAL show reverting spikes.
  * GOLDGUINEA and GOLDM: relative price drifts as a random walk, so their
    deviations are not expected to reverse.
"""

from __future__ import annotations

import calendar
import csv
import io
import math
import random
from datetime import date, timedelta

DEMO_FILENAME = "SYNTHETIC_demo_dataset.csv"
FIRST_DAY = date(2025, 7, 1)
LAST_DAY = date(2026, 6, 30)
LISTING_DAYS = 90

HEADER = [
    "Date", "Instrument Name", "Symbol", "Expiry Date", "Option Type", "Strike Price",
    "Open", "High", "Low", "Close", "Previous Close", "Volume(Lots)", "Value(Lacs)",
    "Open Interest(Lots)",
]


def demo_csv_bytes() -> bytes:
    rng = random.Random(20251025)
    days = [d for d in _days(FIRST_DAY, LAST_DAY) if d.weekday() < 5]
    # Invented per-gram path (INR/g @999), a gentle random walk.
    level, per_gram = 7200.0, {}
    for d in days:
        level *= math.exp(rng.gauss(0.0002, 0.006))
        per_gram[d] = level

    month_ends = [_month_end(y, m) for y, m in _months((2025, 8), (2026, 6))]
    fifths = [date(y, m, 5) for y, m in _months((2025, 9), (2026, 7))]
    contracts = (
        [("GOLDTEN", e) for e in month_ends]
        + [("GOLDPETAL", e) for e in month_ends]
        + [("GOLDGUINEA", e) for e in month_ends]
        + [("GOLDM", e) for e in fifths]
    )

    # Random-walk relative drift (bps) per symbol and day, shared across expiries.
    drift: dict[str, dict[date, float]] = {"GOLDGUINEA": {}, "GOLDM": {}}
    for symbol in drift:
        walk = 0.0
        for d in days:
            walk += rng.gauss(0.0, 1.5)
            drift[symbol][d] = walk

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for d in days:
        for symbol, expiry in contracts:
            if not expiry - timedelta(days=LISTING_DAYS) <= d <= expiry:
                continue
            k = (d - (expiry - timedelta(days=LISTING_DAYS))).days
            price = _price(symbol, per_gram[d], k, drift.get(symbol, {}).get(d, 0.0), rng)
            volume = rng.randint(5, 400)
            writer.writerow([
                d.strftime("%d-%b-%Y"), "FUTCOM", symbol, expiry.strftime("%d-%b-%Y"), "XX", "0",
                price, price, price, price, "", volume, "", rng.randint(50, 3000),
            ])
    return out.getvalue().encode("utf-8")


def _price(symbol: str, per_gram_999: float, k: int, drift_bps: float, rng: random.Random) -> int:
    if symbol == "GOLDTEN":
        return round(per_gram_999 * 10)
    if symbol == "GOLDPETAL":
        dip = 30.0 if k % 6 == 4 else 0.0  # one-day dip, gone the next day
        return round(per_gram_999 * math.exp(-(rng.uniform(-2.0, 2.0) + dip) / 10_000))
    if symbol == "GOLDGUINEA":
        return round(per_gram_999 * 8 * math.exp(drift_bps / 10_000))
    # GOLDM is quoted per 10 g at 995 fineness.
    return round(per_gram_999 * 10 * 995 / 999 * math.exp(drift_bps / 10_000))


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])
