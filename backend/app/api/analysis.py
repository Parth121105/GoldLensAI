"""GET /api/relative-value: per-day normalized prices and cross-contract gaps.

Results are computed from the session's imported rows. ``kind`` says whether those rows
are real ("user_uploaded") or synthetic; the store never holds both at once, and
synthetic rows are never saved to disk.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.analysis.relative_value import DISCLAIMERS, LiquidityFilter, relative_value
from app.api.deps import get_store
from app.normalization import COMPARISON_BASIS
from app.research.engine import merge_observations
from app.store import SessionStore

router = APIRouter(tags=["analysis"])


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


class DayOut(BaseModel):
    trade_date: date
    contracts: list[ContractQuoteOut]
    pairs: list[PairGapOut]


class LiquidityOut(BaseModel):
    min_volume_lots: int
    min_traded_value_lakh: str
    min_open_interest_lots: int
    expiry_buffer_days: int
    max_expiry_gap_days: int


class RelativeValueResponse(BaseModel):
    kind: str
    synthetic: bool
    basis: str
    price_field: str
    disclaimers: list[str]
    liquidity: LiquidityOut
    days: list[DayOut]


MAX_EXPIRY_GAP_DAYS = 10
EXPIRY_BUFFER_DAYS = 7
_CENT = Decimal("0.01")


@router.get("/relative-value", response_model=RelativeValueResponse)
def relative_value_view(store: SessionStore = Depends(get_store)) -> RelativeValueResponse:
    merged, _ = merge_observations(store.snapshot())
    liquidity = LiquidityFilter()
    days = relative_value(
        merged, max_expiry_gap_days=MAX_EXPIRY_GAP_DAYS, expiry_buffer_days=EXPIRY_BUFFER_DAYS,
        liquidity=liquidity,
    )
    return RelativeValueResponse(
        kind=store.kind.value,
        synthetic=store.kind.value == "synthetic",
        basis=COMPARISON_BASIS,
        price_field="close",
        disclaimers=list(DISCLAIMERS),
        liquidity=LiquidityOut(
            min_volume_lots=liquidity.min_volume_lots,
            min_traded_value_lakh=str(liquidity.min_traded_value_lakh),
            min_open_interest_lots=liquidity.min_open_interest_lots,
            expiry_buffer_days=EXPIRY_BUFFER_DAYS,
            max_expiry_gap_days=MAX_EXPIRY_GAP_DAYS,
        ),
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
                        location_basis=p.location_basis,
                    )
                    for p in d.pairs
                ],
            )
            for d in days
        ],
    )

