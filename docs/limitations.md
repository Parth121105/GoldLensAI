# Limitations

## Data

- **Two real trading days** (23 and 27 Oct 2026). Each contract pair needs 686 eligible dates
  for a walk-forward verdict, so the real-data verdict is *Insufficient data* and no edge is
  claimed. About three years of daily Bhavcopies would change that.
- **Closing prices, not fills.** MCX close is a last-half-hour weighted average. Nobody could
  necessarily have traded at it.
- **Volume is not depth.** Daily volume and open interest show activity, not how much could be
  traded at a given price. Far-month contracts can be thin; anything under ₹1 crore traded is
  flagged (an assumption).
- **Yearly data** comes from the MCX package table A2. 2026 runs only to the package date.

## Specifications

- Verified only for expiries GOLDM Sep 2025 – Jul 2027, GOLDTEN Apr 2025 – Jun 2027,
  GOLDGUINEA Jan 2025 – Jun 2027 and GOLDPETAL Apr 2025 – Jun 2027. Older or later contracts are
  refused rather than guessed.
- MCX trading holidays are not known to Gold Lens. Lifecycle dates not taken from the data are
  nominal (weekends skipped only).

## Method

- **Location basis.** GOLDPETAL is priced in Mumbai, the others in Ahmedabad. Gaps involving
  GOLDPETAL include this unadjusted basis.
- **Carry adjustment** uses a straight-line fit of log price on days to expiry, about six
  points per contract. It is a first-order correction.
- **Costs are assumptions**, not broker quotes. Per-order brokerage weighs far more on a 1 g
  GOLDPETAL lot than on a 100 g GOLDM lot, and slippage on thin contracts can be much larger.
- **Synthetic validation** shows the engine finds mispricings it was built to find, and claims
  nothing on clean data. It does not show that such mispricings exist in the real market.

## Running it

- On Render's free tier the disk is not persistent. Files uploaded through the app are lost on
  redeploy or spin-down; the bundled real data in `backend/data/seed/` is reloaded at startup.
- There is one shared session and no user accounts.
