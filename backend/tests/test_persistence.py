"""Imports saved to disk: survive a restart, never duplicated, cleared with the session.

All content is synthetic test data. Synthetic files are never saved, so these tests upload
the synthetic bytes under a name without the SYNTHETIC_ prefix, which the app treats as a
real file. A "restart" is a new app built over the same folder.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.demo import demo_csv_bytes
from app.ingestion import import_bhavcopy_bytes
from app.main import create_app
from app.persistence import FORMAT_VERSION, ImportArchive, _result_to_dict
from app.settings import DEFAULT_STORE_DIR, Settings
from app.store import AlreadyHeldError, SessionStore

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
LEGACY = FIXTURES / "SYNTHETIC_mcx_legacy_15102025.csv"
AS_REAL = "mcx_legacy_15102025.csv"  # same bytes, labelled as a real upload


def app_over(folder: Path) -> TestClient:
    return TestClient(create_app(frontend_dist=None, settings=Settings(store_dir=folder)))


def upload(client: TestClient, data: bytes, filename: str):
    return client.post("/api/datasets", params={"filename": filename}, content=data, headers={"Content-Type": "text/csv"})


def test_imports_survive_a_restart_with_identical_observations(tmp_path):
    first = app_over(tmp_path)
    assert upload(first, LEGACY.read_bytes(), AS_REAL).json()["stored"] is True
    before = first.get("/api/datasets").json()
    obs_before = first.get("/api/observations").json()["observations"]

    restarted = app_over(tmp_path)
    after = restarted.get("/api/datasets").json()

    assert after["observations"] == before["observations"] > 0
    assert after["files"] == before["files"]  # same report, same provenance, same import time
    assert after["contracts"] == before["contracts"]
    assert restarted.get("/api/observations").json()["observations"] == obs_before
    assert "saved on the server's disk" in after["storage"]


def test_only_parsed_rows_are_saved_not_the_uploaded_file(tmp_path):
    client = app_over(tmp_path)
    upload(client, LEGACY.read_bytes(), AS_REAL)

    (saved,) = list(tmp_path.glob("*.json"))
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert saved.stem == payload["report"]["source_sha256"]
    assert payload["format_version"] == FORMAT_VERSION
    assert set(payload) == {"format_version", "report", "observations"}
    assert {o["symbol"] for o in payload["observations"]} <= {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}
    # Prices round-trip as exact decimal strings, never floats.
    assert all(isinstance(o["close"], str) for o in payload["observations"])


def test_reimporting_the_same_file_after_a_restart_is_refused(tmp_path):
    upload(app_over(tmp_path), LEGACY.read_bytes(), AS_REAL)

    restarted = app_over(tmp_path)
    r = upload(restarted, LEGACY.read_bytes(), AS_REAL)

    assert r.status_code == 409 and "already been imported" in r.json()["detail"]
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert len(restarted.get("/api/datasets").json()["files"]) == 1


def test_a_redownloaded_day_with_different_bytes_but_the_same_rows_is_refused(tmp_path):
    client = app_over(tmp_path)
    upload(client, LEGACY.read_bytes(), AS_REAL)
    held = client.get("/api/datasets").json()["observations"]

    # Same rows, different bytes: the other line-ending style, as a re-saved download might have.
    raw = LEGACY.read_bytes()
    resaved = raw.replace(b"\r\n", b"\n") if b"\r\n" in raw else raw.replace(b"\n", b"\r\n")
    assert resaved != raw
    r = upload(app_over(tmp_path), resaved, "mcx_legacy_15102025_redownload.csv")

    assert r.status_code == 409 and "already held with identical values" in r.json()["detail"]
    status = app_over(tmp_path).get("/api/datasets").json()
    assert status["observations"] == held and len(status["files"]) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_clearing_the_session_deletes_the_saved_imports(tmp_path):
    client = app_over(tmp_path)
    upload(client, LEGACY.read_bytes(), AS_REAL)
    assert list(tmp_path.glob("*.json"))

    client.delete("/api/datasets")

    assert not list(tmp_path.glob("*.json"))
    assert app_over(tmp_path).get("/api/datasets").json()["kind"] == "empty"


def test_research_reruns_automatically_and_identically_after_a_restart(tmp_path):
    first = app_over(tmp_path)
    upload(first, demo_csv_bytes(), "demo_as_real.csv")
    before = first.post("/api/research", json={"horizon": 3}).json()

    restarted = app_over(tmp_path)
    # Research results stay in memory; real data gets a fresh run with the assumed costs at startup.
    auto = restarted.get("/api/research").json()
    assert auto["config"]["horizon"] == 5 and auto["costs"]["round_trip_bps"] == 9.6
    after = restarted.post("/api/research", json={"horizon": 3}).json()

    strip = lambda r: {k: v for k, v in r.items() if k != "generated_at"}  # noqa: E731
    assert strip(after) == strip(before)


def test_an_unreadable_saved_file_is_skipped_not_guessed(tmp_path):
    upload(app_over(tmp_path), LEGACY.read_bytes(), AS_REAL)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "future.json").write_text(json.dumps({"format_version": 999}), encoding="utf-8")

    status = app_over(tmp_path).get("/api/datasets").json()

    assert len(status["files"]) == 1  # the good import loads; the two bad files are ignored


def test_a_failed_disk_write_refuses_the_upload_and_keeps_memory_unchanged(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")  # the store folder path is a file, so writing fails
    client = app_over(blocker)

    r = upload(client, LEGACY.read_bytes(), AS_REAL)

    assert r.status_code == 409 and "could not be saved to disk" in r.json()["detail"]
    assert client.get("/api/datasets").json()["files"] == []


def test_store_round_trips_every_field(tmp_path):
    result = import_bhavcopy_bytes(LEGACY.read_bytes(), source_name=AS_REAL)
    archive = ImportArchive(tmp_path)
    archive.save(result)

    (loaded,) = archive.load_all()

    assert loaded.observations == result.observations
    assert loaded.report == result.report
    assert isinstance(loaded.observations[0].close, Decimal)


def test_store_refuses_a_file_whose_rows_are_all_held():
    result = import_bhavcopy_bytes(LEGACY.read_bytes(), source_name=AS_REAL)
    copy = import_bhavcopy_bytes(LEGACY.read_bytes() + b"\n", source_name="copy.csv")
    store = SessionStore()
    store.add(result, max_files=10, max_total_bytes=10**9)

    with pytest.raises(AlreadyHeldError):
        store.add(copy, max_files=10, max_total_bytes=10**9)
    assert len(store.imports) == 1


def test_settings_store_folder_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLDLENS_STORE_DIR", str(tmp_path))
    assert Settings.from_env().store_dir == tmp_path
    monkeypatch.setenv("GOLDLENS_STORE_DIR", "off")
    assert Settings.from_env().store_dir is None
    monkeypatch.setenv("GOLDLENS_STORE_DIR", "")
    assert Settings.from_env().store_dir == DEFAULT_STORE_DIR
    assert Settings().store_dir is None  # built directly: memory only


# --- Synthetic data never reaches the real-data store ------------------------------------------


def test_synthetic_uploads_and_the_demo_are_never_written_to_disk(tmp_path):
    client = app_over(tmp_path)
    assert upload(client, LEGACY.read_bytes(), LEGACY.name).json()["report"]["synthetic"] is True
    client.delete("/api/datasets")
    client.post("/api/datasets/demo")

    assert not list(tmp_path.glob("*.json"))
    assert "saved on the server's disk" not in client.get("/api/datasets").json()["storage"]
    assert app_over(tmp_path).get("/api/datasets").json()["kind"] == "empty"


def test_a_synthetic_file_found_on_disk_is_not_reloaded(tmp_path):
    synthetic = import_bhavcopy_bytes(LEGACY.read_bytes(), source_name=LEGACY.name)
    payload = {"format_version": FORMAT_VERSION, **_result_to_dict(synthetic)}
    (tmp_path / "planted.json").write_text(json.dumps(payload), encoding="utf-8")
    upload(app_over(tmp_path), LEGACY.read_bytes(), AS_REAL)

    status = app_over(tmp_path).get("/api/datasets").json()
    assert status["kind"] == "user_uploaded" and len(status["files"]) == 1


def test_archive_refuses_to_save_synthetic_data(tmp_path):
    with pytest.raises(ValueError, match="never saved"):
        ImportArchive(tmp_path).save(import_bhavcopy_bytes(LEGACY.read_bytes(), source_name=LEGACY.name))


def test_real_data_on_disk_blocks_the_demo_until_cleared(tmp_path):
    upload(app_over(tmp_path), LEGACY.read_bytes(), AS_REAL)

    r = app_over(tmp_path).post("/api/datasets/demo")

    assert r.status_code == 409 and "cannot be combined" in r.json()["detail"]


# --- Committed real-data seed ------------------------------------------------------------------


def test_empty_store_is_seeded_once_and_not_overwritten(tmp_path):
    from app.settings import DEFAULT_SEED_DIR

    store = tmp_path / "store"
    app = TestClient(create_app(frontend_dist=None, settings=Settings(store_dir=store, seed_dir=DEFAULT_SEED_DIR)))
    status = app.get("/api/datasets").json()
    assert status["kind"] == "user_uploaded" and status["observations"] == 48
    assert len(list(store.glob("*.json"))) == len(list(DEFAULT_SEED_DIR.glob("*.json"))) == 2

    app.delete("/api/datasets")
    (store / "keep.txt").write_text("x", encoding="utf-8")
    assert ImportArchive(store).seed_if_empty(tmp_path / "nothing") == 0


def test_seed_holds_only_real_rows():
    from app.settings import DEFAULT_SEED_DIR

    loaded = ImportArchive(DEFAULT_SEED_DIR).load_all()
    assert len(loaded) == 2 and not any(r.report.synthetic for r in loaded)


def test_real_uploads_get_research_without_a_run_and_synthetic_ones_do_not(tmp_path):
    client = app_over(tmp_path / "store")
    upload(client, LEGACY.read_bytes(), AS_REAL)
    assert client.get("/api/research").json()["kind"] == "user_uploaded"

    client.delete("/api/datasets")
    client.post("/api/datasets/demo")
    assert client.get("/api/research").json() is None  # synthetic research is left to the user


def test_bundled_seed_files_are_labelled_real_and_browser_uploads_unverified(tmp_path):
    seed = tmp_path / "seed"
    upload(app_over(seed), LEGACY.read_bytes(), AS_REAL)  # builds a seed folder of one saved import
    settings = Settings(store_dir=tmp_path / "store", seed_dir=seed)
    client = TestClient(create_app(frontend_dist=None, settings=settings))

    status = client.get("/api/datasets").json()
    assert status["bundled"] is True and status["files"][0]["bundled"] is True
    assert status["source_label"].startswith("Real MCX Bhavcopy data · ")
    assert client.get("/api/research").json() is not None

    upload(client, demo_csv_bytes(), "another_day.csv")
    status = client.get("/api/datasets").json()
    assert status["bundled"] is False
    assert status["source_label"] == "User-uploaded · origin unverified"
    assert [f["bundled"] for f in status["files"]] == [True, False]
