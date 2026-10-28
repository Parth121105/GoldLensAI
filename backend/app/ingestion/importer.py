"""Bhavcopy CSV import: parse, validate, de-duplicate, and record provenance.

Rows are never repaired or filled in. Each row ends up in exactly one bucket:
accepted, rejected (with reasons), skipped (outside scope, e.g. options or
other commodities), or dropped as an exact duplicate of an accepted row.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.ingestion.columns import Field, Layout, detect_layout
from app.ingestion.html_table import looks_like_html_table, read_html_table
from app.ingestion.models import (
    ContractCoverage,
    ImportReport,
    ImportResult,
    Observation,
    RejectedRow,
    RowProvenance,
)
from app.ingestion.parsing import (
    DateOrder,
    ParseError,
    has_numeric_dates,
    infer_date_order,
    is_missing,
    parse_date,
    parse_decimal,
    parse_int,
)
from app.instruments import canonical_symbol, is_supported
from app.specs import SpecRegistry, UnknownInstrumentError, default_registry

OPTION_TYPES = frozenset({"CE", "PE", "CA", "PA", "CALL", "PUT"})
SYNTHETIC_PREFIX = "SYNTHETIC_"  # the underscore is required: "Synthetically..." is not a label


class ImportFailedError(ValueError):
    """The file as a whole cannot be imported (as opposed to individual bad rows)."""


@dataclass(slots=True)
class _Row:
    line_number: int
    raw: dict[str, str]
    values: dict[Field, str] = field(default_factory=dict)


def import_bhavcopy(
    path: Path | str,
    *,
    date_order: DateOrder | None = None,
    registry: SpecRegistry | None = None,
    today: date | None = None,
) -> ImportResult:
    path = Path(path)
    data = path.read_bytes()
    return import_bhavcopy_bytes(
        data, source_name=path.name, date_order=date_order, registry=registry, today=today
    )


def import_bhavcopy_bytes(
    data: bytes,
    *,
    source_name: str,
    date_order: DateOrder | None = None,
    registry: SpecRegistry | None = None,
    today: date | None = None,
) -> ImportResult:
    registry = registry or default_registry()
    today = today or datetime.now(UTC).date()
    file_warnings: list[str] = []

    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(data) >= 4 and data[1] == 0 and data[3] == 0):
        raise ImportFailedError(
            f"{source_name} appears to be UTF-16 encoded (for example Excel's 'Unicode Text'). "
            "Save it as a CSV (UTF-8 or comma-delimited) and upload it again."
        )
    if b"\x00" in data:
        raise ImportFailedError(f"{source_name} is not a readable CSV file (contains binary data).")
    text = _decode(data, file_warnings)
    if looks_like_html_table(text):
        # MCX's date-wise download is an HTML table saved as .xls. Rows are numbered
        # by their position in the table (header = 1) instead of by physical line.
        table = read_html_table(text)
        rows = [(i, r) for i, r in enumerate(table, start=1) if any(cell.strip() for cell in r)]
        file_warnings.append(
            "File is an HTML table (MCX's date-wise .xls download), not an Excel workbook; "
            "line numbers refer to table rows, header = 1."
        )
    else:
        reader = csv.reader(io.StringIO(text))
        try:
            # Keep physical line numbers so rejections point at the right line in the file.
            rows = [(reader.line_num, r) for r in reader if any(cell.strip() for cell in r)]
        except csv.Error as exc:
            raise ImportFailedError(
                f"{source_name} is not a readable CSV file (line {reader.line_num}: {exc})"
            ) from exc
    if not rows:
        raise ImportFailedError(f"{source_name} contains no rows")

    headers = rows[0][1]
    try:
        layout, mapping = detect_layout(headers)
    except ValueError as exc:
        raise ImportFailedError(str(exc)) from exc

    records = _to_records(rows[1:], headers, mapping)
    date_order = _resolve_date_order(records, date_order)

    report = ImportReport(
        source_file=source_name,
        source_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        imported_at=datetime.now(UTC),
        layout_id=layout.id,
        layout_verified_against_real_file=layout.verified_against_real_file,
        units=dict(layout.units),
        date_order=date_order.value if date_order else None,
        synthetic=source_name.upper().startswith(SYNTHETIC_PREFIX),
        rows_read=len(records),
        warnings=file_warnings,
    )

    skipped: Counter[str] = Counter()
    candidates: list[Observation] = []
    for record in records:
        outcome = _process_row(record, layout, report, date_order, registry, today)
        if isinstance(outcome, Observation):
            candidates.append(outcome)
        elif isinstance(outcome, RejectedRow):
            report.rejected.append(outcome)
        else:
            skipped[outcome] += 1

    observations = _deduplicate(candidates, report)
    observations.sort(key=lambda o: (o.trade_date, o.symbol, o.expiry))

    report.skipped = dict(sorted(skipped.items()))
    report.accepted = len(observations)
    report.rejected.sort(key=lambda r: r.line_number)
    report.trade_dates = sorted({o.trade_date for o in observations})
    report.coverage = _coverage(observations, registry)
    report.warnings.extend(_filename_date_warnings(source_name, report.trade_dates))
    return ImportResult(observations=observations, report=report)


def _decode(data: bytes, warnings: list[str]) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        warnings.append("File is not valid UTF-8; decoded as Windows-1252.")
        return data.decode("cp1252")


def _to_records(
    rows: list[tuple[int, list[str]]], headers: list[str], mapping: dict[Field, int]
) -> list[_Row]:
    records = []
    for line_number, cells in rows:
        raw = {headers[i]: cells[i] if i < len(cells) else "" for i in range(len(headers))}
        values = {f: (cells[i] if i < len(cells) else "") for f, i in mapping.items()}
        records.append(_Row(line_number=line_number, raw=raw, values=values))
    return records


def _resolve_date_order(records: list[_Row], requested: DateOrder | None) -> DateOrder | None:
    date_values = [
        r.values.get(f, "") for r in records for f in (Field.TRADE_DATE, Field.EXPIRY)
    ]
    try:
        inferred = infer_date_order(date_values)
    except ParseError as exc:
        raise ImportFailedError(str(exc)) from exc

    if requested and inferred and requested != inferred:
        raise ImportFailedError(
            f"Requested date order {requested} contradicts the file, which implies {inferred}"
        )
    order = requested or inferred
    if order is None and has_numeric_dates(date_values):
        raise ImportFailedError(
            "Numeric dates in this file are ambiguous (no day or month above 12). "
            "Specify the date order (DMY or MDY) explicitly."
        )
    return order


def _process_row(
    record: _Row,
    layout: Layout,
    report: ImportReport,
    order: DateOrder | None,
    registry: SpecRegistry,
    today: date,
) -> Observation | RejectedRow | str:
    v = record.values
    raw_symbol = v.get(Field.SYMBOL, "")
    symbol = canonical_symbol(raw_symbol)
    if not symbol:
        return RejectedRow(record.line_number, ("Missing symbol",), record.raw)

    if _is_option(v):
        return "option rows (out of scope)"
    if not is_supported(symbol):
        return f"symbol {symbol} (out of scope)"

    reasons: list[str] = []
    warnings: list[str] = []

    def field_date(f: Field, label: str) -> date | None:
        if is_missing(v.get(f)):
            reasons.append(f"Missing {label}")
            return None
        try:
            return parse_date(v[f], order)
        except ParseError as exc:
            reasons.append(f"{label}: {exc}")
            return None

    def field_decimal(f: Field, label: str) -> Decimal | None:
        try:
            return parse_decimal(v.get(f))
        except ParseError as exc:
            reasons.append(f"{label}: {exc}")
            return None

    def field_int(f: Field, label: str) -> int | None:
        try:
            return parse_int(v.get(f))
        except ParseError as exc:
            reasons.append(f"{label}: {exc}")
            return None

    trade_date = field_date(Field.TRADE_DATE, "trade date")
    expiry = field_date(Field.EXPIRY, "expiry date")
    open_ = field_decimal(Field.OPEN, "open")
    high = field_decimal(Field.HIGH, "high")
    low = field_decimal(Field.LOW, "low")
    close = field_decimal(Field.CLOSE, "close")
    previous_close = field_decimal(Field.PREVIOUS_CLOSE, "previous close")
    settlement = field_decimal(Field.SETTLEMENT, "settlement")
    value = field_decimal(Field.VALUE, "value")
    volume = field_int(Field.VOLUME, "volume")
    open_interest = field_int(Field.OPEN_INTEREST, "open interest")

    if trade_date and expiry and expiry < trade_date:
        reasons.append(f"Expiry {expiry} is before trade date {trade_date}")
    if trade_date and trade_date > today:
        reasons.append(f"Trade date {trade_date} is in the future")
    if trade_date and trade_date.weekday() >= 5:
        warnings.append(f"Trade date {trade_date} is a weekend (special session?)")

    listing = registry.listings.get(symbol)
    if trade_date and listing and trade_date < listing.first_trading_date:
        reasons.append(
            f"{symbol} observation dated {trade_date} precedes the instrument's "
            f"first trading date {listing.first_trading_date}"
        )

    if close is None:
        if is_missing(v.get(Field.CLOSE)):  # otherwise a parse error is already recorded
            reasons.append("Missing close price")
    elif close <= 0:
        reasons.append(f"Close price must be positive, got {close}")

    for label, number in (("previous close", previous_close), ("settlement", settlement)):
        if number is not None and number <= 0:
            reasons.append(f"{label} must be positive, got {number}")
    for label, count in (("volume", volume), ("open interest", open_interest)):
        if count is not None and count < 0:
            reasons.append(f"{label} must not be negative, got {count}")
    if value is not None and value < 0:
        reasons.append(f"value must not be negative, got {value}")

    if Field.VOLUME not in v:
        traded = None
    elif volume is None:
        traded = None
        warnings.append("Volume not reported")
    else:
        traded = volume > 0
    if Field.OPEN_INTEREST in v and is_missing(v.get(Field.OPEN_INTEREST)):
        warnings.append("Open interest not reported")

    open_, high, low = _check_ohlc(open_, high, low, close, traded, reasons, warnings)

    if trade_date is None or expiry is None or close is None or reasons:
        return RejectedRow(record.line_number, tuple(reasons), record.raw)

    try:
        rule = registry.resolve(symbol, expiry).spec.last_trading_day_rule
        if not rule.is_consistent(expiry):
            warnings.append(
                f"Expiry {expiry} does not match the documented last-trading-day rule "
                f"({rule.type}{'' if rule.day is None else f' {rule.day}'}); "
                "check the specification version for this contract."
            )
    except UnknownInstrumentError:
        warnings.append(f"No specification recorded for {symbol}")

    return Observation(
        trade_date=trade_date,
        symbol=symbol,
        raw_symbol=raw_symbol,
        expiry=expiry,
        open=open_,
        high=high,
        low=low,
        close=close,
        previous_close=previous_close,
        settlement=settlement,
        volume=volume,
        value=value,
        open_interest=open_interest,
        traded=traded,
        provenance=RowProvenance(
            source_file=report.source_file,
            source_sha256=report.source_sha256,
            line_number=record.line_number,
            layout_id=layout.id,
        ),
        warnings=tuple(warnings),
    )


def _is_option(v: dict[Field, str]) -> bool:
    option_type = v.get(Field.OPTION_TYPE, "").strip().strip('"').upper()
    instrument = v.get(Field.INSTRUMENT, "").strip().upper()
    try:
        strike = parse_decimal(v.get(Field.STRIKE))
    except ParseError:
        strike = None
    return option_type in OPTION_TYPES or "OPT" in instrument or bool(strike and strike > 0)


def _check_ohlc(
    open_: Decimal | None,
    high: Decimal | None,
    low: Decimal | None,
    close: Decimal | None,
    traded: bool | None,
    reasons: list[str],
    warnings: list[str],
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Validate open/high/low. Zeros on a no-trade day mean 'not reported'."""
    parts = (open_, high, low)
    if traded is not True and all(p is None or p == 0 for p in parts):
        if any(p is not None for p in parts):
            warnings.append("No trades: open/high/low reported as zero and treated as missing")
        return None, None, None

    if any(p is None or p <= 0 for p in parts):
        reasons.append("Open/high/low must all be positive when the contract traded")
        return open_, high, low

    assert open_ is not None and high is not None and low is not None
    if low > high:
        reasons.append(f"Low {low} is above high {high}")
    elif not low <= open_ <= high:
        reasons.append(f"Open {open_} is outside the low-high range [{low}, {high}]")
    if close is not None and close > 0 and low <= high and not low <= close <= high:
        warnings.append(f"Close {close} is outside the low-high range [{low}, {high}]")
    return open_, high, low


def _deduplicate(candidates: list[Observation], report: ImportReport) -> list[Observation]:
    groups: dict[tuple[date, str, date], list[Observation]] = defaultdict(list)
    for obs in candidates:
        groups[(obs.trade_date, obs.symbol, obs.expiry)].append(obs)

    kept: list[Observation] = []
    for (trade_date, symbol, expiry), group in groups.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        signatures = {_market_signature(o) for o in group}
        if len(signatures) == 1:
            kept.append(group[0])
            report.exact_duplicates_dropped += len(group) - 1
            continue
        lines = ", ".join(str(o.provenance.line_number) for o in group)
        for obs in group:
            report.rejected.append(
                RejectedRow(
                    obs.provenance.line_number,
                    (
                        f"Conflicting duplicate rows for {symbol} expiring {expiry} "
                        f"on {trade_date} (lines {lines})",
                    ),
                    {},
                )
            )
    return kept


def _market_signature(o: Observation) -> tuple:
    return (
        o.open, o.high, o.low, o.close, o.previous_close, o.settlement,
        o.volume, o.value, o.open_interest,
    )


def _coverage(observations: list[Observation], registry: SpecRegistry) -> list[ContractCoverage]:
    by_contract: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_contract[obs.contract_id].append(obs)

    coverage = []
    for contract_id, group in sorted(by_contract.items()):
        first = group[0]
        resolution = registry.resolve(first.symbol, first.expiry)
        coverage.append(
            ContractCoverage(
                contract_id=contract_id,
                symbol=first.symbol,
                expiry=first.expiry,
                first_trade_date=min(o.trade_date for o in group),
                last_trade_date=max(o.trade_date for o in group),
                observations=len(group),
                traded_observations=sum(1 for o in group if o.traded),
                spec_status=resolution.status.value,
                spec_version_id=resolution.spec.version_id,
            )
        )
    return coverage


_FILENAME_YMD = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
_FILENAME_DMY = re.compile(r"(?<!\d)(\d{2})[-_]?(\d{2})[-_]?(20\d{2})(?!\d)")


def _filename_date_warnings(name: str, trade_dates: list[date]) -> list[str]:
    """The filename is not trusted, but a disagreement with the contents is worth reporting."""
    candidates = []
    for pattern, order in ((_FILENAME_YMD, "ymd"), (_FILENAME_DMY, "dmy")):
        for m in pattern.finditer(name):
            a, b, c = (int(g) for g in m.groups())
            year, month, day = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
    if not candidates or not trade_dates:
        return []
    if any(d in trade_dates for d in candidates):
        return []
    return [
        f"Filename suggests {candidates[0]} but the file contains trade dates "
        f"{trade_dates[0]} to {trade_dates[-1]}. MCX returns the latest trading day when the requested "
        "date is a holiday or invalid, so no data exists for the requested date. The rows are kept "
        "under the date the file itself states."
    ]
