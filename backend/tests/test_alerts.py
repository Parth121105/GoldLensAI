"""Alerts stay quiet without history and fire only on an unusual move. Synthetic test values."""

import math
import random
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.analysis.alerts import alerts
from app.analysis.relative_value import relative_value
from app.ingestion import import_bhavcopy_bytes
from app.main import create_app

HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)


def history(n_days: int, last_day_shock_bps: float = 0.0, basis_bps: float = 35.0):
    """GOLDTEN and GOLDPETAL, same expiry, with a constant basis and small noise."""
    rng = random.Random(7)
    rows, d, out = [], date(2026, 1, 5), []
    while len(out) < n_days:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    for i, day in enumerate(out):
        ten = 14000.0
        shock = last_day_shock_bps if i == len(out) - 1 else 0.0
        petal = ten * math.exp((basis_bps + rng.gauss(0, 1.0) + shock) / 1e4)
        for sym, px in (("GOLDTEN", f"{ten * 10:.0f}"), ("GOLDPETAL", f"{petal:.2f}")):
            rows.append(f"{day:%d-%b-%Y},FUTCOM,{sym},31-Dec-2026,XX,0,{px},{px},{px},{px},{px},100,500,100\n")
    obs = import_bhavcopy_bytes((HEADER + "".join(rows)).encode(), source_name="al.csv", today=date(2026, 12, 1)).observations
    return relative_value(obs)


def test_a_persistent_gap_never_alerts():
    r = alerts(history(30))
    assert r.pairs_with_baseline == 1 and r.alerts == []


def test_quiet_without_enough_history():
    r = alerts(history(5, last_day_shock_bps=60))
    assert r.pairs_with_baseline == 0 and r.alerts == []


def test_an_unusual_move_beyond_costs_alerts():
    (alert,) = alerts(history(30, last_day_shock_bps=40)).alerts
    assert abs(alert.move_bps) > alert.cost_bps and abs(alert.z) >= 2.5


def test_small_move_inside_costs_does_not_alert():
    assert alerts(history(30, last_day_shock_bps=6)).alerts == []


def test_endpoint_says_no_meaningful_signal_by_default():
    body = TestClient(create_app(frontend_dist=None)).get("/api/alerts").json()
    assert body["quiet"] is True and body["headline"] == "No meaningful signal"
