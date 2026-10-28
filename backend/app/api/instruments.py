"""GET /api/instruments: supported contracts and their specification versions."""

from fastapi import APIRouter

from app.api.schemas import (
    InstrumentOut,
    InstrumentsResponse,
    LaunchMonthOut,
    SourceCitationOut,
    SpecVersionOut,
)
from app.normalization import COMPARISON_BASIS, METHOD_VERSION
from app.research.pairs import SYMBOL_ORDER
from app.specs import ContractSpec, default_registry

router = APIRouter(tags=["instruments"])


@router.get("/instruments", response_model=InstrumentsResponse)
def instruments() -> InstrumentsResponse:
    registry = default_registry()
    out = []
    for symbol in SYMBOL_ORDER:
        versions = registry.versions(symbol)
        if not versions:
            continue
        listing = registry.listings.get(symbol)
        out.append(
            InstrumentOut(
                symbol=symbol,
                name=versions[0].name,
                first_trading_date=listing.first_trading_date if listing else None,
                listing_evidence=listing.evidence if listing else None,
                versions=[_version(v) for v in versions],
            )
        )
    return InstrumentsResponse(
        comparison_basis=COMPARISON_BASIS, method_version=METHOD_VERSION, instruments=out
    )


def _version(spec: ContractSpec) -> SpecVersionOut:
    return SpecVersionOut(
        version_id=spec.version_id,
        verification=spec.verification.value,
        expiry_from=_ym(spec.expiry_from),
        expiry_to=_ym(spec.expiry_to),
        trading_unit_g=str(spec.trading_unit_g),
        quotation_base_g=str(spec.quotation_base_g),
        price_basis_fineness=spec.price_basis_fineness,
        tick_size_inr=str(spec.tick_size_inr),
        price_quote_location=spec.price_quote_location,
        price_quote_text=spec.price_quote_text,
        delivery_unit_g=str(spec.delivery_unit_g),
        quality_text=spec.quality_text,
        price_basis_evidence=spec.price_basis_evidence,
        last_trading_day_text=spec.last_trading_day_text,
        contract_start_text=spec.contract_start_text,
        tender_period_trading_days=spec.tender_period.trading_days if spec.tender_period else None,
        tender_period_text=spec.tender_period.text if spec.tender_period else "",
        delivery_settlement=spec.delivery_settlement,
        making_charge_text=spec.making_charge.text if spec.making_charge else None,
        launch_calendar=[
            LaunchMonthOut(launch=_ym(m.launch), expiry=_ym(m.expiry)) for m in spec.launch_calendar
        ],
        sources=[
            SourceCitationOut(
                id=c.source.id,
                title=c.source.title,
                issuer=c.source.issuer,
                issued_on=c.source.issued_on,
                location=c.location,
                retrieved_from=c.source.retrieved_from,
                retrieved_on=c.source.retrieved_on,
                retrieval_notes=c.source.retrieval_notes,
            )
            for c in spec.sources
        ],
        notes=list(spec.notes),
    )


def _ym(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"
