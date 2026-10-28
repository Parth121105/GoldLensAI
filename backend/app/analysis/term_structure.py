"""Futures curves per contract and the decomposition of day-to-day price changes.

Curve. For each symbol and trade date, the log of each expiry's normalized price
(INR/g @999) is fitted with a straight line against days to expiry T:

    ln P(T) = a + b * T + e

``b`` is the carry slope (shown as bps per day and annualised %), ``a`` the curve level
at T = 0, ``e`` each contract's distance from its own curve. Only contracts with a
verified specification enter the fit; at least two are needed.

Decomposition. For a contract present on two consecutive dates d0 and d1 the identity

    ln P1 - ln P0 = [a1 - a0] + b0 * (T1 - T0) + (b1 - b0) * T1 + (e1 - e0)

splits the move exactly. The first term is further split into the gold move common to
all four contracts (median level change across symbols) and the symbol's own level
change. Reported, in bps:

    gold_move   median level change across symbols
    roll_down   b0 * (T1 - T0): sliding down the old curve as expiry approaches
    curve_change (level change - gold move) + (b1 - b0) * T1: the curve's shape moved
    residual    e1 - e0: the contract moved against its own curve

The four parts add up to the total by construction.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.analysis.relative_value import ContractQuote, DaySnapshot
from app.research.pairs import BPS, SYMBOL_ORDER

DAYS_PER_YEAR = 365


@dataclass(frozen=True, slots=True)
class CurvePoint:
    contract_id: str
    expiry: date
    days_to_expiry: int
    inr_per_gram_999: float
    thin: bool
    fitted: float  # INR/g on the fitted curve at this T
    residual_bps: float


@dataclass(frozen=True, slots=True)
class Curve:
    symbol: str
    trade_date: date
    level: float  # a, log INR/g at T = 0
    slope_per_day: float  # b, log units per day

    points: tuple[CurvePoint, ...]

    @property
    def slope_bps_per_day(self) -> float:
        return self.slope_per_day * BPS

    @property
    def annualised_carry_pct(self) -> float:
        return (math.exp(self.slope_per_day * DAYS_PER_YEAR) - 1) * 100


@dataclass(frozen=True, slots=True)
class MoveSplit:
    contract_id: str
    symbol: str
    from_date: date
    to_date: date
    total_bps: float
    gold_move_bps: float
    roll_down_bps: float
    curve_change_bps: float
    residual_bps: float


@dataclass(slots=True)
class TermStructure:
    curves: list[Curve] = field(default_factory=list)
    gold_move_bps: dict[tuple[date, date], float] = field(default_factory=dict)
    splits: list[MoveSplit] = field(default_factory=list)

    def curve(self, symbol: str, trade_date: date) -> Curve | None:
        return next((c for c in self.curves if c.symbol == symbol and c.trade_date == trade_date), None)


def fit_curve(symbol: str, trade_date: date, quotes: list[ContractQuote]) -> Curve | None:
    usable = [q for q in quotes if q.inr_per_gram_999 is not None and q.spec_verified]
    if len({q.days_to_expiry for q in usable}) < 2:
        return None
    xs = [q.days_to_expiry for q in usable]
    ys = [math.log(float(q.inr_per_gram_999)) for q in usable]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    a = my - b * mx
    points = tuple(
        CurvePoint(
            contract_id=q.contract_id, expiry=q.expiry, days_to_expiry=x,
            inr_per_gram_999=float(q.inr_per_gram_999), thin=q.thin, fitted=math.exp(a + b * x),
            residual_bps=(y - (a + b * x)) * BPS,
        )
        for q, x, y in sorted(zip(usable, xs, ys, strict=True), key=lambda t: t[1])
    )
    return Curve(symbol, trade_date, a, b, points)


def term_structure(days: list[DaySnapshot]) -> TermStructure:
    ts = TermStructure()
    for d in days:
        by_symbol: dict[str, list[ContractQuote]] = defaultdict(list)
        for q in d.contracts:
            by_symbol[q.symbol].append(q)
        for symbol in SYMBOL_ORDER:
            curve = fit_curve(symbol, d.trade_date, by_symbol.get(symbol, []))
            if curve:
                ts.curves.append(curve)

    dates = [d.trade_date for d in days]
    for d0, d1 in zip(dates, dates[1:]):
        pairs = [(ts.curve(s, d0), ts.curve(s, d1)) for s in SYMBOL_ORDER]
        pairs = [(c0, c1) for c0, c1 in pairs if c0 and c1]
        if not pairs:
            continue
        gold = statistics.median(c1.level - c0.level for c0, c1 in pairs) * BPS
        ts.gold_move_bps[(d0, d1)] = gold
        for c0, c1 in pairs:
            before = {p.contract_id: p for p in c0.points}
            for p1 in c1.points:
                p0 = before.get(p1.contract_id)
                if p0 is None:
                    continue
                total = math.log(p1.inr_per_gram_999 / p0.inr_per_gram_999) * BPS
                level = (c1.level - c0.level) * BPS
                roll = c0.slope_per_day * (p1.days_to_expiry - p0.days_to_expiry) * BPS
                shape = (level - gold) + (c1.slope_per_day - c0.slope_per_day) * p1.days_to_expiry * BPS
                ts.splits.append(MoveSplit(
                    contract_id=p1.contract_id, symbol=c1.symbol, from_date=d0, to_date=d1,
                    total_bps=total, gold_move_bps=gold, roll_down_bps=roll, curve_change_bps=shape,
                    residual_bps=p1.residual_bps - p0.residual_bps,
                ))
    return ts


def carry_adjusted_gap_bps(gap_bps: float, days_a: int, days_b: int, slope_a: float, slope_b: float) -> float:
    """Gap with the expiry difference removed: B is moved along the mean of both curves' slopes to A's expiry."""
    carry = (slope_a + slope_b) / 2 * (days_a - days_b) * BPS
    return gap_bps - carry
