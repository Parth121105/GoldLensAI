"""Editable assumptions, read from backend/config/assumptions.json.

Every value in that file is a modelling choice, not an exchange rule. The path can be
overridden with GOLDLENS_ASSUMPTIONS. Each entry is {"value", "unit", "why"} so the page
can show what was assumed and why.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

DEFAULT_ASSUMPTIONS_FILE = Path(__file__).resolve().parents[1] / "config" / "assumptions.json"


@dataclass(frozen=True, slots=True)
class Assumption:
    key: str
    value: object
    unit: str
    why: str


@dataclass(frozen=True, slots=True)
class Assumptions:
    path: Path
    entries: dict[str, Assumption]

    def get(self, key: str) -> object:
        return self.entries[key].value

    @property
    def min_traded_value_lakh(self) -> Decimal:
        return Decimal(str(self.get("liquidity.min_traded_value_lakh")))

    @property
    def min_volume_lots(self) -> int:
        return int(self.get("liquidity.min_volume_lots"))

    @property
    def min_open_interest_lots(self) -> int:
        return int(self.get("liquidity.min_open_interest_lots"))

    @property
    def expiry_buffer_days(self) -> int:
        return int(self.get("lifecycle.expiry_buffer_days"))

    @property
    def max_expiry_gap_days(self) -> int:
        return int(self.get("pairing.max_expiry_gap_days"))


def load_assumptions(path: Path) -> Assumptions:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = {}
    for section, items in raw.items():
        if section.startswith("_"):
            continue
        for name, item in items.items():
            key = f"{section}.{name}"
            entries[key] = Assumption(key, item["value"], item["unit"], item["why"])
    out = Assumptions(path, entries)
    for prop in ("min_traded_value_lakh", "min_volume_lots", "min_open_interest_lots",
                 "expiry_buffer_days", "max_expiry_gap_days"):
        if getattr(out, prop) < 0:
            raise ValueError(f"{prop} in {path} must not be negative")
    return out


@cache
def default_assumptions() -> Assumptions:
    return load_assumptions(Path(os.environ.get("GOLDLENS_ASSUMPTIONS") or DEFAULT_ASSUMPTIONS_FILE))
