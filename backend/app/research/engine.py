"""Research run: merge imported files, build pair series, validate each symbol pair."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.ingestion.models import ImportResult, Observation
from app.research.config import ResearchConfig
from app.research.pairs import PairSeries, build_pair_series
from app.research.validation import PairValidation, validate_symbol_pair
from app.specs import SpecRegistry


class MixedDataError(ValueError):
    """Synthetic and real files must never be analysed together."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    name: str
    sha256: str
    synthetic: bool


@dataclass(frozen=True, slots=True)
class SeriesCoverage:
    pair_id: str
    symbol_pair: str
    comparison_type: str
    expiry_gap_days: int
    aligned_dates: int
    eligible_dates: int
    dates_missing_a: int
    dates_missing_b: int
    ineligible_reasons: dict[str, int]


@dataclass(slots=True)
class ResearchReport:
    generated_at: datetime
    config: ResearchConfig
    synthetic: bool
    sources: list[SourceFile]
    observations: int
    trade_date_range: tuple[date, date] | None
    cross_file_conflicts: list[str]
    coverage: list[SeriesCoverage] = field(default_factory=list)
    validations: list[PairValidation] = field(default_factory=list)
    series: list[PairSeries] = field(default_factory=list)


def run_research(
    imports: list[ImportResult],
    config: ResearchConfig | None = None,
    registry: SpecRegistry | None = None,
) -> ResearchReport:
    config = config or ResearchConfig()
    flags = {r.report.synthetic for r in imports}
    if len(flags) > 1:
        raise MixedDataError("Synthetic and real files cannot be combined in one research run.")

    observations, conflicts = merge_observations(imports)
    series = build_pair_series(observations, config, registry)
    dates = sorted({o.trade_date for o in observations})

    report = ResearchReport(
        generated_at=datetime.now(UTC),
        config=config,
        synthetic=flags == {True},
        sources=[SourceFile(r.report.source_file, r.report.source_sha256, r.report.synthetic)
                 for r in imports],
        observations=len(observations),
        trade_date_range=(dates[0], dates[-1]) if dates else None,
        cross_file_conflicts=conflicts,
        series=series,
        coverage=[_coverage(s) for s in series],
    )

    by_symbol_pair: dict[str, list[PairSeries]] = defaultdict(list)
    for s in series:
        by_symbol_pair[s.symbol_pair].append(s)
    report.validations = [
        validate_symbol_pair(group, config) for _, group in sorted(by_symbol_pair.items())
    ]
    return report


def merge_observations(imports: list[ImportResult]) -> tuple[list[Observation], list[str]]:
    """Combine files. Identical repeats are kept once; conflicting repeats are dropped."""
    groups: dict[tuple[date, str], list[Observation]] = defaultdict(list)
    for result in imports:
        for obs in result.observations:
            groups[(obs.trade_date, obs.contract_id)].append(obs)

    merged, conflicts = [], []
    for (trade_date, contract_id), group in sorted(groups.items()):
        if len({_values(o) for o in group}) == 1:
            merged.append(group[0])
        else:
            files = ", ".join(sorted({o.provenance.source_file for o in group}))
            conflicts.append(f"{contract_id} on {trade_date}: files disagree ({files}); dropped")
    return merged, conflicts


def _values(o: Observation) -> tuple:
    return (o.open, o.high, o.low, o.close, o.previous_close, o.settlement,
            o.volume, o.value, o.open_interest)


def _coverage(series: PairSeries) -> SeriesCoverage:
    reasons: dict[str, int] = defaultdict(int)
    for p in series.points:
        for code in p.ineligible_codes:
            reasons[code] += 1
    return SeriesCoverage(
        pair_id=series.pair_id,
        symbol_pair=series.symbol_pair,
        comparison_type=series.comparison_type.value,
        expiry_gap_days=series.expiry_gap_days,
        aligned_dates=len(series.points),
        eligible_dates=len(series.eligible_points),
        dates_missing_a=len(series.dates_missing_a),
        dates_missing_b=len(series.dates_missing_b),
        ineligible_reasons=dict(reasons),
    )
