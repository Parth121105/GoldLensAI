# Methodology

Short reference for the formulas and decisions. Longer notes are in [methodology/](methodology/).

## 1. Specifications

Fifteen official MCX "contract onwards" PDFs (GOLD, GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL; three
periods each) are transcribed into
[`backend/app/specs/mcx_gold_specs.json`](../backend/app/specs/mcx_gold_specs.json). A version
applies from its "onwards" month until the next version's, and never past its own launch
calendar. Coverage and sources: [methodology/specifications.md](methodology/specifications.md).

| | GOLDM | GOLDTEN | GOLDGUINEA | GOLDPETAL |
|---|---|---|---|---|
| Quote | per 10 g | per 10 g | per 8 g | per 1 g |
| Purity basis | 995 | 999 | 999 | 999 |
| Price location | Ahmedabad | Ahmedabad | Ahmedabad | Mumbai |
| Last trading day | 5th | last calendar day | last calendar day | last calendar day |
| Tender period | last 3 trading days (5 in earlier versions) | | | |

## 2. Normalization

    price per gram at 999 = close ÷ quote grams × 999 ÷ purity basis

So GOLDM is scaled by 999/995 and the others only by their quote unit. The location difference
(Mumbai vs Ahmedabad) is not adjusted; it is reported as a known basis.

## 3. Relative value

    gap (bps) = 10,000 × ln(A ÷ B)

Each contract is paired with the nearest expiry of each other contract, at most 10 days apart.
Contracts are always tracked by expiry; nothing is stitched into a continuous series.

## 4. Carry and the move split

Per contract and day, fit ln P = a + b·T over expiries (T = days to expiry). The slope b is the
carry; annualised carry = e^(365·b) − 1. For mismatched expiries:

    carry-adjusted gap = gap − mean(b_A, b_B) × (T_A − T_B) × 10,000

Between two dates d0 and d1, each contract's move splits exactly into

    ln P1 − ln P0 = gold move + b0·(T1 − T0) + curve change + residual

The gold move is the median curve-level change across the four contracts. The residual is the
contract moving against its own curve.

## 5. Signal and walk-forward

- The baseline is the mean and standard deviation of the previous 10 or 20 eligible gaps of the
  same fixed pair, using strictly earlier dates only. A signal needs |z| ≥ 1.5, 2 or 2.5,
  a deviation larger than one tick, and (when costs are set) a deviation larger than the
  round-trip cost.
- Outcome: the gap's move back toward the baseline after 5 eligible observations.
- Eligible dates exclude contracts within 7 days of expiry (tender period and delivery) and
  contracts with no volume.
- Split: three expanding training folds plus a final 30% holdout. Parameters are chosen on
  training data only. Events are purged at window edges and never overlap.
- A verdict needs at least 20 holdout events and t ≥ 2. That implies a minimum of 686
  eligible dates per pair. Below it, the verdict is *Insufficient data*.

## 6. Costs and P&L

Per leg-side, all assumptions in [`backend/config/assumptions.json`](../backend/config/assumptions.json):
brokerage 0.5, exchange charges 0.3, statutory levies 0.6 and slippage 1.0 bps. A two-leg round
trip is ×4, giving 9.6 bps. Making charges (₹300 per 10 g GOLDTEN, ₹200 per GOLDGUINEA,
₹100 per GOLDPETAL) apply only on delivery. Positions are closed before the buffer, so none is paid.

Synthetic trade P&L uses only the two contracts held: short the dear contract, long the cheap
one, equal grams. The gold move over the same trade (the average return of the two legs) is
reported separately; it cancels out of the spread P&L.

## 7. Alerts

An alert fires on the latest date only if all of these hold:

1. Both legs are liquid (₹1 crore traded, volume and open interest present) and outside the
   7-day buffer.
2. The pair has 20 earlier dates.
3. The carry-adjusted gap is at least 2.5 standard deviations from the pair's own normal gap.
4. The move exceeds the round-trip cost.
