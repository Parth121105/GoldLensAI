"""Versioned contract specifications with source provenance.

Specifications live in ``mcx_gold_specs.json`` rather than in code so that every
value carries the circular it came from and the contract months it covers.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from functools import cache
from pathlib import Path

DEFAULT_SPEC_FILE = Path(__file__).with_name("mcx_gold_specs.json")

# A last trading day that falls on a weekend or holiday moves to the preceding
# working day. Four days covers a weekend plus two consecutive holidays.
EXPIRY_ROLLBACK_TOLERANCE_DAYS = 4


class SpecStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    title: str
    issuer: str
    issued_on: date
    retrieved_from: str
    retrieved_on: date
    retrieval_notes: str


@dataclass(frozen=True, slots=True)
class SourceCitation:
    source: Source
    location: str


@dataclass(frozen=True, slots=True)
class LastTradingDayRule:
    type: str  # "day_of_month" | "last_calendar_day"
    day: int | None = None

    def nominal_date(self, year: int, month: int) -> date:
        if self.type == "day_of_month":
            assert self.day is not None
            return date(year, month, self.day)
        if self.type == "last_calendar_day":
            return date(year, month, calendar.monthrange(year, month)[1])
        raise ValueError(f"Unknown last trading day rule: {self.type}")

    def is_consistent(self, expiry: date) -> bool:
        """True if ``expiry`` is the nominal day or a plausible holiday roll-back."""
        nominal = self.nominal_date(expiry.year, expiry.month)
        earliest = nominal - timedelta(days=EXPIRY_ROLLBACK_TOLERANCE_DAYS)
        return earliest <= expiry <= nominal


@dataclass(frozen=True, slots=True)
class TenderPeriod:
    trading_days: int  # staggered delivery tender period, including expiry day
    incremental_margin_pct: Decimal
    text: str


@dataclass(frozen=True, slots=True)
class MakingCharge:
    inr: Decimal
    per: str
    text: str


@dataclass(frozen=True, slots=True)
class LaunchMonth:
    launch: tuple[int, int]
    expiry: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ContractSpec:
    version_id: str
    symbol: str
    name: str
    verification: SpecStatus
    expiry_from: tuple[int, int]  # (year, month), inclusive
    expiry_to: tuple[int, int]
    trading_unit_g: Decimal
    quotation_base_g: Decimal
    price_basis_fineness: int  # parts per thousand, e.g. 995
    tick_size_inr: Decimal
    price_quote_location: str
    price_quote_text: str
    delivery_unit_g: Decimal
    quality_text: str
    price_basis_evidence: str
    last_trading_day_rule: LastTradingDayRule
    last_trading_day_text: str
    sources: tuple[SourceCitation, ...]
    notes: tuple[str, ...]
    contract_start_text: str = ""
    contract_start_day: int | None = None  # day of the launch month; holidays move it to the next working day
    tender_period: TenderPeriod | None = None
    delivery_settlement: str = ""
    making_charge: MakingCharge | None = None
    launch_calendar: tuple[LaunchMonth, ...] = ()

    def covers_expiry(self, expiry: date) -> bool:
        return self.expiry_from <= (expiry.year, expiry.month) <= self.expiry_to


@dataclass(frozen=True, slots=True)
class SpecResolution:
    """Outcome of looking up the specification for one contract.

    ``spec`` is always set when the symbol is known. When ``status`` is
    UNVERIFIED it is the closest verified version, offered only as an
    assumption the caller must explicitly accept.
    """

    symbol: str
    expiry: date
    status: SpecStatus
    spec: ContractSpec
    reason: str


class UnknownInstrumentError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class InstrumentListing:
    symbol: str
    first_trading_date: date
    evidence: str


class SpecRegistry:
    def __init__(
        self,
        specs: list[ContractSpec],
        sources: dict[str, Source],
        listings: dict[str, InstrumentListing],
        uncovered: dict[str, str] | None = None,
    ):
        self._specs = specs
        self.sources = sources
        self.listings = listings
        # Expiry ranges no source covers, per symbol, stated in plain words.
        self.uncovered = uncovered or {}

    @classmethod
    def from_file(cls, path: Path) -> SpecRegistry:
        raw = json.loads(path.read_text(encoding="utf-8"))
        sources = {
            source_id: Source(
                id=source_id,
                title=s["title"],
                issuer=s["issuer"],
                issued_on=date.fromisoformat(s["issued_on"]),
                retrieved_from=s["retrieved_from"],
                retrieved_on=date.fromisoformat(s["retrieved_on"]),
                retrieval_notes=s["retrieval_notes"],
            )
            for source_id, s in raw["sources"].items()
        }
        specs = [_parse_spec(s, sources) for s in raw["specifications"]]
        listings = {
            symbol: InstrumentListing(
                symbol=symbol,
                first_trading_date=date.fromisoformat(item["first_trading_date"]),
                evidence=item["evidence"],
            )
            for symbol, item in raw.get("instrument_listing", {}).items()
        }
        return cls(specs, sources, listings, raw.get("uncovered_expiries", {}))

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(s.symbol for s in self._specs)

    def versions(self, symbol: str) -> list[ContractSpec]:
        return [s for s in self._specs if s.symbol == symbol]

    def all_versions(self) -> list[ContractSpec]:
        return list(self._specs)

    def resolve(self, symbol: str, expiry: date) -> SpecResolution:
        versions = self.versions(symbol)
        if not versions:
            raise UnknownInstrumentError(f"No specification recorded for symbol {symbol!r}")

        for spec in versions:
            if spec.verification is SpecStatus.VERIFIED and spec.covers_expiry(expiry):
                return SpecResolution(
                    symbol=symbol,
                    expiry=expiry,
                    status=SpecStatus.VERIFIED,
                    spec=spec,
                    reason=f"Expiry {expiry:%Y-%m} is covered by {spec.version_id}.",
                )

        nearest = min(versions, key=lambda s: _month_distance(s, expiry))
        return SpecResolution(
            symbol=symbol,
            expiry=expiry,
            status=SpecStatus.UNVERIFIED,
            spec=nearest,
            reason=(
                f"No verified specification covers {symbol} expiring {expiry:%Y-%m}. "
                f"Nearest version {nearest.version_id} covers "
                f"{_fmt_month(nearest.expiry_from)} to {_fmt_month(nearest.expiry_to)}; "
                "specifications may differ outside that window."
            ),
        )


@cache
def default_registry() -> SpecRegistry:
    return SpecRegistry.from_file(DEFAULT_SPEC_FILE)


def _parse_spec(s: dict, sources: dict[str, Source]) -> ContractSpec:
    rule = s["last_trading_day_rule"]
    citations = []
    for c in s["sources"]:
        if c["id"] not in sources:
            raise ValueError(f"{s['version_id']} cites unknown source {c['id']!r}")
        citations.append(SourceCitation(source=sources[c["id"]], location=c["location"]))
    return ContractSpec(
        version_id=s["version_id"],
        symbol=s["symbol"],
        name=s["name"],
        verification=SpecStatus(s["verification"]),
        expiry_from=_parse_month(s["applies_to_expiry_months"]["from"]),
        expiry_to=_parse_month(s["applies_to_expiry_months"]["to"]),
        trading_unit_g=Decimal(s["trading_unit_g"]),
        quotation_base_g=Decimal(s["quotation_base_g"]),
        price_basis_fineness=int(s["price_basis_fineness"]),
        tick_size_inr=Decimal(s["tick_size_inr"]),
        price_quote_location=s["price_quote_location"],
        price_quote_text=s["price_quote_text"],
        delivery_unit_g=Decimal(s["delivery_unit_g"]),
        quality_text=s["quality_text"],
        price_basis_evidence=s["price_basis_evidence"],
        last_trading_day_rule=LastTradingDayRule(type=rule["type"], day=rule.get("day")),
        last_trading_day_text=s["last_trading_day_text"],
        sources=tuple(citations),
        notes=tuple(s.get("notes", [])),
        contract_start_text=s.get("contract_start_text", ""),
        contract_start_day=(s.get("contract_start_rule") or {}).get("day"),
        tender_period=_tender(s.get("tender_period")),
        delivery_settlement=s.get("delivery_settlement", ""),
        making_charge=_making(s.get("making_charge")),
        launch_calendar=tuple(
            LaunchMonth(_parse_month(m["launch"]), _parse_month(m["expiry"]))
            for m in s.get("launch_calendar", [])
        ),
    )


def _tender(t: dict | None) -> TenderPeriod | None:
    if not t:
        return None
    return TenderPeriod(int(t["trading_days"]), Decimal(t["incremental_margin_pct"]), t["text"])


def _making(m: dict | None) -> MakingCharge | None:
    if not m:
        return None
    return MakingCharge(Decimal(m["inr"]), m["per"], m["text"])


def _parse_month(value: str) -> tuple[int, int]:
    year, month = value.split("-")
    return int(year), int(month)


def _fmt_month(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def _month_distance(spec: ContractSpec, expiry: date) -> int:
    target = expiry.year * 12 + expiry.month
    lo = spec.expiry_from[0] * 12 + spec.expiry_from[1]
    hi = spec.expiry_to[0] * 12 + spec.expiry_to[1]
    if target < lo:
        return lo - target
    if target > hi:
        return target - hi
    return 0
