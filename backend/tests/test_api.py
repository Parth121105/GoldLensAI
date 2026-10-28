"""Dashboard API: instruments, dataset uploads, observations, research.

All uploaded content here is synthetic test data or hand-written test rows.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.demo import demo_csv_bytes
from app.main import create_app
from app.normalization import PriceField, RawQuote, normalize
from app.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
LEGACY = FIXTURES / "SYNTHETIC_mcx_legacy_15102025.csv"
HEADER = (
    "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,"
    "Previous Close,Volume(Lots),Value(Lacs),Open Interest(Lots)\n"
)
ROW = "15-Oct-2025,FUTCOM,GOLDTEN,31-Oct-2025,XX,0,72400,72600,72100,72450,72000,50,36.2,120\n"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(frontend_dist=None))


def upload(client, data: bytes, filename: str, **params):
    return client.post(
        "/api/datasets", params={"filename": filename, **params}, content=data,
        headers={"Content-Type": "text/csv"},
    )


# --- Instruments -------------------------------------------------------------------------


def test_instruments_come_from_the_specification_registry(client):
    body = client.get("/api/instruments").json()

    assert [i["symbol"] for i in body["instruments"]] == ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]
    assert body["comparison_basis"] == "INR per gram, 999 fineness equivalent"
    goldm = body["instruments"][0]["versions"][0]
    assert (goldm["quotation_base_g"], goldm["price_basis_fineness"]) == ("10", 995)
    assert goldm["expiry_from"] == "2025-09" and goldm["verification"] == "verified"
    assert goldm["sources"][0]["id"] == "gold-mini-november-2025-contract-onwards"
    assert goldm["tender_period_trading_days"] == 3 and goldm["launch_calendar"]
    assert body["instruments"][1]["first_trading_date"] == "2025-04-01"


# --- Dataset status and uploads --------------------------------------------------------------


def test_empty_session_status(client):
    body = client.get("/api/datasets").json()

    assert body["kind"] == "empty"
    assert body["files"] == [] and body["observations"] == 0
    assert "memory" in body["storage"] and "Lost" in body["storage"]


def test_upload_synthetic_fixture_reports_importer_results(client):
    r = upload(client, LEGACY.read_bytes(), LEGACY.name)
    body = r.json()

    assert r.status_code == 200 and body["stored"] is True
    rep = body["report"]
    assert (rep["rows_read"], rep["accepted"], rep["rejected_count"], rep["exact_duplicates_dropped"]) == (15, 6, 6, 1)
    assert rep["synthetic"] is True and "synthetic" in rep["provenance"].lower()
    assert {x["line_number"] for x in rep["rejected"]} == {7, 8, 9, 13, 14, 15}
    assert rep["skipped"] == {"option rows (out of scope)": 1, "symbol SILVER (out of scope)": 1}
    assert rep["row_warnings"]["expiry differs from documented rule"] == 1

    status = client.get("/api/datasets").json()
    assert status["kind"] == "synthetic"
    assert status["observations"] == 6
    assert len(status["contracts"]) == 6


def test_user_upload_is_never_labelled_official(client):
    body = upload(client, (HEADER + ROW).encode(), "bhavcopy_15102025.csv").json()

    assert body["stored"] is True
    assert body["report"]["synthetic"] is False
    assert "not verified" in body["report"]["provenance"]
    assert client.get("/api/datasets").json()["kind"] == "user_uploaded"


def test_synthetic_and_user_files_cannot_be_mixed(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    r = upload(client, (HEADER + ROW).encode(), "real.csv")

    assert r.status_code == 409
    assert "cannot be combined" in r.json()["detail"]


def test_identical_file_is_not_imported_twice(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    r = upload(client, LEGACY.read_bytes(), "SYNTHETIC_copy.csv")

    assert r.status_code == 409
    assert "already been imported" in r.json()["detail"]


@pytest.mark.parametrize("data", [b"", b"   \n\n  "])
def test_empty_upload_is_rejected(client, data):
    r = upload(client, data, "empty.csv")

    assert r.status_code == 400
    assert "empty" in r.json()["detail"]


def test_upload_size_limit():
    client = TestClient(create_app(frontend_dist=None, settings=Settings(max_upload_bytes=100)))
    r = upload(client, (HEADER + ROW).encode(), "big.csv")

    assert r.status_code == 413
    assert "100-byte" in r.json()["detail"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"Date,Symbol,Close\n15-Oct-2025,GOLDM,72000\n", "Required columns not found"),
        (b"\x00\x01\x02 binary \x00 junk", "not a readable CSV"),
        ((HEADER + ROW.replace("15-Oct-2025", "05/10/2025").replace("31-Oct-2025", "10/12/2025")).encode(),
         "ambiguous"),
    ],
)
def test_malformed_files_are_rejected_with_reasons(client, data, message):
    r = upload(client, data, "bad.csv")

    assert r.status_code == 422
    assert message in r.json()["detail"]
    assert client.get("/api/datasets").json()["kind"] == "empty"


def test_explicit_date_order_is_passed_to_the_importer(client):
    data = (HEADER + ROW.replace("15-Oct-2025", "05/10/2025").replace("31-Oct-2025", "12/12/2025")).encode()
    body = upload(client, data, "dmy.csv", date_order="DMY").json()

    assert body["stored"] is True
    assert body["report"]["date_order"] == "DMY"
    assert body["report"]["trade_date_from"] == "2025-10-05"


def test_file_with_no_supported_rows_is_reported_but_not_stored(client):
    data = (HEADER + ROW.replace("GOLDTEN", "SILVER")).encode()
    body = upload(client, data, "silver.csv").json()

    assert body["stored"] is False
    assert body["report"]["skipped"] == {"symbol SILVER (out of scope)": 1}
    assert client.get("/api/datasets").json()["kind"] == "empty"


def test_filename_is_reduced_to_a_display_name(client):
    body = upload(client, (HEADER + ROW).encode(), "../../etc/evil\x07name.csv").json()

    assert body["report"]["source_file"] == "evilname.csv"


def test_uploads_are_not_written_to_disk(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    upload(client, LEGACY.read_bytes(), LEGACY.name)

    assert list(tmp_path.iterdir()) == []


def test_session_file_limit():
    client = TestClient(create_app(frontend_dist=None, settings=Settings(max_files=1)))
    upload(client, (HEADER + ROW).encode(), "a.csv")
    r = upload(client, (HEADER + ROW.replace("72450", "72460")).encode(), "b.csv")

    assert r.status_code == 409
    assert "maximum of 1 files" in r.json()["detail"]


def test_clear_empties_session_and_research(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    client.post("/api/research", json={})
    body = client.delete("/api/datasets").json()

    assert body["kind"] == "empty"
    assert_no_research(client)


def test_synthetic_label_needs_the_full_prefix(client):
    """Regression: any name starting with "SYNTHETIC" used to be labelled synthetic."""
    body = upload(client, (HEADER + ROW).encode(), "SyntheticallyNamedRealBhav.csv").json()

    assert body["report"]["synthetic"] is False
    assert "not verified" in body["report"]["provenance"]
    assert client.get("/api/datasets").json()["kind"] == "user_uploaded"


def test_demo_text_needs_the_demo_bytes_not_just_its_name(client):
    """Regression: a user file named like the demo was described as the generated demo."""
    body = upload(client, (HEADER + ROW).encode(), "SYNTHETIC_demo_dataset.csv").json()

    assert body["report"]["synthetic"] is True  # the SYNTHETIC_ prefix rule still applies
    assert "invented" not in body["report"]["provenance"]
    assert "SYNTHETIC_" in body["report"]["provenance"]


def test_demo_dataset_is_labelled_synthetic(client):
    body = client.post("/api/datasets/demo").json()

    assert body["stored"] is True
    assert body["report"]["synthetic"] is True
    assert "invented" in body["report"]["provenance"]
    assert client.get("/api/datasets").json()["kind"] == "synthetic"


# --- Observations ---------------------------------------------------------------------------------


def test_observations_carry_raw_and_backend_normalized_prices(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    body = client.get("/api/observations", params={"symbol": "GOLDM"}).json()

    obs = next(o for o in body["observations"] if o["expiry"] == "2025-11-05")
    assert obs["close"] == "72300"
    expected = normalize(RawQuote("GOLDM", obs_date("2025-11-05"), obs_date("2025-10-15"),
                                  Decimal("72300"), PriceField.CLOSE)).inr_per_gram_999
    assert Decimal(obs["normalized"]["inr_per_gram_999"]) == expected
    assert obs["normalized"]["formula"] == "72300 / 10 g * 999/995"
    assert obs["source_file"] == LEGACY.name and obs["line_number"] == 2
    assert body["trade_dates"] == ["2025-10-15"]


def test_observation_with_unverified_specification_is_not_normalized(client):
    # No specification PDF covers GOLDPETAL expiring before April 2025.
    row = "03-Mar-2025,FUTCOM,GOLDPETAL,31-Mar-2025,XX,0,7200,7210,7190,7205,7200,10,0.7,5\n"
    upload(client, (HEADER + row).encode(), "march.csv")
    (obs,) = client.get("/api/observations").json()["observations"]

    assert obs["normalized"] is None
    assert "No verified specification" in obs["normalization_error"]


def test_observation_filters(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    body = client.get("/api/observations", params=[("symbol", "goldten"), ("symbol", "GOLDPETAL"),
                                                   ("expiry", "2025-10-31")]).json()

    assert {o["contract_id"] for o in body["observations"]} == {"GOLDTEN-2025-10-31", "GOLDPETAL-2025-10-31"}


# --- Research ---------------------------------------------------------------------------------------


def assert_no_research(client):
    r = client.get("/api/research")
    assert r.status_code == 200 and r.json() is None


def test_research_requires_data(client):
    r = client.post("/api/research", json={})

    assert r.status_code == 409
    assert_no_research(client)


def test_insufficient_data_produces_no_fabricated_results(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    body = client.post("/api/research", json={}).json()

    assert body["kind"] == "synthetic"
    assert body["pairs"], "pairs with comparable contracts should be listed"
    for pair in body["pairs"]:
        assert pair["verdict"] == "insufficient_data"
        assert pair["final"] is None or pair["final"]["signals"]["mean_gross_bps"] is None
        assert "not validated" in pair["display_params"]["selected_by"]
    assert body["costs"]["round_trip_bps"] is None
    assert len(body["costs"]["unknown_components"]) == 4


def test_costs_stay_unknown_unless_supplied(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    partial = client.post("/api/research", json={"costs": {"brokerage": {"bps_per_leg_side": 1}}}).json()
    full = client.post("/api/research", json={"costs": {
        name: {"bps_per_leg_side": 0.5, "source": "test"} for name in
        ("brokerage", "exchange_transaction_charges", "statutory_taxes_and_levies", "slippage")
    }}).json()

    assert partial["costs"]["round_trip_bps"] is None
    assert "brokerage" not in partial["costs"]["unknown_components"]
    assert "user assumption" in partial["costs"]["components"][0]["label"]
    assert full["costs"]["round_trip_bps"] == pytest.approx(8.0)


@pytest.mark.parametrize(
    "payload",
    [{"costs": {"made_up_fee": {"bps_per_leg_side": 1}}}, {"costs": {"brokerage": {"bps_per_leg_side": -1}}},
     {"horizon": 0}],
)
def test_invalid_research_requests(client, payload):
    upload(client, LEGACY.read_bytes(), LEGACY.name)

    assert client.post("/api/research", json=payload).status_code == 422


def test_research_result_is_discarded_when_data_changes(client):
    upload(client, LEGACY.read_bytes(), LEGACY.name)
    client.post("/api/research", json={})
    assert client.get("/api/research").status_code == 200

    upload(client, (FIXTURES / "SYNTHETIC_udiff_2025-10-16.csv").read_bytes(), "SYNTHETIC_udiff.csv")
    assert_no_research(client)


def test_end_to_end_upload_normalize_research(client):
    """Upload a synthetic CSV through the API and get real engine output back."""
    r = upload(client, demo_csv_bytes(), "SYNTHETIC_e2e_upload.csv")
    assert r.json()["stored"] is True and r.json()["report"]["rejected_count"] == 0

    obs = client.get("/api/observations", params={"symbol": "GOLDPETAL"}).json()["observations"]
    assert obs and all(o["normalized"] for o in obs)

    body = client.post("/api/research", json={"horizon": 1}).json()
    verdicts = {p["symbol_pair"]: p["verdict"] for p in body["pairs"]}
    # One year of daily data gives fewer than min_events independent holdout signals per
    # pair once simultaneous expiries are counted once, so nothing can be supported.
    assert len(verdicts) == 6
    assert set(verdicts.values()) == {"insufficient_data"}

    pair = next(p for p in body["pairs"] if p["symbol_pair"] == "GOLDM/GOLDPETAL")
    assert 0 < pair["final"]["signals"]["n"] < body["config"]["min_events"]
    assert any("at least 20 are required" in r for r in pair["reasons"])
    assert pair["holdout_from"] > pair["development_to"]
    assert all(f["status"] != "cost_adjusted_candidate" for f in pair["findings"])
    finding = pair["findings"][0]
    assert finding["leg_a"]["source_file"] == "SYNTHETIC_e2e_upload.csv"
    assert finding["leg_a"]["line_number"] > 1
    assert {s["comparison_type"] for s in pair["series"]} == {"cross_expiry"}
    assert client.get("/api/research").json()["generated_at"] == body["generated_at"]


def obs_date(text: str):
    from datetime import date
    return date.fromisoformat(text)


def test_research_is_not_saved_when_the_data_changed_during_the_run():
    """Regression: the "data unchanged?" check and the write were two separate steps."""
    from app.store import SessionStore
    from app.ingestion import import_bhavcopy_bytes

    store = SessionStore()
    first = import_bhavcopy_bytes(LEGACY.read_bytes(), source_name=LEGACY.name)
    store.add(first, max_files=10, max_total_bytes=10**9)
    analysed = store.snapshot()

    store.clear()  # the data changes while research is computing
    assert store.save_research({"stale": True}, analysed) is False
    assert store.research is None

    store.add(first, max_files=10, max_total_bytes=10**9)
    assert store.save_research({"fresh": True}, analysed) is True
    assert store.research == {"fresh": True}
