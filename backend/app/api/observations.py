"""GET /api/observations: imported observations with raw and normalized prices.

Normalization is done here by the existing engine; the frontend never converts
prices itself. Observations whose specification is unverified are returned
with ``normalized = null`` and the reason, never with an assumed value.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_store
from app.api.schemas import NormalizedOut, ObservationOut, ObservationsResponse
from app.ingestion.models import Observation
from app.normalization import COMPARISON_BASIS, NormalizationError, PriceField, RawQuote, normalize
from app.research.engine import merge_observations
from app.store import SessionStore

router = APIRouter(tags=["observations"])

MAX_OBSERVATIONS = 20_000


@router.get("/observations", response_model=ObservationsResponse)
def observations(
    symbol: list[str] | None = Query(default=None, description="Repeat to select several symbols"),
    expiry: list[date] | None = Query(default=None, description="Repeat to select several expiries"),
    price_field: PriceField = Query(default=PriceField.CLOSE),
    store: SessionStore = Depends(get_store),
) -> ObservationsResponse:
    merged, _ = merge_observations(store.snapshot())
    trade_dates = sorted({o.trade_date for o in merged})
    wanted_symbols = {s.strip().upper() for s in symbol} if symbol else None
    wanted_expiries = set(expiry) if expiry else None
    selected = [
        o for o in merged
        if (wanted_symbols is None or o.symbol in wanted_symbols)
        and (wanted_expiries is None or o.expiry in wanted_expiries)
    ][:MAX_OBSERVATIONS]
    return ObservationsResponse(
        kind=store.kind.value,
        price_field=price_field.value,
        trade_dates=trade_dates,
        observations=[_out(o, price_field) for o in selected],
    )


def _out(o: Observation, price_field: PriceField) -> ObservationOut:
    normalized, error = None, None
    price = getattr(o, price_field.value)
    if price is None:
        error = f"No {price_field.value} price in the source row."
    else:
        try:
            n = normalize(RawQuote(o.symbol, o.expiry, o.trade_date, price, price_field))
            normalized = NormalizedOut(
                inr_per_gram_999=str(n.inr_per_gram_999),
                basis=COMPARISON_BASIS,
                quotation_base_g=str(n.quotation_base_g),
                price_basis_fineness=n.price_basis_fineness,
                spec_version_id=n.spec_version_id,
                spec_status=n.spec_status.value,
                formula=n.formula,
                warnings=list(n.warnings),
            )
        except NormalizationError as exc:
            error = str(exc)
    return ObservationOut(
        trade_date=o.trade_date,
        contract_id=o.contract_id,
        symbol=o.symbol,
        expiry=o.expiry,
        open=_s(o.open),
        high=_s(o.high),
        low=_s(o.low),
        close=str(o.close),
        previous_close=_s(o.previous_close),
        settlement=_s(o.settlement),
        volume=o.volume,
        open_interest=o.open_interest,
        traded=o.traded,
        warnings=list(o.warnings),
        source_file=o.provenance.source_file,
        source_sha256=o.provenance.source_sha256,
        line_number=o.provenance.line_number,
        normalized=normalized,
        normalization_error=error,
    )


def _s(value: object) -> str | None:
    return None if value is None else str(value)
