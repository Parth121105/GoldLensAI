"""Specification-aware price normalization.

Comparison basis: INR per gram of gold at 999 fineness.

    per_gram_at_basis = quoted_price / quotation_base_g
    per_gram_999      = per_gram_at_basis * 999 / price_basis_fineness

The fineness step follows MCX's own convention: MCX converts 995 prices to a
999 basis with "* 999/995" (Due Date Rate of GOLDTEN, GOLDGUINEA, GOLDPETAL;
999 delivery premium in GOLDM). Value is treated as proportional to fine gold
content. Nothing else (location basis, taxes, making charges, expiry timing)
is adjusted here; those are reported as warnings.

See docs/methodology/normalization.md for worked examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.instruments import canonical_symbol
from app.specs import SpecRegistry, SpecStatus, UnknownInstrumentError, default_registry

COMPARISON_FINENESS = 999
COMPARISON_BASIS = "INR per gram, 999 fineness equivalent"
METHOD_VERSION = "norm-v1"


class PriceField(StrEnum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    SETTLEMENT = "settlement"
    PREVIOUS_CLOSE = "previous_close"


class NormalizationError(ValueError):
    pass


class UnverifiedSpecificationError(NormalizationError):
    pass


class IncompatibleUnitsError(NormalizationError):
    pass


class InvalidPriceError(NormalizationError):
    pass


@dataclass(frozen=True, slots=True)
class RawQuote:
    """An exchange quote exactly as published, in its own quotation units."""

    symbol: str
    expiry: date
    trade_date: date
    price: Decimal
    price_field: PriceField
    # If the data source states the quotation base, pass it so a mismatch with
    # the specification is caught instead of silently trusted.
    declared_quotation_base_g: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NormalizedQuote:
    raw: RawQuote
    spec_version_id: str
    spec_status: SpecStatus
    quotation_base_g: Decimal
    price_basis_fineness: int
    inr_per_gram_at_basis: Decimal
    inr_per_gram_999: Decimal
    tick_inr_per_gram_999: Decimal
    method_version: str
    formula: str
    warnings: tuple[str, ...]


def normalize(
    quote: RawQuote,
    *,
    registry: SpecRegistry | None = None,
    allow_unverified: bool = False,
) -> NormalizedQuote:
    if not isinstance(quote, RawQuote):
        # Guards against normalizing an already-normalized value twice.
        raise TypeError(f"normalize() expects RawQuote, got {type(quote).__name__}")

    registry = registry or default_registry()
    symbol = canonical_symbol(quote.symbol)
    try:
        resolution = registry.resolve(symbol, quote.expiry)
    except UnknownInstrumentError as exc:
        raise NormalizationError(str(exc)) from exc

    warnings: list[str] = []
    if resolution.status is not SpecStatus.VERIFIED:
        if not allow_unverified:
            raise UnverifiedSpecificationError(resolution.reason)
        warnings.append(f"UNVERIFIED SPECIFICATION ASSUMED: {resolution.reason}")

    spec = resolution.spec
    if not quote.price.is_finite() or quote.price <= 0:
        raise InvalidPriceError(f"Price must be a positive finite number, got {quote.price}")
    if (
        quote.declared_quotation_base_g is not None
        and quote.declared_quotation_base_g != spec.quotation_base_g
    ):
        raise IncompatibleUnitsError(
            f"{symbol} is quoted per {spec.quotation_base_g} g under {spec.version_id}, "
            f"but the input declares {quote.declared_quotation_base_g} g."
        )

    # Multiply before dividing so results that are exact stay exact.
    per_gram_at_basis = quote.price / spec.quotation_base_g
    per_gram_999 = per_gram_at_basis * COMPARISON_FINENESS / spec.price_basis_fineness
    tick_per_gram_999 = (
        spec.tick_size_inr * COMPARISON_FINENESS / (spec.quotation_base_g * spec.price_basis_fineness)
    )

    if quote.price_field is PriceField.SETTLEMENT:
        warnings.append("Settlement price: not an executable trade price.")
    if spec.price_quote_location != "Ex-Ahmedabad":
        warnings.append(
            f"Priced {spec.price_quote_location}; other gold contracts are Ex-Ahmedabad. "
            "Location basis is not adjusted."
        )

    return NormalizedQuote(
        raw=quote,
        spec_version_id=spec.version_id,
        spec_status=resolution.status,
        quotation_base_g=spec.quotation_base_g,
        price_basis_fineness=spec.price_basis_fineness,
        inr_per_gram_at_basis=per_gram_at_basis,
        inr_per_gram_999=per_gram_999,
        tick_inr_per_gram_999=tick_per_gram_999,
        method_version=METHOD_VERSION,
        formula=_formula(quote.price, spec.quotation_base_g, spec.price_basis_fineness),
        warnings=tuple(warnings),
    )


def _formula(price: Decimal, base_g: Decimal, fineness: int) -> str:
    step = f"{price} / {base_g} g"
    if fineness == COMPARISON_FINENESS:
        return f"{step} (already {COMPARISON_FINENESS} basis)"
    return f"{step} * {COMPARISON_FINENESS}/{fineness}"
