"""GET /api/validation/synthetic: the signal engine scored on controlled synthetic data.

SYNTHETIC. Built in memory on request, never stored, never mixed with imported data.
Two runs on the same synthetic market: one with known mispricings injected, and a
control with none, to show the engine finds an edge only where one exists.

The runs are deterministic but slow on a small server (minutes on Render's free CPU), so the
deploy build writes the response to PRECOMPUTED (``python -m app.cli precompute-synthetic``)
and the endpoint serves that file when it exists. Without it the runs are computed on request.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.research.synthetic_validation import (
    BASIS_BPS,
    CARRY_PER_DAY,
    DAILY_VOL,
    INJECT_BPS,
    NOISE_BPS,
    SyntheticValidation,
    cached_run,
    summary,
)

router = APIRouter(tags=["validation"])

# Build output, git-ignored. Regenerated on every deploy, so it always matches the deployed code.
PRECOMPUTED = Path(__file__).resolve().parents[2] / "data" / "cache" / "synthetic_validation.json"


class PairResultOut(BaseModel):
    symbol_pair: str
    eligible_dates: int
    verdict: str
    z_threshold: float | None
    baseline_window: int | None


class PnlOut(BaseModel):
    trades: int
    total_gross_bps: float | None
    total_net_bps: float | None
    mean_gross_bps: float | None
    mean_net_bps: float | None
    hit_rate_net: float | None
    total_gold_move_bps: float | None
    corr_strategy_gold: float | None


class CurvePointOut(BaseModel):
    exit: date
    cumulative_gross_bps: float
    cumulative_net_bps: float
    cumulative_gold_move_bps: float


class RunOut(BaseModel):
    label: str
    injected: bool
    trade_dates: int
    first_date: date
    last_date: date
    eligible_dates_needed: int
    holdout_from: date | None
    holdout_to: date | None
    pairs: list[PairResultOut]
    injections_total: int
    injections_in_holdout: int
    caught: int
    catch_rate: float | None
    clean_points: int
    false_alarms: int
    false_alarm_rate: float | None
    round_trip_cost_bps: float
    cost_labels: list[str]
    making_charges_paid: str
    pnl: PnlOut
    cumulative: list[CurvePointOut]


class SyntheticValidationResponse(BaseModel):
    synthetic: bool = True
    notice: str
    model: list[str]
    runs: list[RunOut]


NOTICE = (
    "SYNTHETIC DATA, NOT MARKET DATA. Generated in memory to test the signal engine against known answers. "
    "Nothing here says anything about real MCX prices."
)


def _run_out(r: SyntheticValidation, label: str, injected: bool) -> RunOut:
    s = summary(r.trades)
    cum, g, n, gold = [], 0.0, 0.0, 0.0
    for t in sorted(r.trades, key=lambda t: t.exit):
        g, n, gold = g + t.gross_bps, n + t.net_bps, gold + t.gold_move_bps
        cum.append(CurvePointOut(exit=t.exit, cumulative_gross_bps=round(g, 2), cumulative_net_bps=round(n, 2),
                                 cumulative_gold_move_bps=round(gold, 2)))

    def f(key: str, nd: int = 2) -> float | None:
        v = s.get(key)
        return None if v is None else round(float(v), nd)

    return RunOut(
        label=label, injected=injected, trade_dates=r.trade_dates, first_date=r.first_date, last_date=r.last_date,
        eligible_dates_needed=r.eligible_dates_needed,
        holdout_from=r.holdout[0] if r.holdout else None, holdout_to=r.holdout[1] if r.holdout else None,
        pairs=[
            PairResultOut(
                symbol_pair=p, eligible_dates=r.eligible_dates_by_pair[p], verdict=r.verdicts[p],
                z_threshold=(r.params_by_pair.get(p) or (None, None))[0],
                baseline_window=(r.params_by_pair.get(p) or (None, None))[1],
            )
            for p in sorted(r.verdicts)
        ],
        injections_total=r.injections_total, injections_in_holdout=r.injections_in_holdout, caught=r.caught,
        catch_rate=None if r.catch_rate is None else round(r.catch_rate, 4),
        clean_points=r.clean_points, false_alarms=r.false_alarms,
        false_alarm_rate=None if r.false_alarm_rate is None else round(r.false_alarm_rate, 5),
        round_trip_cost_bps=r.round_trip_cost_bps, cost_labels=r.cost_labels,
        making_charges_paid="None. Every trade is closed at least the pre-expiry buffer before expiry, "
                            "so no position reaches the tender period or delivery.",
        pnl=PnlOut(
            trades=int(s.get("n", 0)), total_gross_bps=f("total_gross_bps"), total_net_bps=f("total_net_bps"),
            mean_gross_bps=f("mean_gross_bps"), mean_net_bps=f("mean_net_bps"), hit_rate_net=f("hit_rate_net", 4),
            total_gold_move_bps=f("total_gold_move_bps"), corr_strategy_gold=f("corr_strategy_gold", 3),
        ),
        cumulative=cum,
    )


@router.get("/validation/synthetic", response_model=SyntheticValidationResponse)
async def synthetic_validation() -> SyntheticValidationResponse:
    if PRECOMPUTED.is_file():
        return SyntheticValidationResponse.model_validate_json(PRECOMPUTED.read_bytes())
    return await run_in_threadpool(build_response)


def write_precomputed(path: Path = PRECOMPUTED) -> Path:
    """Compute both runs and save the response for the endpoint to serve."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_response().model_dump_json(), encoding="utf-8")
    return path


def build_response() -> SyntheticValidationResponse:
    injected = cached_run(True)
    control = cached_run(False)
    return SyntheticValidationResponse(
        notice=NOTICE,
        model=[
            f"Gold price: random walk with {DAILY_VOL:.1%} daily volatility, about {injected.trade_dates} weekdays "
            f"({injected.first_date:%b %Y} to {injected.last_date:%b %Y}).",
            f"Carry {CARRY_PER_DAY * 365:.1%} a year (log), matching the real curves; each contract has its own "
            f"fixed basis ({', '.join(f'{k} {v:+.0f}' for k, v in BASIS_BPS.items())} bps) and {NOISE_BPS:.0f} bps "
            "of daily noise. Prices are rounded to the real tick sizes.",
            f"Injected mispricing: one contract pushed {INJECT_BPS[0]:.0f}-{INJECT_BPS[1]:.0f} bps away, half of "
            "that the next day, a quarter the day after, then gone. The engine is not told where they are.",
            "The research engine, walk-forward split, parameter grid and cost gating are the same code used on "
            "real data. Synthetic contracts fall outside the verified specification windows, so the current "
            "specification units are assumed for them; real-data runs never do this.",
        ],
        runs=[
            _run_out(injected, "With injected mispricings", True),
            _run_out(control, "Control: same market, nothing injected", False),
        ],
    )
