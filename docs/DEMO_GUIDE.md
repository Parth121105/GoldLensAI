# GoldLensAI: demo guide and judge checklist

A three-minute walkthrough of the running application, the technical notes a judge may ask
about, and the checklist to run before presenting. Everything described here can be shown
live; nothing in this guide depends on data that is not in the repository.

No hackathon brief was available when this guide was written, so it does not assume a
track, rubric or deadline. Adapt the opening line to the event.

## Before the demo (5 minutes)

| Step | Command or action | Expected result |
|---|---|---|
| 1. Build the frontend | `cd frontend` then `npm ci` and `npm run build` | `frontend/dist/` created, no errors |
| 2. Start the server | `cd backend` then `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | `Uvicorn running on http://127.0.0.1:8000` |
| 3. Health | Open http://127.0.0.1:8000/api/health | `{"status": "ok", ...}` |
| 4. Clean session | Open http://127.0.0.1:8000 | Overview says **"No market data loaded."** If not, use **Data → Clear session** |
| 5. Browser | Full-screen window at least 1280 px wide; motion not reduced in the OS | The Overview header shows a slow gold fog |
| 6. Network | None needed | The app makes no external requests; MCX links open only if clicked |

If the fog does not appear (reduced motion, a narrow window or no WebGL), the header stays
flat. That is deliberate; nothing else changes.

Imported gold rows are saved to `backend/data/store/`, so a local restart keeps the data;
research must be re-run after a restart. On Render's free tier a redeploy still empties the session.

## Three-minute script

**0:00 – 0:25 · The problem.** Open the Overview (empty).
> "MCX lists four gold futures: GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL. They have different
> sizes, quote units and fineness, and different expiry days. Comparing them naively produces
> 'anomalies' that are really unit mismatches, costs, or patterns found by looking at the
> answer. GoldLensAI is a research tool that only claims what the evidence supports."

Point out the header: **"No market data loaded."** No numbers are invented when there is no data.

**0:25 – 0:55 · Data onboarding.** Go to **Data**.
- Show the drop zone, the two accepted Bhavcopy layouts, and the session limits.
- Select **Load synthetic demo**.
- Point out the orange **Synthetic data** banner that now appears on every screen, and the
  import report: rows read, accepted, rejected with reasons, SHA-256.
> "I don't have licensed exchange files in the repository, so this is a generated dataset,
> and the app labels it as invented everywhere. A user-uploaded file is labelled
> 'origin unverified', never 'MCX data'."

**0:55 – 1:30 · Normalization.** Go to **Contracts**.
- Read one instrument tile: GOLDM, 100 g contract, quoted per 10 g at 995 fineness,
  "÷ 10 × 999 / 995 = INR per g @999".
- Show the price comparison: three contracts expiring in the same month, all on one basis.
  Switch **Chart / Table** to show the raw quotes in their own units beside the normalized values.
> "Every quote becomes INR per gram at 999 fineness, using versioned specifications taken
> from MCX circulars. Contracts outside a verified specification window are not compared."

**1:30 – 2:20 · Research.** Go to **Research**.
- Set the horizon to **1**, leave all four costs blank, select **Run research**.
- The pill changes to **Run complete**.
- Show the verdict table: **every pair is "Insufficient data"**. Select a pair: its
  walk-forward windows are greyed out because each has fewer than 20 test signals.
- Scroll to the spread chart (gold line, trailing baseline, flagged points) and the flagged
  observations table with source file and line numbers.
> "Spreads are fixed contract pairs, never spliced. Parameters are chosen on training windows
> only, then tested once on a final holdout. One year of data gives fewer than 20 independent
> holdout signals per pair, so the honest answer is 'insufficient data'. Blank costs are
> unknown, not zero, so even a strong pattern could not be validated."

**2:20 – 2:45 · What the evidence does and does not establish.** Go to **Overview**.
- The evidence ladder: flags reached the statistical rung; the cost rung reads
  "n/a · costs unknown"; **0 of 6** pairs validated; "Potentially actionable" reads
  **"Never assigned"**.
> "A flag is a single day against a baseline. It is not a finding and not a trade. Even a
> 'historically validated' pair would need executable quotes and depth before anyone acted."

**2:45 – 3:00 · Close.** Open **Methodology → Implemented today, and what is not**.
> "GoldLensAI turns noisy multi-contract quotes into a transparent, reproducible test, and
> tells you exactly where the evidence stops. The next step is real MCX Bhavcopy history,
> which the importer is built to take."

## Technical notes for judges

| Topic | Detail |
|---|---|
| Stack | React 19, TypeScript 6, Vite 8, Tailwind CSS v4, Motion, GSAP, Vanta.js/Three.js; FastAPI on Python 3.15 |
| Serving | One process: FastAPI serves `/api/*` and the built frontend (same origin, no CORS) |
| Normalization | price ÷ quotation base (g) × 999 ÷ price-basis fineness; specs versioned with sources |
| Spread | 10,000 × ln(A ÷ B) on normalized prices, fixed pairs with expiries ≤ 10 days apart |
| Flags | z against a trailing baseline of the same series, tick-size floor, cost rung |
| Validation | 3 expanding walk-forward folds, final 30% holdout used once; parameters chosen on training data only; events purged at window edges; signals non-overlapping across the whole pair |
| Verdict gates | ≥ 20 holdout signals, t ≥ 2, above controls, majority of qualifying folds positive, net of fully known costs |
| Costs | Four components in bps per leg-side; any unknown component blocks validation |
| Provenance | File name, SHA-256 and line number for every observation and flag |
| Storage | Parsed gold rows saved to disk and reloaded on restart; research re-run on demand |
| Tests | 304 backend tests, including leakage, purging, holdout-independence, package-import, readiness and regression tests |

### Corrections made before submission

An independent review of the research engine found, and this build fixes:
1. Signals from simultaneously trading expiries of the same pair were counted as independent,
   inflating n and t. They are now non-overlapping across the whole pair.
2. Development folds with only one or two test signals voted in the fold-consistency check.
   Folds now vote only with at least 20 test signals.
3. A holdout with zero outcome variance crashed the verdict step.
4. Any file name starting with "SYNTHETIC" (no underscore) was labelled synthetic; the demo
   description was chosen by file name alone.
5. Timestamps with a UTC offset lost the offset; they are now converted to the IST trading day.
6. A research result could be saved for data that changed while it was computing; the check
   and the write now happen under one lock.
7. UTF-16 files (Excel "Unicode Text") were rejected as "binary data"; the message now names
   the encoding and how to fix it.

Fix 1 changed the demo's result: a pair previously shown as "supported before costs" is now,
correctly, "insufficient data".

## Known limitations to state openly

- **Only one real trading day has been tested.** One MCX date-wise download (23 Oct 2026),
  supplied by the user, imports cleanly and matches the legacy layout; MCX blocks automated
  downloads and no exchange file is in the repository. Years of daily files are needed for
  research (the readiness check says `INSUFFICIENT_DATA`), and the UDiFF layout is unchecked.
- Specifications are verified only for expiries Aug/Sep 2025 – Jun/Jul 2026.
- End-of-day close prices are not executable quotes; volume is not depth.
- One shared in-memory session; no accounts; no persistence.

## What a user must supply for a real-data test

Daily MCX Bhavcopy CSV files (legacy or UDiFF layout) for July 2025 – June 2026 or longer,
downloaded by a person from https://www.mcxindia.com/market-data/bhavcopy and uploaded on
the Data screen. Several years of history are needed before any pair can reach 20
independent holdout signals. See [data-requirements.md](data-requirements.md).

## Judge checklist

- [ ] The Overview loads with no data and says so, with no invented numbers.
- [ ] The synthetic demo loads, and the synthetic banner appears on every screen.
- [ ] Contracts shows the normalization path for each instrument and a chart on one basis.
- [ ] Research runs from the form; the status pill reads "Run complete".
- [ ] Unknown costs keep the cost rung at "n/a"; no pair is validated without costs.
- [ ] Flagged observations show their source file and line.
- [ ] Methodology separates what is implemented from what is not.
- [ ] `/api/docs` opens the interactive API documentation.
- [ ] At phone width the layout stacks and nothing scrolls sideways.
