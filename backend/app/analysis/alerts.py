"""Alerts: real-data contract pairs whose gap has moved unusually far from its own normal level.

For each fixed contract pair, the gap is the carry-adjusted gap when expiries differ and the
raw gap when they match. On a trade date an alert fires only if all of these hold:

  * both contracts are liquid and outside the pre-expiry buffer (``tradeable``),
  * the pair has at least ``baseline_dates`` earlier dates (its normal gap is known),
  * the gap is at least ``z_threshold`` standard deviations from that normal level, and
  * the move from normal exceeds the round-trip cost plus ``extra_margin_bps``.

Persistent gaps (location basis, purity rounding) are part of the normal level and never alert.
All thresholds are assumptions in backend/config/assumptions.json. Quiet by default.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.analysis.relative_value import DaySnapshot, PairGap
from app.assumptions import Assumptions, cost_model, default_assumptions


@dataclass(frozen=True, slots=True)
class Alert:
    trade_date: date
    contract_a: str
    contract_b: str
    gap_bps: float
    normal_gap_bps: float
    move_bps: float
    z: float
    cost_bps: float


@dataclass(slots=True)
class AlertReport:
    trade_date: date | None
    z_threshold: float
    baseline_dates: int
    round_trip_cost_bps: float
    extra_margin_bps: float
    pairs_checked: int = 0
    pairs_tradeable: int = 0
    pairs_with_baseline: int = 0
    most_history: int = 0
    alerts: list[Alert] = field(default_factory=list)


def _gap(p: PairGap) -> float:
    return p.carry_adjusted_gap_bps if p.carry_adjusted_gap_bps is not None else p.gap_bps


def alerts(days: list[DaySnapshot], assumptions: Assumptions | None = None) -> AlertReport:
    a = assumptions or default_assumptions()
    z_threshold = float(a.get("alerts.z_threshold"))
    window = int(a.get("alerts.baseline_dates"))
    margin = float(a.get("alerts.extra_margin_bps"))
    cost = cost_model(a).round_trip_bps() or 0.0
    report = AlertReport(days[-1].trade_date if days else None, z_threshold, window, cost, margin)
    if not days:
        return report

    history: dict[tuple[str, str], list[float]] = defaultdict(list)
    for d in days[:-1]:
        for p in d.pairs:
            history[(p.contract_a, p.contract_b)].append(_gap(p))

    latest = days[-1]
    for p in latest.pairs:
        report.pairs_checked += 1
        prior = history.get((p.contract_a, p.contract_b), [])[-window:]
        report.most_history = max(report.most_history, len(prior))
        if not p.tradeable:
            continue
        report.pairs_tradeable += 1
        if len(prior) < window:
            continue
        report.pairs_with_baseline += 1
        mean, std = statistics.fmean(prior), statistics.stdev(prior)
        move = _gap(p) - mean
        if std == 0:
            continue
        z = move / std
        if abs(z) >= z_threshold and abs(move) > cost + margin:
            report.alerts.append(Alert(latest.trade_date, p.contract_a, p.contract_b, _gap(p), mean, move, z, cost))
    return report
