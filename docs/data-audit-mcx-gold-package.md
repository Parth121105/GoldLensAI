# Data audit: MCX gold package (25 Oct 2026) and the 23 Oct 2026 Bhavcopy

Audit of the data supplied on 26 Oct 2026 and how it was integrated. Every number
below was produced by the code in this repository; the commands to reproduce
them are at the end. The data files themselves are not in Git
(`backend/data/raw/` is ignored, as for all exchange data).

## Sources

| File | Real format | SHA-256 | Role |
|---|---|---|---|
| `Gold_Lens_AI_MCX_Gold_Complete.pdf` (25 pages) | PDF 1.4 | `e7472cb3…7fff` | The package. Its appendix carries tables A1, A2, B1 and B2 as exact CSV blocks. |
| `BhavCopyDateWise_23102026.xls` | **HTML table, not an Excel workbook** (16,737 rows × 15 columns, all MCX commodities) | `4a931460…a735` | The raw date-wise download the package names as its source for B1 and B2. Used to cross-check the package. |
| `mcx_gold_main_contract.csv`, `mcx_gold_yearwise_all_contracts.csv` | CSV | `791e0742…441a`, `d6f6daa3…94b9` | Earlier year-wise extracts. Used to cross-check A1 and A2. |

No ZIP archive existed; the tables were recovered from the PDF.

**Provenance.** The files were supplied by the user. GoldLensAI cannot prove they
came from MCX, so the app labels every one of them "User upload · origin
unverified". They are never labelled synthetic or official.

## Extraction from the PDF

`python -m app.cli package-extract <pdf> backend/data/raw/mcx_gold_package_2026-10-23`

- Text comes from `pdftotext` 4.00 (shipped with Git for Windows). The PDF is only read.
- Each block between `===BEGIN <name>` and `===END <name>` is split on whitespace;
  no value in the package contains a space. The running page footer, page number
  and form feed that pdftotext interleaves at page breaks are removed (only those
  three exact patterns).
- **Every recovered row must have the header's column count**, or extraction stops.
  This guard caught the page-break footers during development.
- A `manifest.json` records the PDF hash, the tool version and each CSV's hash.

## Audit per table

`python -m app.cli package-audit <the four CSVs> --out audit.json`

| Table | Kind | Rows read | Accepted | Rejected | Duplicates | Coverage | Missing (NA) | Warnings |
|---|---|---|---|---|---|---|---|---|
| A1 `A1_yearwise_GOLD_main.csv` | Year-wise, GOLD 1 kg | 21 | 21 | 0 | 0 | 2005–2026, **2009 absent** | `yoy_price_change_pct` 2 (2005 first year; 2010 after the 2009 gap) | 2026 is year-to-date (`is_partial_year = 1`) |
| A2 `A2_yearwise_all_gold_contracts.csv` | Year-wise, 24 symbols | 131 | 131 | 0 | 0 | 2005–2026, 2009 absent | `trading_days` 11, `premium_value_lakh` 126 (reported only from 2026) | 2 rows (GOLDPTLDEL 2016, 2017) have lots traded but no `trading_days` |
| B1 `B1_datewise_gold_futures.csv` | Daily futures | 30 | 30 | 0 | 0 | **1 trading date** (2026-10-23), 5 symbols, 30 expiries | `open`/`high`/`low` 2 each (GOLD no-trade rows) | 24 expiries outside the verified specification window; 6 GOLD rows have no specification in GoldLensAI |
| B2 `B2_datewise_gold_options_traded.csv` | Daily options | 201 | 201 | 0 | 0 | 1 trading date, underlyings GOLD and GOLDM, 5 expiries | none | none |

### Checks applied

- **All tables:** exact header; types (integer, decimal, ISO date, enumerations);
  `NA` is missing, never zero; non-negative counts and values; key-based
  de-duplication (identical rows dropped and counted, conflicting rows rejected).
- **A1:** `implied_avg_price_per_10g = total_value_lakh × 100000 / lots_traded / 100`;
  `trading_days ≈ total / avg daily turnover`; `yoy_price_change_pct` recomputed from
  consecutive years and required to be NA after a gap. All agree.
- **A2:** zero lots implies zero value; `trading_days` present when lots traded.
- **B1:** expiry not before trade date; `days_to_expiry`; OHLC consistency on traded
  rows; `no_trade` agrees with `volume_lots`; `close_per_10g = close × 10 / quote_unit_g`;
  `change_pct` recomputed; **units against the contract specification**:
  `quote_unit_g` must equal the specification's quotation base, and
  `qty_kg = volume_lots × lot grams / 1000` (GOLDM 100 g, GOLDTEN 10 g, GOLDGUINEA 8 g,
  GOLDPETAL 1 g). A unit contradiction rejects the row when the specification is
  verified for that expiry and is a warning otherwise. All 24 rows for the four
  researched symbols agree with the specification units.
- **B2:** option type CE/PE; strike positive; OHLC consistency; option premiums are
  stored separately and never used as futures prices.

### Units (from the package's data dictionary, confirmed by the checks)

| Column | Unit |
|---|---|
| `open`…`close`, `prev_close` (B1) | INR per `quote_unit_g` grams (10, 8 or 1) |
| `close_per_10g` (B1) | INR per 10 g, **not adjusted for fineness** (GOLDM is quoted at 995). GoldLensAI ignores it and normalizes from the raw close. |
| `volume_lots`, `open_interest_lots` | Contracts (lots) |
| `qty_kg` | Kilograms (MCX "Volume (In 000's)", grams ÷ 1000) |
| `value_lakh`, `total_value_lakh` | INR lakh (1 lakh = 100,000) |
| B2 prices and `strike` | INR per 10 g (option premium) |

## Cross-checks against independent copies

| Comparison | Result |
|---|---|
| B1 vs the raw HTML Bhavcopy's 30 gold FUTCOM rows (open, high, low, close, previous close, volume, value, open interest, quantity) | **Identical** (0 mismatches) |
| B2 vs the raw file's gold OPTFUT rows | **Identical**; B2 is exactly the 201 traded rows of 4,622 (0 missing) |
| A1 vs `mcx_gold_main_contract.csv` (lots, value, turnover, implied price, YoY) | Identical (0 mismatches) |
| A2 vs `mcx_gold_yearwise_all_contracts.csv` (lots, value, turnover, premium) | Identical (0 mismatches) |
| Raw HTML Bhavcopy imported directly vs B1 through the Bhavcopy importer | The same 24 observations; merged with 0 conflicts |

The raw file's columns are exactly GoldLensAI's legacy Bhavcopy layout, which was
written from secondary sources. That layout is now marked as checked against one
real download. The UDiFF layout is still unchecked.

## How the data is integrated

| Data | Where it goes | Used for |
|---|---|---|
| B1 futures, raw HTML Bhavcopy | Existing Bhavcopy importer → research observations (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL only; GOLD 1 kg and everything else skipped and counted) and, for B1, the package store with every column | Contracts, coverage, research |
| B2 options | Package store only | Display and audit; never a futures price |
| A1, A2 annual totals | Package store only | Reference context; never expanded into daily data or used as targets |

Upload on the **Data** screen (or `POST /api/datasets`). Tables are recognised by
their header, not their file name. Re-uploading identical content is refused
(409); a key already held from another file is dropped if identical and rejected
with a reason if it differs. Synthetic and user files cannot be mixed.

## Model readiness

GoldLensAI contains **no trained machine-learning model**. Research is a
rule-based signal engine judged by walk-forward validation. `GET /api/readiness`
(and the Data and Research screens) report:

| Check | With the package + raw file loaded |
|---|---|
| More than one trading date | **Fail**: 1 date (2026-10-23) |
| Verified specifications | **Fail**: 0 of 24 contracts (expiries 30 Oct 2026 – 5 Apr 2027 are outside the verified windows, which end Jun/Jul 2026) |
| A pair with a baseline (≥ 26 eligible dates) | **Fail**: 0 |
| A pair with walk-forward history (≥ 686 eligible dates) | **Fail**: 0 |
| Year-wise data used only as context; options kept separate | Pass |

**Verdict: `INSUFFICIENT_DATA`.** The 686 comes from the configuration: the holdout
must be able to hold 20 non-overlapping signals of 6 eligible dates each
(120 dates), each of the 3 development folds the same, and the holdout is 30% of
the dates. Year-wise rows cannot substitute for daily history and were not used
to train or test anything.

## What is needed for a defensible daily model or walk-forward test

1. **Daily futures history:** MCX date-wise Bhavcopies (the same `.xls` download, one
   per trading day) for at least about **2.7 years** of trading days with liquid
   contracts, so each contract pair has at least 686 eligible dates after the
   expiry buffer and volume filters. More is better: 686 is a necessary minimum,
   not a guarantee that 20 signals occur.
2. **Verified specifications for the expiries covered**, from MCX's launch-calendar
   circulars for each contract year (for this file: expiries Oct 2026 – Apr 2027).
3. **Real transaction costs with sources** (brokerage, exchange charges, statutory
   levies, slippage) before any result can be cost-adjusted.

## Reproduce

```powershell
cd backend
.venv\Scripts\python.exe -m app.cli package-extract <path>\Gold_Lens_AI_MCX_Gold_Complete.pdf data\raw\mcx_gold_package_2026-10-23
.venv\Scripts\python.exe -m app.cli package-audit (Get-ChildItem data\raw\mcx_gold_package_2026-10-23\*.csv) --out data\raw\mcx_gold_package_2026-10-23\audit.json
.venv\Scripts\python.exe -m app.cli readiness <path>\BhavCopyDateWise_23102026.xls
```
