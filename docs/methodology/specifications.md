# Contract specifications

The machine-readable registry is
[`backend/app/specs/mcx_gold_specs.json`](../../backend/app/specs/mcx_gold_specs.json).
This page explains where each value comes from and what is still uncertain.

## Sources

| ID | Issued | What it contains | Copy obtained from |
|---|---|---|---|
| MCX/TRD/456/2025 | 2025-09-11 | Full contract specifications of GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL (Annexures 2–5) and launch calendars | [broker mirror (PDF)](https://www.steelcitynettrade.com/Circulars/Modification%20in%20Launch%20Calendar%20of%20Gold%20Mini,%20Gold%20Ten,%20Gold%20Guinea.pdf) |
| MCX/MCXCCL/148/2025 | 2025-03-25 | GOLDTEN delivery and settlement procedure, including "The price of 10 Gram Gold is on the basis of 999 purity" | [broker mirror (PDF)](https://www.steelcitynettrade.com/Circulars/Delivery%20&%20Settlement%20Procedure%20for%20GOLD%20TEN%20Contract%201.pdf) |

`mcxindia.com` returned HTTP 403 to automated requests on 2026-10-25, so both
circulars were read from a broker's mirror. The PDF metadata names MCX as the
author. Check them against the copies on mcxindia.com when you can open the
site in a browser.

## Verified values

| | GOLDM | GOLDTEN | GOLDGUINEA | GOLDPETAL |
|---|---|---|---|---|
| Trading unit | 100 g | 10 g | 8 g | 1 g |
| Quotation / base value | per 10 g | per 10 g | per 8 g | per 1 g |
| Price basis fineness | 995 | 999 | 999 | 999 |
| Tick size | ₹1 per 10 g | ₹1 per 10 g | ₹1 per 8 g | ₹1 per 1 g |
| Price quote | Ex-Ahmedabad | Ex-Ahmedabad | Ex-Ahmedabad | **Ex-Mumbai** |
| Last trading day | 5th of expiry month | last calendar day | last calendar day | last calendar day |
| Delivery logic | Compulsory | Compulsory | Compulsory | Compulsory |
| Verified for expiries | Sep 2025 – Jul 2026 | Aug 2025 – Jun 2026 | Aug 2025 – Jun 2026 | Aug 2025 – Jun 2026 |

All four quotes exclude GST and include import duty and customs.
If the last trading day is a holiday, it moves to the preceding working day.

### How the price basis fineness was established

The circulars state a *quality specification*, which is a delivery
requirement, not a statement about what the quoted price refers to. The price
basis was taken from these passages:

- **GOLDM (995).** The quality specification is 995, and a seller delivering
  999 purity receives "Rate of delivery * 999/995". That premium only makes
  sense if the quoted rate is for 995.
- **GOLDTEN (999).** MCXCCL/148/2025 says so directly. The Due Date Rate is
  Ahmedabad 995 spot × 999/995.
- **GOLDGUINEA, GOLDPETAL (999).** The quality specification is 999, and the
  Due Date Rate is the 995 spot converted with × 999/995 and then scaled by 8/10
  or 1/10.

## Verification windows

Each specification version is marked verified only for the expiry months in
its circular's launch calendar. For any other contract, lookup returns
`UNVERIFIED`. Normalization then refuses the contract unless the caller passes
`allow_unverified=True`, and every such result carries an
`UNVERIFIED SPECIFICATION ASSUMED` warning.

## Unresolved

1. **Contracts expiring after Jun/Jul 2026.** No later full specification was
   read. MCX circular 552/2026 (September 2026) mentions GOLDPETAL and GOLDTEN
   October 2026 expiries, but mcxindia.com blocked the download.
2. **Contracts before Aug/Sep 2025.** TRD/456/2025 changed only the launch
   calendar. Earlier specifications were probably the same apart from the
   calendar, but this has not been confirmed from a primary document.
   Secondary sources describe an older 995-purity Gold Guinea and a Gold Petal
   that was not 1 g deliverable before 2019.
3. **GOLDTEN listing.** Trading began on 2025-04-01 according to MCXCCL/148/2025
   (contracts expiring April 2025 onward) and consistent secondary reports. The
   launch circular MCX/TRD/134/2025 was not read.
4. **GOLDTEN tender period.** The tender period is the last 5 trading days in
   MCXCCL/148/2025 (March 2025) but the last 3 in TRD/456/2025 (September 2025).
   It doesn't affect normalization, but it matters for lifecycle analysis in
   Phase 4.
5. **Good Delivery changes, July 2026.** MCX/PMT/375/2026 expanded the refiners
   accepted for delivery, effective 2026-07-13 (secondary reports). It isn't
   known to change the price basis or units.
