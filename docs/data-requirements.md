# Data needed from you

mcxindia.com and mcxccl.com return HTTP 403 to automated requests (checked
2026-10-25 on the Bhavcopy page, the gold product pages, a circular PDF and
the MCXCCL UDiFF page). These files have to be downloaded in a browser.

Put CSVs in `backend/data/raw/`. Git ignores that folder. Send PDFs however is
convenient; they will be cited in `backend/app/specs/mcx_gold_specs.json`.

## 1. Daily Bhavcopy files (required for any real analysis)

**Where:** https://www.mcxindia.com/market-data/bhavcopy

**What:** one end-of-day file per trading day, in CSV format, for the
commodity futures segment.

**Which dates:**

| Priority | Range | Why |
|---|---|---|
| First | Any 2–3 recent trading days | Confirms the actual column layout before bulk download |
| Main | 1 Jul 2025 – 30 Jun 2026 | Matches the verified specification window (expiries Aug/Sep 2025 – Jun/Jul 2026) |
| Later | After 30 Jun 2026 | Usable only once a newer specification circular is supplied (see 2b) |

**Why so many days:** walk-forward validation needs at least about 20
non-overlapping signal events in the holdout alone, for each contract pair.
With roughly 250 trading days, three folds and a 30% holdout, that's
achievable only if the data spans many months. A few days of data will
correctly return `insufficient_data`.

**Expected format:** either layout described in
[data-import.md](data-import.md). The importer reports which layout it
detected and whether that layout has been confirmed against a real file. It
hasn't been confirmed yet; your first files will do that.

## 2. Circulars and specification PDFs

| # | Document | Why it's needed | Status |
|---|---|---|---|
| a | GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL contract specification PDFs from https://www.mcxindia.com/products/bullion/gold | Confirms the copies obtained from a mirror | 403 |
| b | MCX circular 552/2026 (Sept 2026) and any 2026 circular modifying these contracts | Extends the verified window past Jun/Jul 2026 | 403 |
| c | MCX/TRD/134/2025 (2025-03-18), GOLDTEN launch | Confirms the GOLDTEN listing date and the specifications of the Apr–Jul 2025 expiries | not read |
| d | Earlier specification circulars for GOLDM, GOLDGUINEA, GOLDPETAL | Needed only if you want history before Aug 2025 | not read |
| e | MCX/PMT/375/2026 (Good Delivery, July 2026) | Confirms it doesn't change purity or price basis | secondary reports only |
| f | MCXCCL UDiFF Bhavcopy format document | Confirms column names and units | 403 |

## 3. Cost sources (needed to move beyond "costs unknown")

| Component | Typical source |
|---|---|
| Exchange transaction charges | MCX circular on transaction charges |
| Statutory taxes and levies | Commodity Transaction Tax, stamp duty, GST on charges, SEBI fees. Official notifications, or your broker's contract note |
| Brokerage | Your broker's tariff |
| Slippage | No official source. Must be a stated assumption, or measured from executable quotes |

Until these are provided, the engine reports "costs unknown" and can't
produce a validated finding.
