"""Transaction cost assumptions.

Every component starts UNKNOWN. A component becomes known only when a value is
supplied, and each supplied value records its source (or is labelled a user
assumption). A missing cost is never treated as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

# A spread round trip trades two legs, each entered and exited: four leg-sides.
LEG_SIDES_PER_ROUND_TRIP = 4

COMPONENT_NAMES = (
    "brokerage",
    "exchange_transaction_charges",
    "statutory_taxes_and_levies",
    "slippage",
)


@dataclass(frozen=True, slots=True)
class CostComponent:
    name: str
    bps_per_leg_side: float | None = None
    source: str | None = None
    as_of: date | None = None

    def __post_init__(self) -> None:
        if self.bps_per_leg_side is not None and self.bps_per_leg_side < 0:
            raise ValueError(f"{self.name}: cost must not be negative")

    @property
    def known(self) -> bool:
        return self.bps_per_leg_side is not None

    @property
    def label(self) -> str:
        if not self.known:
            return f"{self.name}: unknown"
        origin = self.source or "user assumption, no source recorded"
        when = f", as of {self.as_of}" if self.as_of else ""
        return f"{self.name}: {self.bps_per_leg_side} bps per leg-side ({origin}{when})"


def _all_unknown() -> tuple[CostComponent, ...]:
    return tuple(CostComponent(name) for name in COMPONENT_NAMES)


@dataclass(frozen=True, slots=True)
class CostModel:
    components: tuple[CostComponent, ...] = field(default_factory=_all_unknown)

    def __post_init__(self) -> None:
        names = [c.name for c in self.components]
        if sorted(names) != sorted(COMPONENT_NAMES):
            raise ValueError(f"Cost model must define exactly {COMPONENT_NAMES}, got {names}")

    @property
    def unknown_components(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.components if not c.known)

    @property
    def fully_known(self) -> bool:
        return not self.unknown_components

    def round_trip_bps(self) -> float | None:
        """Total cost of entering and exiting both legs, or None if any part is unknown."""
        if not self.fully_known:
            return None
        per_side = sum(c.bps_per_leg_side for c in self.components if c.bps_per_leg_side is not None)
        return per_side * LEG_SIDES_PER_ROUND_TRIP

    def with_component(
        self, name: str, bps_per_leg_side: float, source: str | None = None, as_of: date | None = None
    ) -> CostModel:
        if name not in COMPONENT_NAMES:
            raise ValueError(f"Unknown cost component {name!r}")
        updated = tuple(
            replace(c, bps_per_leg_side=bps_per_leg_side, source=source, as_of=as_of)
            if c.name == name
            else c
            for c in self.components
        )
        return CostModel(updated)

    @classmethod
    def from_dict(cls, data: dict) -> CostModel:
        """Build from {"brokerage": {"bps_per_leg_side": 1.0, "source": "...", "as_of": "2026-10-01"}, ...}."""
        model = cls()
        for name, spec in data.items():
            as_of = date.fromisoformat(spec["as_of"]) if spec.get("as_of") else None
            model = model.with_component(name, float(spec["bps_per_leg_side"]), spec.get("source"), as_of)
        return model
