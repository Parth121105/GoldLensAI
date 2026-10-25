"""Causal baseline and anomaly classification for one pair series.

Baseline at an eligible point i: mean and sample standard deviation of the
previous ``window`` eligible spreads of the same series, strictly before i.
The point itself and anything after it are never used.

Levels (each requires the one before):
  1. CANDIDATE_ANOMALY       |z| >= z_threshold
  2. STATISTICAL_ANOMALY     ...and |deviation| exceeds the tick-resolution floor
  3. COST_ADJUSTED_CANDIDATE ...and |deviation| exceeds known round-trip costs
A historically validated finding is a separate, pair-level conclusion from
walk-forward validation (see validation.py), never a per-point label.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import StrEnum

from app.research.costs import CostModel
from app.research.pairs import PairPoint, PairSeries


class PointStatus(StrEnum):
    INELIGIBLE = "ineligible"
    INSUFFICIENT_HISTORY = "insufficient_history"
    DEGENERATE_BASELINE = "degenerate_baseline"
    WITHIN_BASELINE = "within_baseline"
    CANDIDATE_ANOMALY = "candidate_anomaly"
    STATISTICAL_ANOMALY = "statistical_anomaly"
    COST_ADJUSTED_CANDIDATE = "cost_adjusted_candidate"


SIGNAL_STATUSES = frozenset({PointStatus.STATISTICAL_ANOMALY, PointStatus.COST_ADJUSTED_CANDIDATE})


@dataclass(frozen=True, slots=True)
class Assessment:
    point: PairPoint
    status: PointStatus
    baseline_n: int
    baseline_mean_bps: float | None
    baseline_std_bps: float | None
    deviation_bps: float | None
    z_score: float | None
    round_trip_cost_bps: float | None
    net_edge_bps: float | None
    notes: tuple[str, ...]

    @property
    def has_baseline(self) -> bool:
        return self.z_score is not None


def assess_series(
    series: PairSeries, *, z_threshold: float, window: int, costs: CostModel
) -> list[Assessment]:
    round_trip = costs.round_trip_bps()
    history: list[float] = []
    out = []
    for point in series.points:
        if not point.eligible:
            out.append(_bare(point, PointStatus.INELIGIBLE, len(history), point.ineligible_reasons))
            continue

        prior = history[-window:]
        history.append(point.spread_bps)
        if len(prior) < window:
            out.append(
                _bare(point, PointStatus.INSUFFICIENT_HISTORY, len(prior),
                      (f"{len(prior)} of {window} prior eligible observations",))
            )
            continue

        mean = statistics.fmean(prior)
        std = statistics.stdev(prior)
        deviation = point.spread_bps - mean
        if std == 0:
            out.append(
                Assessment(point, PointStatus.DEGENERATE_BASELINE, len(prior), mean, std, deviation,
                           None, round_trip, None, ("Baseline has zero variation",))
            )
            continue

        z = deviation / std
        status, notes, net = _classify(abs(deviation), abs(z), z_threshold, point.resolution_bps,
                                       round_trip, costs)
        out.append(Assessment(point, status, len(prior), mean, std, deviation, z, round_trip, net, notes))
    return out


def _classify(
    abs_dev: float,
    abs_z: float,
    z_threshold: float,
    resolution: float,
    round_trip: float | None,
    costs: CostModel,
) -> tuple[PointStatus, tuple[str, ...], float | None]:
    if abs_z < z_threshold:
        return PointStatus.WITHIN_BASELINE, (), None
    if abs_dev <= resolution:
        return (
            PointStatus.CANDIDATE_ANOMALY,
            (f"Deviation {abs_dev:.2f} bps is within tick resolution {resolution:.2f} bps",),
            None,
        )
    if round_trip is None:
        return (
            PointStatus.STATISTICAL_ANOMALY,
            ("Costs unknown: " + ", ".join(costs.unknown_components),),
            None,
        )
    net = abs_dev - round_trip
    if net <= 0:
        return (
            PointStatus.STATISTICAL_ANOMALY,
            (f"Deviation {abs_dev:.2f} bps does not exceed round-trip cost {round_trip:.2f} bps",),
            net,
        )
    return PointStatus.COST_ADJUSTED_CANDIDATE, (), net


def _bare(point: PairPoint, status: PointStatus, n: int, notes: tuple[str, ...]) -> Assessment:
    return Assessment(point, status, n, None, None, None, None, None, None, notes)
