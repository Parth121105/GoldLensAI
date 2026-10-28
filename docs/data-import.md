# Importing MCX Bhavcopy files

Implementation: [`backend/app/ingestion/`](../backend/app/ingestion/).

## Where files go

Put CSV files in `backend/data/raw/`. Git ignores that folder, so exchange data
is never committed.

```powershell
cd backend
.venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv
.venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv --json          # full report
.venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv --date-order DMY # if dates are ambiguous
```

The CLI only validates the file and prints a report; it stores nothing.

### Uploading through the dashboard or API

Upload files on the dashboard's **Data** screen, or send each file as the raw
request body:

```powershell
curl.exe -X POST "http://localhost:8000/api/datasets?filename=bhav.csv" `
  -H "Content-Type: text/csv" --data-binary "@data\raw\bhav.csv"
```

The same importer validates the file, and the response contains the report
described below.

- **Size.** Uploads above `GOLDLENS_MAX_UPLOAD_BYTES` (default 5 MB) are
  refused with HTTP 413.
- **Bad files.** Empty files return 400. Binary or unreadable files, missing
  required columns, and ambiguous numeric dates return 422 with the reason.
- **Filename.** It is used only as a display name, never as a path.
- **Synthetic labelling.** A name starting with `SYNTHETIC_` marks the file as
  synthetic.
- **Storage.** The uploaded file is never written to disk. The accepted gold
  rows and the import report are saved as one JSON file per import in
  `backend/data/store/` (git-ignored; `GOLDLENS_STORE_DIR` overrides it, `off`
  disables it) and reloaded at startup. Re-importing an identical file, or a file
  whose gold rows are all already held with identical values, returns 409 and
  stores nothing. **Clear session** deletes the saved files.

## Supported layouts

The legacy layout was checked on 26 Oct 2026 against one real MCX date-wise
download supplied by the user (`BhavCopyDateWise_23102026.xls`, 16,737 rows), so
its reports carry `layout_verified_against_real_file: true`. The UDiFF layout has
not been checked against a real file (its column names come from secondary
sources) and reports `false`.

### MCX date-wise download (`.xls`)

MCX's date-wise download is **not an Excel workbook**: it is an HTML `<table>`
saved with an `.xls` extension, with the legacy columns (`Date`, `Instrument
Name`, `Symbol`, `Expiry Date`, `Option Type`, `Strike Price`, `Open`, `High`,
`Low`, `Close`, `Previous Close`, `Volume(Lots)`, `Volume(In 000's)`,
`Value(Lacs)`, `Open Interest(Lots)`). The importer reads the first table with
the standard library's HTML parser; nothing in the file is executed or fetched.
Rejected-row numbers then refer to table rows (header = 1). A full-market day is
about 17 MB, so the default upload limit is 25 MB.

### GoldLensAI package tables (A1, A2, B1, B2)

The four tables of the MCX gold data package are recognised by their exact
header row and audited by `app/ingestion/package.py`; see
[data-audit-mcx-gold-package.md](data-audit-mcx-gold-package.md). B1 (daily
futures) also goes through the Bhavcopy importer into research. B2 (options) and
A1/A2 (year-wise totals) are stored separately and never become futures prices.

Header matching ignores case, spaces and punctuation.

**Legacy MCX Bhavcopy** (`mcx-bhavcopy-legacy`)

| Column | Field | Unit |
|---|---|---|
| Date | trade date | |
| Instrument Name | instrument (FUTCOM, OPTFUT, ...) | |
| Symbol | symbol | |
| Expiry Date | expiry | |
| Option Type, Strike Price | used to skip options | |
| Open, High, Low, Close, Previous Close | prices | contract's quotation base |
| Volume (Lots) | volume | lots |
| Value (Lacs) | traded value | INR lakhs |
| Open Interest (Lots) | open interest | lots |

**UDiFF Bhavcopy** (`udiff-bhavcopy`): TradDt, TckrSymb, XpryDt,
FinInstrmTp, OptnTp, StrkPric, OpnPric, HghPric, LwPric, ClsPric,
PrvsClsgPric, SttlmPric, TtlTradgVol, TtlTrfVal, OpnIntrst. The units of
volume, value and open interest are unverified.

Required: trade date, symbol, expiry, close.

## What happens to each row

Every row lands in exactly one bucket:

| Bucket | When |
|---|---|
| **Accepted** | All checks pass (row may carry warnings) |
| **Rejected** | Any check fails; every reason is listed with the line number |
| **Skipped** | Options rows, or symbols other than GOLDM / GOLDTEN / GOLDGUINEA / GOLDPETAL |
| **Duplicate dropped** | Identical to another row for the same trade date + symbol + expiry |

### Rejection rules

- A field can't be parsed (bad number, bad date).
- Trade date, expiry or close is missing.
- The expiry is before the trade date, or the trade date is in the future.
- A GOLDTEN row is dated before the instrument's first trading date
  (2025-04-01).
- Close, previous close or settlement is not positive.
- Volume, open interest or value is negative.
- On a traded row, open/high/low is missing or not positive, low is above
  high, or open is outside [low, high].
- Two rows share a trade date + symbol + expiry but have different values.
  Both are rejected; neither is chosen.

### Warnings (row accepted)

- No trades: zero open/high/low is treated as "not reported", not as a price
  of 0.
- Volume or open interest is not reported. It stays empty and is never
  filled in.
- Close lies outside [low, high].
- The trade date is a weekend (possibly a special session).
- The expiry doesn't match the documented last-trading-day rule.

### File-level checks

- **Dates.** Day/month order is inferred from values above 12. If the order
  can't be decided, or the file mixes both orders, the import stops and asks
  for `--date-order`.
- **Filename.** A date in the filename is compared with the trade dates in
  the file, and any mismatch is reported. The file contents always win.
- **Encoding.** Files that aren't valid UTF-8 are decoded as Windows-1252,
  with a warning.

## Provenance

Every accepted observation keeps its source file name, the file's SHA-256, the
line number and the detected layout. Each import report records the import
time, row counts, the trade dates covered, and coverage per contract. Each
contract is identified as `SYMBOL-EXPIRY` and is never spliced with other
expiries.

## Synthetic files

Files whose names start with `SYNTHETIC_` are reported as `synthetic: true`.
The fixtures in `backend/tests/fixtures/synthetic/` are hand-written for tests
and are not market data.

## Importing a folder of Bhavcopy files

Put MCX "BhavCopyDateWise" downloads (HTML tables saved as `.xls`) or CSVs in
`backend/data/raw/bhavcopy/`, then from `backend/`:

```
python -m app.cli import-dir data/raw/bhavcopy
```

Each file's gold futures rows are saved to the store and listed per day and
contract. A file whose rows are already held (a re-download of the same day)
is skipped. If a file's name asks for one date but it contains another, MCX
served the latest trading day because the requested date was a holiday or
invalid; the rows keep the date the file states, and a warning says so.
Restart the server afterwards so it loads the new rows.
