"""Analyses of the session's imported rows.

GET /api/relative-value: per-day normalized prices and cross-contract gaps.
GET /api/term-structure: per-symbol futures curves and the split of day-to-day moves.

``kind`` says whether the rows are real ("user_uploaded") or synthetic; the store never
holds both at once, and synthetic rows are never saved to disk.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.analysis.relative_value import DISCLAIMERS, relative_value
from app.analysis.term_structure import term_structure
from app.api.deps import get_store
from app.assumptions import Assumptions, default_assumptions
from app.ingestion.models import Observation
from app.normalization import COMPARISON_BASIS
from app.research.engine import merge_observations
from app.specs import SpecStatus, default_registry
from app.store import SessionStore

router = APIRouter(tags=["analysis"])

_CENT = Decimal("0.01")


# --- Relative value ---------------------------------------------------------------------------


class ContractQuoteOut(BaseModel):
    contract_id: str
    symbol: str
    expiry: date
    close: str
    quotation_base_g: str
    price_basis_fineness: int
    price_quote_location: str
    inr_per_gram_999: str | None
    spec_version_id: str | None
    spec_verified: bool
    volume: int | None
    traded_value_lakh: str | None
    open_interest: int | None
    days_to_expiry: int
    thin: bool
    thin_reasons: list[str]
    error: str | None


class PairGapOut(BaseModel):
    symbol_a: str
    symbol_b: str
    contract_a: str
    contract_b: str
    expiry_gap_days: int
    gap_bps: float
    resolution_bps: float
    tradeable: bool
    not_tradeable_reasons: list[str]
    location_basis: str | None
    carry_bps: float | None = Field(description="Part of the gap explained by carry over the expiry difference")
    carry_adjusted_gap_bps: float | None


class DayOut(BaseModel):
    trade_date: date
    contracts: list[ContractQuoteOut]
    pairs: list[PairGapOut]


class AssumptionOut(BaseModel):
    key: str
    value: str
    unit: str
    why: str


class LiquidityOut(BaseModel):
    min_volume_lots: int
    min_traded_value_lakh: str
    min_open_interest_lots: int
    expiry_buffer_days: int
    max_expiry_gap_days: int
    official_tender_period: str = Field(description="From the MCX specifications of the contracts held")
    assumptions_file: str
    assumptions: list[AssumptionOut]


class RelativeValueResponse(BaseModel):
    kind: str
    synthetic: bool
    basis: str
    price_field: str
    disclaimers: list[str]
    liquidity: LiquidityOut
    days: list[DayOut]


def _liquidity_out(a: Assumptions, merged: list[Observation]) -> LiquidityOut:
    registry = default_registry()
    tender = sorted({
        r.spec.tender_period.trading_days
        for o in merged
        if (r := registry.resolve(o.symbol, o.expiry)).status is SpecStatus.VERIFIED and r.spec.tender_period
    })
    official = (
        f"Last {' or '.join(str(t) for t in tender)} trading days, including expiry day "
        "(MCX contract specifications)"
        if tender
        else "No verified specification for the contracts held"
    )
    return LiquidityOut(
        min_volume_lots=a.min_volume_lots,
        min_traded_value_lakh=str(a.min_traded_value_lakh),
        min_open_interest_lots=a.min_open_interest_lots,
        expiry_buffer_days=a.expiry_buffer_days,
        max_expiry_gap_days=a.max_expiry_gap_days,
        official_tender_period=official,
        assumptions_file="backend/config/assumptions.json",
        assumptions=[AssumptionOut(key=e.key, value=str(e.value), unit=e.unit, why=e.why) for e in a.entries.values()],
    )


def _opt(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


@router.get("/relative-value", response_model=RelativeValueResponse)
def relative_value_view(store: SessionStore = Depends(get_store)) -> RelativeValueResponse:
    merged, _ = merge_observations(store.snapshot())
    assumptions = default_assumptions()
    days = relative_value(merged, assumptions=assumptions)
    return RelativeValueResponse(
        kind=store.kind.value,
        synthetic=store.kind.value == "synthetic",
        basis=COMPARISON_BASIS,
        price_field="close",
        disclaimers=list(DISCLAIMERS),
        liquidity=_liquidity_out(assumptions, merged),
        days=[
            DayOut(
                trade_date=d.trade_date,
                contracts=[
                    ContractQuoteOut(
                        contract_id=q.contract_id, symbol=q.symbol, expiry=q.expiry, close=str(q.close),
                        quotation_base_g=str(q.quotation_base_g), price_basis_fineness=q.price_basis_fineness,
                        price_quote_location=q.price_quote_location,
                        inr_per_gram_999=None if q.inr_per_gram_999 is None else str(q.inr_per_gram_999.quantize(_CENT)),
                        spec_version_id=q.spec_version_id, spec_verified=q.spec_verified, volume=q.volume,
                        traded_value_lakh=None if q.traded_value_lakh is None else str(q.traded_value_lakh),
                        open_interest=q.open_interest, days_to_expiry=q.days_to_expiry, thin=q.thin,
                        thin_reasons=list(q.thin_reasons), error=q.error,
                    )
                    for q in d.contracts
                ],
                pairs=[
                    PairGapOut(
                        symbol_a=p.symbol_a, symbol_b=p.symbol_b, contract_a=p.contract_a,
                        contract_b=p.contract_b, expiry_gap_days=p.expiry_gap_days,
                        gap_bps=round(p.gap_bps, 2), resolution_bps=round(p.resolution_bps, 3),
                        tradeable=p.tradeable, not_tradeable_reasons=list(p.not_tradeable_reasons),
                        location_basis=p.location_basis, carry_bps=_opt(p.carry_bps),
                        carry_adjusted_gap_bps=_opt(p.carry_adjusted_gap_bps),
                    )
                    for p in d.pairs
                ],
            )
            for d in days
        ],
    )


# --- Term structure ---------------------------------------------------------------------------


class CurvePointOut(BaseModel):
    contract_id: str
    expiry: date
    days_to_expiry: int
    inr_per_gram_999: float
    fitted: float
    residual_bps: float
    thin: bool


class CurveOut(BaseModel):
    symbol: str
    trade_date: date
    slope_bps_per_day: float
    annualised_carry_pct: float
    raw_check_annualised_pct: float | None = Field(
        description="Carry from the nearest and farthest raw closing prices as quoted, no normalization or fit"
    )
    points: list[CurvePointOut]


class MoveSplitOut(BaseModel):
    contract_id: str
    symbol: str
    from_date: date
    to_date: date
    total_bps: float
    gold_move_bps: float
    roll_down_bps: float
    curve_change_bps: float
    residual_bps: float


class TermStructureResponse(BaseModel):
    kind: str
    synthetic: bool
    method: list[str]
    curves: list[CurveOut]
    splits: list[MoveSplitOut]


TERM_METHOD = [
    "Curve: ln(price per gram at 999) against days to expiry, fitted with a straight line per contract "
    "and day. The slope is the carry, shown in bps per day and annualised.",
    "Only contracts with a verified specification are fitted; thin contracts are included but marked.",
    "Move split between consecutive imported dates: gold move (median curve-level change across the four "
    "contracts) + roll-down (old slope x days elapsed) + curve change (this contract's level change "
    "beyond the gold move, plus the slope change) + residual (the contract moved against its own "
    "curve). The parts add up to the total exactly.",
    "Consecutive imported dates are not necessarily consecutive trading days.",
]


def _raw_carry(merged: list[Observation], symbol: str, trade_date: date) -> float | None:
    """Annualised carry from the nearest and farthest expiries' closing prices exactly as MCX quotes them."""
    import math

    rows = sorted((o for o in merged if o.symbol == symbol and o.trade_date == trade_date), key=lambda o: o.expiry)
    if len(rows) < 2 or rows[0].expiry == rows[-1].expiry:
        return None
    near, far = rows[0], rows[-1]
    per_day = math.log(float(far.close) / float(near.close)) / (far.expiry - near.expiry).days
    return round((math.exp(per_day * 365) - 1) * 100, 3)


@router.get("/term-structure", response_model=TermStructureResponse)
def term_structure_view(store: SessionStore = Depends(get_store)) -> TermStructureResponse:
    merged, _ = merge_observations(store.snapshot())
    ts = term_structure(relative_value(merged))
    return TermStructureResponse(
        kind=store.kind.value,
        synthetic=store.kind.value == "synthetic",
        method=TERM_METHOD,
        curves=[
            CurveOut(
                symbol=c.symbol, trade_date=c.trade_date, slope_bps_per_day=round(c.slope_bps_per_day, 4),
                annualised_carry_pct=round(c.annualised_carry_pct, 3),
                raw_check_annualised_pct=_raw_carry(merged, c.symbol, c.trade_date),
                points=[
                    CurvePointOut(
                        contract_id=p.contract_id, expiry=p.expiry, days_to_expiry=p.days_to_expiry,
                        inr_per_gram_999=round(p.inr_per_gram_999, 2), fitted=round(p.fitted, 2),
                        residual_bps=round(p.residual_bps, 2), thin=p.thin,
                    )
                    for p in c.points
                ],
            )
            for c in ts.curves
        ],
        splits=[
            MoveSplitOut(
                contract_id=s.contract_id, symbol=s.symbol, from_date=s.from_date, to_date=s.to_date,
                total_bps=round(s.total_bps, 2), gold_move_bps=round(s.gold_move_bps, 2),
                roll_down_bps=round(s.roll_down_bps, 2), curve_change_bps=round(s.curve_change_bps, 2),
                residual_bps=round(s.residual_bps, 2),
            )
            for s in ts.splits
        ],
    )


# --- Lifecycle --------------------------------------------------------------------------------


class CalendarEntryOut(BaseModel):
    symbol: str
    contract_id: str | None
    expiry_month: str
    launch_month: str
    listing_date: date
    tender_start: date
    expiry: date
    expiry_source: str
    tender_trading_days: int
    making_charge: str | None
    spec_version_id: str


class ContractStatusOut(BaseModel):
    contract_id: str
    trade_date: date
    days_to_expiry: int
    trading_days_to_expiry: int
    phase: str


class YearlyRowOut(BaseModel):
    year: int
    symbol: str
    lots_traded: int
    total_value_crore: float
    trading_days: int | None
    partial_year: bool


class LifecycleResponse(BaseModel):
    kind: str
    trade_dates: list[date]
    notes: list[str]
    expiry_buffer_days: int
    calendar: list[CalendarEntryOut]
    status: list[ContractStatusOut]
    yearly_source: str | None
    yearly_problem: str | None
    yearly: list[YearlyRowOut]


LIFECYCLE_NOTES = [
    "Listing, tender-period and expiry dates come from the verified MCX specifications. MCX holidays are "
    "not applied, so dates not in the imported data are nominal (weekends skipped only).",
    "Tender period: the last 3 or 5 trading days including expiry day, by specification version. Positions "
    "open at expiry go to compulsory delivery, with making charges for GOLDTEN, GOLDGUINEA and GOLDPETAL.",
    "Yearly volume is from the MCX gold data package table A2. The latest year runs only to the package date.",
]


@router.get("/lifecycle", response_model=LifecycleResponse)
def lifecycle_view(store: SessionStore = Depends(get_store)) -> LifecycleResponse:
    from app.analysis.lifecycle import contract_calendar, contract_status, yearly_volume

    merged, _ = merge_observations(store.snapshot())
    assumptions = default_assumptions()
    yearly = yearly_volume()
    last_year = max((r.year for r in yearly.rows), default=None)
    return LifecycleResponse(
        kind=store.kind.value,
        trade_dates=sorted({o.trade_date for o in merged}),
        notes=LIFECYCLE_NOTES,
        expiry_buffer_days=assumptions.expiry_buffer_days,
        calendar=[CalendarEntryOut(
            symbol=e.symbol, contract_id=e.contract_id, expiry_month=e.expiry_month, launch_month=e.launch_month,
            listing_date=e.listing_date, tender_start=e.tender_start, expiry=e.expiry, expiry_source=e.expiry_source,
            tender_trading_days=e.tender_trading_days, making_charge=e.making_charge, spec_version_id=e.spec_version_id,
        ) for e in contract_calendar(merged)],
        status=[
            ContractStatusOut(contract_id=s.contract_id, trade_date=s.trade_date, days_to_expiry=s.days_to_expiry,
                              trading_days_to_expiry=s.trading_days_to_expiry, phase=s.phase)
            for s in contract_status(merged, assumptions.expiry_buffer_days)
        ],
        yearly_source=yearly.source_file,
        yearly_problem=yearly.problem,
        yearly=[
            YearlyRowOut(year=r.year, symbol=r.symbol, lots_traded=r.lots_traded,
                         total_value_crore=round(float(r.total_value_lakh) / 100, 2), trading_days=r.trading_days,
                         partial_year=r.year == last_year)
            for r in yearly.rows
        ],
    )


# --- Real-data verdict ------------------------------------------------------------------------


class PairVerdictOut(BaseModel):
    symbol_pair: str
    eligible_dates: int
    needed: int
    verdict: str


class VerdictResponse(BaseModel):
    kind: str
    trade_dates: int
    needed_per_pair: int
    pairs: list[PairVerdictOut]
    statement: str


@router.get("/verdict", response_model=VerdictResponse)
def verdict_view(store: SessionStore = Depends(get_store)) -> VerdictResponse:
    """Eligible dates per symbol pair against the walk-forward minimum. No edge is claimed below it."""
    from itertools import combinations

    from app.research.config import ResearchConfig
    from app.research.pairs import SYMBOL_ORDER, build_pair_series
    from app.research.readiness import Minimums

    merged, _ = merge_observations(store.snapshot())
    config = ResearchConfig()
    needed = Minimums.from_config(config).eligible_dates_per_pair
    dates_by_pair: dict[str, set[date]] = {f"{a}/{b}": set() for a, b in combinations(SYMBOL_ORDER, 2)}
    for s in build_pair_series(merged, config):
        dates_by_pair[s.symbol_pair].update(p.trade_date for p in s.eligible_points)
    pairs = [
        PairVerdictOut(
            symbol_pair=k, eligible_dates=len(v), needed=needed,
            verdict="insufficient_data" if len(v) < needed else "run_walk_forward",
        )
        for k, v in dates_by_pair.items()
    ]
    if all(p.verdict == "insufficient_data" for p in pairs):
        statement = (
            f"No edge is claimed. Every pair has fewer than the {needed} eligible dates the walk-forward test "
            "needs, so the verdict on real data is Insufficient data. The problem statement accepts this: a "
            "rigorous demonstration that no persistent edge can yet be shown is a valid outcome."
        )
    else:
        statement = "At least one pair has enough eligible dates; run the walk-forward test for a verdict."
    return VerdictResponse(
        kind=store.kind.value, trade_dates=len({o.trade_date for o in merged}), needed_per_pair=needed,
        pairs=pairs, statement=statement,
    )
