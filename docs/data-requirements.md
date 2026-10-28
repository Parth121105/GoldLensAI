# Data needed for a real-data verdict

Gold Lens holds two real trading days (23 and 27 Oct 2026). The walk-forward needs **686
eligible dates per contract pair** before it can return anything other than *Insufficient
data* (see [methodology.md](methodology.md#5-signal-and-walk-forward)). This page lists what
would close that gap.

mcxindia.com and mcxccl.com refuse automated requests, and Gold Lens does not scrape them.
Every file below has to be downloaded by a person in a browser.

## 1. Daily Bhavcopy files

**Where:** https://www.mcxindia.com/market-data/bhavcopy (date-wise download, commodity
futures). How to import them: [data-import.md](data-import.md), or the "Adding new Bhavcopy
files" section of the [README](../README.md).

**How many:** about 250 trading days a year, so 686 eligible dates is close to three years
of daily files. Dates where a contract is inside its 7-day pre-expiry buffer or has no volume
do not count, so in practice slightly more is needed.

**Which years:** the verified specifications only reach back to expiries in early 2025
(GOLDGUINEA Jan 2025, GOLDTEN and GOLDPETAL Apr 2025, GOLDM Sep 2025). Daily files from early
2025 to today give fewer than 500 trading days, which is not enough on its own. Two ways forward:

- add older specification PDFs (section 2) and import older Bhavcopies, or
- keep importing new days as they come. Pairs involving GOLDTEN cannot reach 686 dates
  before about 2028, because GOLDTEN was only listed in April 2025.

## 2. Older contract specification PDFs

Needed only to normalize contracts expiring before the dates above. Put each PDF in
`backend/data/raw/specs/` (git-ignored) and transcribe its values into
[`backend/app/specs/mcx_gold_specs.json`](../backend/app/specs/mcx_gold_specs.json).
Coverage today: [methodology/specifications.md](methodology/specifications.md).

| Contract | Earliest verified expiry | Needed for older history |
|---|---|---|
| GOLDM | Sep 2025 | "contract onwards" PDFs before November 2025 |
| GOLDGUINEA | Jan 2025 | PDFs before January 2025 |
| GOLDPETAL | Apr 2025 | PDFs before April 2025 |
| GOLDTEN | Apr 2025 | none; this is its first listing |

## 3. Better cost figures (optional)

Costs are already set as stated assumptions in
[`backend/config/assumptions.json`](../backend/config/assumptions.json) (9.6 bps round trip).
Replacing them with sourced figures would make a verdict more credible:

| Component | Source |
|---|---|
| Exchange transaction charges | MCX circular on transaction charges |
| Statutory levies | CTT, stamp duty, GST on charges and SEBI fees, from official notifications or a broker contract note |
| Brokerage | A broker's tariff |
| Slippage | No official source. Measure it from executable quotes or keep it as an assumption |
