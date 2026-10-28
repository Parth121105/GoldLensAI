"""Cross-contract relative value on each trade date.

For every date, each contract is normalized to INR per gram at 999 fineness using its
verified specification, then contracts of different symbols are paired with the nearest
matching expiry (at most ``max_expiry_gap_days`` apart). The gap is 10,000 * ln(A / B) in
basis points, shown next to both legs' volume, traded value and open interest.

What the numbers are not:
  * Close prices are MCX's published closing prices, not prices anyone could have traded at.
  * Volume is how much traded that day, not how much could trade now (market depth).
  * GOLDPETAL is priced Ex-Mumbai, the others Ex-Ahmedabad. That location basis is part of
    any GOLDPETAL gap and is not adjusted.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import combinations

from app.ingestion.models import Observation
from app.normalization import NormalizationError, PriceField, RawQuote, normalize
from app.research.pairs import BPS, SYMBOL_ORDER
from app.specs import SpecRegistry, SpecStatus, default_registry

DISCLAIMERS = (
    "Prices are MCX published closing prices. They are not guaranteed fill prices.",
    "Volume and open interest describe what traded that day. They are not market depth.",
    "GOLDPETAL is quoted Ex-Mumbai and the others Ex-Ahmedabad. Gaps involving GOLDPETAL "
    "include this location basis, which is not adjusted.",
)


@dataclass(frozen=True, slots=True)
class LiquidityFilter:
    """A contract is thin on a date if any threshold is missed. Thin contracts are never tradeable.

    Traded value is used because lots differ in size between contracts (1 g to 100 g).
    """

    min_volume_lots: int = 1
    min_traded_value_lakh: Decimal = Decimal("100")  # INR 1 crore
    min_open_interest_lots: int = 1

    def reasons(self, o: Observation) -> list[str]:
        out = []
        if o.volume is None or o.volume < self.min_volume_lots:
            out.append(f"volume {o.volume if o.volume is not None else 'not reported'} lots")
        if o.value is None or o.value < self.min_traded_value_lakh:
            shown = "not reported" if o.value is None else f"Rs {o.value} lakh"
            out.append(f"traded value {shown}, below Rs {self.min_traded_value_lakh} lakh")
        if o.open_interest is None or o.open_interest < self.min_open_interest_lots:
            out.append(f"open interest {o.open_interest if o.open_interest is not None else 'not reported'} lots")
        return out


@dataclass(frozen=True, slots=True)
class ContractQuote:
    contract_id: str
    symbol: str
    expiry: date
    close: Decimal
    quotation_base_g: Decimal
    price_basis_fineness: int
    price_quote_location: str
    inr_per_gram_999: Decimal | None
    tick_per_gram_999: Decimal | None
    spec_version_id: str | None
    spec_verified: bool
    volume: int | None
    traded_value_lakh: Decimal | None
    open_interest: int | None
    days_to_expiry: int
    thin_reasons: tuple[str, ...]
    error: str | None = None

    @property
    def thin(self) -> bool:
        return bool(self.thin_reasons)


@dataclass(frozen=True, slots=True)
class PairGap:
    symbol_a: str
    symbol_b: str
    contract_a: str
    contract_b: str
    expiry_gap_days: int
    gap_bps: float
    resolution_bps: float
    tradeable: bool
    not_tradeable_reasons: tuple[str, ...]
    location_basis: str | None


@dataclass(slots=True)
class DaySnapshot:
    trade_date: date
    contracts: list[ContractQuote] = field(default_factory=list)
    pairs: list[PairGap] = field(default_factory=list)


def relative_value(
    observations: list[Observation],
    *,
    max_expiry_gap_days: int = 10,
    expiry_buffer_days: int = 7,
    liquidity: LiquidityFilter | None = None,
    registry: SpecRegistry | None = None,
) -> list[DaySnapshot]:
    registry = registry or default_registry()
    liquidity = liquidity or LiquidityFilter()
    by_day: dict[date, list[Observation]] = defaultdict(list)
    for o in observations:
        if o.symbol in SYMBOL_ORDER:
            by_day[o.trade_date].append(o)

    days = []
    for trade_date in sorted(by_day):
        rows = sorted(by_day[trade_date], key=lambda o: (SYMBOL_ORDER.index(o.symbol), o.expiry))
        snap = DaySnapshot(trade_date, [_quote(o, liquidity, registry) for o in rows])
        snap.pairs = _pairs(snap.contracts, max_expiry_gap_days, expiry_buffer_days)
        days.append(snap)
    return days


def _quote(o: Observation, liquidity: LiquidityFilter, registry: SpecRegistry) -> ContractQuote:
    common = dict(
        contract_id=o.contract_id, symbol=o.symbol, expiry=o.expiry, close=o.close,
        volume=o.volume, traded_value_lakh=o.value, open_interest=o.open_interest,
        days_to_expiry=(o.expiry - o.trade_date).days, thin_reasons=tuple(liquidity.reasons(o)),
    )
    try:
        n = normalize(RawQuote(o.symbol, o.expiry, o.trade_date, o.close, PriceField.CLOSE), registry=registry)
    except NormalizationError as exc:
        spec = registry.resolve(o.symbol, o.expiry).spec
        return ContractQuote(
            **common, quotation_base_g=spec.quotation_base_g, price_basis_fineness=spec.price_basis_fineness,
            price_quote_location=spec.price_quote_location, inr_per_gram_999=None, tick_per_gram_999=None,
            spec_version_id=None,
            spec_verified=False, error=str(exc),
        )
    spec = registry.resolve(o.symbol, o.expiry).spec
    return ContractQuote(
        **common, quotation_base_g=spec.quotation_base_g, price_basis_fineness=spec.price_basis_fineness,
        price_quote_location=spec.price_quote_location, inr_per_gram_999=n.inr_per_gram_999,
        tick_per_gram_999=n.tick_inr_per_gram_999,
        spec_version_id=n.spec_version_id, spec_verified=n.spec_status is SpecStatus.VERIFIED,
    )


def _pairs(quotes: list[ContractQuote], max_gap: int, expiry_buffer: int) -> list[PairGap]:
    usable = [q for q in quotes if q.inr_per_gram_999 is not None]
    by_symbol: dict[str, list[ContractQuote]] = defaultdict(list)
    for q in usable:
        by_symbol[q.symbol].append(q)

    out = []
    for symbol_a, symbol_b in combinations(SYMBOL_ORDER, 2):
        for a in by_symbol.get(symbol_a, []):
            candidates = [(abs((a.expiry - b.expiry).days), b.expiry, b) for b in by_symbol.get(symbol_b, [])]
            candidates = [c for c in candidates if c[0] <= max_gap]
            if not candidates:
                continue
            gap_days, _, b = min(candidates, key=lambda c: (c[0], c[1]))
            pa, pb = float(a.inr_per_gram_999), float(b.inr_per_gram_999)
            resolution = BPS * (float(a.tick_per_gram_999) / pa + float(b.tick_per_gram_999) / pb)
            reasons = [f"{q.contract_id} is thin: {'; '.join(q.thin_reasons)}" for q in (a, b) if q.thin]
            reasons += [
                f"{q.contract_id} expires in {q.days_to_expiry} days, inside the {expiry_buffer}-day "
                "tender/delivery buffer"
                for q in (a, b) if q.days_to_expiry < expiry_buffer
            ]
            if a.price_quote_location != b.price_quote_location:
                basis = (f"{a.symbol} {a.price_quote_location} vs {b.symbol} {b.price_quote_location}: "
                         "location basis included, not adjusted")
            else:
                basis = None
            out.append(PairGap(
                symbol_a=a.symbol, symbol_b=b.symbol, contract_a=a.contract_id, contract_b=b.contract_id,
                expiry_gap_days=gap_days, gap_bps=BPS * math.log(pa / pb), resolution_bps=resolution,
                tradeable=not reasons, not_tradeable_reasons=tuple(reasons), location_basis=basis,
            ))
    return out

