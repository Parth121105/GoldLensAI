"""Contract lifecycle: listing, tender period and expiry, plus yearly liquidity.

Dates come from the verified specifications (start-day rule, last-trading-day rule,
tender period length and launch calendar). MCX trading holidays are not known to Gold
Lens, so calendar dates are *nominal*: weekends are skipped, holidays are not. For
contracts present in the imported data, the expiry date published by MCX is used.

The tender period is the last N trading days including the expiry day (N = 3 or 5,
by specification version). Its start is counted back over weekdays only.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.ingestion.models import Observation
from app.ingestion.package import PackageImportError, import_package_table
from app.research.pairs import SYMBOL_ORDER
from app.specs import ContractSpec, SpecRegistry, SpecStatus, default_registry

YEARLY_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "yearly"


def _weekday_on_or_after(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _weekday_on_or_before(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def tender_start(expiry: date, trading_days: int) -> date:
    """First day of a tender period of ``trading_days`` weekdays ending on (and including) ``expiry``."""
    d, left = expiry, trading_days - 1
    while left > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def weekdays_until(start: date, end: date) -> int:
    """Weekdays after ``start`` up to and including ``end``."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    symbol: str
    contract_id: str | None  # set when the contract appears in the imported data
    expiry_month: str
    launch_month: str
    listing_date: date
    tender_start: date
    expiry: date
    expiry_source: str  # "imported data" or "nominal (rule, weekends only)"
    tender_trading_days: int
    making_charge: str | None
    spec_version_id: str


@dataclass(frozen=True, slots=True)
class ContractStatus:
    contract_id: str
    trade_date: date
    days_to_expiry: int
    trading_days_to_expiry: int  # weekdays, holidays not applied
    phase: str  # "trading" | "near_expiry" | "tender_period"


def _nominal_expiry(spec: ContractSpec, year: int, month: int) -> date:
    return _weekday_on_or_before(spec.last_trading_day_rule.nominal_date(year, month))


def _listing(spec: ContractSpec, launch: tuple[int, int]) -> date:
    day = spec.contract_start_day or 1
    day = min(day, calendar.monthrange(*launch)[1])
    return _weekday_on_or_after(date(launch[0], launch[1], day))


def contract_calendar(
    observations: list[Observation],
    *,
    registry: SpecRegistry | None = None,
) -> list[CalendarEntry]:
    """Every verified launch-calendar entry still trading on the first imported date (or all, without data)."""
    registry = registry or default_registry()
    held = {(o.symbol, o.expiry.year, o.expiry.month): o for o in observations}
    first = min((o.trade_date for o in observations), default=date.min)

    out = []
    for symbol in SYMBOL_ORDER:
        for spec in registry.versions(symbol):
            if spec.verification is not SpecStatus.VERIFIED or not spec.tender_period:
                continue
            for m in spec.launch_calendar:
                if not spec.expiry_from <= m.expiry <= spec.expiry_to:
                    continue
                obs = held.get((symbol, *m.expiry))
                expiry = obs.expiry if obs else _nominal_expiry(spec, *m.expiry)
                if expiry < first:
                    continue
                out.append(CalendarEntry(
                    symbol=symbol,
                    contract_id=obs.contract_id if obs else None,
                    expiry_month=f"{m.expiry[0]:04d}-{m.expiry[1]:02d}",
                    launch_month=f"{m.launch[0]:04d}-{m.launch[1]:02d}",
                    listing_date=_listing(spec, m.launch),
                    tender_start=tender_start(expiry, spec.tender_period.trading_days),
                    expiry=expiry,
                    expiry_source="imported data" if obs else "nominal (rule, weekends only)",
                    tender_trading_days=spec.tender_period.trading_days,
                    making_charge=spec.making_charge.text if spec.making_charge else None,
                    spec_version_id=spec.version_id,
                ))
    out.sort(key=lambda e: (SYMBOL_ORDER.index(e.symbol), e.expiry))
    return out


def contract_status(
    observations: list[Observation], expiry_buffer_days: int, registry: SpecRegistry | None = None
) -> list[ContractStatus]:
    registry = registry or default_registry()
    out = []
    for o in sorted(observations, key=lambda o: (o.trade_date, SYMBOL_ORDER.index(o.symbol), o.expiry)):
        if o.symbol not in SYMBOL_ORDER:
            continue
        r = registry.resolve(o.symbol, o.expiry)
        days = (o.expiry - o.trade_date).days
        tdays = weekdays_until(o.trade_date, o.expiry)
        tender = r.spec.tender_period.trading_days if r.status is SpecStatus.VERIFIED and r.spec.tender_period else None
        if tender is not None and o.trade_date >= tender_start(o.expiry, tender):
            phase = "tender_period"
        elif days < expiry_buffer_days:
            phase = "near_expiry"
        else:
            phase = "trading"
        out.append(ContractStatus(o.contract_id, o.trade_date, days, tdays, phase))
    return out


@dataclass(frozen=True, slots=True)
class YearlyRow:
    year: int
    symbol: str
    lots_traded: int
    total_value_lakh: Decimal
    trading_days: int | None


@dataclass(frozen=True, slots=True)
class YearlyVolume:
    source_file: str | None
    rows: list[YearlyRow]
    problem: str | None


def yearly_volume(directory: Path = YEARLY_DIR) -> YearlyVolume:
    """Year-wise volume per contract from the A2 package table in ``directory``, validated on load."""
    files = sorted(directory.glob("A2_*.csv")) if directory.is_dir() else []
    if not files:
        return YearlyVolume(None, [], f"No A2 year-wise file in {directory.name}/. Add A2_yearwise_all_gold_contracts.csv.")
    path = files[-1]
    try:
        table = import_package_table(path.read_bytes(), source_name=path.name)
    except (PackageImportError, OSError) as exc:
        return YearlyVolume(path.name, [], f"{path.name} could not be read: {exc}")
    if table.table.id != "A2":
        return YearlyVolume(path.name, [], f"{path.name} is not the A2 year-wise table.")
    rows = [
        YearlyRow(r["year"], r["symbol"], r["lots_traded"], r["total_value_lakh"], r["trading_days"])
        for r in table.rows
        if r["symbol"] in SYMBOL_ORDER
    ]
    rows.sort(key=lambda r: (SYMBOL_ORDER.index(r.symbol), r.year))
    return YearlyVolume(path.name, rows, None)
