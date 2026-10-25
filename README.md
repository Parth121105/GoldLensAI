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
| Historical MCX data | None included. Import workflow not built yet. |
| Contract specifications | Not yet verified or encoded. |

## Repository layout

```
backend/            FastAPI service (Python)
  app/main.py       Application factory; all routes mounted under /api
  app/api/health.py GET /api/health
  tests/            pytest suite
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
