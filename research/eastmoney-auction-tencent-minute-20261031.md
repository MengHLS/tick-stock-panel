# Eastmoney auction probe and Tencent minute observations (2026-10-31)

Status: research note plus implementation evidence. Initial probe window was
2026-10-31 19:07-19:09 Asia/Shanghai, a Saturday; the most recent trading day
was Friday 2026-10-30. Product code was subsequently added for both sources.

## Primary findings: Eastmoney

### Observed sample

The following request succeeded:

```text
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=0
```

Observed response facts:

- HTTP 200; `data.trendsTotal=241`.
- Metadata included `preClose=1354.0` and `beticks=33300|34200|54000|34200|41400|46800|54000`.
- Exactly 241 `data.trends` rows were returned.
- First row: `2026-10-30 09:30,1363.00,1363.00,1363.00,1363.00,1534,209084200.00,1363.000`.
- Last row: `2026-10-30 15:00,1389.15,1392.05,1392.05,1389.15,2546,354415936.00,1377.900`.
- No row timestamped 09:15-09:25 appeared in this sample.

The response row had eight comma-separated slots. The first slot was the timestamp; slots 2-8 were numeric. The common mapping `time, open, close, high, low, volume, amount, average` is an inference from the response/chart ecosystem, not a first-party API specification verified in this probe.

### Auction conclusion

The sample proves only that this `iscr=0` request returned one 09:30 bar and then 09:31 onward, with no 09:15-09:25 rows. The 09:30 bar must not be treated as a proved 09:25 auction print.

A later request with `iscr=1&iscca=0` succeeded and returned 256 points for
2026-10-30. Its 09:15-09:25 rows carried virtual matching prices with zero
volume/amount; the 09:25 row still had zero volume/amount; the 09:26 row carried
the final 09:25 match (`600519`: price 1363.00, 1534 lots, 209,084,200 yuan).
This confirms the logical 09:25 result must be read from the 09:26 source row,
not from 09:25 or 09:31.

### Other tested variants

The following exact URL was requested first without explicit `fields1`/`fields2`:

```text
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&iscr=1
```

Observed result: HTTP 200, `rc=102`, `data=null`. No trends were returned.

The counterpart returned a transport error on that attempt:

```text
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&iscr=0
```

Under the same explicit field list used for the successful `iscr=0` sample, the following variants were also attempted:

```text
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=1
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=1&iscca=0
https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&ndays=1&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=0&iscca=1
```

Observed result: transport errors; no usable payload. Other transport errors occurred during retries. Therefore the `iscr=0` versus `iscr=1` auction comparison, and the endpoint semantics of `iscca`, remain unverified.

### What is known about `iscca`

First-party Eastmoney chart JavaScript loaded from:

```text
https://quote.eastmoney.com/newstatic/build/a.js
https://emcharts.dftzj.com/ec/3.18.1/emcharts.min.js
```

uses chart options named `iscr` and `iscca` (for example, `iscr:a,iscca:s` in the page bundle). The minified chart code also contains 09:15-related tick logic and handling for `iscr`.

This establishes only that Eastmoney's chart layer recognizes such options. It does not establish an HTTP parameter contract for `trends2/get`, nor prove that auction rows are returned by this endpoint. No official first-party API documentation was found or verified.

## Provided Tencent observations

The following were confirmed by the parent task using direct HTTP requests via curl, PowerShell, and Python `urllib`; I did not independently re-run them in this probe.

- `https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m1,,800` returned 800 recent rows.
- `param=...,801` and `param=...,1000` returned the default 320 rows.
- Tested SH/SZ stocks, ETFs, and indices succeeded.
- One tested Beijing-listed symbol returned no minute rows; coverage remains unverified.
- The fresh 800-row sample contained 77 rows for 2026-10-27 (partial) and 241 rows each for 2026-10-28, 2026-10-29, and 2026-10-30.
- On 2026-10-30, the minute volume sum was 59,927 lots and matched the `qt` quote value of 59,927.
- Every `m1` row had slot 6 equal to `{}`; there was no reliable per-minute amount directly in that field.
- Tencent `day/query` for 2026-10-26 through 2026-10-30 returned cumulative amount but no OHLC. It included post-15:00 points through 15:30; those points must be filtered.

Tencent amount alignment remains an open parent-task investigation and is not a finding of this report.

## Additional provided observations

The parent also reported, and this probe did not re-test:

- The existing core plugin loader can register a minute plugin without core route edits (L2).
- Eastmoney `clist` requests with `pz=500` or `pz=6000` capped at 100 rows; SH/SZ totaled 5,563 and BJ 363 in the sample. A full-market fetch is therefore unnecessary for the narrow investigation.

## Limitations

- The successful `iscr=1` sample is stock `1.600519` only; process-volume semantics still need a live 09:15-09:25 market sample.
- Several payload attempts failed at the transport layer; transport failure is not evidence that data is absent.
- The successful sample is stock `1.600519` only, for one recent trading day.
- The 09:30 bar is not used; the final result is taken from the 09:26 source row.
- Eastmoney batch fields during 09:15-09:25 are still scheduled for live-session verification, so persisted names use cumulative/reference wording.

## Scope clarification and follow-up

The user confirmed that both final opening-auction results and the
09:15-09:25 auction process are required. Process observations must retain
their actual vendor and acquisition times. Missing intervals must remain
missing; final results must not be backfilled into earlier process cutoffs.

A follow-up inspection of the same first-party chart bundle confirmed its
`trends2` adapter reads timestamp, close, volume and average from array
positions 0, 2, 5 and 7 respectively and constructs K rows from positions
0 through 6. This supports the chart mapping, but does not establish
matched/unmatched auction-volume semantics. Requests with explicit fields,
`ut`, `iscr=1` and `iscca=1` to push2 and push2his both failed at the
transport layer on this follow-up. No auction capability is newly verified.

## Implementation follow-up

On this Windows host, Python `httpx` requests to Eastmoney `clist` and
`trends2` intermittently received `Server disconnected without sending a
response`, while PowerShell requests to the same URLs succeeded. This is a
transport-path limitation, not evidence that the endpoint lacks data.

The live implementation therefore avoids `clist` and `trends2` as the Python
collection path:

- full-market process snapshots use `ulist.np/get` batches driven by the local
  `instruments/instruments.parquet` stock universe;
- final-result cross-checks use the single-symbol `stock/get` endpoint and its
  `f86` Beijing timestamp;
- both paths fail closed on a missing/duplicate batch row, wrong trade date,
  incomplete page set, or final sample mismatch.

The 09:15-09:25 `ulist` field semantics still require a real trading-session
observation. Source fields are consequently stored as cumulative/reference
values, with no fabricated unmatched quantities.
