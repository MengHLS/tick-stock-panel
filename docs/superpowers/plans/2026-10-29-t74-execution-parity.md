# Historical ST Filtering and T74 Execution Corrections

The user authorized correcting the three diagnosed differences sequentially.
These are L3 corrections to shared engines, preserving existing uncommitted work.
No commits, production data migration, or overwriting saved results are included.

## 1. Historical ST filtering

- [x] Reproduce current-name leakage in both panel and matrix filters.
- [x] Read normalized `st_history` records through the repository, with
  `symbol`, `flag_date`, and Boolean `st_flag` (true = ST, false = normal).
  Align backward by effective date; never backfill from a future observation.
- [x] Historical entry filters use these records instead of current names.
  Missing history produces a clear error when exclusion is requested;
  unknown individual dates are excluded. Realtime name filtering is unchanged.
- [x] Historical scanner, `run_all`, composite and shared-matrix execution
  consume the same effective-dated snapshot; shared matrix cache keys include
  a status digest. Historical minute scanning fails closed.
- [x] Cover normal/ST/normal transitions, absent history, unknown dates,
  both backtest paths and snapshot refresh. Keep ST history outside the
  persisted price-matrix cache so price generations do not hide status changes.

## 2. Holding-day alignment

- [x] Reproduce the premature day-4 decision with signal-close planning enabled.
- [x] Count the entry session once, evaluate on day 5, and execute an expired
  holding at the following open. Cover day 10 and day 74 as well.

## 3. MA exit activation

- [x] Reproduce a prior profitable close followed by a losing MA exit signal.
- [x] Activate on the maximum completed holding close, including the signal day.
  Preserve existing signal-time alignment and T+1 constraints.

## Verification

- [x] Run each reproducer red before its correction and green afterwards.
- [x] Run affected filter, matrix, execution, provenance and backtest modules.
- [x] Review the final task diff separately from existing local changes.
- [x] Report missing production ST coverage and distinguish these corrections
  from a complete reproduction of the original system's archived return.

Ruling: an absent or unknown historical status is excluded from the entry
universe (fail-closed), rather than treating it as normal. This is safer than
the original project's unknown-allowed behavior, but exact reproduction still
requires its effective-dated status history and unknown-policy decision.

Ruling: the panel path also uses the attached effective-dated status for
historical limit-up/limit-down calculations. Direct matrix locks and existing
enriched `consecutive_limit_ups` remain precomputed from their original
pipeline and must be rebuilt before claiming full PIT event parity.

Independent review found that historical scanner and `run_all` paths still
used current names. They now consume the same effective-dated snapshot, with a
status digest in the shared-matrix cache key; historical minute scanning fails
closed instead of silently using current names.
