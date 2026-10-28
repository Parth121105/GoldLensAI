"""Lifecycle dates, contract phases and yearly volume. Rows are synthetic test values."""

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis.lifecycle import contract_calendar, contract_status, tender_start, weekdays_until, yearly_volume
from app.ingestion import import_bhavcopy_bytes
from app.main import create_app

HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)
A2_HEADER = "year,symbol,lots_traded,total_value_lakh,avg_daily_turnover_lakh,trading_days,premium_value_lakh\n"


def obs(*lines):
    text = HEADER + "".join(
        f"{d},FUTCOM,{s},{e},XX,0,{c},{c},{c},{c},{c},100,500,100\n" for d, s, e, c in lines
    )
    return import_bhavcopy_bytes(text.encode(), source_name="lc.csv", today=date(2026, 12, 31)).observations


def test_tender_period_counts_back_over_weekdays_including_expiry():
    assert tender_start(date(2026, 10, 30), 3) == date(2026, 10, 28)  # Fri -> Wed
    assert tender_start(date(2026, 11, 2), 3) == date(2026, 10, 29)  # Mon -> previous Thu
    assert tender_start(date(2025, 6, 30), 5) == date(2025, 6, 24)
    assert weekdays_until(date(2026, 10, 23), date(2026, 10, 30)) == 5


def test_phases_on_real_style_dates():
    rows = obs(("27-Oct-2026", "GOLDTEN", "30-Oct-2026", "142713"), ("28-Oct-2026", "GOLDTEN", "30-Oct-2026", "142800"),
               ("27-Oct-2026", "GOLDTEN", "30-Nov-2026", "144347"))
    phases = {(s.contract_id, s.trade_date): s.phase for s in contract_status(rows, expiry_buffer_days=7)}

    assert phases[("GOLDTEN-2026-10-30", date(2026, 10, 27))] == "near_expiry"
    assert phases[("GOLDTEN-2026-10-30", date(2026, 10, 28))] == "tender_period"
    assert phases[("GOLDTEN-2026-11-30", date(2026, 10, 27))] == "trading"


def test_calendar_uses_imported_expiries_and_verified_rules():
    rows = obs(("23-Oct-2026", "GOLDM", "05-Nov-2026", "140453"))
    cal = contract_calendar(rows)
    nov = next(e for e in cal if e.symbol == "GOLDM" and e.expiry_month == "2026-11")

    assert nov.contract_id == "GOLDM-2026-11-05" and nov.expiry_source == "imported data"
    assert nov.listing_date == date(2026, 5, 6)  # 6th of the May 2026 launch month
    assert nov.tender_trading_days == 3 and nov.tender_start == date(2026, 11, 3)
    assert all(e.expiry >= date(2026, 10, 23) for e in cal)
    ten_dec = next(e for e in cal if e.symbol == "GOLDTEN" and e.expiry_month == "2026-12")
    assert ten_dec.expiry_source.startswith("nominal") and ten_dec.making_charge


def test_yearly_volume_reads_and_validates_the_a2_table(tmp_path: Path):
    (tmp_path / "A2_yearwise_all_gold_contracts.csv").write_text(
        A2_HEADER + "2025,GOLDTEN,4282150,4980170.74,19302.99,258.0,NA\n2025,GOLD,1,1.0,1.0,258.0,NA\n", encoding="utf-8"
    )
    y = yearly_volume(tmp_path)

    assert y.problem is None and [(r.symbol, r.year) for r in y.rows] == [("GOLDTEN", 2025)]
    assert "No A2" in yearly_volume(tmp_path / "missing").problem


def test_lifecycle_endpoint():
    client = TestClient(create_app(frontend_dist=None))
    body = client.get("/api/lifecycle").json()
    assert body["kind"] == "empty" and body["calendar"] and body["status"] == []
