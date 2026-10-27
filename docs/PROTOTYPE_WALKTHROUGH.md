# GoldLensAI prototype walkthrough

*Written 25 Oct 2026, against the working tree on top of commit `83c0602`.*

This document is for developers and for the project owner. Each statement is
labelled with how it is known:

- **Verified**: checked against the source code and a passing test or a command
  run on 25 Oct 2026. The test or command is named.
- **Unverified**: an assumption that has not been confirmed. Most of these
  concern real MCX files.
- **Recommendation**: suggested next work. Not implemented.

---

## 1. Current prototype status

### Works (verified)

| Capability | Evidence |
|---|---|
| Backend test suite | 231 tests pass (section 8) |
| Frontend lint and production build | Pass (section 8) |
| Dashboard with five screens served by FastAPI | 17/17 browser checks on the production-style server (previous task, 25 Oct 2026) |
| CSV upload → validation → import → normalization → research → display | `test_api.py::test_end_to_end_upload_normalize_research`; browser checks |
| Clear empty states, and an "unavailable" state when the server is down | Browser checks (previous task) |
| Synthetic data is labelled and never presented as MCX data | `test_api.py::test_demo_dataset_is_labelled_synthetic`, `::test_user_upload_is_never_labelled_official` |
| `/api` routing preserved when the frontend is served | `test_frontend_serving.py` (42 tests) |

### Does not work, or not proven

| Gap | Status |
|---|---|
| Import of a **genuine** MCX Bhavcopy | **Unverified.** No genuine file exists in the repository, and none has been tested. |
| Normalization or research on contracts expiring **after Jun/Jul 2026** | **Blocked by design.** Their specifications are unverified (section 7.4). |
| Data that survives a restart | Not implemented. Storage is memory only. |
| Separate sessions per user | Not implemented. One shared session. |
| Frontend unit tests | None. No test framework is installed. The frontend is covered by browser checks run from outside the repo. |

**Genuine MCX data:** none in the repository (`backend/data/raw/` is ignored by Git). Update,
26 Oct 2026: one MCX date-wise download for 23 Oct 2026 and a user-supplied data package were
imported and audited locally; see [data-audit-mcx-gold-package.md](data-audit-mcx-gold-package.md).
The only CSV files in the repository are the synthetic test fixtures.

---

## 2. Application architecture

```
Browser (React SPA)
  │  fetch('/api/...')            same origin; the Vite proxy in dev, FastAPI in production
  ▼
FastAPI  backend/app/main.py  create_app()
  ├─ GZipMiddleware (responses ≥ 1 KB)
  ├─ /api routers ─ backend/app/api/{health,instruments,datasets,observations,research}.py
  │     │             schemas: backend/app/api/schemas.py   dependencies: backend/app/api/deps.py
  │     ├─ SessionStore (in memory) ── backend/app/store.py
  │     ├─ Importer ─── backend/app/ingestion/{importer,columns,parsing,models}.py
  │     ├─ Specs ────── backend/app/specs/{registry.py,mcx_gold_specs.json}
  │     ├─ Normalize ── backend/app/normalization.py
  │     └─ Research ─── backend/app/research/{pairs,signals,validation,costs,config,engine}.py
  └─ Frontend route (never matches /api) ── backend/app/frontend.py → frontend/dist
```

| Layer | Files | Responsibility |
|---|---|---|
| UI | `frontend/src/App.tsx`, `views/*.tsx`, `components/*`, `state/*` | Display only. No price conversion or statistics in the browser. |
| API client | `frontend/src/api/client.ts`, `types.ts` | Typed `fetch` wrappers. Error messages come from the API's `detail`. |
| HTTP API | `backend/app/api/*.py` | Validates requests and calls the domain code below. |
| Session | `backend/app/store.py`, `backend/app/settings.py` | In-memory list of imports plus the latest research result, with limits. |
| Ingestion | `backend/app/ingestion/` | Parses, validates, de-duplicates and records provenance. Never fills in values. |
| Specifications | `backend/app/specs/` | Versioned contract specifications with source citations and verified expiry windows. |
| Normalization | `backend/app/normalization.py` | Converts a quote to INR per gram at 999 fineness. |
| Research | `backend/app/research/` | Pair series, anomaly levels, costs and walk-forward validation. |
| Synthetic demo | `backend/app/demo.py` | Generated CSV (`SYNTHETIC_demo_dataset.csv`) that goes through the real importer. |

Persistence: **none**. Uploads are parsed from the request body and never written to disk
(verified: `test_api.py::test_uploads_are_not_written_to_disk`).

---

## 3. User walkthrough

### 3.1 Launch locally (Windows PowerShell)

One-time setup, from the repository root:

```powershell
py -3.15 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend; npm ci; cd ..
```

**Option A: production-style, one server** (what Render runs):

```powershell
cd frontend; npm run build; cd ..
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000.

**Option B: development, two terminals.** Changes reload as you edit.

```powershell
# Terminal 1
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# Terminal 2
cd frontend
npm run dev
```

Open http://localhost:5173. The Vite proxy forwards `/api` to port 8000.

Verified: both options were exercised on 25 Oct 2026 (previous task). Option A ran the
17 browser checks. Option B ran the Vite proxy check and the backend-down and Retry checks.

### 3.2 Empty dashboard

With nothing loaded:
- the header badge reads **No market data loaded**;
- **Overview** says no prices or findings exist and offers **Import CSV files** or **Load
  synthetic demo**;
- the **Contracts**, **Research** and **Evidence ladder** panels say there is nothing to
  compare.

If the backend is unreachable, the header reads **Server unreachable**. The screens say the
data is unavailable rather than empty, and offer **Retry**. *(Verified by browser checks.)*

### 3.3 Load the synthetic demo (clearly labelled)

Select **Overview → Load synthetic demo** or **Data → Load synthetic demo**. You get 2,778
invented observations for all four contracts, Jul 2025 – Jun 2026. A banner on every screen
reads "Synthetic data … not MCX markets".

The demo is built so outcomes differ by pair:
- GOLDPETAL has brief one-day dips that reverse the next day;
- GOLDGUINEA and GOLDM drift as a random walk.

*(Source: `backend/app/demo.py`.)*

### 3.4 Inspect contracts and normalized prices

**Contracts** shows:
- the specification table from `/api/instruments`: unit, quotation base, price-basis
  fineness, tick, location, last trading day, verified window and source circular;
- a comparison of up to three contracts. The default picks contracts from the expiry month
  shared by the most symbols, for example GOLDTEN, GOLDGUINEA and GOLDPETAL all expiring
  31 Oct 2025.
- **Chart:** normalized close prices, INR per g at 999 fineness. A line breaks wherever a
  contract has no observation.
- **Table:** the raw close in the contract's own units (for example
  `Close, INR / 10 g @995` for GOLDM) next to the normalized value. Hover for the source file
  and line, or the formula.

Raw prices are never plotted on a shared axis, because their units differ.

### 3.5 Run research

**Research → Run research**:
- **Outcome horizon.** Default 5; the API accepts 1–60.
- **Costs.** Four components, in basis points per leg-side, each with an optional source and
  as-of date. Blank means **unknown**, never zero.

The results show:
- the assumptions used;
- a verdict per contract pair;
- the walk-forward windows (greyed out when below the evidence threshold);
- the spread chart against its trailing baseline, with flagged points marked;
- a table of flagged observations, each showing the source file and line of both contracts.

What the demo produces, verified via the API on 25 Oct 2026 after the signal-overlap
correction (see the note below):
- **Horizon 1, costs unknown:** every pair is `insufficient_data`, with 8–18 independent
  holdout signals against the 20 required.
- **Horizon 1, all four costs = 0.25 bps:** the same; known costs cannot help a pair that
  lacks independent evidence.
- **Default horizon 5:** every pair is `insufficient_data`; no parameter set reaches 20
  training signals, so most pairs have no holdout test at all.

> **Correction (25 Oct 2026).** An earlier version of this walkthrough reported GOLDM/GOLDPETAL
> as "supported before costs" at horizon 1, and `historically_validated` with 0.25 bps costs.
> Those results counted one market move once per simultaneously trading expiry, which
> inflated the signal count and t-statistic. Signals are now non-overlapping across the whole
> pair, and folds with fewer than 20 test signals no longer vote, so one year of synthetic
> data honestly supports no verdict. The constructed-data tests in
> `backend/tests/test_research_validation.py` still exercise every verdict.

### 3.6 Reading the Overview

The **evidence ladder** counts, for each pair, the flagged observations at each level. It also
shows the walk-forward verdict. "Actionable" always reads "Not assigned". When costs are
unknown, the cost-adjusted column reads "n/a · costs unknown".

---

## 4. CSV import walkthrough

### 4.1 Accepted layouts (verified: `columns.py`, `test_importer.py`)

Header names match after lower-casing and removing everything except letters and digits,
so `Volume (Lots)`, `VOLUME_LOTS` and `volumelots` are equivalent.

**Legacy MCX Bhavcopy** (`mcx-bhavcopy-legacy`)

| Field | Accepted headers | Required |
|---|---|---|
| Trade date | Date, TradeDate | **Yes** |
| Symbol | Symbol | **Yes** |
| Expiry | Expiry Date, Expiry | **Yes** |
| Close | Close | **Yes** |
| Open / High / Low | Open / High / Low | No |
| Previous close | Previous Close, Prev Close | No |
| Volume (lots) | Volume (Lots) | No |
| Value (INR lakhs) | Value (Lacs), Value (Lakhs), Value (In Lacs), Value (In Lakhs) | No |
| Open interest (lots) | Open Interest (Lots), Open Interest | No |
| Instrument, option type, strike | Instrument Name, Option Type, Strike Price | No; used only to skip options |

**UDiFF Bhavcopy** (`udiff-bhavcopy`): required `TradDt`, `TckrSymb`, `XpryDt`,
`ClsPric`. Optional: `OpnPric`, `HghPric`, `LwPric`, `PrvsClsgPric`, `SttlmPric`,
`TtlTradgVol`, `TtlTrfVal`, `OpnIntrst`, `FinInstrmTp`, `OptnTp`, `StrkPric`. The units of
volume, value and open interest are recorded as unverified.

If a required column is missing, the whole file is rejected (HTTP 422) with the missing
names and up to 300 characters of the headers seen.
*(`test_api.py::test_malformed_files_are_rejected_with_reasons`)*

**Unverified:** neither layout has been compared with a file downloaded from MCX. The
column names came from secondary sources. Every import report says
`layout_verified_against_real_file: false`.

### 4.2 Dates (verified: `parsing.py`, `test_parsing.py`)

- **Unambiguous formats:**
  - `15-Oct-2025`, `15OCT2025`, `15 Oct 2025` and `15/Oct/2025` (month names are not case
    sensitive);
  - `2025-10-15`, `20251015`, and `2025-10-15T00:00:00`.
- **Numeric dates** such as `05/11/2025` or `05-11-2025`:
  - The day/month order is inferred from any value above 12 in the trade-date and expiry
    columns.
  - If no value decides it, the file is rejected and asks for `date_order` (`DMY` or `MDY`).
  - If the file mixes both orders, it is rejected.
  - If the requested order contradicts the file, it is rejected.
- **Rejected values:** two-digit years, and years outside 2000–2100.
- **Filename dates:** a date in the filename is only compared with the contents. A mismatch
  produces a warning, and the contents win.

### 4.3 Symbols, expiries and instruments (verified: `instruments.py`, `importer.py`)

- **Symbols:** spaces and quotes are removed and the text upper-cased. `GOLDPTL` is mapped to
  `GOLDPETAL`.
- **In scope:** only `GOLDM`, `GOLDTEN`, `GOLDGUINEA` and `GOLDPETAL`. Rows for other symbols
  are **skipped** and counted, for example "symbol SILVER (out of scope)".
- **Options:** a row is treated as an option, then skipped and counted, if any of these hold:
  - the option type is CE, PE, CA, PA, CALL or PUT;
  - the instrument name contains `OPT`;
  - the strike is above 0.
- **Contract identity:** each contract is `SYMBOL-EXPIRY`, for example `GOLDTEN-2025-10-31`.
  Expiries are never joined into a continuous series.

### 4.4 Row validation (verified: `importer.py`, `test_importer.py`)

Each row ends up in exactly one of four buckets: accepted, rejected, skipped, or dropped as
an exact duplicate.

**Rejected, with line number and reasons:**
- missing symbol, trade date, expiry or close;
- a value that can't be parsed;
- expiry before the trade date, or a trade date in the future;
- a GOLDTEN row dated before 2025-04-01;
- close, previous close or settlement ≤ 0;
- negative volume, open interest or value;
- on a traded row: missing or non-positive open/high/low, low above high, or open outside
  [low, high];
- two rows with the same date, symbol and expiry but different values. **Both** are rejected.

**Accepted with a warning:**
- zero open/high/low on a day with no trades. These become "not reported", never a price of 0.
- volume or open interest not reported (left empty, never filled in);
- close outside [low, high];
- a weekend trade date;
- an expiry that doesn't match the documented last-trading-day rule. The rule allows up to 4
  days earlier for holidays.

**Whole-file failures (HTTP 422):**
- the file contains NUL bytes (binary);
- it isn't a readable CSV;
- it has no rows;
- a required column is missing;
- the dates are ambiguous or contradictory.

Files that aren't valid UTF-8 are decoded as Windows-1252, with a warning.

### 4.5 Upload limits and session rules (verified: `settings.py`, `store.py`, `test_api.py`)

| Rule | Default | Response |
|---|---|---|
| File size | 25,000,000 bytes (`GOLDLENS_MAX_UPLOAD_BYTES`) | 413 |
| Files per session | 2,000 (`GOLDLENS_MAX_FILES`) | 409 |
| Total bytes per session | 40,000,000,000 (`GOLDLENS_MAX_TOTAL_BYTES`) | 409 |
| Empty body | — | 400 |
| Identical content uploaded twice | — | 409 |
| Synthetic and uploaded files in one session | — | 409 |
| File with no supported gold futures rows | — | 200, `stored: false`, report returned |

The filename is reduced to a display name: directory parts and control characters are
removed, and it is capped at 200 characters. It is never used as a path.
*(`test_filename_is_reduced_to_a_display_name`)*

### 4.6 Labelling (verified)

- A file whose name starts with `SYNTHETIC_`, or the built-in demo, is **synthetic**.
- Any other upload is **user-uploaded · origin unverified**. The provenance text says
  GoldLensAI has not verified that it came from MCX.
- **No code path labels data as verified MCX data.**

Note the limitation: a synthetic file renamed without the prefix would be labelled
"user-uploaded", not synthetic. It would still not be presented as genuine MCX data.

### 4.7 Obtaining and testing a genuine Bhavcopy (manual steps)

mcxindia.com blocks automated downloads, so this must be done by a person in a web browser.

1. Open https://www.mcxindia.com/market-data/bhavcopy.
2. Choose **trading dates from Jul 2025 to Jun 2026**. Contracts in files after mid-2026
   expire outside the verified specification window, so they will import but won't be
   normalized or researched (section 7.4).
3. Download **two or three single days first**, in CSV format, and save them in
   `backend\data\raw\`. Git ignores that folder.
4. Validate without the server:

   ```powershell
   cd backend
   .venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv
   .venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv --json > ..\import-report.json
   ```

5. Check the report:
   - Which layout was detected?
   - Are the rows for GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL **accepted**?
   - Is anything **rejected**, and for what reason?
   - Does the expiry match the documented rule (no "last-trading-day rule" warnings)?
   - Do the trade dates match the file?
6. If the whole file fails with "Required columns not found", the real headers differ from
   the expected ones. The error lists the headers it saw; share that line so the column
   mapping in `columns.py` can be corrected.
7. Then upload the same files on the **Data** screen. They will be labelled
   "user-uploaded · origin unverified", which is correct.

---

## 5. Research interpretation

### 5.1 The comparison (verified: `pairs.py`, `test_research_costs_pairs.py`)

- **Spread:** `spread_bps = 10,000 × ln(A ÷ B)`, where A and B are each contract's
  normalized INR per g @999. Positive means A is rich relative to B.
- **Which contracts are paired:** only those whose expiries are at most **10 days** apart.
  A gap of 0 is labelled `same_expiry`; otherwise the pair is `cross_expiry`. GOLDM expires
  on the 5th and the others at month-end, so GOLDM pairs are always cross-expiry.
- **Which dates are eligible:** both contracts must have an observation that day. A date is
  then excluded if:
  - either contract's specification is unverified;
  - either volume is unknown or below 1;
  - it's within **7 calendar days** of the nearer expiry.
  
  Each exclusion is counted with its reason.

### 5.2 Evidence levels (verified: `signals.py`, `test_research_signals.py`)

The baseline is the mean and standard deviation of the previous *W* eligible spreads **in
the same series**, strictly before the date in question.

| Level | Condition |
|---|---|
| 1 Candidate anomaly | \|z\| ≥ k |
| 2 Statistical anomaly | Level 1, and the deviation exceeds both contracts' tick resolution |
| 3 Cost-adjusted candidate | Level 2, and the deviation exceeds the **known** round-trip cost. Impossible while any cost is unknown. |
| 4 Historically validated | A pair-level verdict from walk-forward validation, not a point label |
| 5 Potentially actionable | **Never assigned by the software** |

### 5.3 Costs (verified: `costs.py`, `test_api.py::test_costs_stay_unknown_unless_supplied`)

- **Components:** brokerage, exchange transaction charges, statutory taxes and levies, and
  slippage, in bps per leg-side.
- **Round trip** = 4 × (sum of components), covering two legs, each entered and exited.
- **If any component is unknown,** the round trip is not computed, no point reaches level 3,
  and no pair can be validated.
- **Labelling:** each supplied value shows its source, or "user assumption, no source
  recorded".

### 5.4 Walk-forward validation (verified: `validation.py`, `test_research_validation.py`)

**Defaults** (`config.py`):
- horizon 5;
- z ∈ {1.5, 2.0, 2.5} and W ∈ {10, 20};
- holdout = the last 30% of eligible dates, with 3 expanding folds before it;
- a verdict needs **≥ 20 non-overlapping holdout signals** and t ≥ 2.

**Procedure:**
- Parameters are chosen on training windows only. The holdout is evaluated once.
- An event counts in a window only if its outcome date is inside the same window.
- Signals never overlap within a pair, across all of its contract series, so one market move
  counts once.
- A development fold votes on consistency only if it has at least 20 test signals.
- **Proof that the holdout doesn't influence selection:** rewriting every holdout price
  leaves the folds and the chosen parameters unchanged
  (`test_holdout_data_cannot_influence_parameter_choice`).

| Verdict | Meaning |
|---|---|
| `insufficient_data` | Too few dates or holdout signals. The dashboard hides statistics below the threshold. |
| `not_supported` | Out of sample, deviations did not reliably revert more than ordinary days |
| `supported_before_costs_costs_unknown` | Gross evidence supports reversion, but costs are unknown |
| `not_supported_after_costs` | Reversion was smaller than the supplied costs |
| `historically_validated` | Survived out-of-sample testing net of the supplied costs |

### 5.5 Why "historically validated" is not an arbitrage

The result describes past end-of-day data only. Specifically:
- **Close prices aren't simultaneously tradable.** The Bhavcopy close is a last-half-hour
  weighted average, so the two contracts' closes may not have been tradable at the same
  moment.
- **Volume isn't depth.** It says nothing about how much could actually be executed.
- **Some costs aren't modelled:** location basis (GOLDPETAL is Ex-Mumbai), delivery making
  charges and carry between different expiries.
- **Costs are only as good as their inputs.** They're what you enter, not observed fills.
- **Sample sizes are small.** The t-statistic is descriptive, and events in different series
  on nearby dates may be correlated.

The software never assigns level 5. Acting on any result needs live executable quotes,
order-book depth, current costs and independent review.

---

## 6. API reference (verified against `backend/app/api/*.py` and `test_api.py`)

All routes are under `/api`; interactive docs are at `/api/docs`. Prices are decimal strings.

| Method and path | Purpose | Responses |
|---|---|---|
| `GET /api/health` | Liveness | 200 |
| `GET /api/instruments` | Four contracts and their specification versions, with sources | 200 |
| `GET /api/datasets` | Data kind (`empty`, `user_uploaded`, `synthetic`), files with import reports, merged contract coverage, cross-file conflicts, limits | 200 |
| `POST /api/datasets?filename=…[&date_order=DMY\|MDY]` | Upload one CSV as the raw body (`Content-Type: text/csv`) | 200 (`stored` true or false); 400 empty body, or a name with no usable characters; 413 too large; 422 unreadable, missing columns, ambiguous dates, bad `date_order`, missing `filename`; 409 duplicate, mixed kinds or limit |
| `POST /api/datasets/demo` | Load the synthetic demo | 200; 409 if user data is loaded or the demo is already loaded |
| `DELETE /api/datasets` | Clear uploads and research | 200 |
| `GET /api/observations?symbol=…&expiry=…&price_field=close` | Observations with raw prices, normalized value, formula, specification version and provenance; `normalized: null` with a reason when unverified. Up to 20,000 rows. | 200; 422 bad `price_field` or date |
| `POST /api/research` | Run research. Body `{"horizon": 1–60, "costs": {name: {"bps_per_leg_side": 0–1000, "source": "…", "as_of": "YYYY-MM-DD"}}}` | 200; 409 no data; 422 invalid horizon, unknown cost name, negative cost, malformed JSON |
| `GET /api/research` | Latest result for the current data; discarded when the data changes | 200; `null` body if none has been run |
| Any other `/api/...` path | — | 404 JSON for every method (`test_unknown_api_paths_are_404_for_every_method`) |
| Wrong method on an existing route | — | 405 |

Example (PowerShell, server on port 8000):

```powershell
curl.exe -X POST "http://localhost:8000/api/datasets?filename=bhav.csv" -H "Content-Type: text/csv" --data-binary "@backend\data\raw\bhav.csv"
curl.exe -X POST "http://localhost:8000/api/research" -H "Content-Type: application/json" -d '{\"horizon\": 5}'
```

---

## 7. Known limitations and risks

1. **Memory-only storage.** Uploads and research results are lost on restart, redeploy or
   Render free-tier spin-down. *(Verified: `store.py`; nothing is written to disk.)*
2. **One shared session.** There are no accounts, and every visitor shares one dataset. Run
   a single server process, since each process has its own memory.
3. **Render free tier.** The service sleeps when idle; the first request can take about a
   minute. The disk is temporary.
   **Unverified:** the Render deployment itself has not been run. `render.yaml` and the build
   script have only been tested locally.
4. **Specification date coverage.** Specifications are verified only for expiries
   GOLDM Sep 2025 – Jul 2026 and GOLDTEN/GOLDGUINEA/GOLDPETAL Aug 2025 – Jun 2026, from MCX
   circular MCX/TRD/456/2025. As of 25 Oct 2026, **contracts currently trading fall outside
   this window**. They are imported, but `normalized` is null and research marks them
   ineligible (`unverified_spec`). *(Verified: `test_observation_with_unverified_specification_is_not_normalized`,
   `test_unverified_specification_is_ineligible_unless_allowed`.)* Circular 552/2026 and
   later specification circulars have not been read (mcxindia.com returned 403).
5. **Real-data compatibility.** **Unverified.** Unknowns:
   - the real column names;
   - the real date format;
   - whether untraded contracts carry close = 0, which would be **rejected**, or the
     previous close;
   - whether UDiFF futures rows have an empty strike;
   - the units of UDiFF volume.
6. **Evidence threshold versus data length.** At horizon 5, about a year of daily data yields
   fewer than 20 holdout signals per pair, so `insufficient_data` is the expected honest
   outcome. *(Verified on the demo.)*
7. **Synthetic detection depends on the filename** (section 4.6).
8. **The browser tests aren't in the repo.** The 17 checks rely on the design skill's Chrome
   driver and live outside the repository. The frontend has no unit tests.
9. **Response size.** A full research response is about 2.9 MB of JSON (about 320 KB with
   gzip) for the demo.
10. **One theme.** The interface is a single dark "research terminal" theme; there is no light
    mode. The charts are hand-drawn SVG with table views and keyboard-readable tooltips.

---

## 8. Verification results (this run, 25 Oct 2026)

| Command | Result |
|---|---|
| `git status --short --untracked-files=all` | 39 entries (8 modified, 31 untracked); HEAD `83c0602` |
| Backup check: `sha256sum -c SHA256SUMS.txt` in `GoldLensAI-backups\20261025-185707` | 3/3 OK |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | **231 passed**, 1 warning (Starlette's `httpx` deprecation notice) |
| `npm run lint` in `frontend/` | **Pass**: 0 warnings, 0 errors, exit 0 |
| `npm run build` in `frontend/` | **Pass**: `index-DwFlEEJo.js` 429.83 kB (133.36 kB gzip), CSS 24.86 kB |
| Search for genuine Bhavcopy files | **None found** |

Tests by file:

| File | Tests |
|---|---|
| test_api | 30 |
| test_frontend_serving | 42 |
| test_health | 6 |
| test_importer | 29 |
| test_normalization | 27 |
| test_parsing | 37 |
| test_research_costs_pairs | 15 |
| test_research_signals | 8 |
| test_research_validation | 14 |
| test_specs | 23 |

The browser checks were **not** rerun in this task, because no application code changed. The
latest result, 17/17 on the production-style server, is from the previous task on the same
day.

---

## 9. Files changed in this task

Only this document was created: `docs/PROTOTYPE_WALKTHROUGH.md`. No application code, tests,
configuration or data were modified.

---

## 10. Next steps, in dependency order (recommendations, not implemented)

1. **Get two or three genuine Bhavcopy CSVs** for trading dates Jul 2025 – Jun 2026 (section
   4.7). Everything below depends on this.
2. **Confirm or correct the column mapping** in `columns.py` against those files. Then set
   `verified_against_real_file=True` for that layout, and add a test using a small,
   **non-synthetic** fixture only if the licence allows committing it. Otherwise, write a test
   that reproduces just the header row.
3. **Decide how untraded contracts are handled** once the real file shows how MCX reports
   them (close = 0 or the previous close).
4. **Add specifications for current contracts.** Obtain MCX circular 552/2026 and any later
   specification circulars, then add new versions to `mcx_gold_specs.json`.
5. **Collect enough history** (many months of daily files), plus cost sources (exchange
   circular, broker tariff, statutory rates), before reading any verdict as more than
   "insufficient data".
6. **Choose a persistent storage approach** before relying on uploads across restarts. That
   is a cost decision on Render.
7. **Commit the current working tree in reviewed milestones** (Render config, API and
   dashboard, then fixes), then deploy to Render's free plan and confirm the free instance
   type in the Blueprint preview.
