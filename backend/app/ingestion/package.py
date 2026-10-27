"""Import the GoldLensAI MCX gold data package (tables A1, A2, B1, B2).

The package (``Gold_Lens_AI_MCX_Gold_Complete.pdf``) carries four tables as CSV
blocks: two year-wise aggregate tables and two date-wise tables for one trading
day. Each table has an exact header, so a file is recognised by its header row,
not by its name.

Rules, as for the Bhavcopy importer:
  * values are never repaired, filled in or forward-filled;
  * every row is accepted, rejected (with reasons) or dropped as an exact
    duplicate of an accepted row, and the counts add up to the rows read;
  * year-wise and date-wise tables stay separate (the package's own rule), and
    option premiums never enter a futures price series.

Derived columns (days_to_expiry, change_pct, close_per_10g, qty_kg,
implied_avg_price_per_10g, yoy_price_change_pct, trading_days) are recomputed
from the raw columns and reported as warnings when they disagree. A unit that
contradicts a verified contract specification rejects the row.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Callable

from app.ingestion.columns import normalize_header
from app.ingestion.importer import SYNTHETIC_PREFIX
from app.ingestion.models import RejectedRow
from app.ingestion.parsing import ParseError, is_missing, parse_date, parse_decimal, parse_int
from app.specs import SpecRegistry, UnknownInstrumentError, default_registry
from app.specs.registry import SpecStatus


class TableKind(StrEnum):
    ANNUAL = "annual"  # year-wise aggregates: reference context only
    FUTURES = "futures"  # date-wise futures: the research engine's input
    OPTIONS = "options"  # date-wise option premiums: stored, never used as futures prices


class ColumnType(StrEnum):
    INT = "int"
    DECIMAL = "decimal"
    DATE = "date"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: ColumnType
    nullable: bool = False
    minimum: Decimal | None = None  # inclusive
    positive: bool = False
    choices: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class TableSpec:
    id: str
    kind: TableKind
    title: str
    file_name: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]

    @property
    def header(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


ZERO = Decimal(0)


def _int(name: str, **kw: Any) -> Column:
    return Column(name, ColumnType.INT, **kw)


def _dec(name: str, **kw: Any) -> Column:
    return Column(name, ColumnType.DECIMAL, **kw)


def _date(name: str) -> Column:
    return Column(name, ColumnType.DATE)


def _text(name: str, **kw: Any) -> Column:
    return Column(name, ColumnType.TEXT, **kw)


A1 = TableSpec(
    id="A1",
    kind=TableKind.ANNUAL,
    title="GOLD 1 kg main contract, one row per year",
    file_name="A1_yearwise_GOLD_main.csv",
    columns=(
        _int("year"),
        _int("lots_traded", minimum=ZERO),
        _dec("total_value_lakh", minimum=ZERO),
        _dec("avg_daily_turnover_lakh", minimum=ZERO),
        _int("trading_days", minimum=ZERO),
        _dec("implied_avg_price_per_10g", positive=True),
        _dec("yoy_price_change_pct", nullable=True),
        _text("is_partial_year", choices=frozenset({"0", "1"})),
    ),
    key=("year",),
)

A2 = TableSpec(
    id="A2",
    kind=TableKind.ANNUAL,
    title="Every gold contract, one row per symbol and year",
    file_name="A2_yearwise_all_gold_contracts.csv",
    columns=(
        _int("year"),
        _text("symbol"),
        _int("lots_traded", minimum=ZERO),
        _dec("total_value_lakh", minimum=ZERO),
        _dec("avg_daily_turnover_lakh", minimum=ZERO),
        _int("trading_days", nullable=True, minimum=ZERO),
        _dec("premium_value_lakh", nullable=True, minimum=ZERO),
    ),
    key=("year", "symbol"),
)

B1 = TableSpec(
    id="B1",
    kind=TableKind.FUTURES,
    title="Gold futures, one row per contract per trading date",
    file_name="B1_datewise_gold_futures.csv",
    columns=(
        _date("date"),
        _text("symbol"),
        _date("expiry_date"),
        _int("days_to_expiry", minimum=ZERO),
        _int("quote_unit_g", positive=True),
        _dec("open", nullable=True, positive=True),
        _dec("high", nullable=True, positive=True),
        _dec("low", nullable=True, positive=True),
        _dec("close", positive=True),
        _dec("prev_close", nullable=True, positive=True),
        _dec("change_pct", nullable=True),
        _dec("close_per_10g", positive=True),
        _int("volume_lots", minimum=ZERO),
        _dec("qty_kg", minimum=ZERO),
        _dec("value_lakh", minimum=ZERO),
        _int("open_interest_lots", minimum=ZERO),
        _text("no_trade", choices=frozenset({"0", "1"})),
    ),
    key=("date", "symbol", "expiry_date"),
)

B2 = TableSpec(
    id="B2",
    kind=TableKind.OPTIONS,
    title="Gold options that traded, one row per contract per trading date",
    file_name="B2_datewise_gold_options_traded.csv",
    columns=(
        _date("date"),
        _text("underlying"),
        _date("expiry_date"),
        _text("option_type", choices=frozenset({"CE", "PE"})),
        _dec("strike", positive=True),
        _dec("open", nullable=True, minimum=ZERO),
        _dec("high", nullable=True, minimum=ZERO),
        _dec("low", nullable=True, minimum=ZERO),
        _dec("close", minimum=ZERO),
        _dec("prev_close", nullable=True, minimum=ZERO),
        _int("volume_lots", minimum=ZERO),
        _dec("value_lakh", minimum=ZERO),
        _int("open_interest_lots", minimum=ZERO),
    ),
    key=("date", "underlying", "expiry_date", "option_type", "strike"),
)

PACKAGE_TABLES = (A1, A2, B1, B2)

# Option underlyings recognised in the package. GOLD (1 kg) is not one of the four
# contracts GoldLensAI researches, but its rows are valid package data.
KNOWN_GOLD_SYMBOLS = frozenset({"GOLD", "GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"})


class PackageImportError(ValueError):
    """The file as a whole cannot be imported as a package table."""


Row = dict[str, Any]


@dataclass(slots=True)
class PackageImport:
    table: TableSpec
    source_file: str
    source_sha256: str
    size_bytes: int
    imported_at: datetime
    rows_read: int = 0
    rows: list[Row] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    exact_duplicates_dropped: int = 0
    cross_file_duplicates: int = 0  # identical rows already held from another file
    row_warnings: Counter[str] = field(default_factory=Counter)
    missing_values: dict[str, int] = field(default_factory=dict)
    numeric_ranges: dict[str, tuple[str, str]] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return len(self.rows)

    @property
    def synthetic(self) -> bool:
        """Same rule as the Bhavcopy importer: only a SYNTHETIC_ file-name prefix marks test data."""
        return self.source_file.upper().startswith(SYNTHETIC_PREFIX)

    def key_of(self, row: Row) -> tuple:
        return tuple(row[k] for k in self.table.key)


def detect_package_table(headers: list[str]) -> TableSpec | None:
    keys = tuple(normalize_header(h) for h in headers)
    for table in PACKAGE_TABLES:
        if keys == tuple(normalize_header(c) for c in table.header):
            return table
    return None


def read_csv_rows(data: bytes, source_name: str) -> list[tuple[int, list[str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PackageImportError(f"{source_name} is not UTF-8 text") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        return [(reader.line_num, r) for r in reader if any(cell.strip() for cell in r)]
    except csv.Error as exc:
        raise PackageImportError(f"{source_name} is not a readable CSV file ({exc})") from exc


def import_package_table(
    data: bytes,
    *,
    source_name: str,
    registry: SpecRegistry | None = None,
    today: date | None = None,
) -> PackageImport:
    registry = registry or default_registry()
    today = today or datetime.now(UTC).date()
    rows = read_csv_rows(data, source_name)
    if not rows:
        raise PackageImportError(f"{source_name} contains no rows")
    table = detect_package_table(rows[0][1])
    if table is None:
        raise PackageImportError(
            f"{source_name} is not one of the package tables A1, A2, B1 or B2 (header does not match)"
        )

    result = PackageImport(
        table=table,
        source_file=source_name,
        source_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        imported_at=datetime.now(UTC),
        rows_read=len(rows) - 1,
    )
    missing: Counter[str] = Counter()
    candidates: list[tuple[int, Row]] = []
    for line_number, cells in rows[1:]:
        row, reasons, warnings = _parse_row(table, cells, missing)
        if not reasons:
            CHECKS[table.id](row, reasons, warnings, registry, today)
        result.row_warnings.update(warnings)
        if reasons:
            result.rejected.append(RejectedRow(line_number, tuple(reasons), dict(zip(table.header, cells))))
        else:
            row["line_number"] = line_number
            candidates.append((line_number, row))

    result.rows = _deduplicate(table, candidates, result)
    result.rejected.sort(key=lambda r: r.line_number)
    result.missing_values = {c.name: missing[c.name] for c in table.columns if missing[c.name]}
    result.numeric_ranges = _ranges(table, result.rows)
    result.coverage = COVERAGE[table.kind](result.rows)
    TABLE_CHECKS.get(table.id, lambda r: None)(result)
    return result


# --- Rows --------------------------------------------------------------------


def _parse_row(table: TableSpec, cells: list[str], missing: Counter[str]) -> tuple[Row, list[str], list[str]]:
    reasons: list[str] = []
    if len(cells) != len(table.columns):
        return {}, [f"Expected {len(table.columns)} columns, found {len(cells)}"], []
    row: Row = {}
    for column, raw in zip(table.columns, cells):
        if is_missing(raw):
            missing[column.name] += 1
            row[column.name] = None
            if not column.nullable:
                reasons.append(f"Missing {column.name}")
            continue
        try:
            row[column.name] = _parse_value(column, raw)
        except ParseError as exc:
            reasons.append(f"{column.name}: {exc}")
            continue
        value = row[column.name]
        if column.choices is not None and value not in column.choices:
            reasons.append(f"{column.name} must be one of {sorted(column.choices)}, got {raw!r}")
        if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
            if column.positive and value <= 0:
                reasons.append(f"{column.name} must be positive, got {raw}")
            if column.minimum is not None and value < column.minimum:
                reasons.append(f"{column.name} must be at least {column.minimum}, got {raw}")
    return row, reasons, []


def _parse_value(column: Column, raw: str) -> Any:
    if column.type is ColumnType.INT:
        return parse_int(raw)
    if column.type is ColumnType.DECIMAL:
        return parse_decimal(raw)
    if column.type is ColumnType.DATE:
        return parse_date(raw)
    return raw.strip().strip('"').upper()


def _close_enough(a: Decimal, b: Decimal, tolerance: str) -> bool:
    return abs(a - b) <= Decimal(tolerance)


def _ohlc(row: Row, reasons: list[str], warnings: list[str], *, traded: bool) -> None:
    o, h, lo, c = row["open"], row["high"], row["low"], row["close"]
    if not traded:
        if any(v is not None for v in (o, h, lo)):
            warnings.append("open/high/low reported on a no-trade row")
        return
    if o is None or h is None or lo is None:
        reasons.append("open/high/low missing on a traded row")
        return
    if lo > h:
        reasons.append(f"low {lo} is above high {h}")
    elif not lo <= o <= h:
        reasons.append(f"open {o} is outside the low-high range [{lo}, {h}]")
    if lo <= h and not lo <= c <= h:
        warnings.append("close outside the low-high range")


def _dates(row: Row, reasons: list[str], today: date) -> None:
    if row["expiry_date"] < row["date"]:
        reasons.append(f"expiry_date {row['expiry_date']} is before date {row['date']}")
    if row["date"] > today:
        reasons.append(f"date {row['date']} is in the future")


def _check_b1(row: Row, reasons: list[str], warnings: list[str], registry: SpecRegistry, today: date) -> None:
    _dates(row, reasons, today)
    if (row["expiry_date"] - row["date"]).days != row["days_to_expiry"]:
        warnings.append("days_to_expiry differs from expiry_date - date")

    traded = row["volume_lots"] > 0
    if (row["no_trade"] == "1") == traded:
        reasons.append(f"no_trade={row['no_trade']} contradicts volume_lots={row['volume_lots']}")
    _ohlc(row, reasons, warnings, traded=traded)

    unit = Decimal(row["quote_unit_g"])
    if not _close_enough(row["close_per_10g"], row["close"] * 10 / unit, "0.5"):
        warnings.append("close_per_10g differs from close x 10 / quote_unit_g")
    prev = row["prev_close"]
    if prev and row["change_pct"] is not None and not _close_enough(
        row["change_pct"], (row["close"] - prev) / prev * 100, "0.001"
    ):
        warnings.append("change_pct differs from (close - prev_close) / prev_close x 100")

    symbol = row["symbol"]
    if symbol not in KNOWN_GOLD_SYMBOLS:
        warnings.append(f"symbol not a known gold contract")
    try:
        resolution = registry.resolve(symbol, row["expiry_date"])
    except UnknownInstrumentError:
        warnings.append("no specification recorded for this symbol (units not cross-checked)")
        return
    spec = resolution.spec
    verified = resolution.status is SpecStatus.VERIFIED
    if not verified:
        warnings.append("expiry outside the verified specification window")
    if unit != spec.quotation_base_g:
        message = f"quote_unit_g {unit} contradicts the specification ({spec.quotation_base_g} g)"
        (reasons if verified else warnings).append(message)
    expected_kg = Decimal(row["volume_lots"]) * spec.trading_unit_g / 1000
    if not _close_enough(row["qty_kg"], expected_kg, "0.0005"):
        message = f"qty_kg {row['qty_kg']} contradicts volume_lots x {spec.trading_unit_g} g lot ({expected_kg} kg)"
        (reasons if verified else warnings).append(message)


def _check_b2(row: Row, reasons: list[str], warnings: list[str], registry: SpecRegistry, today: date) -> None:
    _dates(row, reasons, today)
    if row["underlying"] not in KNOWN_GOLD_SYMBOLS:
        warnings.append("underlying not a known gold contract")
    _ohlc(row, reasons, warnings, traded=row["volume_lots"] > 0)


def _check_a1(row: Row, reasons: list[str], warnings: list[str], registry: SpecRegistry, today: date) -> None:
    _year(row, reasons, today)
    lots = row["lots_traded"]
    if lots and not _close_enough(
        row["implied_avg_price_per_10g"], row["total_value_lakh"] * 100_000 / lots / 100, "1"
    ):
        warnings.append("implied_avg_price_per_10g differs from total_value_lakh x 100000 / lots_traded / 100")
    _trading_days(row, warnings)


def _check_a2(row: Row, reasons: list[str], warnings: list[str], registry: SpecRegistry, today: date) -> None:
    _year(row, reasons, today)
    if row["lots_traded"] == 0 and row["total_value_lakh"] != 0:
        reasons.append("total_value_lakh is non-zero with no lots traded")
    if row["trading_days"] is None and row["lots_traded"] > 0:
        warnings.append("trading_days missing although lots traded")
    _trading_days(row, warnings)


def _year(row: Row, reasons: list[str], today: date) -> None:
    if not 2000 <= row["year"] <= today.year:
        reasons.append(f"year {row['year']} is outside 2000-{today.year}")


def _trading_days(row: Row, warnings: list[str]) -> None:
    days, avg = row["trading_days"], row["avg_daily_turnover_lakh"]
    if days and avg and abs(row["total_value_lakh"] / avg - days) > 1:
        warnings.append("trading_days differs from total_value_lakh / avg_daily_turnover_lakh")


CHECKS: dict[str, Callable[..., None]] = {"A1": _check_a1, "A2": _check_a2, "B1": _check_b1, "B2": _check_b2}


# --- Table-level checks and summaries ------------------------------------------


def _check_a1_table(result: PackageImport) -> None:
    """yoy_price_change_pct must follow from consecutive years, and be NA after a gap."""
    by_year = {r["year"]: r for r in result.rows}
    for year, row in sorted(by_year.items()):
        prev = by_year.get(year - 1)
        yoy = row["yoy_price_change_pct"]
        if prev is None:
            if yoy is not None:
                result.warnings.append(f"{year}: yoy_price_change_pct given although {year - 1} is absent")
            continue
        expected = (row["implied_avg_price_per_10g"] / prev["implied_avg_price_per_10g"] - 1) * 100
        if yoy is None or not _close_enough(yoy, expected, "0.01"):
            result.warnings.append(f"{year}: yoy_price_change_pct {yoy} differs from the implied prices ({expected:.2f})")
    partial = [y for y, r in by_year.items() if r["is_partial_year"] == "1"]
    if partial:
        result.warnings.append(
            f"Partial years {partial}: totals are year-to-date and not comparable with full years."
        )


TABLE_CHECKS: dict[str, Callable[[PackageImport], None]] = {"A1": _check_a1_table}


def _deduplicate(table: TableSpec, candidates: list[tuple[int, Row]], result: PackageImport) -> list[Row]:
    groups: dict[tuple, list[tuple[int, Row]]] = defaultdict(list)
    for line_number, row in candidates:
        groups[tuple(row[k] for k in table.key)].append((line_number, row))
    kept: list[Row] = []
    for key, group in groups.items():
        signatures = {tuple(r[c.name] for c in table.columns) for _, r in group}
        if len(signatures) == 1:
            kept.append(group[0][1])
            result.exact_duplicates_dropped += len(group) - 1
            continue
        lines = ", ".join(str(n) for n, _ in group)
        for line_number, row in group:
            result.rejected.append(
                RejectedRow(line_number, (f"Conflicting rows for key {dict(zip(table.key, key))} (lines {lines})",),
                            {c.name: str(row[c.name]) for c in table.columns})
            )
    kept.sort(key=lambda r: r["line_number"])
    return kept


def _ranges(table: TableSpec, rows: list[Row]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for column in table.columns:
        if column.type in (ColumnType.INT, ColumnType.DECIMAL, ColumnType.DATE):
            values = [r[column.name] for r in rows if r[column.name] is not None]
            if values:
                out[column.name] = (str(min(values)), str(max(values)))
    return out


def _annual_coverage(rows: list[Row]) -> dict[str, Any]:
    years = sorted({r["year"] for r in rows})
    if not years:
        return {"years": 0}
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in years]
    symbols = Counter(r.get("symbol", "GOLD") for r in rows)
    return {
        "years": len(years),
        "first_year": years[0],
        "last_year": years[-1],
        "missing_years": gaps,
        "rows_per_symbol": dict(sorted(symbols.items())),
    }


def _datewise_coverage(rows: list[Row]) -> dict[str, Any]:
    dates = sorted({r["date"] for r in rows})
    symbol_key = "symbol" if rows and "symbol" in rows[0] else "underlying"
    expiries = sorted({(r[symbol_key], r["expiry_date"]) for r in rows})
    return {
        "trading_dates": len(dates),
        "first_date": dates[0].isoformat() if dates else None,
        "last_date": dates[-1].isoformat() if dates else None,
        "symbols": sorted({r[symbol_key] for r in rows}),
        "contract_expiries": len(expiries),
        "rows_per_symbol": dict(sorted(Counter(r[symbol_key] for r in rows).items())),
    }


COVERAGE: dict[TableKind, Callable[[list[Row]], dict[str, Any]]] = {
    TableKind.ANNUAL: _annual_coverage,
    TableKind.FUTURES: _datewise_coverage,
    TableKind.OPTIONS: _datewise_coverage,
}


def audit_dict(result: PackageImport) -> dict[str, Any]:
    """Machine-readable audit record for one imported table."""
    return {
        "table_id": result.table.id,
        "kind": result.table.kind.value,
        "title": result.table.title,
        "source_file": result.source_file,
        "source_sha256": result.source_sha256,
        "size_bytes": result.size_bytes,
        "imported_at": result.imported_at.isoformat(),
        "rows_read": result.rows_read,
        "accepted": result.accepted,
        "rejected": len(result.rejected),
        "exact_duplicates_dropped": result.exact_duplicates_dropped,
        "cross_file_duplicates": result.cross_file_duplicates,
        "rejected_rows": [{"line_number": r.line_number, "reasons": list(r.reasons)} for r in result.rejected],
        "row_warnings": dict(sorted(result.row_warnings.items())),
        "table_warnings": list(result.warnings),
        "missing_values": result.missing_values,
        "numeric_ranges": result.numeric_ranges,
        "coverage": result.coverage,
    }
