"""Model and research readiness: is there enough of the right data to test anything?

GoldLensAI has no machine-learning model. Its research engine is rule-based:
z-score flags on fixed contract-pair spreads, judged by walk-forward validation
with a final holdout. This module checks, before anything is run, whether the
loaded data can support that engine (or any future model under the same
chronological rules), and says exactly what is missing. It never trains, fills
in or manufactures data.

Thresholds come from the research configuration, not from guesses:
  * a baseline needs max(baseline_windows) + horizon + 1 aligned dates in a series;
  * the holdout needs min_events non-overlapping signals, and each signal spans
    horizon + 1 eligible dates, so it needs at least min_events * (horizon + 1)
    dates; each development fold needs the same for its test block. That gives a
    necessary (not sufficient) minimum of eligible dates per contract pair.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.ingestion.models import ImportResult
from app.ingestion.package import PackageImport, TableKind
from app.research.config import ResearchConfig
from app.research.engine import merge_observations
from app.research.pairs import build_pair_series
from app.research.validation import _split
from app.specs import SpecRegistry, default_registry
from app.specs.registry import SpecStatus

MODEL_STATEMENT = (
    "GoldLensAI contains no trained machine-learning model. Research is a rule-based signal "
    "engine (z-score flags on fixed contract-pair spreads) judged by walk-forward validation. "
    "Readiness below applies to that engine and to any future model under the same "
    "chronological train / test / holdout rules."
)


class Verdict(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"  # flags can be computed; no walk-forward verdict possible
    WALK_FORWARD_FEASIBLE = "WALK_FORWARD_FEASIBLE"  # necessary conditions met; not a promise of signals


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Minimums:
    dates_for_baseline: int
    dates_for_holdout: int
    eligible_dates_per_pair: int

    @staticmethod
    def from_config(config: ResearchConfig) -> Minimums:
        holdout = config.min_events * (config.horizon + 1)
        per_pair = math.ceil(max(
            holdout / config.holdout_fraction,
            (config.n_folds + 1) * holdout / (1 - config.holdout_fraction),
        ))
        return Minimums(max(config.baseline_windows) + config.horizon + 1, holdout, per_pair)


@dataclass(slots=True)
class Readiness:
    verdict: Verdict
    model: str
    checks: list[Check]
    minimums: Minimums
    summary: dict
    missing: list[str] = field(default_factory=list)
    split_plan: dict | None = None


def assess(
    imports: list[ImportResult],
    package: list[PackageImport] | None = None,
    config: ResearchConfig | None = None,
    registry: SpecRegistry | None = None,
) -> Readiness:
    config = config or ResearchConfig()
    registry = registry or default_registry()
    package = package or []
    minimums = Minimums.from_config(config)

    observations, _ = merge_observations(imports)
    dates = sorted({o.trade_date for o in observations})
    per_contract = Counter(o.contract_id for o in observations)
    expiries = sorted({(o.symbol, o.expiry) for o in observations})
    unverified = sorted({
        (o.symbol, o.expiry) for o in observations
        if registry.resolve(o.symbol, o.expiry).status is not SpecStatus.VERIFIED
    })

    series = build_pair_series(observations, config, registry) if observations else []
    eligible: dict[str, set[date]] = defaultdict(set)
    for s in series:
        eligible[s.symbol_pair].update(p.trade_date for p in s.eligible_points)
    best_pair, best_dates = max(((k, len(v)) for k, v in eligible.items()), key=lambda kv: kv[1], default=(None, 0))

    checks = [
        Check(
            "daily_history",
            "More than one trading date of futures data",
            len(dates) >= 2,
            f"{len(dates)} trading date(s)" + (f", {dates[0]} to {dates[-1]}" if dates else "")
            + f"; {len(expiries)} contract expiries; observations per contract "
            + (f"{min(per_contract.values())}-{max(per_contract.values())}" if per_contract else "0") + ".",
        ),
        Check(
            "verified_specifications",
            "Contracts with a verified specification, so prices can be normalized",
            len(expiries) > len(unverified),
            f"{len(expiries) - len(unverified)} of {len(expiries)} contracts verified"
            + (f"; unverified expiries {min(e for _, e in unverified)} to {max(e for _, e in unverified)}" if unverified else "") + ".",
        ),
        Check(
            "baseline",
            f"A contract pair with at least {minimums.dates_for_baseline} eligible dates (one baseline and outcome)",
            best_dates >= minimums.dates_for_baseline,
            f"Best pair {best_pair or '-'}: {best_dates} eligible dates.",
        ),
        Check(
            "walk_forward",
            f"A contract pair with at least {minimums.eligible_dates_per_pair} eligible dates "
            f"(3 folds + holdout, each able to hold {config.min_events} non-overlapping signals)",
            best_dates >= minimums.eligible_dates_per_pair,
            f"Best pair {best_pair or '-'}: {best_dates} of {minimums.eligible_dates_per_pair} needed.",
        ),
        Check(
            "gaps",
            "No unexplained gaps longer than a week between trading dates",
            len(dates) >= 2 and not _long_gaps(dates),
            _gap_detail(dates),
        ),
        Check(
            "no_rolling",
            "Contract expiries handled without splicing",
            True,
            "Each comparison is a fixed pair of contracts; series are never rolled or spliced, and dates "
            f"within {config.lifecycle_buffer_days} days of expiry are excluded.",
        ),
    ]
    kinds = Counter(p.table.kind for p in package)
    if kinds[TableKind.ANNUAL]:
        checks.append(Check(
            "annual_context", "Year-wise aggregates used only as context", True,
            f"{kinds[TableKind.ANNUAL]} annual table(s) loaded. They are never expanded into daily prices "
            "or used as targets.",
        ))
    if kinds[TableKind.OPTIONS]:
        checks.append(Check(
            "options_separate", "Option premiums kept out of futures series", True,
            f"{kinds[TableKind.OPTIONS]} options table(s) loaded and stored separately; research does not use them.",
        ))

    failed = {c.id for c in checks if not c.passed}
    if failed & {"daily_history", "verified_specifications", "baseline"}:
        verdict = Verdict.INSUFFICIENT_DATA
    elif "walk_forward" in failed:
        verdict = Verdict.EXPLORATORY_ONLY
    else:
        verdict = Verdict.WALK_FORWARD_FEASIBLE

    missing = []
    if len(dates) < 2 or "walk_forward" in failed:
        years = minimums.eligible_dates_per_pair / 250
        missing.append(
            f"Daily futures history: at least {minimums.eligible_dates_per_pair} eligible trading dates per "
            f"contract pair (about {years:.1f} years of daily MCX Bhavcopies after expiry-buffer and volume "
            f"filters). Loaded: {len(dates)} trading date(s)."
        )
    if unverified:
        missing.append(
            "Verified contract specifications for expiries "
            f"{min(e for _, e in unverified):%b %Y} to {max(e for _, e in unverified):%b %Y} (MCX launch-calendar circulars); "
            "until then those contracts are imported but not normalized."
        )
    if "gaps" in failed and len(dates) >= 2:
        missing.append("The missing trading dates listed under 'gaps', or confirmation that they were holidays.")

    plan = None
    if best_pair is not None and best_dates >= config.n_folds + 2:
        plan = split_plan(sorted(eligible[best_pair]), config)
    return Readiness(
        verdict=verdict,
        model=MODEL_STATEMENT,
        checks=checks,
        minimums=minimums,
        summary={
            "observations": len(observations),
            "trading_dates": len(dates),
            "first_date": dates[0].isoformat() if dates else None,
            "last_date": dates[-1].isoformat() if dates else None,
            "contracts": len(expiries),
            "unverified_contracts": len(unverified),
            "pairs": len(eligible),
            "best_pair": best_pair,
            "best_pair_eligible_dates": best_dates,
            "package_tables": {p.table.id: p.accepted for p in package},
        },
        missing=missing,
        split_plan=plan,
    )


def split_plan(dates: list[date], config: ResearchConfig) -> dict | None:
    """The chronological split validation would use: expanding folds, then a final holdout.

    Mirrors validation.validate_symbol_pair: the holdout is the last
    ceil(holdout_fraction * n) dates and is never used for selection.
    """
    dates = sorted(set(dates))
    holdout_size = math.ceil(len(dates) * config.holdout_fraction)
    dev = dates[: len(dates) - holdout_size]
    if len(dev) < config.n_folds + 1 or holdout_size < 1:
        return None
    blocks = _split(dev, config.n_folds + 1)
    return {
        "folds": [
            {"train": [blocks[0][0].isoformat(), blocks[f][-1].isoformat()],
             "test": [blocks[f + 1][0].isoformat(), blocks[f + 1][-1].isoformat()]}
            for f in range(config.n_folds)
        ],
        "development": [dev[0].isoformat(), dev[-1].isoformat()],
        "holdout": [dates[len(dev)].isoformat(), dates[-1].isoformat()],
    }


def _long_gaps(dates: list[date]) -> list[tuple[date, date]]:
    return [(a, b) for a, b in zip(dates, dates[1:]) if (b - a) > timedelta(days=7)]


def _gap_detail(dates: list[date]) -> str:
    if len(dates) < 2:
        return "Not assessable with fewer than two trading dates."
    gaps = _long_gaps(dates)
    if not gaps:
        return "No gap longer than 7 calendar days."
    shown = ", ".join(f"{a} to {b}" for a, b in gaps[:5])
    return f"{len(gaps)} gap(s) longer than 7 days: {shown}{'...' if len(gaps) > 5 else ''}."
