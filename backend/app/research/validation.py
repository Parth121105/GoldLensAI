"""Walk-forward validation of the spread-reversion hypothesis for one symbol pair.

Hypothesis: when a pair's normalized spread is a statistical anomaly against
its trailing baseline, it moves back toward that baseline over the next
``horizon`` eligible observations by more than ordinary (non-signal)
observations do, and by more than round-trip costs.

Leakage controls:
  * Baselines are causal (signals.py).
  * An event belongs to a window only if both its date and its outcome date lie
    inside the window, so outcomes never cross into a later window (purging).
  * Signal events in the same series do not overlap: a new event may start
    only after the previous event's outcome date.
  * Parameters are chosen on training windows only. The final holdout is
    evaluated once, with parameters chosen on the development period.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.research.config import ResearchConfig
from app.research.pairs import PairSeries
from app.research.signals import SIGNAL_STATUSES, assess_series

Params = tuple[float, int]  # (z_threshold, baseline_window)


@dataclass(frozen=True, slots=True)
class Event:
    pair_id: str
    trade_date: date
    outcome_date: date
    deviation_bps: float
    # Movement of the spread toward the baseline mean (positive = reverted).
    gross_bps: float
    net_bps: float | None


@dataclass(frozen=True, slots=True)
class OutcomeStats:
    n: int
    mean_gross_bps: float | None
    std_gross_bps: float | None
    t_stat_gross: float | None
    hit_rate: float | None
    mean_net_bps: float | None
    t_stat_net: float | None


@dataclass(frozen=True, slots=True)
class WindowResult:
    label: str
    train: tuple[date, date]
    test: tuple[date, date]
    params: Params | None
    train_signals: int
    signals: OutcomeStats
    controls: OutcomeStats
    status: str


class Verdict(StrEnum):
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_SUPPORTED = "not_supported"
    GROSS_ONLY_COSTS_UNKNOWN = "supported_before_costs_costs_unknown"
    NOT_SUPPORTED_AFTER_COSTS = "not_supported_after_costs"
    HISTORICALLY_VALIDATED = "historically_validated"


@dataclass(slots=True)
class PairValidation:
    symbol_pair: str
    series_ids: list[str]
    eligible_dates: int
    development: tuple[date, date] | None = None
    holdout: tuple[date, date] | None = None
    folds: list[WindowResult] = field(default_factory=list)
    final: WindowResult | None = None
    sensitivity: dict[str, OutcomeStats] = field(default_factory=dict)
    verdict: Verdict = Verdict.INSUFFICIENT_DATA
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _EventSet:
    signals: list[Event]
    controls: list[Event]


def validate_symbol_pair(series_list: list[PairSeries], config: ResearchConfig) -> PairValidation:
    symbol_pair = series_list[0].symbol_pair
    dates = sorted({p.trade_date for s in series_list for p in s.eligible_points})
    result = PairValidation(symbol_pair, [s.pair_id for s in series_list], len(dates))

    blocks_needed = config.n_folds + 1
    holdout_size = math.ceil(len(dates) * config.holdout_fraction)
    dev_dates = dates[: len(dates) - holdout_size]
    if len(dev_dates) < blocks_needed or holdout_size < 1:
        result.reasons.append(
            f"Only {len(dates)} eligible dates; cannot form {config.n_folds} folds plus a holdout."
        )
        return result

    hold_dates = dates[len(dev_dates):]
    result.development = (dev_dates[0], dev_dates[-1])
    result.holdout = (hold_dates[0], hold_dates[-1])

    events = {params: _events(series_list, params, config) for params in config.parameter_grid}

    blocks = _split(dev_dates, blocks_needed)
    for f in range(config.n_folds):
        train = (blocks[0][0], blocks[f][-1])
        test = (blocks[f + 1][0], blocks[f + 1][-1])
        result.folds.append(_evaluate(f"fold {f + 1}", train, test, events, config))

    result.final = _evaluate("final holdout", result.development, result.holdout, events, config)
    for params, ev in events.items():
        result.sensitivity[f"z={params[0]}, window={params[1]}"] = _stats(
            _in_window(ev.signals, result.holdout)
        )

    _decide(result, config)
    return result


def _events(series_list: list[PairSeries], params: Params, config: ResearchConfig) -> _EventSet:
    z_threshold, window = params
    signals, controls = [], []
    for series in series_list:
        assessed = [
            a for a in assess_series(series, z_threshold=z_threshold, window=window, costs=config.costs)
            if a.point.eligible
        ]
        next_allowed: date | None = None
        for i, a in enumerate(assessed):
            j = i + config.horizon
            if not a.has_baseline or j >= len(assessed) or not a.deviation_bps:
                continue
            direction = 1.0 if a.deviation_bps > 0 else -1.0
            outcome = assessed[j].point
            gross = direction * (a.point.spread_bps - outcome.spread_bps)
            event = Event(
                pair_id=series.pair_id,
                trade_date=a.point.trade_date,
                outcome_date=outcome.trade_date,
                deviation_bps=a.deviation_bps,
                gross_bps=gross,
                net_bps=None if a.round_trip_cost_bps is None else gross - a.round_trip_cost_bps,
            )
            if a.status in SIGNAL_STATUSES:
                if next_allowed is None or a.point.trade_date > next_allowed:
                    signals.append(event)
                    next_allowed = outcome.trade_date
            else:
                controls.append(event)
    return _EventSet(signals, controls)


def _evaluate(
    label: str,
    train: tuple[date, date],
    test: tuple[date, date],
    events: dict[Params, _EventSet],
    config: ResearchConfig,
) -> WindowResult:
    params, train_n = _select(events, train, config)
    if params is None:
        empty = _stats([])
        return WindowResult(label, train, test, None, 0, empty, empty,
                            f"no parameter set has {config.min_events} training signals")
    chosen = events[params]
    signals = _stats(_in_window(chosen.signals, test))
    controls = _stats(_in_window(chosen.controls, test))
    status = "ok" if signals.n >= config.min_events else f"only {signals.n} test signals"
    return WindowResult(label, train, test, params, train_n, signals, controls, status)


def _select(
    events: dict[Params, _EventSet], train: tuple[date, date], config: ResearchConfig
) -> tuple[Params | None, int]:
    """Highest mean gross outcome on training signals; grid order breaks ties."""
    best: tuple[float, Params, int] | None = None
    for params in config.parameter_grid:
        train_signals = _in_window(events[params].signals, train)
        if len(train_signals) < config.min_events:
            continue
        score = statistics.fmean(e.gross_bps for e in train_signals)
        if best is None or score > best[0]:
            best = (score, params, len(train_signals))
    return (best[1], best[2]) if best else (None, 0)


def _decide(result: PairValidation, config: ResearchConfig) -> None:
    final = result.final
    assert final is not None
    s, c = final.signals, final.controls

    if final.params is None or s.n < config.min_events:
        result.verdict = Verdict.INSUFFICIENT_DATA
        result.reasons.append(
            f"Holdout has {s.n} signal events; at least {config.min_events} are required."
        )
        return

    evaluable = [f for f in result.folds if f.params is not None and f.signals.n > 0]
    positive_folds = sum(1 for f in evaluable if (f.signals.mean_gross_bps or 0) > 0)
    assert s.mean_gross_bps is not None
    gross_supported = (
        s.mean_gross_bps > 0
        and (s.t_stat_gross or 0) >= config.min_t_stat
        and (c.mean_gross_bps is None or s.mean_gross_bps > c.mean_gross_bps)
        and positive_folds * 2 > len(evaluable)
    )
    result.reasons.append(
        f"Holdout: {s.n} signals, mean reversion {s.mean_gross_bps:.2f} bps "
        f"(t={s.t_stat_gross:.2f}), controls {_fmt(c.mean_gross_bps)} bps; "
        f"{positive_folds}/{len(evaluable)} folds positive."
    )
    if not gross_supported:
        result.verdict = Verdict.NOT_SUPPORTED
        return
    if s.mean_net_bps is None:
        result.verdict = Verdict.GROSS_ONLY_COSTS_UNKNOWN
        result.reasons.append("Costs unknown: " + ", ".join(config.costs.unknown_components))
        return
    if s.mean_net_bps <= 0 or (s.t_stat_net or 0) < config.min_t_stat:
        result.verdict = Verdict.NOT_SUPPORTED_AFTER_COSTS
        result.reasons.append(f"Mean net of costs {s.mean_net_bps:.2f} bps (t={_fmt(s.t_stat_net)}).")
        return
    result.verdict = Verdict.HISTORICALLY_VALIDATED
    result.reasons.append(
        f"Mean net of costs {s.mean_net_bps:.2f} bps (t={_fmt(s.t_stat_net)}). Historical result only; "
        "requires independent verification with executable quotes and depth."
    )


def _in_window(events: list[Event], window: tuple[date, date]) -> list[Event]:
    start, end = window
    return [e for e in events if start <= e.trade_date and e.outcome_date <= end]


def _stats(events: list[Event]) -> OutcomeStats:
    n = len(events)
    if n == 0:
        return OutcomeStats(0, None, None, None, None, None, None)
    gross = [e.gross_bps for e in events]
    mean = statistics.fmean(gross)
    std = statistics.stdev(gross) if n > 1 else None
    nets = [e.net_bps for e in events if e.net_bps is not None]
    mean_net = statistics.fmean(nets) if len(nets) == n else None
    std_net = statistics.stdev(nets) if mean_net is not None and n > 1 else None
    return OutcomeStats(
        n=n,
        mean_gross_bps=mean,
        std_gross_bps=std,
        t_stat_gross=_t(mean, std, n),
        hit_rate=sum(1 for g in gross if g > 0) / n,
        mean_net_bps=mean_net,
        t_stat_net=_t(mean_net, std_net, n),
    )


def _t(mean: float | None, std: float | None, n: int) -> float | None:
    if mean is None or std is None or std == 0:
        return None
    return mean / (std / math.sqrt(n))


def _split(items: list[date], k: int) -> list[list[date]]:
    size, extra = divmod(len(items), k)
    blocks, start = [], 0
    for i in range(k):
        end = start + size + (1 if i < extra else 0)
        blocks.append(items[start:end])
        start = end
    return blocks


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
