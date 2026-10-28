# Contract specifications

The machine-readable registry is
[`backend/app/specs/mcx_gold_specs.json`](../../backend/app/specs/mcx_gold_specs.json).
Every version in it was transcribed from an official MCX contract specification
PDF kept in `backend/data/raw/specs/` (git-ignored, like all exchange data).
`python -m app.cli specs` prints the registry.

## Sources and coverage

A PDF titled "X contract onwards" governs contracts expiring from month X until
the month before the next PDF for the same contract takes over, and never past
the last expiry in its own launch calendar.

| Contract | PDF (contract onwards) | Reference circulars | Expiries covered | Tender period | Making charge on delivery |
|---|---|---|---|---|---|
| GOLD | February 2026 | MCX/TRD/086/2025 (2025-02-14) | 2026-02 – 2026-06 | last 5 trading days, 5% | – |
| GOLD | August 2026 | MCX/TRD/383/2025 (2025-08-04) | 2026-08 – 2026-12 | last 3 trading days, 8.34% | – |
| GOLD | February 2027 | MCX/TRD/040/2026 (2026-01-27), MCX/PMT/375/2026 (2026-07-01) | 2027-02 – 2027-12 | last 3, 8.34% | – |
| GOLDM | November 2025 | MCX/TRD/456/2025 (2025-09-11) | 2025-09 – 2026-04 ¹ | last 3, 8.34% | – |
| GOLDM | May 2026 | MCX/TRD/041/2026, MCX/PMT/178/2026 (2026-04-06) | 2026-05 – 2026-07 | last 3, 8.34% | – |
| GOLDM | August 2026 | + MCX/PMT/375/2026 | 2026-08 – 2027-07 | last 3, 8.34% | – |
| GOLDTEN | April 2025 | MCX/TRD/134/2025 (2025-03-18), MCXCCL/C&S/058/2025 | 2025-04 – 2025-10 | last 5, 5% | ₹300 per 10 g |
| GOLDTEN | November 2025 | MCX/TRD/456/2025 | 2025-11 – 2026-06 | last 3, 8.34% | ₹300 per 10 g |
| GOLDTEN | July 2026 | MCX/TRD/044/2026, MCX/PMT/375/2026 | 2026-07 – 2027-06 | last 3, 8.34% | ₹300 per 10 g |
| GOLDGUINEA | January 2025 | MCX/TRD/650/2024 (2024-09-30) | 2025-01 – 2025-11 | last 5, 5% | ₹200 per guinea |
| GOLDGUINEA | December 2025 | MCX/TRD/456/2025 | 2025-12 – 2026-06 | last 3, 8.34% | ₹200 per guinea |
| GOLDGUINEA | July 2026 | MCX/TRD/042/2026, MCX/PMT/375/2026 | 2026-07 – 2027-06 | last 3, 8.34% | ₹200 per guinea |
| GOLDPETAL | April 2025 | MCX/TRD/858/2024 (2024-12-31) | 2025-04 – 2025-11 | last 5, 5% | ₹100 per 1 g coin |
| GOLDPETAL | December 2025 | MCX/TRD/456/2025 | 2025-12 – 2026-06 | last 3, 8.34% | ₹100 per 1 g coin |
| GOLDPETAL | July 2026 | MCX/TRD/043/2026, MCX/PMT/375/2026 | 2026-07 – 2027-06 | last 3, 8.34% | ₹100 per 1 g coin |

¹ The November 2025 GOLDM PDF's launch calendar also lists the September and
October 2025 expiries. No other PDF covers them, so they are included.

**Not covered by any PDF:** GOLD before 2026-02 and after 2027-12; GOLDM before
2025-09 and after 2027-07; GOLDTEN after 2027-06 (first listed April 2025);
GOLDGUINEA before 2025-01 and after 2027-06; GOLDPETAL before 2025-04 and after
2027-06. Lookups for those expiries return `UNVERIFIED`, and normalization
refuses them unless `allow_unverified=True` is passed explicitly.

GOLD (1 kg) is recorded for reference only; Gold Lens compares GOLDM, GOLDTEN,
GOLDGUINEA and GOLDPETAL.

## Values that do not change between versions

| | GOLDM | GOLDTEN | GOLDGUINEA | GOLDPETAL |
|---|---|---|---|---|
| Trading unit | 100 g | 10 g | 8 g | 1 g |
| Quotation / base value | per 10 g | per 10 g | per 8 g | per 1 g |
| Price basis fineness | 995 | 999 | 999 | 999 |
| Tick size | ₹1 per 10 g | ₹1 per 10 g | ₹1 per 8 g | ₹1 per 1 g |
| Price quote | Ex-Ahmedabad | Ex-Ahmedabad | Ex-Ahmedabad | **Ex-Mumbai** |
| Contract start day | 6th of launch month | 1st of launch month | 1st of launch month | 1st of launch month |
| Last trading day | 5th of expiry month | last calendar day | last calendar day | last calendar day |

All quotes exclude GST and include import duty and customs. A start day that is
a holiday moves to the following working day; a last trading day that is a
holiday moves to the preceding working day.

### How the price basis fineness was established

The PDFs state a *quality specification*, which is a delivery requirement.
The price basis comes from these passages:

- **GOLDM (995).** The quality specification is 995, and a seller delivering
  999 purity receives "Rate of delivery * 999/995". That premium only makes
  sense if the quoted rate is for 995.
- **GOLDTEN (999).** "The price of 10 Gram Gold is on the basis of 999 purity."
  The Due Date Rate is Ahmedabad 995 spot × 999/995.
- **GOLDGUINEA, GOLDPETAL (999).** "The price of Gold Guinea / 1 Gram Gold Coin
  is on the basis of 999 purity." The Due Date Rate is the 995 spot × 999/995,
  scaled by 8/10 or 1/10.

## Notes

- GOLDPETAL is priced Ex-Mumbai; the others Ex-Ahmedabad. Normalization does not
  adjust for location; the difference is reported as a known basis.
- The July 2026 GOLDPETAL spec sheet says buyer funds pay-in is T+2, while its
  delivery procedure says E+1. The procedure value is recorded.
- Making charges are paid by the buyer on delivery. They affect the cost of a
  position held into delivery, not the quoted price.
