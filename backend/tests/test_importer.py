import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion import DateOrder, ImportFailedError, import_bhavcopy, import_bhavcopy_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
LEGACY_FILE = FIXTURES / "SYNTHETIC_mcx_legacy_15102025.csv"
UDIFF_FILE = FIXTURES / "SYNTHETIC_udiff_2025-10-16.csv"
TODAY = date(2026, 10, 25)

LEGACY_HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)


def run_inline(rows: str, name="SYNTHETIC_inline.csv", header=LEGACY_HEADER, **kw):
    kw.setdefault("today", TODAY)
    return import_bhavcopy_bytes((header + rows).encode(), source_name=name, **kw)


@pytest.fixture(scope="module")
def legacy():
    return import_bhavcopy(LEGACY_FILE, today=TODAY)


def by_line(result, line):
    return next(o for o in result.observations if o.provenance.line_number == line)


def rejection(result, line):
    return " | ".join(next(r for r in result.report.rejected if r.line_number == line).reasons)


# --- Legacy fixture: every row lands in exactly one bucket ---------------------


def test_legacy_fixture_row_accounting(legacy):
    r = legacy.report

    assert r.rows_read == 15
    assert r.accepted == 6
    assert len(r.rejected) == 6
    assert r.exact_duplicates_dropped == 1
    assert r.skipped == {"option rows (out of scope)": 1, "symbol SILVER (out of scope)": 1}
    assert r.accepted + len(r.rejected) + r.exact_duplicates_dropped + sum(r.skipped.values()) == r.rows_read


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (7, "Open 72900 is outside the low-high range"),
        (8, "volume must not be negative"),
        (9, "Expiry 2025-09-30 is before trade date 2025-10-15"),
        (13, "Conflicting duplicate rows"),
        (14, "Conflicting duplicate rows"),
        (15, "Not a number: 'abc'"),
    ],
)
def test_legacy_fixture_rejection_reasons(legacy, line, reason):
    assert reason in rejection(legacy, line)


def test_padded_symbol_and_thousands_separators(legacy):
    obs = by_line(legacy, 2)

    assert obs.symbol == "GOLDM"
    assert obs.raw_symbol == "  GOLDM     "
    assert obs.open == Decimal("72000.00")
    assert obs.value == Decimal("8676.00")
    assert obs.expiry == date(2025, 11, 5)
    assert obs.contract_id == "GOLDM-2025-11-05"


def test_lowercase_symbol_is_canonicalised(legacy):
    assert by_line(legacy, 5).symbol == "GOLDPETAL"


def test_no_trade_row_keeps_close_and_drops_zero_ohlc(legacy):
    obs = by_line(legacy, 4)

    assert obs.traded is False
    assert (obs.open, obs.high, obs.low) == (None, None, None)
    assert obs.close == Decimal("57900")
    assert any("No trades" in w for w in obs.warnings)


def test_missing_open_interest_is_recorded_not_filled(legacy):
    obs = by_line(legacy, 5)

    assert obs.open_interest is None
    assert "Open interest not reported" in obs.warnings


def test_expiry_inconsistent_with_rule_is_flagged(legacy):
    obs = by_line(legacy, 17)

    assert any("last-trading-day rule" in w for w in obs.warnings)


def test_provenance_points_back_to_source(legacy):
    obs = by_line(legacy, 3)
    expected_hash = hashlib.sha256(LEGACY_FILE.read_bytes()).hexdigest()

    assert obs.provenance.source_file == LEGACY_FILE.name
    assert obs.provenance.source_sha256 == expected_hash == legacy.report.source_sha256
    assert obs.provenance.layout_id == "mcx-bhavcopy-legacy"


def test_report_metadata(legacy):
    r = legacy.report

    assert r.synthetic is True
    # Checked on 26 Oct 2026 against one real MCX date-wise download (see columns.py).
    assert r.layout_verified_against_real_file is True
    assert r.units["volume"] == "lots"
    assert r.trade_dates == [date(2025, 10, 15)]
    assert r.warnings == []


def test_coverage_is_per_contract_not_spliced(legacy):
    ids = [c.contract_id for c in legacy.report.coverage]

    assert ids == [
        "GOLDGUINEA-2025-10-31", "GOLDM-2025-11-05", "GOLDM-2025-11-25",
        "GOLDPETAL-2025-10-31", "GOLDPETAL-2025-11-30", "GOLDTEN-2025-10-31",
    ]
    assert all(c.spec_status == "verified" for c in legacy.report.coverage)


# --- UDiFF fixture -------------------------------------------------------------


def test_udiff_layout():
    result = import_bhavcopy(UDIFF_FILE, today=TODAY)

    assert result.report.layout_id == "udiff-bhavcopy"
    assert result.report.accepted == 2
    obs = result.observations[0]
    assert obs.trade_date == date(2025, 10, 16)
    assert obs.settlement == Decimal("72500")
    assert obs.volume == 1100


# --- File-level failures ---------------------------------------------------------


def test_empty_file_fails():
    with pytest.raises(ImportFailedError, match="no rows"):
        import_bhavcopy_bytes(b"\n\n", source_name="empty.csv")


def test_missing_required_column_fails():
    with pytest.raises(ImportFailedError, match="missing: expirydate"):
        run_inline("15-Oct-2025,GOLDM,72000\n", header="Date,Symbol,Close\n")


def test_ambiguous_numeric_dates_fail_without_explicit_order():
    rows = "05/10/2025,FUTCOM,GOLDTEN,10/12/2025,XX,0,1,1,1,72450,1,1,1,1\n"
    with pytest.raises(ImportFailedError, match="ambiguous"):
        run_inline(rows)


def test_explicit_date_order_resolves_ambiguity():
    rows = "05/10/2025,FUTCOM,GOLDTEN,12/12/2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    result = run_inline(rows, date_order=DateOrder.DMY)

    assert result.observations[0].trade_date == date(2025, 10, 5)
    assert result.report.date_order == "DMY"


def test_month_first_order_is_inferred():
    rows = "10/15/2025,FUTCOM,GOLDTEN,10/31/2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    result = run_inline(rows)

    assert result.report.date_order == "MDY"
    assert result.observations[0].expiry == date(2025, 10, 31)


def test_requested_order_contradicting_file_fails():
    rows = "10/15/2025,FUTCOM,GOLDTEN,10/31/2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    with pytest.raises(ImportFailedError, match="contradicts"):
        run_inline(rows, date_order=DateOrder.DMY)


# --- Row-level rules -----------------------------------------------------------------


def test_goldten_before_listing_is_rejected():
    rows = "14-Mar-2025,FUTCOM,GOLDTEN,30-Apr-2025,XX,0,1,1,1,88000,1,1,1,1\n"
    result = run_inline(rows)

    assert result.report.accepted == 0
    assert "first trading date 2025-04-01" in result.report.rejected[0].reasons[0]


def test_future_trade_date_is_rejected():
    rows = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    result = run_inline(rows, today=date(2025, 10, 1))

    assert "in the future" in result.report.rejected[0].reasons[0]


def test_traded_row_with_zero_ohlc_is_rejected():
    rows = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,0,0,0,72450,72000,5,1,1\n"
    result = run_inline(rows)

    assert "must all be positive when the contract traded" in result.report.rejected[0].reasons[0]


def test_low_above_high_is_rejected():
    rows = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72100,72600,72450,72000,5,1,1\n"
    result = run_inline(rows)

    assert "Low 72600 is above high 72100" in result.report.rejected[0].reasons[0]


def test_missing_close_is_rejected():
    rows = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72600,72100,,72000,5,1,1\n"
    result = run_inline(rows)

    assert "Missing close price" in result.report.rejected[0].reasons


def test_weekend_trade_date_is_flagged():
    rows = "18-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    result = run_inline(rows)

    assert any("weekend" in w for w in result.observations[0].warnings)


def test_filename_date_disagreeing_with_contents_is_reported():
    rows = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72600,72100,72450,72000,5,1,1\n"
    result = run_inline(rows, name="bhav_2025-10-01.csv")

    assert result.report.synthetic is False
    assert any("Filename suggests 2025-10-01" in w for w in result.report.warnings)
    assert result.observations[0].trade_date == date(2025, 10, 15)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
def test_utf16_files_get_an_encoding_message_not_binary(encoding):
    """Regression: Excel 'Unicode Text' exports were reported as binary data."""
    data = "Date,Symbol,Expiry Date,Close\n15-Oct-2025,GOLDM,05-Nov-2025,121000\n".encode(encoding)

    with pytest.raises(ImportFailedError, match="UTF-16"):
        import_bhavcopy_bytes(data, source_name="excel_unicode.csv")


# --- MCX "BhavCopyDateWise" download: an HTML table saved with an .xls extension -----------

HTML_HEADER = [
    "Date", "Instrument Name", "Symbol", "Expiry Date", "Option Type", "Strike Price", "Open", "High",
    "Low", "Close", "Previous Close", "Volume(Lots)", "Volume(In 000's)", "Value(Lacs)", "Open Interest(Lots)",
]


AFTER_27_OCT = date(2026, 10, 28)


def mcx_html(rows: list[list[str]]) -> bytes:
    """The layout of the real download (synthetic values): padded symbols, '27 Oct 2026' dates, '04DEC2026' expiries."""
    head = "".join(f'<th style="padding: 5px;">{h}</th>' for h in HTML_HEADER)
    body = "".join("<tr>" + "".join(f'<td style="padding: 5px; text-align: left;">{c}</td>' for c in r) + "</tr>" for r in rows)
    return f'<table border="1"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'.encode()


def html_row(day, symbol, expiry, close, option="-", lots="10"):
    return [day, "FUTCOM", symbol, expiry, option, "0", close, close, close, close, close, lots,
            "1.000 GRMS  ", "14.00", "5"]


def test_mcx_html_download_with_padded_symbols_and_compact_expiries():
    data = mcx_html([
        html_row("27 Oct 2026", "GOLDM       ", "05NOV2026", "142509.00"),
        html_row("27 Oct 2026", "GOLDM       ", "04DEC2026", "144042.00"),
        html_row("27 Oct 2026", "GOLDTEN     ", "30OCT2026", "142713.00"),
        html_row("27 Oct 2026", "GOLDM       ", "29OCT2026", "2827.50", option="CE"),
    ])
    result = import_bhavcopy_bytes(data, source_name="SYNTHETIC_BhavCopyDateWise_27102026.xls", today=AFTER_27_OCT)

    assert result.report.trade_dates == [date(2026, 10, 27)]
    assert not any("Filename suggests" in w for w in result.report.warnings)
    assert result.report.skipped == {"option rows (out of scope)": 1}
    # Each expiry is its own contract; nothing is stitched into a near-month series.
    assert sorted(o.contract_id for o in result.observations) == [
        "GOLDM-2026-11-05", "GOLDM-2026-12-04", "GOLDTEN-2026-10-30"]
    assert {o.symbol for o in result.observations} == {"GOLDM", "GOLDTEN"}


def test_mcx_returns_the_latest_trading_day_for_a_holiday_request():
    """Asked for Sunday 25 Oct 2026 (DDMMYYYY in the name); MCX served Friday 23 Oct."""
    data = mcx_html([html_row("23 Oct 2026", "GOLDM", "05NOV2026", "140453.00")])
    result = import_bhavcopy_bytes(data, source_name="SYNTHETIC_BhavCopyDateWise_25102026.xls", today=AFTER_27_OCT)

    assert result.report.trade_dates == [date(2026, 10, 23)]
    (warning,) = [w for w in result.report.warnings if "Filename suggests" in w]
    assert "Filename suggests 2026-10-25" in warning and "latest trading day" in warning


def test_response_dates_in_month_day_year_order():
    """Requests use DD/MM/YYYY; the MCX response uses MM/DD/YYYY. 10/27/2026 can only be MDY."""
    rows = "10/27/2026,FUTCOM,GOLDTEN,10/30/2026,XX,0,141502,142995,140872,142713,141797,5,1,1\n"
    result = run_inline(rows, today=AFTER_27_OCT)

    assert result.report.date_order == "MDY"
    (obs,) = result.observations
    assert (obs.trade_date, obs.expiry) == (date(2026, 10, 27), date(2026, 10, 30))


def test_ambiguous_numeric_dates_are_not_guessed():
    rows = "03/10/2026,FUTCOM,GOLDTEN,31-Dec-2026,XX,0,1,1,1,1,1,5,1,1\n"
    assert run_inline(rows, date_order=DateOrder.MDY, today=AFTER_27_OCT).observations[0].trade_date == date(2026, 3, 10)
    assert run_inline(rows, date_order=DateOrder.DMY, today=AFTER_27_OCT).observations[0].trade_date == date(2026, 10, 3)
