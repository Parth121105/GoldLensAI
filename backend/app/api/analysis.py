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
