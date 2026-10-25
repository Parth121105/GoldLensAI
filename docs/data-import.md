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

Importing only validates the file and prints a report. Nothing is stored yet;
persistence comes in Phase 5.

## Supported layouts

Neither layout has been checked against a real MCX download yet, because
mcxindia.com blocks automated access. Column names come from secondary
sources. Every report includes `layout_verified_against_real_file: false`
until that changes.

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
