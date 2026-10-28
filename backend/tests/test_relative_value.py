"""Relative value per day. All rows are synthetic test values in the real MCX layout."""

import math
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.analysis.relative_value import LiquidityFilter, relative_value
from app.ingestion import import_bhavcopy_bytes
from app.main import create_app

HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)
TODAY = date(2026, 10, 28)


def rows(*lines):
    return import_bhavcopy_bytes((HEADER + "".join(lines)).encode(), source_name="rv.csv", today=TODAY).observations


def line(symbol, expiry, close, lots=100, value=500, oi=100, day="23-Oct-2026"):
    return f"{day},FUTCOM,{symbol},{expiry},XX,0,{close},{close},{close},{close},{close},{lots},{value},{oi}\n"


def test_contracts_are_normalized_and_paired_with_the_nearest_expiry():
    obs = rows(
        line("GOLDM", "05-Nov-2026", "140453"),   # 995 per 10 g
        line("GOLDM", "04-Dec-2026", "141954"),
        line("GOLDTEN", "30-Oct-2026", "140832"),  # 999 per 10 g
        line("GOLDTEN", "30-Nov-2026", "142260"),
    )
    (day,) = relative_value(obs)

    goldm_nov = next(q for q in day.contracts if q.contract_id == "GOLDM-2026-11-05")
    assert goldm_nov.inr_per_gram_999 == Decimal("14045.3") * 999 / 995
    pairs = {(p.contract_a, p.contract_b): p for p in day.pairs}
    # GOLDM 5 Nov pairs with GOLDTEN 30 Oct (6 days), not 30 Nov (25 days).
    assert set(pairs) == {("GOLDM-2026-11-05", "GOLDTEN-2026-10-30"), ("GOLDM-2026-12-04", "GOLDTEN-2026-11-30")}
    p = pairs[("GOLDM-2026-11-05", "GOLDTEN-2026-10-30")]
    assert p.expiry_gap_days == 6
    assert math.isclose(p.gap_bps, 10_000 * math.log(float(goldm_nov.inr_per_gram_999) / 14083.2), rel_tol=1e-9)
    assert p.location_basis is None


def test_goldpetal_gap_carries_the_location_basis():
    obs = rows(line("GOLDTEN", "30-Nov-2026", "142260"), line("GOLDPETAL", "30-Nov-2026", "14297"))
    (pair,) = relative_value(obs)[0].pairs

    assert "Ex-Mumbai" in pair.location_basis and "not adjusted" in pair.location_basis


def test_thin_contracts_are_never_tradeable():
    obs = rows(
        line("GOLDTEN", "31-Mar-2027", "149912", lots=158, value=235.75, oi=370),
        line("GOLDGUINEA", "31-Mar-2027", "120141", lots=52, value=62.22, oi=211),
    )
    (day,) = relative_value(obs, liquidity=LiquidityFilter())
    guinea = next(q for q in day.contracts if q.symbol == "GOLDGUINEA")

    assert guinea.thin and "below Rs 100 lakh" in guinea.thin_reasons[0]
    (pair,) = day.pairs
    assert not pair.tradeable and "GOLDGUINEA-2027-03-31 is thin" in pair.not_tradeable_reasons[0]


def test_contracts_near_expiry_are_not_tradeable():
    obs = rows(
        line("GOLDTEN", "30-Oct-2026", "142713", day="27-Oct-2026"),
        line("GOLDGUINEA", "30-Oct-2026", "114413", day="27-Oct-2026"),
    )
    (pair,) = relative_value(obs)[0].pairs

    assert not pair.tradeable and any("tender/delivery buffer" in r for r in pair.not_tradeable_reasons)


def test_unverified_contracts_are_shown_but_not_paired():
    obs = rows(line("GOLDTEN", "30-Jul-2027", "150000"), line("GOLDGUINEA", "30-Jul-2027", "120000"))
    (day,) = relative_value(obs)

    assert all(q.inr_per_gram_999 is None and q.error for q in day.contracts)
    assert day.pairs == []


def test_endpoint_reports_kind_and_disclaimers():
    client = TestClient(create_app(frontend_dist=None))
    data = (HEADER + line("GOLDTEN", "30-Nov-2026", "142260") + line("GOLDPETAL", "30-Nov-2026", "14297")).encode()
    client.post("/api/datasets", params={"filename": "rv.csv"}, content=data, headers={"Content-Type": "text/csv"})

    body = client.get("/api/relative-value").json()
    assert body["kind"] == "user_uploaded" and body["synthetic"] is False
    assert any("not guaranteed fill prices" in d for d in body["disclaimers"])
    assert any("not market depth" in d for d in body["disclaimers"])
    (day,) = body["days"]
    assert day["pairs"][0]["location_basis"]
