# SYNTHETIC TEST FIXTURES — NOT MARKET DATA

Every file in this folder is hand-written for pipeline tests. Prices, volumes
and open interest are invented to exercise validation rules (duplicates, bad
OHLC, negative volume, options rows, out-of-scope symbols, and so on).

- Never use these files for research or present them as MCX observations.
- File names start with `SYNTHETIC_`, which the importer reports as
  `synthetic: true`.
- Column layouts follow the formats described in `docs/data-import.md`; they
  have not been checked against a real MCX download.
