# GoldLensAI

An explainable, specification-aware research platform for comparing MCX gold
futures contracts (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL).

It is a research and decision-support tool. It is not a trading bot, not a
live market terminal, and not financial advice.

![GoldLensAI Overview with the labelled synthetic demo loaded](docs/screenshots/overview.jpg)

*Screenshot of the running app with the **synthetic** demo dataset loaded. Every number in it
describes invented prices, and the app says so on every screen.*

## The problem

MCX lists four gold futures that look interchangeable but are not. Each has its own contract
size (100 g, 10 g, 8 g, 1 g), quote unit (per 10 g, 8 g or 1 g) and price-basis fineness
(995 or 999), and they expire on different days. Comparing their raw quotes is meaningless,
and naive "spread anomaly" screens built on them find patterns that vanish once units,
expiries, costs and out-of-sample testing are handled properly.

GoldLensAI answers one question honestly: **after converting every quote to the same basis,
do deviations between fixed contract pairs revert often enough, out of sample and net of
real costs, to be worth a closer look?** It shows exactly how far the evidence got, and it
refuses to claim more than the data supports.

**Who it is for:** students, analysts and researchers studying MCX gold futures
relative value, who need a transparent, reproducible method rather than a black-box signal.

**What makes it different**
- **Specification-aware:** every quote is normalized from versioned MCX specifications with
  their sources, and contracts outside a verified window are not compared.
- **Honest evidence ladder:** candidate → statistical → cost-adjusted → historically
  validated. "Potentially actionable" is never assigned by software.
- **Unknown costs are never zero:** without all four cost components, nothing can be validated.
- **No look-ahead:** walk-forward folds, a holdout used once, non-overlapping signals.
- **Provenance everywhere:** every flagged point links back to its source file and line,
  and synthetic data is labelled on every screen.

A three-minute demo script and a judge checklist are in
[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

## Current status

| Area | State |
|---|---|
| Dashboard (`frontend/`) | Research workspace: Overview, Contracts, Data, Research, Methodology. Every number comes from the API. See [Using the dashboard](#using-the-dashboard). |
| Backend (`backend/`) | FastAPI: health, instruments, CSV upload, observations, research. Serves the built frontend in production. |
| Deployment | One free Render web service (`render.yaml`). See [Deploying to Render](#deploying-to-render). |
| Contract specifications | Verified from MCX circulars for expiries Aug/Sep 2025 – Jun/Jul 2026. Other periods are unverified. See [docs/methodology/specifications.md](docs/methodology/specifications.md). |
| Normalization | INR per gram at 999 fineness, with tests. See [docs/methodology/normalization.md](docs/methodology/normalization.md). |
| Data import | Upload CSVs in the dashboard (or the CLI). Parsed gold rows are **saved to disk** and survive a restart. See [docs/data-import.md](docs/data-import.md). |
| Research engine | Spread anomalies, cost model (unknown ≠ zero), lifecycle filters and walk-forward validation, run from the dashboard. See [docs/methodology/research.md](docs/methodology/research.md). One real MCX trading day (23 Oct 2026) has been imported and audited; research needs years of daily history, so nothing has been validated on real data. On the one-year synthetic demo every pair is `insufficient_data`, which is the honest result for that much history. |
| Historical MCX data | **None in Git.** A user-supplied package (year-wise totals 2005–2026 and one trading day, 23 Oct 2026, of futures and options) and the raw MCX date-wise file for that day were audited locally; see [docs/data-audit-mcx-gold-package.md](docs/data-audit-mcx-gold-package.md). Readiness verdict: `INSUFFICIENT_DATA`. See [docs/data-requirements.md](docs/data-requirements.md) for what to download. |

## Architecture and data flow

```
 Browser (React 19 + TypeScript, Vite, Tailwind CSS v4)
   Overview · Contracts · Data · Research · Methodology
        │  same-origin fetch, JSON (prices as decimal strings)
        ▼
 FastAPI  /api/*                         serves frontend/dist for every other path
   datasets ──► ingestion: CSV layout detection, row validation, provenance (file, SHA-256, line)
                 │
                 ▼
               normalization: price ÷ quotation base × 999 ÷ fineness  (versioned MCX specs)
                 │
   research ──► fixed contract pairs → spread = 10,000 × ln(A ÷ B)
                 → trailing-baseline z flags → tick and cost rungs
                 → walk-forward folds + one final holdout → verdict per pair
   SessionStore: imported files (gold rows saved to backend/data/store) and the latest research result (memory)
```

The frontend does no financial calculation; it formats and displays what the API returns.

## Repository layout

```
backend/            FastAPI service (Python)
  app/main.py       Application factory; API routes under /api, then the built frontend
  app/frontend.py   Serves frontend/dist with a single-page-app fallback
  app/api/          Routers: health, instruments, datasets, observations, research (+ schemas)
  app/store.py      In-memory session store for uploads and the latest research run
  app/settings.py   Upload and session limits (environment-overridable)
  app/demo.py       Generator for the SYNTHETIC demonstration dataset
  app/specs/        Versioned contract specifications with sources (JSON + loader)
  app/ingestion/    Bhavcopy CSV parsing, validation, provenance
  app/normalization.py  Specification-aware price normalization
  app/research/     Pair spreads, anomaly levels, costs, walk-forward validation
  app/cli.py        Command-line tools (specs, import)
  data/raw/         Your local MCX CSV files (ignored by Git)
  tests/            pytest suite; tests/fixtures/synthetic/ holds SYNTHETIC test data
  requirements.txt      Pinned runtime dependencies
  requirements-dev.txt  Pinned runtime + test dependencies
docs/               Methodology and data-import documentation
frontend/           Vite + React + TypeScript client
  src/views/        Overview, Contracts, Data, Research, Methodology screens
  src/components/   Shell, UI primitives, bento layout, SVG time-series chart,
                    RevealText (GSAP headline reveal), FogBackdrop (Vanta.js header background)
  src/lib/gsap.ts   GSAP setup: SplitText, CustomEase and the shared ease
  src/api/          Typed API client mirroring backend/app/api/schemas.py
  vite.config.ts    Dev server proxies /api to http://localhost:8000
render.yaml         Render Blueprint (one free web service)
scripts/render-build.sh  Render build: frontend, then backend dependencies
```

## Prerequisites

- Node.js 24 and npm 11 (verified with Node 24.22.1, npm 11.19.1)
- Python 3.15 via the Windows `py` launcher (verified with 3.15.1; 3.13 also
  works for the current dependencies)

Everything runs locally. No paid services, API keys, or `.env` file are needed.

## Setup (Windows PowerShell, run once)

From the repository root:

```powershell
# Backend: project-local virtual environment and pinned dependencies
py -3.15 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

# Frontend: exact versions from package-lock.json
cd frontend
npm ci
cd ..
```

The commands call the virtual environment's `python.exe` directly, so you do
not need to run `Activate.ps1` or change the PowerShell execution policy.

## Running (two terminals)

**Terminal 1 — backend** (http://localhost:8000):

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend** (http://localhost:5173):

```powershell
cd frontend
npm run dev
```

Check that the two are connected by opening
http://localhost:5173/api/health. That request goes through the Vite proxy
to FastAPI. Interactive API docs are at http://localhost:8000/api/docs.

If the backend is not running, `/api` requests through the proxy return
HTTP 502.

### Production-style run (one server, like Render)

Build the frontend once, then FastAPI serves both the site and the API on one
port:

```powershell
cd frontend
npm run build
cd ..\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. Routing rules:

| Path | Served |
|---|---|
| `/api/...` | The API only. Unknown API paths return a JSON 404, never the web page. |
| Files in `frontend/dist` (`/assets/...`, `/favicon.svg`) | That file |
| A missing file such as `/assets/old.js` | 404 |
| Any other path, e.g. `/research` | `index.html` (client-side routing) |

If `frontend/dist` hasn't been built, FastAPI serves only the API, so the
two-terminal setup above is unaffected.

## Using the dashboard

Open http://localhost:5173 (development) or http://localhost:8000 (production
build). The workflow:

1. **Data**: choose one or more Bhavcopy CSV files and select **Upload and
   validate**. Each file goes to `POST /api/datasets`, and the backend importer
   reports rows accepted, rejected (with line numbers and reasons), skipped and
   de-duplicated. **Load synthetic demo** loads a generated, clearly labelled
   dataset instead.
2. **Contracts**: compare up to three contracts. The chart and table show
   normalized INR per gram at 999 fineness from `GET /api/observations`. Raw
   quotes appear only in the table, in their own units. A gap in a line means
   no observation that day.
3. **Research**: set the outcome horizon and any known costs, each with a
   source, then select **Run research**. Results come from the existing engine
   via `POST /api/research`: a verdict per contract pair, walk-forward
   windows, a spread chart against its baseline, and flagged observations with
   source file and line.
4. **Overview**: data status, the evidence ladder per pair (candidate →
   statistical → cost-adjusted → walk-forward verdict; "actionable" is never
   assigned), contract coverage and workflow progress.
5. **Methodology**: formulas, anomaly levels, verdict definitions, sources and
   limits.

With no data loaded, every screen says so and shows the next step. No numbers
are filled in.

### Genuine and synthetic data

| Label | When | Meaning |
|---|---|---|
| No market data loaded | Nothing imported | Nothing to compare |
| User-uploaded data · origin unverified | You uploaded a CSV | GoldLensAI checks the format, not that the file came from MCX |
| Synthetic data — not market data | The demo, or any file whose name starts with `SYNTHETIC_` | Invented prices; every screen shows a banner |

Synthetic and uploaded files cannot be combined in one session, and identical
files are refused.

### Where uploaded data lives

Uploads are parsed in memory; the uploaded files are never written to disk.
The **parsed gold rows** of each accepted file are saved as one small JSON file
in `backend/data/store/` (git-ignored) and reloaded when the server starts, so
imports survive a local restart. Re-importing an identical file, or a file whose
gold rows are all already held (for example a re-downloaded day), is refused.
**Clear session** deletes the saved files. Package tables (A1, A2, B2) and the
latest research result stay in memory; research is re-run from the saved rows.
On Render's free tier the disk is not persistent, so a redeploy or spin-down
still empties the session. Run one server process (the default).

Limits (environment variables, all optional):

| Variable | Default |
|---|---|
| `GOLDLENS_MAX_UPLOAD_BYTES` | 25,000,000 bytes per file (MCX's full-market daily `.xls` is about 17 MB) |
| `GOLDLENS_MAX_FILES` | 2,000 files per session (about eight years of daily files) |
| `GOLDLENS_MAX_TOTAL_BYTES` | 40,000,000,000 bytes uploaded per session |
| `GOLDLENS_STORE_DIR` | `backend/data/store`; set to `off` to keep imports in memory only |

Only accepted gold rows are kept (about 30 per daily file, roughly 12 KB on disk),
never the raw upload, so the byte limits bound upload volume rather than memory.

## API

All routes are under `/api`. Interactive documentation is at `/api/docs`.
Schemas are defined in [backend/app/api/schemas.py](backend/app/api/schemas.py).
Prices are decimal strings, so exchange quotes are never rounded by JSON.

| Method and path | Purpose | Main errors |
|---|---|---|
| `GET /api/health` | Liveness | |
| `GET /api/instruments` | Supported contracts and specification versions with sources | |
| `GET /api/datasets` | Session status: data kind, files, import reports, contract coverage, limits | |
| `POST /api/datasets?filename=…&date_order=DMY` | Upload one CSV as the raw request body (`Content-Type: text/csv`); `date_order` is optional (`DMY` or `MDY`) | 400 empty, 413 too large, 422 unreadable or missing columns or ambiguous dates, 409 duplicate, mixed or limit reached |
| `POST /api/datasets/demo` | Load the synthetic demonstration dataset | 409 if user data is loaded |
| `DELETE /api/datasets` | Clear uploads and research | |
| `GET /api/observations?symbol=…&expiry=…` | Raw and backend-normalized observations, with provenance (file, SHA-256, line) | |
| `POST /api/research` | Run research. Body: `{"horizon": 5, "costs": {"brokerage": {"bps_per_leg_side": 1, "source": "…", "as_of": "2026-10-01"}}}`; omitted costs stay unknown | 409 no data, 422 invalid horizon or cost |
| `GET /api/research` | Latest research for the current data, or `null` (HTTP 200) if none has been run | |
| `GET /api/package/rows?table=A1` | Accepted rows of one imported package table (A1, A2, B1, B2) | 404 unknown or not imported |
| `GET /api/readiness` | Whether the loaded data can support walk-forward research or a model, the checks behind the verdict and the data still missing | |

`POST /api/datasets` also accepts MCX's date-wise `.xls` download (an HTML table)
and the four package tables, recognised by their header row. Package uploads return
a `package` audit; annual and options tables return no Bhavcopy `report`.

A file with no supported gold futures rows returns `stored: false` with its
report and adds nothing.

### `GET /api/health`

Liveness check. It reports only that the API process is running, not that
any data has been loaded.

```json
{
  "status": "ok",
  "service": "goldlensai-backend",
  "version": "0.1.0",
  "api_version": "1",
  "server_time": "2026-10-25T10:42:30.350713Z"
}
```

| Field | Meaning |
|---|---|
| `status` | Always `"ok"` when the process can serve requests |
| `service` | Service identifier |
| `version` | Backend application version |
| `api_version` | Version of the public API contract |
| `server_time` | Current server time, ISO 8601, UTC |

## Command-line tools

From `backend/`:

```powershell
# List contract specification versions, verification windows and sources
.venv\Scripts\python.exe -m app.cli specs

# Validate a Bhavcopy CSV and print accepted/rejected/skipped rows
.venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv

# Run spread research and walk-forward validation over many files
.venv\Scripts\python.exe -m app.cli research (Get-ChildItem data\raw\*.csv) --costs costs.json

# Recover the package tables from its PDF, audit them, and assess readiness
.venv\Scripts\python.exe -m app.cli package-extract <package.pdf> data\raw\<folder>
.venv\Scripts\python.exe -m app.cli package-audit (Get-ChildItem data\raw\<folder>\*.csv) --out audit.json
.venv\Scripts\python.exe -m app.cli readiness data\raw\BhavCopyDateWise_23102026.xls
```

Without `--costs`, every cost component is reported as unknown and no result
can be classed as validated.

See [docs/data-import.md](docs/data-import.md) for supported layouts and
validation rules.

## Checks

```powershell
# Backend tests (from the repository root)
backend\.venv\Scripts\python.exe -m pytest backend\tests\ -q

# Frontend lint, type-check and production build
cd frontend
npm run lint
npm run build
cd ..
```

Results on 25 Oct 2026 (Windows 11, Node 24.22.1, Python 3.15.1):

| Check | Result |
|---|---|
| Backend tests | 304 passed (28 Oct 2026) |
| Frontend lint (oxlint) and type-check + build (`tsc -b && vite build`) | Pass |
| Browser walk-through against the production build (empty state, malformed and valid upload, research run, contracts chart and table, deep link, console errors) | 17 of 17 checks passed |
| Animation runtime checks (fog created and destroyed, reduced motion, phone width, failed requests, console errors) | 10 of 10 passed |
| Layout inspection at 1440, 768 and 390 px for all five screens | No failures |

The browser checks used a headless Chrome driver during development; they are not part of
this repository's test suite.

## Deploying to Render

[render.yaml](render.yaml) defines **one** web service on Render's **free**
plan. It serves the API and the built frontend from the same origin, so no
CORS configuration is needed.

| Setting | Value |
|---|---|
| Plan | `free`. This is stated explicitly, because Render's default for a new web service is a paid instance type. |
| Build | `bash scripts/render-build.sh`: checks Node 24, runs `npm ci` and `npm run build` in `frontend/`, then `pip install -r backend/requirements.txt` |
| Start | `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT` (no `--reload`) |
| Health check | `/api/health` |
| Python | `PYTHON_VERSION=3.14.8` (Render's documented default for new services) |
| Node | `NODE_VERSION=24.22.1`; the build script stops on any other major version |

No environment secrets are needed and none are defined.

### Steps

1. Commit and push the repository to GitHub, including `render.yaml`.
2. In the Render Dashboard choose **New → Blueprint** and connect the
   GitHub repository. The repository is private, so allow Render's GitHub app
   to access it.
3. Render reads `render.yaml` and proposes one web service, `goldlensai`.
   Check that it shows the **Free** instance type, then apply.
4. When the deploy finishes, open `https://<service>.onrender.com/api/health`,
   then the site root.

### Free-tier limitations

- **Sleeps when idle.** A free web service spins down after a period without
  traffic. The next request wakes it, which can take up to about a minute.
- **Uploads do not survive.** Uploaded data and research results are held in
  memory, so they are lost on every restart, redeploy or spin-down. After the
  service wakes up, the dashboard is empty again and says so.
- **No market data is deployed.** `backend/data/raw/` is ignored by Git. A
  fresh deployment starts with no data; upload files or load the labelled
  synthetic demo.
- **One shared session.** There are no user accounts: everyone using the same
  deployment sees and changes the same in-memory data.
- **Persistent storage needs a decision first.** Saving imported files or
  research results (for example in SQLite) would not survive on the free tier.
  Persistent disks and managed databases are paid on Render. Choose a storage
  approach before implementing Phase 5 storage.

## Known limitations

- **One real trading day only.** One MCX date-wise download (23 Oct 2026) has been imported: the legacy layout's
  columns match it, and the user-supplied package agrees with it row for row. The UDiFF layout is unchecked, and
  research needs years of daily files (readiness: `INSUFFICIENT_DATA`).
- **No machine-learning model.** Research is rule-based; `GET /api/readiness` states what data a model or a
  walk-forward test would need. Year-wise totals are reference context only.
- **Specification window.** Specifications are verified only for expiries Aug/Sep 2025 – Jun/Jul 2026. Other
  contracts are shown, but they are not normalized or researched.
- **Evidence threshold.** About a year of daily data yields fewer than the 20 independent out-of-sample signals a
  verdict needs (simultaneous expiries of one pair count once). The engine then honestly reports `insufficient_data`;
  several years of history are needed for a real test.
- **Fold rule.** A development fold votes on consistency only if it has 20 test signals. At the default settings
  that needs roughly two and a half years or more of daily data before any pair can be supported or validated.
  This is deliberately conservative; `min_events` in `backend/app/research/config.py` controls it.
- **Charts and theme.** The charts are hand-drawn SVG, with keyboard-readable tooltips and table views. The interface
  has one dark theme.
- **Single session.** There are no user accounts; one shared dataset, saved to the server's disk.

## Dependency notes

- **Animation (frontend/package.json):** Motion handles tile entrances, route changes and
  disclosures. GSAP (`gsap`, `@gsap/react`) handles the Overview headline reveal (SplitText)
  and chart line drawing. Vanta.js on Three.js draws the Overview header's fog; both load on
  demand in their own chunk, and only when the user allows motion, the screen is at least
  768 px wide and WebGL is available. Everything respects `prefers-reduced-motion`.
- **Not used:** Lenis (smooth scrolling would add latency to the most frequent action in a
  research tool and fight the tables' own scroll areas) and `ogl`. They appear only in the
  repository-root `package.json`, which the build does not use; the frontend build installs
  from `frontend/package-lock.json`.

- `uvicorn` is installed without the `[standard]` extras. Those extras
  currently fail to resolve on Python 3.15 and are not needed.
- To add a backend dependency, install it into `backend\.venv`, then update
  the pins in `requirements.txt` (runtime) or `requirements-dev.txt` (tests).
