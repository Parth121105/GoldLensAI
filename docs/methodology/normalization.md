# Price normalization (method `norm-v1`)

Implementation: [`backend/app/normalization.py`](../../backend/app/normalization.py).
Tests: [`backend/tests/test_normalization.py`](../../backend/tests/test_normalization.py).

## Goal

Express quotes from contracts with different quotation bases and price-basis
purities in one unit. Then any price difference that remains is not just an
artifact of units.

**Comparison basis: INR per gram of gold at 999 fineness.**

## Formula

```
per_gram_at_basis = quoted_price / quotation_base_g
per_gram_999      = per_gram_at_basis × 999 / price_basis_fineness
```

`quotation_base_g` and `price_basis_fineness` come from the specification
version that covers the contract's expiry (see `specifications.md`). Each
result records the version ID, the formula applied, and the original quote.

### Why 999 / fineness

MCX uses exactly this proportional conversion in its own documents:

- The Due Date Rate of GOLDTEN, GOLDGUINEA and GOLDPETAL is the 995 spot
  price × 999/995.
- A GOLDM seller delivering 999 gold is paid the rate × 999/995.
- A GOLDTEN seller delivering 9999 gold is paid the DDR × 0.9999/0.999.

So value is treated as proportional to fine-gold content, which is the
exchange's convention. 999 was chosen as the reference because three of the
four contracts are already priced on it, so they need no fineness adjustment.

## Worked examples

| Contract | Quote | ÷ base | At basis | × 999/fineness | INR/g @999 |
|---|---|---|---|---|---|
| GOLDM | 72,000 per 10 g @995 | ÷ 10 | 7,200.00 | × 999/995 | 7,228.944724 |
| GOLDTEN | 72,450 per 10 g @999 | ÷ 10 | 7,245.00 | × 1 | 7,245.00 |
| GOLDGUINEA | 57,960 per 8 g @999 | ÷ 8 | 7,245.00 | × 1 | 7,245.00 |
| GOLDPETAL | 7,245 per 1 g @999 | ÷ 1 | 7,245.00 | × 1 | 7,245.00 |

These are illustrative inputs for the arithmetic, not market prices.

Consistency check: GOLDM at 71,640 per 10 g @995 = 7,164 /g @995 = 7,192.8 /g
@999, which equals GOLDTEN at 71,928 per 10 g.

## Tick size in comparison units

A ₹1 tick is a different amount per gram in each contract. This sets a floor
on how small a price difference can be meaningful:

| Contract | ₹ per gram @999 per tick |
|---|---|
| GOLDM | 0.100402 |
| GOLDTEN | 0.100000 |
| GOLDGUINEA | 0.125000 |
| GOLDPETAL | 1.000000 |

## Safeguards

- **Unverified specification.** The quote is refused unless the caller
  explicitly allows it, and the result is then flagged.
- **Declared unit conflict.** If the input states a quotation base that
  disagrees with the specification, an `IncompatibleUnitsError` is raised.
- **Double normalization.** `normalize()` accepts only a `RawQuote`, so passing
  an already-normalized value raises `TypeError`.
- **Invalid price.** Zero, negative, NaN and infinite prices are rejected.
- **Precision.** Arithmetic uses `Decimal`, multiplying before dividing, so
  exact results stay exact.

## Not adjusted (reported as warnings or left for later phases)

| Difference | Treatment |
|---|---|
| Location basis: GOLDPETAL is Ex-Mumbai, the others Ex-Ahmedabad | Warning on every GOLDPETAL result; no adjustment |
| Settlement price used instead of a traded price | Warning: "not an executable trade price" |
| Expiry timing: GOLDM expires on the 5th, the others at month-end | Not a price adjustment; handled in Phase 4 |
| GOLDTEN making charge (₹300 per 10 g, paid by the buyer on delivery) | Delivery cost; Phase 4 cost model |
| GST, brokerage, exchange fees, slippage | Phase 4 cost model; never assumed zero |
