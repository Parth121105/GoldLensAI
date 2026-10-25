"""Records produced by the Bhavcopy importer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RowProvenance:
    source_file: str
    source_sha256: str
    line_number: int
    layout_id: str


@dataclass(frozen=True, slots=True)
class Observation:
    """One end-of-day record for one contract (symbol + expiry), as published.

    Prices are raw exchange quotes in the contract's own quotation units.
    ``traded`` is None when the file does not report volume.
    """

    trade_date: date
    symbol: str
    raw_symbol: str
    expiry: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    previous_close: Decimal | None
    settlement: Decimal | None
    volume: int | None
    value: Decimal | None
    open_interest: int | None
    traded: bool | None
    provenance: RowProvenance
    warnings: tuple[str, ...] = ()

    @property
    def contract_id(self) -> str:
        return f"{self.symbol}-{self.expiry.isoformat()}"


@dataclass(frozen=True, slots=True)
class RejectedRow:
    line_number: int
    reasons: tuple[str, ...]
    raw: dict[str, str]


@dataclass(frozen=True, slots=True)
class ContractCoverage:
    contract_id: str
    symbol: str
    expiry: date
    first_trade_date: date
    last_trade_date: date
    observations: int
    traded_observations: int
    spec_status: str
    spec_version_id: str


@dataclass(slots=True)
class ImportReport:
    source_file: str
    source_sha256: str
    size_bytes: int
    imported_at: datetime
    layout_id: str
    layout_verified_against_real_file: bool
    units: dict[str, str]
    date_order: str | None
    synthetic: bool
    rows_read: int = 0
    accepted: int = 0
    exact_duplicates_dropped: int = 0
    rejected: list[RejectedRow] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    trade_dates: list[date] = field(default_factory=list)
    coverage: list[ContractCoverage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportResult:
    observations: list[Observation]
    report: ImportReport
