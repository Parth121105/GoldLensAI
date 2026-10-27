"""MCX gold data package (tables A1, A2, B1, B2), the HTML Bhavcopy and data readiness.

Inline tables below are SYNTHETIC: invented values in the package's exact formats.
The last section runs on the real extracted package only if it is present locally
(backend/data/raw/ is ignored by Git).
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion import import_bhavcopy_bytes
from app.ingestion.package import PackageImportError, TableKind, import_package_table
from app.ingestion.package_pdf import PackageExtractError, extract_blocks
from app.main import create_app
from app.research import ResearchConfig
from app.research.readiness import Verdict, assess, split_plan
from app.research.validation import validate_symbol_pair
from app.research.pairs import build_pair_series
from app.demo import demo_csv_bytes
from app.store import SessionStore

TODAY = date(2026, 10, 26)

A1_HEADER = "year,lots_traded,total_value_lakh,avg_daily_turnover_lakh,trading_days,implied_avg_price_per_10g,yoy_price_change_pct,is_partial_year\n"
A2_HEADER = "year,symbol,lots_traded,total_value_lakh,avg_daily_turnover_lakh,trading_days,premium_value_lakh\n"
B1_HEADER = "date,symbol,expiry_date,days_to_expiry,quote_unit_g,open,high,low,close,prev_close,change_pct,close_per_10g,volume_lots,qty_kg,value_lakh,open_interest_lots,no_trade\n"
B2_HEADER = "date,underlying,expiry_date,option_type,strike,open,high,low,close,prev_close,volume_lots,value_lakh,open_interest_lots\n"

# lots 1000, value 1000 lakh -> implied 1000 * 1e5 / 1000 / 100 = 1000 per 10 g
A1_ROWS = (
    "2020,1000,1000.00,4.00,250,1000.0,NA,0\n"
    "2021,1000,1100.00,4.40,250,1100.0,10.0,0\n"
    "2023,1000,1200.00,4.80,250,1200.0,NA,1\n"
)
# GOLDM expiring 2025-11-05 is inside the verified window: quoted per 10 g, 100 g lot.
B1_GOOD = (
    "2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,72450.0,50,5.0,3622.5,120,0\n"
    "2025-10-15,GOLD,2025-12-05,51,10,NA,NA,NA,72800.0,72800.0,0.0,72800.0,0,0.0,0.0,0,1\n"
)
B2_GOOD = (
    "2025-10-15,GOLDM,2025-10-29,CE,72000,500.0,520.0,480.0,510.0,505.0,10,51.0,30\n"
    "2025-10-15,GOLDM,2025-10-29,PE,72000,450.0,470.0,440.0,455.0,460.0,8,36.4,22\n"
)


def table(data: str, name: str = "SYNTHETIC_table.csv"):
    return import_package_table(data.encode(), source_name=name, today=TODAY)


def reasons(result) -> list[str]:
    return [reason for r in result.rejected for reason in r.reasons]


# --- Formats and accounting -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "table_id", "kind"),
    [
        (A1_HEADER + A1_ROWS, "A1", TableKind.ANNUAL),
        (A2_HEADER + "2020,GOLDM,10,100.0,0.4,250,NA\n", "A2", TableKind.ANNUAL),
        (B1_HEADER + B1_GOOD, "B1", TableKind.FUTURES),
        (B2_HEADER + B2_GOOD, "B2", TableKind.OPTIONS),
    ],
)
def test_each_table_is_recognised_by_its_header_and_rows_add_up(data, table_id, kind):
    result = table(data, name="SYNTHETIC_anything.csv")  # the name does not decide the table

    assert result.table.id == table_id and result.table.kind is kind
    assert result.rows_read == result.accepted + len(result.rejected) + result.exact_duplicates_dropped
    assert result.rejected == []


def test_unknown_header_is_not_a_package_table():
    with pytest.raises(PackageImportError, match="not one of the package tables"):
        table("date,close\n2025-10-15,1\n")


def test_dates_and_numbers_are_typed_and_na_is_missing_not_zero():
    result = table(B1_HEADER + B1_GOOD)
    goldm, gold = result.rows

    assert goldm["date"] == date(2025, 10, 15) and goldm["expiry_date"] == date(2025, 11, 5)
    assert str(goldm["close"]) == "72450.0"
    assert gold["open"] is None and gold["high"] is None  # NA, never 0
    assert result.missing_values == {"open": 1, "high": 1, "low": 1}


# --- Row validation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("row", "message"),
    [
        # low above high
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,71000.0,72100.0,72450.0,72000.0,0.625,72450.0,50,5.0,3622.5,120,0", "is above high"),
        # no_trade flag contradicts volume
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,72450.0,50,5.0,3622.5,120,1", "contradicts volume_lots"),
        # GOLDM is quoted per 10 g under its verified specification
        ("2025-10-15,GOLDM,2025-11-05,21,8,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,90562.5,50,5.0,3622.5,120,0", "contradicts the specification"),
        # 50 lots of 100 g is 5 kg, not 50 kg
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,72450.0,50,50.0,3622.5,120,0", "contradicts volume_lots x 100 g lot"),
        # expiry before the trade date
        ("2025-10-15,GOLDM,2025-10-05,0,10,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,72450.0,50,5.0,3622.5,120,0", "before date"),
        # negative open interest
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,72450.0,72000.0,0.625,72450.0,50,5.0,3622.5,-1,0", "must be at least 0"),
        # missing close
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,NA,72000.0,0.625,72450.0,50,5.0,3622.5,120,0", "Missing close"),
        # wrong column count
        ("2025-10-15,GOLDM,2025-11-05,21,10", "Expected 17 columns"),
        # unparseable number
        ("2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,abc,72000.0,0.625,72450.0,50,5.0,3622.5,120,0", "Not a number"),
    ],
)
def test_invalid_futures_rows_are_rejected_with_a_reason(row, message):
    result = table(B1_HEADER + row + "\n")

    assert result.accepted == 0
    assert any(message in r for r in reasons(result)), reasons(result)


def test_derived_column_disagreement_is_a_warning_not_a_silent_fix():
    row = "2025-10-15,GOLDM,2025-11-05,21,10,72000.0,72600.0,71900.0,72450.0,72000.0,9.999,99999.0,50,5.0,3622.5,120,0\n"
    result = table(B1_HEADER + row)

    assert result.accepted == 1
    assert str(result.rows[0]["close_per_10g"]) == "99999.0"  # kept as published
    assert result.row_warnings["close_per_10g differs from close x 10 / quote_unit_g"] == 1
    assert result.row_warnings["change_pct differs from (close - prev_close) / prev_close x 100"] == 1


def test_unit_mismatch_outside_the_verified_window_is_only_a_warning():
    row = "2026-10-23,GOLDM,2026-11-05,13,8,140802.0,141500.0,139772.0,140453.0,141802.0,-0.951,175566.25,39364,3936.4,553872.9,42924,0\n"
    result = table(B1_HEADER + row)

    assert result.accepted == 1
    assert result.row_warnings["expiry outside the verified specification window"] == 1
    assert any("contradicts the specification" in w for w in result.row_warnings)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (B2_HEADER + "2025-10-15,GOLDM,2025-10-29,XX,72000,500.0,520.0,480.0,510.0,505.0,10,51.0,30\n", "option_type must be one of"),
        (B2_HEADER + "2025-10-15,GOLDM,2025-10-29,CE,0,500.0,520.0,480.0,510.0,505.0,10,51.0,30\n", "strike must be positive"),
        (A1_HEADER + "2020,-5,1000.00,4.00,250,1000.0,NA,0\n", "lots_traded must be at least 0"),
        (A1_HEADER + "2020,1000,1000.00,4.00,250,1000.0,NA,2\n", "is_partial_year must be one of"),
        (A2_HEADER + "2020,GOLDM,0,100.0,0.4,250,NA\n", "non-zero with no lots traded"),
        (A2_HEADER + "2099,GOLDM,10,100.0,0.4,250,NA\n", "outside 2000"),
    ],
)
def test_invalid_option_and_annual_rows_are_rejected(data, message):
    result = table(data)

    assert result.accepted == 0
    assert any(message in r for r in reasons(result)), reasons(result)


def test_annual_consistency_checks_follow_the_package_formulas():
    result = table(A1_HEADER + A1_ROWS)

    assert result.accepted == 3
    assert result.row_warnings == {}
    assert result.coverage["missing_years"] == [2022]
    assert any("Partial years [2023]" in w for w in result.warnings)


def test_yoy_after_a_missing_year_must_be_na():
    rows = "2020,1000,1000.00,4.00,250,1000.0,NA,0\n2022,1000,1100.00,4.40,250,1100.0,10.0,0\n"
    result = table(A1_HEADER + rows)

    assert any("2021 is absent" in w for w in result.warnings)


# --- Duplicates and idempotent imports -----------------------------------------------------------


def test_exact_duplicates_are_dropped_and_conflicts_rejected():
    dup = B2_HEADER + B2_GOOD + B2_GOOD.splitlines()[0] + "\n"
    conflict = B2_HEADER + B2_GOOD + "2025-10-15,GOLDM,2025-10-29,CE,72000,500.0,520.0,480.0,511.0,505.0,10,51.0,30\n"

    assert table(dup).exact_duplicates_dropped == 1
    rejected = table(conflict)
    assert rejected.accepted == 1 and len(rejected.rejected) == 2
    assert all("Conflicting rows for key" in r for r in reasons(rejected))


def test_store_is_idempotent_and_checks_keys_across_files():
    store = SessionStore()
    limits = {"max_files": 10, "max_total_bytes": 10**9}
    store.add_package(table(A1_HEADER + A1_ROWS, "SYNTHETIC_a1.csv"), **limits)

    with pytest.raises(ValueError, match="already been imported"):
        store.add_package(table(A1_HEADER + A1_ROWS, "SYNTHETIC_a1_again.csv"), **limits)

    overlap = table(A1_HEADER + "2021,1000,1100.00,4.40,250,1100.0,10.0,0\n2024,1000,1300.00,5.20,250,1300.0,NA,0\n", "SYNTHETIC_a1_b.csv")
    store.add_package(overlap, **limits)
    assert overlap.cross_file_duplicates == 1 and overlap.accepted == 1

    clash = table(A1_HEADER + "2020,1000,1000.00,4.00,250,999.0,NA,0\n", "SYNTHETIC_a1_c.csv")
    store.add_package(clash, **limits)
    assert clash.accepted == 0 and "Conflicts with SYNTHETIC_a1.csv" in clash.rejected[0].reasons[0]


def test_synthetic_and_user_package_tables_are_not_mixed():
    store = SessionStore()
    store.add_package(table(A1_HEADER + A1_ROWS, "SYNTHETIC_a1.csv"), max_files=10, max_total_bytes=10**9)

    with pytest.raises(ValueError, match="cannot be combined"):
        store.add_package(table(A2_HEADER + "2020,GOLDM,10,100.0,0.4,250,NA\n", "user_a2.csv"), max_files=10, max_total_bytes=10**9)


# --- Through the API: separation of data types ---------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(frontend_dist=Path("does-not-exist")))


def post(client, text: str, name: str):
    return client.post("/api/datasets", params={"filename": name}, content=text.encode(), headers={"Content-Type": "text/csv"})


def test_options_and_annual_tables_never_become_futures_observations(client):
    for text, name in ((B2_HEADER + B2_GOOD, "SYNTHETIC_b2.csv"), (A1_HEADER + A1_ROWS, "SYNTHETIC_a1.csv")):
        body = post(client, text, name).json()
        assert body["stored"] is True and body["report"] is None

    status = client.get("/api/datasets").json()
    assert status["observations"] == 0 and status["files"] == []
    assert {p["table_id"]: p["kind"] for p in status["package"]} == {"B2": "options", "A1": "annual"}
    assert client.post("/api/research", json={}).status_code == 409  # still no futures data


def test_futures_table_feeds_research_through_the_existing_importer(client):
    body = post(client, B1_HEADER + B1_GOOD, "SYNTHETIC_b1.csv").json()

    assert body["package"]["accepted"] == 2  # every row kept in the package store
    assert body["report"]["accepted"] == 1  # GOLDM only: GOLD 1 kg is out of research scope
    assert body["report"]["skipped"] == {"symbol GOLD (out of scope)": 1}
    status = client.get("/api/datasets").json()
    assert status["observations"] == 1 and len(status["files"]) == 1
    assert post(client, B1_HEADER + B1_GOOD, "SYNTHETIC_b1.csv").status_code == 409  # idempotent


def test_package_rows_and_unknown_tables(client):
    post(client, A1_HEADER + A1_ROWS, "SYNTHETIC_a1.csv")
    body = client.get("/api/package/rows", params={"table": "a1"}).json()

    assert [r["year"] for r in body["rows"]] == [2020, 2021, 2023]
    assert body["rows"][0]["implied_avg_price_per_10g"] == "1000.0"  # decimal string, not a float
    assert client.get("/api/package/rows", params={"table": "B2"}).status_code == 404
    assert client.get("/api/package/rows", params={"table": "Z9"}).status_code == 404


def test_adding_reference_tables_does_not_change_research(client):
    client.post("/api/datasets/demo")
    before = client.post("/api/research", json={"horizon": 1}).json()
    post(client, A1_HEADER + A1_ROWS, "SYNTHETIC_a1.csv")
    after = client.post("/api/research", json={"horizon": 1}).json()

    strip = lambda r: {k: v for k, v in r.items() if k != "generated_at"}  # noqa: E731
    assert strip(before) == strip(after)


# --- HTML Bhavcopy (.xls that is really an HTML table) ------------------------------------------

HTML = """
<table border="1"><thead><tr><th>Date</th><th>Instrument Name</th><th>Symbol</th><th>Expiry Date</th>
<th>Option Type</th><th>Strike Price</th><th>Open</th><th>High</th><th>Low</th><th>Close</th>
<th>Previous Close</th><th>Volume(Lots)</th><th>Volume(In 000's)</th><th>Value(Lacs)</th>
<th>Open Interest(Lots)</th></tr></thead><tbody>
<tr><td>15 Oct 2025</td><td>FUTCOM</td><td>GOLDM</td><td>05NOV2025</td><td>-</td><td>0</td><td>72000.00</td>
<td>72600.00</td><td>71900.00</td><td>72450.00</td><td>72000.00</td><td>50</td><td>5.000 GRMS</td><td>3622.50</td><td>120</td></tr>
<tr><td>15 Oct 2025</td><td>OPTFUT</td><td>GOLDM</td><td>29OCT2025</td><td>CE</td><td>72000</td><td>500.00</td>
<td>520.00</td><td>480.00</td><td>510.00</td><td>505.00</td><td>10</td><td>1.000 GRMS</td><td>51.00</td><td>30</td></tr>
<tr><td>15 Oct 2025</td><td>FUTCOM</td><td>SILVER</td><td>05DEC2025</td><td>-</td><td>0</td><td>1</td><td>1</td><td>1</td>
<td>1</td><td>1</td><td>1</td><td>1 GRMS</td><td>1</td><td>1</td></tr>
</tbody></table>
"""


def test_html_table_bhavcopy_is_parsed_as_the_legacy_layout():
    result = import_bhavcopy_bytes(HTML.encode(), source_name="SYNTHETIC_BhavCopyDateWise_15102025.xls", today=TODAY)
    r = result.report

    assert r.layout_id == "mcx-bhavcopy-legacy" and r.layout_verified_against_real_file is True
    assert (r.rows_read, r.accepted) == (3, 1)
    assert r.skipped == {"option rows (out of scope)": 1, "symbol SILVER (out of scope)": 1}
    obs = result.observations[0]
    assert (obs.trade_date, obs.expiry, str(obs.close)) == (date(2025, 10, 15), date(2025, 11, 5), "72450.00")
    assert any("HTML table" in w for w in r.warnings)


# --- PDF block extraction ----------------------------------------------------------------------


def test_pdf_blocks_survive_page_breaks_and_crlf():
    text = (
        "===BEGIN A1_yearwise_GOLD_main.csv " + A1_HEADER.strip() + " 2020,1000,1000.00,4.00,250,1000.0,NA,0\r\n"
        "Gold Lens AI - MCX gold training dataset | Source: MCX India | Prepared 25 Oct 2026\r\n\r\nPage 18\r\n\f"
        "2021,1000,1100.00,4.40,250,1100.0,10.0,0 ===END A1_yearwise_GOLD_main.csv"
    )
    (t,) = extract_blocks(text)

    assert t.file_name == "A1_yearwise_GOLD_main.csv" and t.rows == 2
    assert table(t.csv_text).accepted == 2


def test_pdf_block_with_a_broken_row_fails_instead_of_guessing():
    text = "===BEGIN x.csv a,b,c 1,2,3 4,5 ===END x.csv"
    with pytest.raises(PackageExtractError, match="do not have 3 columns"):
        extract_blocks(text)


# --- Readiness and chronological splits ---------------------------------------------------------


def test_empty_session_is_insufficient_data():
    r = assess([])

    assert r.verdict is Verdict.INSUFFICIENT_DATA
    assert "no trained machine-learning model" in r.model
    assert r.split_plan is None and r.missing


def test_one_trading_date_is_insufficient_and_says_what_is_missing():
    result = import_bhavcopy_bytes(HTML.encode(), source_name="SYNTHETIC_one_day.xls", today=TODAY)
    r = assess([result])

    assert r.verdict is Verdict.INSUFFICIENT_DATA
    assert {c.id for c in r.checks if not c.passed} >= {"daily_history", "baseline", "walk_forward"}
    assert any("686 eligible trading dates" in m for m in r.missing)


def test_one_year_of_demo_data_is_exploratory_only():
    demo = import_bhavcopy_bytes(demo_csv_bytes(), source_name="SYNTHETIC_demo.csv")
    r = assess([demo])

    assert r.verdict is Verdict.EXPLORATORY_ONLY
    assert r.minimums.eligible_dates_per_pair == 686  # 20 signals x 6 dates, 3 folds + 30% holdout
    assert r.summary["best_pair_eligible_dates"] < 686


def test_thresholds_follow_the_configuration_not_fixed_numbers():
    demo = import_bhavcopy_bytes(demo_csv_bytes(), source_name="SYNTHETIC_demo.csv")
    small = ResearchConfig(horizon=1, min_events=2)

    assert assess([demo], config=small).verdict is Verdict.WALK_FORWARD_FEASIBLE


def test_split_plan_is_chronological_with_the_holdout_last():
    dates = [date(2025, 1, 1).fromordinal(date(2025, 1, 1).toordinal() + i) for i in range(100)]
    plan = split_plan(list(reversed(dates)), ResearchConfig())  # input order must not matter

    assert plan["holdout"] == [dates[70].isoformat(), dates[99].isoformat()]  # last 30%
    assert plan["development"] == [dates[0].isoformat(), dates[69].isoformat()]
    for fold in plan["folds"]:
        assert fold["train"][0] == dates[0].isoformat()
        assert fold["train"][1] < fold["test"][0]  # training ends before testing starts
        assert fold["test"][1] <= plan["development"][1] < plan["holdout"][0]  # holdout untouched


def test_split_plan_matches_the_windows_validation_actually_uses():
    demo = import_bhavcopy_bytes(demo_csv_bytes(), source_name="SYNTHETIC_demo.csv")
    config = replace(ResearchConfig(), horizon=1)
    series = [s for s in build_pair_series(demo.observations, config) if s.symbol_pair == "GOLDM/GOLDTEN"]
    validated = validate_symbol_pair(series, config)
    dates = sorted({p.trade_date for s in series for p in s.eligible_points})
    plan = split_plan(dates, config)

    assert plan["holdout"] == [d.isoformat() for d in validated.holdout]
    assert [f["test"] for f in plan["folds"]] == [[w.test[0].isoformat(), w.test[1].isoformat()] for w in validated.folds]


def test_unverified_expiry_range_is_by_date_not_by_symbol():
    """Regression: the range was taken from a list sorted by symbol, so it could miss the latest expiry."""
    rows = (
        "2026-10-23,GOLDM,2027-04-05,164,10,148382.0,148466.0,147093.0,147499.0,149038.0,-1.033,147499.0,142,14.2,2099.41,108,0\n"
        "2026-10-23,GOLDTEN,2026-10-30,7,10,141444.0,141872.0,140130.0,140832.0,142223.0,-0.978,140832.0,16895,168.95,23829.92,22198,0\n"
    )
    result = import_bhavcopy_bytes((B1_HEADER + rows).encode(), source_name="SYNTHETIC_b1.csv", today=TODAY)
    check = next(c for c in assess([result]).checks if c.id == "verified_specifications")

    assert "2026-10-30 to 2027-04-05" in check.detail


# --- Real package (only if extracted locally) -----------------------------------------------------

REAL = Path(__file__).parents[1] / "data" / "raw" / "mcx_gold_package_2026-10-23"


@pytest.mark.skipif(not REAL.is_dir(), reason="real package not extracted locally (backend/data/raw is ignored by Git)")
@pytest.mark.parametrize(
    ("name", "rows", "kind"),
    [
        ("A1_yearwise_GOLD_main.csv", 21, TableKind.ANNUAL),
        ("A2_yearwise_all_gold_contracts.csv", 131, TableKind.ANNUAL),
        ("B1_datewise_gold_futures.csv", 30, TableKind.FUTURES),
        ("B2_datewise_gold_options_traded.csv", 201, TableKind.OPTIONS),
    ],
)
def test_real_package_tables_import_without_rejections(name, rows, kind):
    result = import_package_table((REAL / name).read_bytes(), source_name=name)

    assert (result.table.kind, result.rows_read, result.accepted, len(result.rejected)) == (kind, rows, rows, 0)
