"""Instrument identity: the supported symbols and how raw symbols map to them."""

import re

SUPPORTED_SYMBOLS = frozenset({"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"})

# MCX/TRD/456/2025 gives GOLDPETAL the contract description prefix "GOLDPTL".
SYMBOL_ALIASES = {"GOLDPTL": "GOLDPETAL"}

_STRIP = re.compile(r"[\s\"']+")


def canonical_symbol(raw: str) -> str:
    """Upper-case and remove padding, quotes and internal whitespace."""
    cleaned = _STRIP.sub("", raw).upper()
    return SYMBOL_ALIASES.get(cleaned, cleaned)


def is_supported(symbol: str) -> bool:
    return symbol in SUPPORTED_SYMBOLS
