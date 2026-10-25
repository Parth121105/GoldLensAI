# GoldLensAI

An explainable, specification-aware research platform for comparing MCX gold
futures contracts (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL).

It is a research and decision-support tool. It is not a trading bot, not a
live market terminal, and not financial advice.

## Current status

| Area | State |
|---|---|
| Frontend shell (`frontend/`) | Vite + React + TypeScript + Tailwind v4 + Motion. Placeholder page only. |
| Backend (`backend/`) | FastAPI app with `GET /api/health`. No data or research endpoints yet. |
| Contract specifications | Verified from MCX circulars for expiries Aug/Sep 2025 – Jun/Jul 2026. Other periods are unverified. See [docs/methodology/specifications.md](docs/methodology/specifications.md). |
| Normalization | INR per gram at 999 fineness, with tests. See [docs/methodology/normalization.md](docs/methodology/normalization.md). |
| Data import | CSV validation pipeline plus a CLI. Not yet stored or exposed through the API. See [docs/data-import.md](docs/data-import.md). |
| Research engine | Spread anomalies, cost model (unknown ≠ zero), lifecycle filters and walk-forward validation, with tests. See [docs/methodology/research.md](docs/methodology/research.md). **Not yet run on real data.** |
| Historical MCX data | **None included.** Tests use clearly labelled synthetic data only. See [docs/data-requirements.md](docs/data-requirements.md) for what to download. |

## Repository layout

```
backend/            FastAPI service (Python)
  app/main.py       Application factory; all routes mounted under /api
  app/api/health.py GET /api/health
  app/specs/        Versioned contract specifications with sources (JSON + loader)
  app/ingestion/    Bhavcopy CSV parsing, validation, provenance
  app/normalization.py  Specification-aware price normalization
  app/research/     Pair spreads, anomaly levels, costs, walk-forward validation
  app/cli.py        Command-line tools (specs, import)
  data/raw/         Your local MCX CSV files (ignored by Git)
  tests/            pytest suite; tests/fixtures/synthetic/ holds SYNTHETIC test data
docs/               Methodology and data-import documentation
  requirements.txt      Pinned runtime dependencies
  requirements-dev.txt  Pinned runtime + test dependencies
frontend/           Vite + React + TypeScript client
  vite.config.ts    Dev server proxies /api to http://localhost:8000
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

## API

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
```

Without `--costs`, every cost component is reported as unknown and no result
can be classed as validated.

See [docs/data-import.md](docs/data-import.md) for supported layouts and
validation rules.

## Checks

```powershell
# Backend tests
cd backend
.venv\Scripts\python.exe -m pytest
cd ..

# Frontend lint, type-check and production build
cd frontend
npm run lint
npm run build
cd ..
```

## Dependency notes

- `uvicorn` is installed without the `[standard]` extras. Those extras
  currently fail to resolve on Python 3.15 and are not needed.
- To add a backend dependency, install it into `backend\.venv`, then update
  the pins in `requirements.txt` (runtime) or `requirements-dev.txt` (tests).
