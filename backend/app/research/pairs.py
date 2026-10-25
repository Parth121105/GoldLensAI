"""Build relative-spread series for fixed pairs of contracts.

A pair series always compares the same two contracts (symbol + expiry). It is
never rolled or spliced into another expiry; when a contract expires its series
ends, and the next expiry pair starts a new series with no inherited history.

Dates are kept only when both legs have an observation. Nothing is filled in.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from itertools import combinations

from app.ingestion.models import Observation
from app.normalization import NormalizationError, RawQuote, normalize
from app.research.config import ResearchConfig
from app.specs import SpecRegistry, SpecStatus, default_registry

SYMBOL_ORDER = ("GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL")
BPS = 10_000


class ComparisonType(StrEnum):
    SAME_EXPIRY = "same_expiry"
    CROSS_EXPIRY = "cross_expiry"


@dataclass(frozen=True, slots=True)
class Leg:
    contract_id: str
    raw_price: Decimal
    per_gram_999: Decimal
    tick_per_gram_999: Decimal
    volume: int | None
    spec_version_id: str
    spec_status: SpecStatus
    source_file: str
    line_number: int


@dataclass(frozen=True, slots=True)
class PairPoint:
    trade_date: date
    leg_a: Leg
    leg_b: Leg
    # 10,000 * ln(A / B) on the normalized INR/g @999 basis. Positive: A is rich.
    spread_bps: float
    # Smallest spread change expressible given both tick sizes.
    resolution_bps: float
    days_to_nearer_expiry: int
    eligible: bool
    ineligible_reasons: tuple[str, ...]
    # Stable codes for the same reasons, for counting: unverified_spec,
    # volume_unknown, volume_below_min, lifecycle_buffer.
    ineligible_codes: tuple[str, ...]


@dataclass(slots=True)
class PairSeries:
    symbol_a: str
    symbol_b: str
    contract_a: str
    contract_b: str
    expiry_a: date
    expiry_b: date
    comparison_type: ComparisonType
    expiry_gap_days: int
    points: list[PairPoint] = field(default_factory=list)
    dates_missing_a: list[date] = field(default_factory=list)
    dates_missing_b: list[date] = field(default_factory=list)
    unusable: list[tuple[date, str]] = field(default_factory=list)

    @property
    def pair_id(self) -> str:
        return f"{self.contract_a}|{self.contract_b}"

    @property
    def symbol_pair(self) -> str:
        return f"{self.symbol_a}/{self.symbol_b}"

    @property
    def eligible_points(self) -> list[PairPoint]:
        return [p for p in self.points if p.eligible]


def build_pair_series(
    observations: list[Observation],
    config: ResearchConfig,
    registry: SpecRegistry | None = None,
) -> list[PairSeries]:
    registry = registry or default_registry()
    contracts: dict[str, dict[date, Observation]] = defaultdict(dict)
    for obs in observations:
        contracts[obs.contract_id][obs.trade_date] = obs

    by_symbol: dict[str, list[tuple[str, date]]] = defaultdict(list)
    for contract_id, rows in contracts.items():
        first = next(iter(rows.values()))
        by_symbol[first.symbol].append((contract_id, first.expiry))

    series_list = []
    for symbol_a, symbol_b in combinations(SYMBOL_ORDER, 2):
        for contract_a, expiry_a in sorted(by_symbol.get(symbol_a, []), key=lambda c: c[1]):
            for contract_b, expiry_b in sorted(by_symbol.get(symbol_b, []), key=lambda c: c[1]):
                gap = abs((expiry_a - expiry_b).days)
                if gap > config.max_expiry_gap_days:
                    continue
                series = PairSeries(
                    symbol_a=symbol_a,
                    symbol_b=symbol_b,
                    contract_a=contract_a,
                    contract_b=contract_b,
                    expiry_a=expiry_a,
                    expiry_b=expiry_b,
                    comparison_type=(
                        ComparisonType.SAME_EXPIRY if gap == 0 else ComparisonType.CROSS_EXPIRY
                    ),
                    expiry_gap_days=gap,
                )
                _fill_points(series, contracts[contract_a], contracts[contract_b], config, registry)
                series_list.append(series)
    return series_list


def _fill_points(
    series: PairSeries,
    rows_a: dict[date, Observation],
    rows_b: dict[date, Observation],
    config: ResearchConfig,
    registry: SpecRegistry,
) -> None:
    series.dates_missing_b = sorted(set(rows_a) - set(rows_b))
    series.dates_missing_a = sorted(set(rows_b) - set(rows_a))

    for trade_date in sorted(set(rows_a) & set(rows_b)):
        legs = []
        for obs in (rows_a[trade_date], rows_b[trade_date]):
            leg_or_error = _leg(obs, config, registry)
            if isinstance(leg_or_error, str):
                series.unusable.append((trade_date, leg_or_error))
                break
            legs.append(leg_or_error)
        if len(legs) != 2:
            continue
        leg_a, leg_b = legs

        a, b = float(leg_a.per_gram_999), float(leg_b.per_gram_999)
        spread = BPS * math.log(a / b)
        resolution = BPS * (float(leg_a.tick_per_gram_999) / a + float(leg_b.tick_per_gram_999) / b)
        days_left = min((series.expiry_a - trade_date).days, (series.expiry_b - trade_date).days)

        reasons: list[tuple[str, str]] = []
        for leg in (leg_a, leg_b):
            if leg.spec_status is not SpecStatus.VERIFIED and not config.allow_unverified_specs:
                reasons.append(("unverified_spec", f"{leg.contract_id}: unverified specification"))
            if leg.volume is None:
                reasons.append(
                    ("volume_unknown", f"{leg.contract_id}: volume not reported (liquidity unknown)")
                )
            elif leg.volume < config.min_volume:
                reasons.append((
                    "volume_below_min",
                    f"{leg.contract_id}: volume {leg.volume} below minimum {config.min_volume}",
                ))
        if days_left < config.lifecycle_buffer_days:
            reasons.append((
                "lifecycle_buffer",
                f"{days_left} days to nearer expiry, inside the {config.lifecycle_buffer_days}-day "
                "delivery/tender buffer",
            ))

        series.points.append(
            PairPoint(
                trade_date=trade_date,
                leg_a=leg_a,
                leg_b=leg_b,
                spread_bps=spread,
                resolution_bps=resolution,
                days_to_nearer_expiry=days_left,
                eligible=not reasons,
                ineligible_reasons=tuple(text for _, text in reasons),
                ineligible_codes=tuple(dict.fromkeys(code for code, _ in reasons)),
            )
        )


def _leg(obs: Observation, config: ResearchConfig, registry: SpecRegistry) -> Leg | str:
    price = getattr(obs, config.price_field.value)
    if price is None:
        return f"{obs.contract_id}: no {config.price_field.value} price"
    try:
        # Unverified specifications are normalized so the value can be shown,
        # but such points are marked ineligible above unless explicitly allowed.
        result = normalize(
            RawQuote(obs.symbol, obs.expiry, obs.trade_date, price, config.price_field),
            registry=registry,
            allow_unverified=True,
        )
    except NormalizationError as exc:
        return f"{obs.contract_id}: {exc}"
    return Leg(
        contract_id=obs.contract_id,
        raw_price=price,
        per_gram_999=result.inr_per_gram_999,
        tick_per_gram_999=result.tick_inr_per_gram_999,
        volume=obs.volume,
        spec_version_id=result.spec_version_id,
        spec_status=result.spec_status,
        source_file=obs.provenance.source_file,
        line_number=obs.provenance.line_number,
    )
