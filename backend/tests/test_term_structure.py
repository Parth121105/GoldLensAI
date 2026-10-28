"""Futures curves, the split of day-to-day moves, carry-adjusted gaps and the assumptions file.

All prices are synthetic test values.
"""

import json
import math
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.analysis.relative_value import relative_value
from app.analysis.term_structure import term_structure
from app.assumptions import DEFAULT_ASSUMPTIONS_FILE, default_assumptions, load_assumptions
from app.ingestion import import_bhavcopy_bytes
from app.main import create_app

HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)
TODAY = date(2026, 12, 31)
CARRY_PER_DAY = 0.0003  # 3 bps a day


def line(day, symbol, expiry, close):
    return f"{day},FUTCOM,{symbol},{expiry},XX,0,{close},{close},{close},{close},{close},100,500,100\n"


def curve_rows(day: date, spot: float, symbols=("GOLDTEN", "GOLDGUINEA")):
    """Prices on an exact exponential curve: per-gram spot * exp(carry * days to expiry)."""
    out = []
    expiries = [date(2026, 11, 30), date(2026, 12, 31), date(2027, 1, 29)]
    for symbol in symbols:
        base = {"GOLDTEN": 10, "GOLDGUINEA": 8}[symbol]
        for e in expiries:
            per_gram = spot * math.exp(CARRY_PER_DAY * (e - day).days)
            out.append(line(f"{day:%d-%b-%Y}", symbol, f"{e:%d-%b-%Y}", f"{per_gram * base:.2f}"))
    return out


def snapshot(*days):
    text = HEADER + "".join(r for d, spot in days for r in curve_rows(d, spot))
    obs = import_bhavcopy_bytes(text.encode(), source_name="ts.csv", today=TODAY).observations
    return relative_value(obs)


def test_curve_slope_recovers_the_carry():
    ts = term_structure(snapshot((date(2026, 10, 23), 14000.0)))

    for curve in ts.curves:
        assert curve.slope_per_day == pytest.approx(CARRY_PER_DAY, rel=1e-3)
        assert curve.annualised_carry_pct == pytest.approx((math.exp(CARRY_PER_DAY * 365) - 1) * 100, rel=1e-2)
        assert all(abs(p.residual_bps) < 0.1 for p in curve.points)


def test_move_split_adds_up_and_isolates_the_gold_move():
    ts = term_structure(snapshot((date(2026, 10, 23), 14000.0), (date(2026, 10, 27), 14000.0 * math.exp(0.01))))

    assert ts.gold_move_bps[(date(2026, 10, 23), date(2026, 10, 27))] == pytest.approx(100 + 0.0, abs=0.5)
    for s in ts.splits:
        parts = s.gold_move_bps + s.roll_down_bps + s.curve_change_bps + s.residual_bps
        assert parts == pytest.approx(s.total_bps, abs=1e-9)
        # Four days closer to expiry on an unchanged 3 bps/day curve: -12 bps of roll-down.
        assert s.roll_down_bps == pytest.approx(-12, abs=0.1)
        assert abs(s.curve_change_bps) < 0.5 and abs(s.residual_bps) < 0.5


def test_carry_adjustment_removes_the_expiry_difference():
    day = date(2026, 10, 23)
    spot = 14000.0
    rows = curve_rows(day, spot, symbols=("GOLDTEN",))
    # GOLDM expiring 5 Dec 2026, on the same curve but quoted per 10 g at 995.
    goldm = spot * math.exp(CARRY_PER_DAY * (date(2026, 12, 4) - day).days) * 10 * 995 / 999
    rows += [line("23-Oct-2026", "GOLDM", "04-Dec-2026", f"{goldm:.2f}"),
             line("23-Oct-2026", "GOLDM", "05-Jan-2027", f"{goldm * math.exp(CARRY_PER_DAY * 32):.2f}")]
    obs = import_bhavcopy_bytes((HEADER + "".join(rows)).encode(), source_name="c.csv", today=TODAY).observations
    (snap,) = relative_value(obs)

    pair = next(p for p in snap.pairs if p.contract_a == "GOLDM-2026-12-04")
    assert pair.contract_b == "GOLDTEN-2026-11-30" and pair.expiry_gap_days == 4
    assert pair.gap_bps == pytest.approx(12, abs=0.2)  # 4 days of 3 bps carry
    assert pair.carry_adjusted_gap_bps == pytest.approx(0, abs=0.2)
    same = [p for p in snap.pairs if p.expiry_gap_days == 0]
    assert all(p.carry_adjusted_gap_bps is None for p in same)


def test_assumptions_file_drives_the_liquidity_filter(tmp_path):
    raw = json.loads(DEFAULT_ASSUMPTIONS_FILE.read_text(encoding="utf-8"))
    raw["liquidity"]["min_traded_value_lakh"]["value"] = "1000"
    path = tmp_path / "a.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    custom = load_assumptions(path)

    obs = import_bhavcopy_bytes((HEADER + line("23-Oct-2026", "GOLDTEN", "30-Nov-2026", "142260")).encode(),
                                source_name="l.csv", today=TODAY).observations
    assert not relative_value(obs)[0].contracts[0].thin  # 500 lakh passes the default Rs 1 crore
    assert relative_value(obs, assumptions=custom)[0].contracts[0].thin


def test_default_assumptions_are_labelled():
    a = default_assumptions()
    assert a.min_traded_value_lakh == Decimal("100") and a.expiry_buffer_days == 7
    assert all(e.why and e.unit for e in a.entries.values())


def test_endpoints_expose_curves_and_assumptions():
    client = TestClient(create_app(frontend_dist=None))
    text = HEADER + "".join(curve_rows(date(2026, 10, 23), 14000.0) + curve_rows(date(2026, 10, 27), 14100.0))
    client.post("/api/datasets", params={"filename": "ts.csv"}, content=text.encode(),
                headers={"Content-Type": "text/csv"})

    ts = client.get("/api/term-structure").json()
    assert len(ts["curves"]) == 4 and len(ts["splits"]) == 6
    rv = client.get("/api/relative-value").json()["liquidity"]
    assert "3 trading days" in rv["official_tender_period"]
    assert {a["key"] for a in rv["assumptions"]} >= {"liquidity.min_traded_value_lakh", "lifecycle.expiry_buffer_days"}
