# Historical ST filtering

Historical strategy backtests and historical screener runs use effective-dated
risk-warning status, rather than the latest instrument name. This applies to
both the panel and matrix entry filters, including composite strategies,
shared matrix scans and optimizer preparation. Realtime screening continues
to use current instrument names.

## Normalized local dataset

The repository reads `st_history/**/*.parquet` below the configured data
directory. All files use these columns:

| Column | Type | Meaning |
| --- | --- | --- |
| symbol | string | Standard security code |
| flag_date | date | First trading date when this status takes effect |
| st_flag | bool | true = ST or *ST; false = explicitly known normal |

Records apply from `flag_date` until the next record for the same security.
The last effective record on or before the market date is used. Future records
are never filled backward. Conflicting records for the same security and
effective date are rejected. Missing records are unknown, not normal.

This is a reader for normalized historical data, not an assertion that any
installed provider already supports automatic ST-history synchronization.
Data must come from a source that supplies historical status, including normal
intervals. Current names, current instrument snapshots and inferred price-limit
percentages must not be converted into synthetic historical records.

## Missing coverage

When historical exclusion is enabled and no dataset exists, the backtest
returns an explicit error. With partial coverage, unknown security dates are
excluded from the entry universe. Turning off exclusion is an explicit choice
to run without that filter; it does not certify historical stocks as normal.
Entry filtering never suppresses the exits of an existing position.

Historical minute-strategy replay and historical minute screener runs currently
reject ST exclusion because their market rows do not yet carry effective-dated
status through every filter stage.

Historical status is attached after loading the price matrix and is not stored
inside the price-matrix disk cache. A new preparation reads updated status even
when prices hit the existing disk cache; the in-process shared-matrix cache key
includes a status-snapshot digest. An optimizer preparation retains the same
status snapshot across its trials.

On the panel path, attached effective-dated status also drives historical
limit-up/limit-down price calculations. This correction does not repair legacy
enriched first-board flags, and the direct matrix precomputed lock/event columns
still carry their original pipeline's ST basis. Rebuild those derived columns
before claiming full PIT event parity. Saved results remain immutable; a new
backtest is required.

## Execution corrections in the same change

Holding extensions count market sessions inclusively from the actual entry
session. The day-5 decision occurs at that day's close; expiration on days 5,
10 or 74 is executed at the next available open.

`exit_signal_requires_profit` activates once any completed holding close is
strictly above the entry price, including the signal-day close. It stays armed
when a later exit signal occurs at a loss. Intraday highs do not activate it.
New result provenance uses `strategy_backtest_v2` and records this basis;
previously saved snapshots are not rewritten.
