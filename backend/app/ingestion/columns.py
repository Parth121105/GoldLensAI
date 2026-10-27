"""Supported Bhavcopy column layouts.

The legacy layout's columns were checked on 26 Oct 2026 against one MCX
date-wise download supplied by the user (BhavCopyDateWise_23102026.xls, an HTML
table, SHA-256 4a931460...; 16,737 rows, 15 columns). The UDiFF layout has not
been checked against a real file; its column names come from secondary sources.
See docs/data-import.md. Header matching ignores case, spaces and punctuation,
so "Volume (Lots)" and "VOLUME_LOTS" both match "volumelots".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Field(StrEnum):
    TRADE_DATE = "trade_date"
    SYMBOL = "symbol"
    EXPIRY = "expiry"
    INSTRUMENT = "instrument"
    OPTION_TYPE = "option_type"
    STRIKE = "strike"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    PREVIOUS_CLOSE = "previous_close"
    SETTLEMENT = "settlement"
    VOLUME = "volume"
    VALUE = "value"
    OPEN_INTEREST = "open_interest"


REQUIRED_FIELDS = frozenset({Field.TRADE_DATE, Field.SYMBOL, Field.EXPIRY, Field.CLOSE})


@dataclass(frozen=True, slots=True)
class Layout:
    id: str
    description: str
    aliases: dict[Field, tuple[str, ...]]
    units: dict[str, str]
    verified_against_real_file: bool = False


LEGACY = Layout(
    id="mcx-bhavcopy-legacy",
    description="MCX Bhavcopy CSV (Date, Instrument Name, Symbol, Expiry Date, ...)",
    aliases={
        Field.TRADE_DATE: ("date", "tradedate"),
        Field.SYMBOL: ("symbol",),
        Field.EXPIRY: ("expirydate", "expiry"),
        Field.INSTRUMENT: ("instrumentname", "instrument"),
        Field.OPTION_TYPE: ("optiontype",),
        Field.STRIKE: ("strikeprice", "strike"),
        Field.OPEN: ("open",),
        Field.HIGH: ("high",),
        Field.LOW: ("low",),
        Field.CLOSE: ("close",),
        Field.PREVIOUS_CLOSE: ("previousclose", "prevclose"),
        Field.VOLUME: ("volumelots",),
        Field.VALUE: ("valuelacs", "valuelakhs", "valuelakh", "valueinlacs", "valueinlakhs"),
        Field.OPEN_INTEREST: ("openinterestlots", "openinterest"),
    },
    units={"volume": "lots", "value": "INR lakhs", "open_interest": "lots"},
    verified_against_real_file=True,
)

UDIFF = Layout(
    id="udiff-bhavcopy",
    description="Unified Distilled File Format (UDiFF) Bhavcopy (TradDt, TckrSymb, XpryDt, ...)",
    aliases={
        Field.TRADE_DATE: ("traddt",),
        Field.SYMBOL: ("tckrsymb",),
        Field.EXPIRY: ("xprydt",),
        Field.INSTRUMENT: ("fininstrmtp",),
        Field.OPTION_TYPE: ("optntp",),
        Field.STRIKE: ("strkpric",),
        Field.OPEN: ("opnpric",),
        Field.HIGH: ("hghpric",),
        Field.LOW: ("lwpric",),
        Field.CLOSE: ("clspric",),
        Field.PREVIOUS_CLOSE: ("prvsclsgpric",),
        Field.SETTLEMENT: ("sttlmpric",),
        Field.VOLUME: ("ttltradgvol",),
        Field.VALUE: ("ttltrfval",),
        Field.OPEN_INTEREST: ("opnintrst",),
    },
    units={
        "volume": "as reported in TtlTradgVol (unit unverified)",
        "value": "as reported in TtlTrfVal (unit unverified)",
        "open_interest": "as reported in OpnIntrst (unit unverified)",
    },
)

LAYOUTS = (LEGACY, UDIFF)

_NON_ALNUM = re.compile(r"[^a-z0-9]")


class MissingColumnsError(ValueError):
    pass


def normalize_header(header: str) -> str:
    return _NON_ALNUM.sub("", header.lstrip("﻿").lower())


def detect_layout(headers: list[str]) -> tuple[Layout, dict[Field, int]]:
    """Pick the layout whose required columns are all present, preferring more matches."""
    keys = [normalize_header(h) for h in headers]
    best: tuple[Layout, dict[Field, int], set[Field]] | None = None
    for layout in LAYOUTS:
        mapping: dict[Field, int] = {}
        for field, aliases in layout.aliases.items():
            for alias in aliases:
                if alias in keys:
                    mapping[field] = keys.index(alias)
                    break
        missing = set(REQUIRED_FIELDS) - mapping.keys()
        if best is None or (len(missing), -len(mapping)) < (len(best[2]), -len(best[1])):
            best = (layout, mapping, missing)

    assert best is not None
    layout, mapping, missing = best
    if missing:
        names = ", ".join(sorted(layout.aliases[f][0] for f in missing))
        seen = repr(headers)
        if len(seen) > 300:
            seen = seen[:300] + "..."
        raise MissingColumnsError(
            f"Required columns not found (closest layout: {layout.id}; missing: {names}). "
            f"Headers seen: {seen}"
        )
    return layout, mapping
