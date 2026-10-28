"""SYNTHETIC validation of the signal engine on controlled data. NOT MARKET DATA.

A deterministic synthetic history long enough for the walk-forward minimum is built in
memory (never stored, never mixed with imported data). Known mispricings are injected,
the unchanged research engine is run on it, and the result is scored against the
injections:

  * caught         share of injected mispricings in the final holdout on which a signal
                   fired in a pair containing the shocked contract, on the injection date
  * false alarms   share of clean holdout points (no active injection in either leg)
                   that fired a signal anyway
  * P&L            the engine's non-overlapping holdout trades, priced only from the two
                   contracts held: short the rich leg, long the cheap leg, equal grams,
                   closed ``horizon`` eligible observations later. Before and after the
                   round-trip costs in backend/config/assumptions.json.
  * gold move      the average log return of the two legs over each trade, i.e. what an
                   outright gold position would have made. Strategy P&L is the difference
                   of the two legs, so the gold move cancels out of it; both are reported.

Model of the synthetic market, per gram at 999 fineness:
    spot: geometric random walk, 0.9% daily volatility
    contract price = spot * exp(carry * days to expiry) * exp(symbol basis + noise)
    carry 12% a year; symbol basis fixed (GOLDPETAL +15 bps for its Mumbai location);
    noise 2 bps a day per contract. Quoted prices are rounded to the real tick.
Injected mispricing: one contract is pushed 10-30 bps away for a day, half of that the
next day, a quarter the day after, then gone.
"""

from __future__ import annotations

import calendar
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

from app.assumptions import cost_model
from app.ingestion.models import ImportReport, ImportResult, Observation, RowProvenance
from app.research.config import ResearchConfig
from app.research.engine import run_research
from app.research.pairs import SYMBOL_ORDER
from app.research.readiness import Minimums
from app.research.signals import SIGNAL_STATUSES, assess_series
from app.research.validation import _events, _in_window

SOURCE = "SYNTHETIC_validation_in_memory"
FIRST_DAY = date(2021, 1, 4)
LAST_DAY = date(2026, 6, 30)
SEED = 20261028
DAILY_VOL = 0.009
CARRY_PER_DAY = math.log(1.12) / 365
NOISE_BPS = 2.0
BASIS_BPS = {"GOLDM": 0.0, "GOLDTEN": 5.0, "GOLDGUINEA": -3.0, "GOLDPETAL": 15.0}
QUOTE = {"GOLDM": (10, 995), "GOLDTEN": (10, 999), "GOLDGUINEA": (8, 999), "GOLDPETAL": (1, 999)}
INJECT_EVERY_DAYS = 2  # on average
INJECT_BPS = (10.0, 30.0)
DECAY = (1.0, 0.5, 0.25)
LISTED_MONTHS = 3


@dataclass(frozen=True, slots=True)
class Injection:
    trade_date: date
    contract_id: str
    size_bps: float


@dataclass(frozen=True, slots=True)
class Trade:
    pair: str
    contract_a: str
    contract_b: str
    entry: date
    exit: date
    gross_bps: float
    net_bps: float
    gold_move_bps: float


@dataclass(slots=True)
class SyntheticValidation:
    trade_dates: int
    first_date: date
    last_date: date
    eligible_dates_needed: int
    eligible_dates_by_pair: dict[str, int]
    verdicts: dict[str, str]
    params_by_pair: dict[str, tuple[float, int] | None]
    holdout: tuple[date, date] | None
    injections_total: int
    injections_in_holdout: int
    caught: int
    clean_points: int
    false_alarms: int
    round_trip_cost_bps: float
    cost_labels: list[str]
    trades: list[Trade] = field(default_factory=list)

    @property
    def catch_rate(self) -> float | None:
        return self.caught / self.injections_in_holdout if self.injections_in_holdout else None

    @property
    def false_alarm_rate(self) -> float | None:
        return self.false_alarms / self.clean_points if self.clean_points else None


def _last_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _expiry(symbol: str, year: int, month: int) -> date:
    day = 5 if symbol == "GOLDM" else calendar.monthrange(year, month)[1]
    return _last_weekday(date(year, month, day))


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def generate(seed: int = SEED, inject: bool = True) -> tuple[list[Observation], list[Injection]]:
    rng = random.Random(seed)
    days = [FIRST_DAY + timedelta(n) for n in range((LAST_DAY - FIRST_DAY).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    spot, path = 5500.0, {}
    for d in days:
        spot *= math.exp(rng.gauss(0, DAILY_VOL))
        path[d] = spot

    expiries = {s: [_expiry(s, y, m) for y, m in _months(FIRST_DAY, LAST_DAY + timedelta(days=130))] for s in SYMBOL_ORDER}
    live = {
        d: {s: [e for e in expiries[s] if e > d and (e - d).days <= 31 * LISTED_MONTHS] for s in SYMBOL_ORDER}
        for d in days
    }

    # Injections: a contract at least two weeks from expiry, so it stays eligible.
    shocks: dict[tuple[date, str], float] = {}
    injections = []
    for i, d in enumerate(days):
        if not inject or rng.random() >= 1 / INJECT_EVERY_DAYS or i + len(DECAY) >= len(days):
            continue
        symbol = rng.choice(SYMBOL_ORDER)
        candidates = [e for e in live[d][symbol] if (e - d).days >= 14]
        if not candidates:
            continue
        expiry = rng.choice(candidates)
        contract = f"{symbol}-{expiry.isoformat()}"
        size = rng.uniform(*INJECT_BPS) * rng.choice((-1, 1))
        injections.append(Injection(d, contract, size))
        for k, w in enumerate(DECAY):
            key = (days[i + k], contract)
            shocks[key] = shocks.get(key, 0.0) + size * w

    sha = "0" * 64
    obs = []
    for d in days:
        for symbol in SYMBOL_ORDER:
            base, fineness = QUOTE[symbol]
            for e in live[d][symbol]:
                contract = f"{symbol}-{e.isoformat()}"
                log_dev = (BASIS_BPS[symbol] + rng.gauss(0, NOISE_BPS) + shocks.get((d, contract), 0.0)) / 1e4
                per_g = path[d] * math.exp(CARRY_PER_DAY * (e - d).days + log_dev)
                quote = Decimal(per_g * base * fineness / 999).quantize(Decimal(1), ROUND_HALF_UP)
                obs.append(Observation(
                    trade_date=d, symbol=symbol, raw_symbol=symbol, expiry=e, open=quote, high=quote, low=quote,
                    close=quote, previous_close=None, settlement=None, volume=1000,
                    value=Decimal(10000), open_interest=1000, traded=True,
                    provenance=RowProvenance(SOURCE, sha, len(obs) + 2, "synthetic-in-memory"),
                ))
    return obs, injections


def _active(injections: list[Injection]) -> set[tuple[date, str]]:
    """(date, contract) pairs where an injected deviation is still present."""
    return {(i.trade_date, i.contract_id) for i in injections}


def run(seed: int = SEED, inject: bool = True) -> SyntheticValidation:
    obs, injections = generate(seed, inject)
    report = ImportReport(
        source_file=SOURCE, source_sha256="0" * 64, size_bytes=0, imported_at=datetime.now(UTC),
        layout_id="synthetic-in-memory", layout_verified_against_real_file=False, units={}, date_order=None,
        synthetic=True, rows_read=len(obs), accepted=len(obs),
    )
    # Synthetic contract dates run outside the verified specification windows; the units of
    # the current versions are assumed. Real-data runs never set this.
    config = ResearchConfig(costs=cost_model(), allow_unverified_specs=True)
    research = run_research([ImportResult(obs, report)], config)
    dates = sorted({o.trade_date for o in obs})

    by_pair = {}
    for s in research.series:
        by_pair.setdefault(s.symbol_pair, []).append(s)

    holdouts = [v.holdout for v in research.validations if v.holdout]
    holdout = (max(h[0] for h in holdouts), min(h[1] for h in holdouts)) if holdouts else None

    # Days on which any trace of an injection remains, per contract (for "clean" points).
    trace: set[tuple[date, str]] = set()
    for i in injections:
        k = dates.index(i.trade_date)
        for j in range(len(DECAY)):
            if k + j < len(dates):
                trace.add((dates[k + j], i.contract_id))

    flagged: set[tuple[date, str]] = set()  # (date, contract) with a signal in some pair
    eligible_with: set[tuple[date, str]] = set()
    clean_points = false_alarms = 0
    trades: list[Trade] = []
    params_by_pair = {}
    for v in research.validations:
        params = v.final.params if v.final else None
        params_by_pair[v.symbol_pair] = params
        if params is None or holdout is None:
            continue
        series_list = by_pair[v.symbol_pair]
        for s in series_list:
            for a in assess_series(s, z_threshold=params[0], window=params[1], costs=config.costs):
                p = a.point
                if not p.eligible or not holdout[0] <= p.trade_date <= holdout[1] or not a.has_baseline:
                    continue
                legs = (p.leg_a.contract_id, p.leg_b.contract_id)
                for c in legs:
                    eligible_with.add((p.trade_date, c))
                signal = a.status in SIGNAL_STATUSES
                if signal:
                    for c in legs:
                        flagged.add((p.trade_date, c))
                if not any((p.trade_date, c) in trace for c in legs):
                    clean_points += 1
                    false_alarms += signal

        points = {(s.pair_id, p.trade_date): p for s in series_list for p in s.points}
        for e in _in_window(_events(series_list, params, config).signals, holdout):
            p0, p1 = points[(e.pair_id, e.trade_date)], points[(e.pair_id, e.outcome_date)]
            ra = math.log(float(p1.leg_a.per_gram_999) / float(p0.leg_a.per_gram_999))
            rb = math.log(float(p1.leg_b.per_gram_999) / float(p0.leg_b.per_gram_999))
            trades.append(Trade(
                pair=v.symbol_pair, contract_a=p0.leg_a.contract_id, contract_b=p0.leg_b.contract_id,
                entry=e.trade_date, exit=e.outcome_date, gross_bps=e.gross_bps,
                net_bps=e.net_bps if e.net_bps is not None else float("nan"),
                gold_move_bps=(ra + rb) / 2 * 1e4,
            ))

    in_holdout = [i for i in injections if holdout and holdout[0] <= i.trade_date <= holdout[1]
                  and (i.trade_date, i.contract_id) in eligible_with]
    caught = sum(1 for i in in_holdout if (i.trade_date, i.contract_id) in flagged)
    trades.sort(key=lambda t: (t.entry, t.pair))
    return SyntheticValidation(
        trade_dates=len(dates), first_date=dates[0], last_date=dates[-1],
        eligible_dates_needed=Minimums.from_config(config).eligible_dates_per_pair,
        eligible_dates_by_pair={v.symbol_pair: v.eligible_dates for v in research.validations},
        verdicts={v.symbol_pair: v.verdict.value for v in research.validations},
        params_by_pair=params_by_pair, holdout=holdout,
        injections_total=len(injections), injections_in_holdout=len(in_holdout), caught=caught,
        clean_points=clean_points, false_alarms=false_alarms,
        round_trip_cost_bps=config.costs.round_trip_bps() or 0.0,
        cost_labels=[c.label for c in config.costs.components],
        trades=trades,
    )


@cache
def cached_run(inject: bool = True) -> SyntheticValidation:
    """The injected run, or the control: the same synthetic market with no mispricings injected."""
    return run(inject=inject)


def summary(trades: list[Trade]) -> dict[str, float | int | None]:
    if not trades:
        return {"n": 0}
    gross = [t.gross_bps for t in trades]
    net = [t.net_bps for t in trades]
    gold = [t.gold_move_bps for t in trades]
    corr = statistics.correlation(gross, gold) if len(trades) > 2 and statistics.pstdev(gold) > 0 else None
    return {
        "n": len(trades),
        "total_gross_bps": sum(gross),
        "total_net_bps": sum(net),
        "mean_gross_bps": statistics.fmean(gross),
        "mean_net_bps": statistics.fmean(net),
        "hit_rate_net": sum(1 for x in net if x > 0) / len(net),
        "total_gold_move_bps": sum(gold),
        "corr_strategy_gold": corr,
    }
