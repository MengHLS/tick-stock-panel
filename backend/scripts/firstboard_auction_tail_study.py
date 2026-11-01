"""First-board pullback (331-style) candidates: auction/opening right-tail study.

The study borrows the formation process of the T74 first-board pullback
strategy (event -> five-day observation window -> bucket score -> next-day
entry) and asks a different question: among the same candidates, can auction
(09:15-09:25) and opening (09:30-09:35) information raise the probability of a
right-tail outcome? A right-tail outcome is MFE >= 20% within 20 sessions from
the next-day open; the tail-before-stop variant is reported separately.

Development (2020-2022) fixes feature directions and thresholds; validation
(2023-2024) and stress (2025-2026H1) only evaluate the frozen rule. Everything
else is exploratory and multiplicity is not adjusted.

Usage (from backend/):
    uv run python scripts/firstboard_auction_tail_study.py \
        --data-dir ../data --minute-dir /path/to/mint-5 \
        --output ../.artifacts/firstboard_auction_tail
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

os.environ.setdefault("POLARS_MAX_THREADS", "6")

VERSION = "firstboard-auction-tail-v1"
SESSIONS = 20
TAIL = 0.20
STOP = -0.06
PERIODS = {
    "development": ("2020-01-01", "2022-12-31"),
    "validation": ("2023-01-01", "2024-12-31"),
    "stress": ("2025-01-01", "2026-06-30"),
    "extension": ("2026-08-01", "2026-09-30"),
}


def round_half_up(expr: pl.Expr, decimals: int = 2) -> pl.Expr:
    factor = 10.0**decimals
    return (expr * factor + 0.5).floor() / factor


def bucket_score(
    expr_max_amp: pl.Expr, expr_mean_amp: pl.Expr, expr_volume_ratio: pl.Expr
) -> pl.Expr:
    """Frozen 3F bucket score of the T74 strategy (max amp, mean amp, volume)."""
    s_max = pl.when(expr_max_amp < 0.08).then(0.75).otherwise(0.25)
    s_mean = (
        pl.when(expr_mean_amp < 0.02)
        .then(0.90)
        .when(expr_mean_amp < 0.04)
        .then(0.70)
        .when(expr_mean_amp < 0.06)
        .then(0.50)
        .when(expr_mean_amp < 0.08)
        .then(0.30)
        .otherwise(0.10)
    )
    s_volume = (
        pl.when(expr_volume_ratio < 0.5)
        .then(0.10)
        .when(expr_volume_ratio < 0.8)
        .then(0.30)
        .when(expr_volume_ratio < 1.2)
        .then(0.50)
        .when(expr_volume_ratio < 2.0)
        .then(0.70)
        .otherwise(0.90)
    )
    return (s_max + s_mean + s_volume) / 3.0


def main_board_filter() -> pl.Expr:
    symbol = pl.col("symbol")
    return (
        symbol.str.contains(r"^\d{6}\.(SH|SZ)$").fill_null(False)
        & ~symbol.str.starts_with("30").fill_null(False)
        & ~symbol.str.starts_with("688").fill_null(False)
        & ~symbol.str.starts_with("689").fill_null(False)
    )


def build_year_events(
    data_dir: Path,
    year: int,
    calendar: pl.DataFrame,
    st_history: pl.DataFrame,
) -> pl.DataFrame:
    """Reconstruct the T74 candidate set for signal dates in ``year``."""
    files = sorted((data_dir / "kline_daily_enriched").glob("date=*/part.parquet"))
    low, high = f"{year - 1}-11-01", f"{year + 1}-02-28"
    files = [p for p in files if low <= p.parent.name[5:] <= high]
    if not files:
        return pl.DataFrame()
    columns = [
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "raw_close",
        "raw_high",
        "raw_low",
        "volume",
        "consecutive_limit_ups",
    ]
    frame = pl.scan_parquet([str(p) for p in files]).select(columns).collect(engine="streaming")
    frame = frame.filter(main_board_filter()).sort(["symbol", "date"])

    from app.tickflow.security_status import attach_st_history

    frame = attach_st_history(frame, st_history).join(calendar, on="date", how="left")
    valid = (
        (pl.col("open") > 0)
        & (pl.col("high") > 0)
        & (pl.col("low") > 0)
        & (pl.col("close") > 0)
        & (pl.col("raw_close") > 0)
        & (pl.col("raw_high") > 0)
        & (pl.col("raw_low") > 0)
        & (pl.col("volume") > 0)
        & (pl.col("high") >= pl.col("low"))
    )
    frame = frame.with_columns(valid.alias("valid"))
    seed = (
        (pl.col("consecutive_limit_ups") == 1)
        & pl.col("valid")
        & (pl.col("open") < pl.col("high") - 1e-9)
    )
    frame = frame.with_columns(seed.alias("seed"))

    leads = {
        "raw_close": 6,
        "raw_high": 6,
        "raw_low": 6,
        "volume": 1,
        "valid": 6,
        "session_no": 6,
        "date": 6,
        "st_flag": 6,
        "open": 6,
        "close": 6,
    }
    exprs = []
    for name, count in leads.items():
        for k in range(1, count + 1):
            exprs.append(pl.col(name).shift(-k).over("symbol").alias(f"{name}__{k}"))
    frame = frame.with_columns(exprs)

    amplitudes = []
    for k in range(1, 6):
        previous = pl.col("raw_close") if k == 1 else pl.col(f"raw_close__{k - 1}")
        amplitudes.append(
            ((pl.col(f"raw_high__{k}") - pl.col(f"raw_low__{k}")) / previous).alias(f"amp_{k}")
        )
    frame = frame.with_columns(amplitudes)
    frame = frame.with_columns(
        pl.min_horizontal([pl.col(f"raw_close__{k}") for k in range(1, 6)]).alias("min_close_5"),
        pl.max_horizontal([pl.col(f"amp_{k}") for k in range(1, 6)]).alias("max_amplitude"),
        pl.mean_horizontal([pl.col(f"amp_{k}") for k in range(1, 6)]).alias("mean_amplitude"),
        pl.all_horizontal([pl.col(f"valid__{k}") for k in range(1, 7)]).alias("future_valid"),
        (pl.col("volume__1") / pl.col("volume")).alias("volume_ratio"),
    )
    frame = frame.with_columns(
        (pl.col("min_close_5") / pl.col("raw_close") - 1.0).alias("pullback"),
    )
    frame = frame.with_columns(
        bucket_score(
            pl.col("max_amplitude"), pl.col("mean_amplitude"), pl.col("volume_ratio")
        ).alias("score"),
    )
    ready = (
        pl.col("seed")
        & pl.col("valid")
        & pl.col("future_valid")
        & ((pl.col("session_no__5") - pl.col("session_no")) == 5)
        & ((pl.col("session_no__6") - pl.col("session_no")) == 6)
    )
    eligible = (
        ready
        & (pl.col("pullback") < -1e-9)
        & (pl.col("max_amplitude") < 0.14)
        & pl.col("max_amplitude").is_finite()
        & pl.col("mean_amplitude").is_finite()
        & pl.col("volume_ratio").is_finite()
    )
    events = frame.filter(eligible).with_columns(
        pl.col("date").alias("seed_date"),
        pl.col("date__5").alias("signal_date"),
        pl.col("date__6").alias("entry_date"),
        pl.col("raw_close__5").alias("t_raw_close"),
        pl.col("raw_close__4").alias("t_prev_raw_close"),
        pl.col("session_no__6").alias("entry_session"),
        pl.col("st_flag__5").alias("st_signal"),
        pl.col("st_flag__6").alias("st_entry"),
        (pl.col("open__6") * pl.col("raw_close__6") / pl.col("close__6")).alias("d_raw_open"),
        pl.col("open__6").alias("d_adj_open"),
        (pl.col("high") * pl.col("raw_close") / pl.col("close")).alias("seed_raw_high"),
    )
    events = events.with_columns(
        (pl.col("d_raw_open") / pl.col("t_raw_close") - 1.0).alias("entry_open_gap"),
        (pl.col("t_raw_close") / pl.col("t_prev_raw_close") - 1.0).alias("signal_day_change"),
        pl.when(pl.col("st_entry")).then(0.05).otherwise(0.10).alias("limit_pct_entry"),
    ).filter(~pl.col("st_signal").fill_null(False))
    events = events.with_columns(
        round_half_up(pl.col("t_raw_close") * (1.0 + pl.col("limit_pct_entry")), 2).alias(
            "limit_up_entry"
        ),
    )
    events = events.with_columns(
        (pl.col("d_raw_open") >= pl.col("limit_up_entry") - 1e-9).alias("open_at_limit"),
    ).with_columns(
        pl.col("entry_open_gap").is_between(-0.04, 0.04).alias("gap_ok"),
        pl.col("signal_day_change").is_between(-0.05, 0.05).alias("prev_change_ok"),
        (~pl.col("open_at_limit")).alias("not_limit_open"),
        pl.col("signal_date").dt.year().alias("year"),
    )
    return events.select(
        [
            "symbol",
            "year",
            "seed_date",
            "signal_date",
            "entry_date",
            "entry_session",
            "score",
            "pullback",
            "max_amplitude",
            "mean_amplitude",
            "volume_ratio",
            "entry_open_gap",
            "signal_day_change",
            "gap_ok",
            "prev_change_ok",
            "not_limit_open",
            "st_entry",
            "d_adj_open",
            "d_raw_open",
            "seed_raw_high",
        ]
    )


def build_events(data_dir: Path, start_year: int, end_year: int) -> pl.DataFrame:
    """Build candidates year by year so memory stays bounded."""
    dates = sorted(
        p.parent.name[5:] for p in (data_dir / "kline_daily_enriched").glob("date=*/part.parquet")
    )
    calendar = pl.DataFrame(
        {
            "date": [dt.date.fromisoformat(d) for d in dates],
            "session_no": list(range(len(dates))),
        }
    )
    from app.tickflow.security_status import read_st_history

    st_history = read_st_history(data_dir)
    pieces = []
    for year in range(start_year, end_year + 1):
        piece = build_year_events(data_dir, year, calendar, st_history)
        if piece.height:
            pieces.append(piece)
        print(f"{year}: candidates={piece.height}", flush=True)
    events = pl.concat(pieces).unique(subset=["symbol", "signal_date"], keep="first")
    return events.sort(["signal_date", "symbol"])


def attach_features(
    data_dir: Path,
    minute_dir: Path,
    events: pl.DataFrame,
    output: Path,
) -> pl.DataFrame:
    """Join auction snapshots, the 09:30 five-minute bar and forward outcomes."""
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / "duckdb_tmp").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=6")
    con.execute("SET memory_limit='5GB'")
    con.execute(f"SET temp_directory='{output.parent / 'duckdb_tmp'}'")
    con.register("events", events)
    con.execute("CREATE TABLE ev AS SELECT * FROM events")

    enriched = str(data_dir / "kline_daily_enriched" / "date=*" / "part.parquet")
    dates = sorted(
        p.parent.name[5:] for p in (data_dir / "kline_daily_enriched").glob("date=*/part.parquet")
    )
    calendar = pl.DataFrame(
        {
            "date": [dt.date.fromisoformat(d) for d in dates],
            "session_no": list(range(len(dates))),
        }
    )
    con.register("cal", calendar)
    con.execute(f"""
        CREATE TABLE daily AS
        SELECT d.symbol, d.date, c.session_no, d.open, d.high, d.low, d.close, d.raw_close, d.volume
        FROM read_parquet('{enriched}', union_by_name=true) d JOIN cal c USING(date)
        WHERE d.date BETWEEN DATE '2018-12-01' AND DATE '2026-11-30'
    """)

    result = str(
        data_dir / "ext_data" / "auction_result" / "timeseries" / "date=*" / "part.parquet"
    )
    preopen = str(
        data_dir / "ext_data" / "auction_preopen" / "timeseries" / "date=*" / "part.parquet"
    )
    con.execute(f"""
        CREATE TABLE au AS
        SELECT e.*,
               r.has_result, r.auction_open, r.prev_close AS au_prev_close,
               r.volume_shares AS au_volume_shares, r.amount AS au_amount,
               r.trade_count AS au_trade_count, r.result_time, r.opening_gap AS au_gap,
               p.last_ref_price, p.last_matched_shares, p.last_unmatched_buy_shares,
               p.last_unmatched_sell_shares, p.last_imbalance,
               p.last_minute_matched_growth, p.last_minute_price_change,
               p.post0920_matched_growth, p.last_time, p.last_age_ms,
               p.preopen_rows, p.invalid_preopen_rows, p.c0920_ref_price,
               p.c0924_ref_price, p.c0924_matched_shares,
               p.c0924_unmatched_buy_shares, p.c0924_unmatched_sell_shares,
               p.last_minute_matched_delta_shares
        FROM ev e
        LEFT JOIN read_parquet('{result}') r ON r.symbol = e.symbol AND r.date = e.entry_date
        LEFT JOIN read_parquet('{preopen}') p ON p.symbol = e.symbol AND p.date = e.entry_date
    """)
    con.execute("""
        CREATE TABLE signal_bar AS
        SELECT e.symbol, e.signal_date, d.volume * 100.0 AS prev_volume_shares
        FROM ev e JOIN daily d ON d.symbol = e.symbol AND d.date = e.signal_date
    """)
    con.execute("""
        CREATE TABLE au2 AS
        SELECT a.*, s.prev_volume_shares
        FROM au a LEFT JOIN signal_bar s USING(symbol, signal_date)
    """)
    files = sorted(str(p) for p in minute_dir.glob("*.parquet"))
    if not files:
        raise ValueError(f"no five-minute parquet under {minute_dir}")
    con.execute(f"""
        CREATE TABLE m5 AS
        SELECT CASE WHEN symbol LIKE '%.XSHG' THEN replace(symbol, '.XSHG', '.SH')
                    WHEN symbol LIKE '%.XSHE' THEN replace(symbol, '.XSHE', '.SZ')
                    ELSE symbol END AS symbol,
               timezone('UTC', to_timestamp(ts / 1000))::DATE AS date,
               open, high, low, close, volume, amount
        FROM read_parquet({files!r})
        WHERE ts % 86400000 = 5400000
    """)
    con.execute("""
        CREATE TABLE joined AS
        SELECT a.*, m.open AS bar_open, m.high AS bar_high, m.low AS bar_low,
               m.close AS bar_close, m.volume AS bar_volume, m.amount AS bar_amount
        FROM au2 a LEFT JOIN m5 m ON m.symbol = a.symbol AND m.date = a.entry_date
    """)
    con.execute("""
        CREATE TABLE fwd AS
        SELECT e.symbol, e.signal_date, e.entry_session, e.d_adj_open,
               d.session_no - e.entry_session AS k, d.open AS f_open,
               d.high AS f_high, d.low AS f_low, d.close AS f_close
        FROM ev e JOIN daily d
          ON d.symbol = e.symbol
         AND d.session_no BETWEEN e.entry_session AND e.entry_session + 25
    """)
    panel = con.execute("""
        SELECT j.*, f.k, f.f_open, f.f_high, f.f_low, f.f_close
        FROM joined j LEFT JOIN fwd f USING(symbol, signal_date)
    """).pl()
    panel.write_parquet(output)
    print(f"panel rows={panel.height} -> {output}", flush=True)
    return panel


def aggregate(panel: pl.DataFrame) -> pl.DataFrame:
    """Collapse the event x forward-session panel into event-level outcomes."""
    keys = ["symbol", "signal_date"]
    constants = [
        c for c in panel.columns if c not in (*keys, "k", "f_open", "f_high", "f_low", "f_close")
    ]
    events = panel.group_by(keys, maintain_order=True).agg(
        [pl.col(c).first() for c in constants if c not in keys]
    )
    entry = pl.col("d_adj_open")
    outcomes = panel.group_by(keys, maintain_order=True).agg(
        ((pl.col("f_high") / entry - 1).filter(pl.col("k") <= 10)).max().alias("mfe10"),
        ((pl.col("f_high") / entry - 1).filter(pl.col("k") <= SESSIONS)).max().alias("mfe20"),
        ((pl.col("f_high") / entry - 1).filter((pl.col("k") >= 1) & (pl.col("k") <= SESSIONS)))
        .max()
        .alias("mfe20_next"),
        ((pl.col("f_low") / entry - 1).filter(pl.col("k") <= SESSIONS)).min().alias("mae20"),
        (pl.col("f_close").filter(pl.col("k") == 5).max() / entry.first() - 1).alias("ret5"),
        (pl.col("f_close").filter(pl.col("k") == 10).max() / entry.first() - 1).alias("ret10"),
        (pl.col("f_close").filter(pl.col("k") == SESSIONS).max() / entry.first() - 1).alias(
            "ret20"
        ),
        pl.col("k").filter((pl.col("f_high") / entry - 1) >= TAIL).min().alias("first_tail_k"),
        pl.col("k").filter((pl.col("f_low") / entry - 1) <= STOP).min().alias("first_stop_k"),
        pl.col("k").max().alias("k_max"),
    )
    events = events.join(outcomes, on=keys)
    events = events.with_columns(
        (pl.col("mfe20") >= TAIL).alias("tail20"),
        (pl.col("mfe20") >= 0.10).alias("tail10"),
        (pl.col("mfe20") >= 0.30).alias("tail30"),
        (
            pl.col("first_tail_k").is_not_null()
            & (pl.col("first_stop_k").is_null() | (pl.col("first_tail_k") < pl.col("first_stop_k")))
        ).alias("tail_before_stop"),
        (pl.col("au_volume_shares") / pl.col("prev_volume_shares")).alias("vol_vs_prev"),
        pl.col("last_imbalance").alias("imbalance"),
        (pl.col("bar_amount") / pl.col("bar_volume")).alias("bar_vwap"),
        (pl.col("bar_open") / pl.col("auction_open") - 1).alias("bar_open_vs_auction"),
        (pl.col("bar_close") / pl.col("bar_open") - 1).alias("bar_ret"),
        ((pl.col("bar_high") - pl.col("bar_low")) / pl.col("bar_open")).alias("bar_range"),
        (pl.col("bar_volume") / pl.col("prev_volume_shares")).alias("bar_vol_vs_prev"),
        (
            (pl.col("bar_close") - pl.col("bar_low")) / (pl.col("bar_high") - pl.col("bar_low"))
        ).alias("bar_pos"),
        (pl.col("bar_close") / pl.col("bar_amount") * pl.col("bar_volume") - 1).alias(
            "bar_vwap_bias"
        ),
        (pl.col("bar_close") * pl.col("d_adj_open") / pl.col("d_raw_open")).alias("entry_0935_adj"),
    )
    events = events.with_columns(
        ((pl.col("mfe20_next") + 1) * pl.col("d_adj_open") / pl.col("entry_0935_adj") - 1).alias(
            "mfe20_0935"
        ),
    ).with_columns((pl.col("mfe20_0935") >= TAIL).alias("tail20_0935"))
    events = events.with_columns(
        pl.col("signal_date").dt.strftime("%Y-%m-%d").alias("date_str"),
    )
    return events.with_columns(
        pl.col("date_str").map_elements(period_of, return_dtype=pl.String).alias("period"),
    )


def period_of(date_str: str) -> str:
    for name, (start, end) in PERIODS.items():
        if start <= date_str <= end:
            return name
    return "pre_development"


def bootstrap_diff(
    dates: np.ndarray,
    outcome: np.ndarray,
    group: np.ndarray,
    samples: int = 2000,
    seed: int = 20261101,
) -> tuple[float, float, float]:
    """Date-clustered bootstrap CI of rate(group) - rate(rest)."""
    rng = np.random.default_rng(seed)
    order = np.argsort(dates)
    dates, outcome, group = dates[order], outcome[order], group[order]
    unique, inverse = np.unique(dates, return_inverse=True)
    days = len(unique)
    n1 = np.bincount(inverse[group], minlength=days)
    s1 = np.bincount(inverse[group], weights=outcome[group], minlength=days)
    n0 = np.bincount(inverse[~group], minlength=days)
    s0 = np.bincount(inverse[~group], weights=outcome[~group], minlength=days)
    observed = s1.sum() / max(n1.sum(), 1) - s0.sum() / max(n0.sum(), 1)
    diffs = np.empty(samples)
    for i in range(samples):
        draw = rng.integers(0, days, days)
        diffs[i] = s1[draw].sum() / max(n1[draw].sum(), 1) - s0[draw].sum() / max(n0[draw].sum(), 1)
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(observed), float(low), float(high)


def _cluster_sums(days: np.ndarray, outcome: np.ndarray, mask: np.ndarray):
    unique, inverse = np.unique(days, return_inverse=True)
    sums = np.bincount(inverse, weights=np.where(mask, outcome, 0.0), minlength=len(unique))
    counts = np.bincount(inverse, weights=mask.astype(float), minlength=len(unique))
    return unique, inverse, sums, counts


def paired_diff(
    days: np.ndarray,
    outcome: np.ndarray,
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    samples: int = 2000,
    seed: int = 20261101,
) -> tuple[float, float, float]:
    """Day-clustered bootstrap of rate(a) - rate(b) on the same candidate days."""
    rng = np.random.default_rng(seed)
    unique, _, sums_a, counts_a = _cluster_sums(days, outcome, mask_a)
    _, _, sums_b, counts_b = _cluster_sums(days, outcome, mask_b)
    observed = sums_a.sum() / max(counts_a.sum(), 1) - sums_b.sum() / max(counts_b.sum(), 1)
    diffs = np.empty(samples)
    for i in range(samples):
        draw = rng.integers(0, len(unique), len(unique))
        diffs[i] = sums_a[draw].sum() / max(counts_a[draw].sum(), 1) - sums_b[draw].sum() / max(
            counts_b[draw].sum(), 1
        )
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(observed), float(low), float(high)


def _rate(frame: pl.DataFrame, mask: pl.Expr | None = None) -> dict:
    sub = frame.filter(mask) if mask is not None else frame
    n = sub.height
    k = int(sub["tail20"].sum()) if n else 0
    return {"n": n, "tail20": (k / n) if n else None}


def analyze(events: pl.DataFrame, samples: int) -> dict:
    executable = events.filter(
        pl.col("gap_ok")
        & pl.col("prev_change_ok")
        & pl.col("not_limit_open")
        & pl.col("mfe20").is_not_null()
        & (pl.col("k_max") >= SESSIONS)
    )
    auction = executable.filter((pl.col("has_result") == 1) & (pl.col("auction_open") > 0))
    preopen = auction.filter(
        (pl.col("last_time") >= 92400000)
        & (pl.col("last_time") <= 92500000)
        & (pl.col("last_age_ms") <= 30000)
    )
    if auction.filter(pl.col("period") == "development").height == 0:
        raise ValueError(
            "development period (2020-2022) has no samples; run the full 2018-2026 range "
            "so score buckets and thresholds can be fitted"
        )
    coverage = {
        "candidates": events.height,
        "executable": executable.height,
        "auction_result": auction.height,
        "preopen_fresh": preopen.height,
        "opening_bar": executable.filter(
            pl.col("bar_open").is_not_null() & (pl.col("entry_0935_adj") > 0)
        ).height,
        "by_year": {
            str(row["year"]): row["len"]
            for row in events.group_by("year").len().sort("year").to_dicts()
        },
    }
    baseline = {}
    for period in ("development", "validation", "stress", "extension"):
        frame = auction.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        baseline[period] = {
            "n": frame.height,
            "tail20": float(frame["tail20"].mean()),
            "tail10": float(frame["tail10"].mean()),
            "tail30": float(frame["tail30"].mean()),
            "tail_before_stop": float(frame["tail_before_stop"].mean()),
            "mfe20": float(frame["mfe20"].mean()),
            "ret20": float(frame["ret20"].mean()),
        }

    # --- experiment A: does the 331 formation score predict the right tail? ---
    auction = auction.with_columns(
        pl.min_horizontal(pl.lit(2.0), (pl.col("score") * 3.0).floor())
        .cast(pl.Int8)
        .alias("score_bucket")
    )
    score_gradient = []
    for period in ("development", "validation", "stress", "extension"):
        frame = auction.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        for bucket in (0, 1, 2):
            part = frame.filter(pl.col("score_bucket") == bucket)
            if part.height == 0:
                continue
            score_gradient.append(
                {
                    "period": period,
                    "score_bucket": bucket,
                    "n": part.height,
                    "tail20": float(part["tail20"].mean()),
                    "tail_before_stop": float(part["tail_before_stop"].mean()),
                    "mae20": float(part["mae20"].mean()),
                    "ret20": float(part["ret20"].mean()),
                }
            )
    score_tests = []
    for period in ("development", "validation", "stress"):
        frame = auction.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        for bucket in (0, 2):
            mask = (frame["score_bucket"] == bucket).to_numpy()
            diff, low, high = bootstrap_diff(
                frame["date_str"].to_numpy(),
                frame["tail20"].to_numpy().astype(float),
                mask,
                samples=samples,
            )
            score_tests.append(
                {
                    "period": period,
                    "bucket": bucket,
                    "n": int(mask.sum()),
                    "tail": float(frame["tail20"].to_numpy()[mask].mean()) if mask.any() else None,
                    "diff_vs_rest": diff,
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    # --- mechanism: amplitude quintiles (descriptive, full sample) ---
    amplitude = []
    labels = ["1", "2", "3", "4", "5"]
    for feature in ("max_amplitude", "mean_amplitude"):
        bucketed = auction.with_columns(
            pl.col(feature).qcut([0.2, 0.4, 0.6, 0.8], labels=labels).alias("bucket")
        )
        for row in (
            bucketed.group_by("bucket")
            .agg(
                pl.len().alias("n"),
                pl.col("tail20").mean().alias("tail20"),
                pl.col("mae20").mean().alias("mae20"),
                pl.col("ret20").mean().alias("ret20"),
            )
            .sort("bucket")
            .to_dicts()
        ):
            amplitude.append({"feature": feature, **row})

    # --- experiment B: within-day auction TailStrength ranking ---
    ranked = preopen.with_columns(pl.len().over("signal_date").alias("day_n")).filter(
        (pl.col("day_n") >= 4)
        & pl.col("last_minute_price_change").is_not_null()
        & pl.col("last_minute_matched_growth").is_not_null()
        & pl.col("imbalance").is_not_null()
        & pl.col("vol_vs_prev").is_not_null()
    )
    ranks = []
    for feature, alias in (
        ("last_minute_price_change", "rank_price"),
        ("last_minute_matched_growth", "rank_growth"),
        ("imbalance", "rank_imbalance"),
        ("vol_vs_prev", "rank_volume"),
    ):
        ranks.append(
            (pl.col(feature).rank(method="average").over("signal_date") / pl.col("day_n")).alias(
                alias
            )
        )
    ranked = ranked.with_columns(ranks)
    ranked = ranked.with_columns(
        ((pl.col("rank_price") + pl.col("rank_growth") + pl.col("rank_imbalance")) / 3.0).alias(
            "tail_strength"
        )
    )
    ranked = ranked.with_columns(
        (
            (pl.col("tail_strength") >= 0.70)
            & (pl.col("rank_volume") < 0.75)
            & (pl.col("last_minute_price_change") > 0)
        ).alias("tail_rule"),
        pl.col("score")
        .rank(method="ordinal", descending=True)
        .over("signal_date")
        .alias("score_rank"),
        pl.col("tail_strength")
        .rank(method="ordinal", descending=True)
        .over("signal_date")
        .alias("tail_rank"),
    )
    ranked = ranked.with_columns(
        ((pl.col("score_rank") <= 3) & (pl.col("score") >= 0.55)).alias("score_top3"),
        ((pl.col("tail_rank") <= 3) & pl.col("tail_rule")).alias("tail_top3"),
    )
    ranked = ranked.with_columns(
        (pl.col("score_top3") & pl.col("tail_rule")).alias("veto_top3"),
    )
    selection = []
    for period in ("development", "validation", "stress"):
        frame = ranked.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        outcome = frame["tail20"].to_numpy().astype(float)
        days = frame["date_str"].to_numpy()
        for name in ("tail_rule", "score_top3", "tail_top3", "veto_top3"):
            mask = frame[name].to_numpy()
            if mask.any():
                selection.append(
                    {
                        "period": period,
                        "selection": name,
                        "n": int(mask.sum()),
                        "tail20": float(outcome[mask].mean()),
                        "mfe20": float(frame["mfe20"].to_numpy()[mask].mean()),
                    }
                )
        for name in ("tail_top3", "veto_top3"):
            mask_a = frame[name].to_numpy()
            mask_b = frame["score_top3"].to_numpy()
            if mask_a.any() and mask_b.any():
                diff, low, high = paired_diff(days, outcome, mask_a, mask_b, samples=samples)
                selection.append(
                    {
                        "period": period,
                        "selection": f"{name}_vs_score_top3",
                        "n": int(mask_a.sum()),
                        "n_ref": int(mask_b.sum()),
                        "diff": diff,
                        "ci_low": low,
                        "ci_high": high,
                    }
                )
    rule_vs_rest = []
    for period in ("development", "validation", "stress"):
        frame = ranked.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        mask = frame["tail_rule"].to_numpy()
        diff, low, high = bootstrap_diff(
            frame["date_str"].to_numpy(),
            frame["tail20"].to_numpy().astype(float),
            mask,
            samples=samples,
        )
        rule_vs_rest.append(
            {
                "period": period,
                "n": int(mask.sum()),
                "tail": float(frame["tail20"].to_numpy()[mask].mean()),
                "tail_rest": float(frame["tail20"].to_numpy()[~mask].mean()),
                "diff": diff,
                "ci_low": low,
                "ci_high": high,
            }
        )

    # --- experiment C: entry-day auction gap buckets ---
    auction = auction.with_columns(
        pl.when(pl.col("entry_open_gap") < 0)
        .then(pl.lit("negative"))
        .when(pl.col("entry_open_gap") < 0.02)
        .then(pl.lit("0-2"))
        .when(pl.col("entry_open_gap") < 0.04)
        .then(pl.lit("2-4"))
        .otherwise(pl.lit("4+"))
        .alias("gap_bucket"),
    )
    gap = (
        auction.group_by("gap_bucket")
        .agg(
            pl.len().alias("n"),
            pl.col("tail20").mean().alias("tail20"),
            pl.col("mfe20").mean().alias("mfe20"),
        )
        .sort("gap_bucket")
        .to_dicts()
    )
    gap_tests = []
    for period in ("development", "validation", "stress", "extension"):
        frame = auction.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        mask = (frame["gap_bucket"] == "2-4").to_numpy()
        if mask.sum() < 20:
            continue
        diff, low, high = bootstrap_diff(
            frame["date_str"].to_numpy(),
            frame["tail20"].to_numpy().astype(float),
            mask,
            samples=samples,
        )
        gap_tests.append(
            {
                "period": period,
                "n": int(mask.sum()),
                "tail": float(frame["tail20"].to_numpy()[mask].mean()),
                "tail_rest": float(frame["tail20"].to_numpy()[~mask].mean()),
                "diff": diff,
                "ci_low": low,
                "ci_high": high,
            }
        )

    # --- experiment D: opening five-minute confirmation ---
    dev_auction = auction.filter(pl.col("period") == "development")
    bar_threshold = float(dev_auction["bar_ret"].quantile(0.80))
    opening = []
    for period in ("development", "validation", "stress"):
        frame = auction.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        for name, mask in (
            ("bar_ret_top20", (frame["bar_ret"] > bar_threshold).to_numpy()),
            (
                "bar_ret_bottom20",
                (frame["bar_ret"] <= float(dev_auction["bar_ret"].quantile(0.20))).to_numpy(),
            ),
        ):
            if mask.sum() == 0:
                continue
            diff, low, high = bootstrap_diff(
                frame["date_str"].to_numpy(),
                frame["tail20"].to_numpy().astype(float),
                mask,
                samples=samples,
            )
            opening.append(
                {
                    "period": period,
                    "test": name,
                    "n": int(mask.sum()),
                    "tail": float(frame["tail20"].to_numpy()[mask].mean()),
                    "tail_rest": float(frame["tail20"].to_numpy()[~mask].mean()),
                    "diff": diff,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
    # 09:35 close entry after a strong first bar
    confirmed = preopen.filter(
        (pl.col("entry_0935_adj") > 0)
        & pl.col("bar_open").is_not_null()
        & pl.col("bar_close").is_not_null()
        & pl.col("bar_vwap").is_not_null()
    ).with_columns(
        ((pl.col("bar_ret") > 0) & (pl.col("bar_close") > pl.col("bar_vwap"))).alias("strong_open")
    )
    confirmation = []
    for period in ("development", "validation", "stress"):
        frame = confirmed.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        mask = frame["strong_open"].to_numpy()
        outcome = frame["tail20_0935"].to_numpy().astype(float)
        diff, low, high = bootstrap_diff(
            frame["date_str"].to_numpy(),
            outcome,
            mask,
            samples=samples,
        )
        confirmation.append(
            {
                "period": period,
                "n_strong": int(mask.sum()),
                "n_weak": int((~mask).sum()),
                "tail_strong": float(outcome[mask].mean()) if mask.any() else None,
                "tail_weak": float(outcome[~mask].mean()) if (~mask).any() else None,
                "diff": diff,
                "ci_low": low,
                "ci_high": high,
            }
        )

    # --- negative control: buy-pressure composite with a negative volume weight ---
    dev = preopen.filter(pl.col("period") == "development")
    stats: dict[str, dict[str, float]] = {}
    for feature in ("imbalance", "last_minute_matched_growth", "vol_vs_prev"):
        values = dev[feature].drop_nulls().to_numpy()
        low, high = np.percentile(values, [1, 99])
        clipped = np.clip(dev[feature].fill_null(0).to_numpy(), low, high)
        stats[feature] = {
            "mean": float(clipped.mean()),
            "std": float(clipped.std()),
            "low": float(low),
            "high": float(high),
        }

    def zscore(feature: str) -> pl.Expr:
        st = stats[feature]
        return (
            pl.col(feature).fill_null(st["mean"]).clip(st["low"], st["high"]) - st["mean"]
        ) / st["std"]

    composite = (
        0.5 * zscore("imbalance")
        + 0.25 * zscore("last_minute_matched_growth")
        - 0.25 * zscore("vol_vs_prev")
    )
    with_composite = preopen.with_columns(composite.alias("buy_pressure"))
    threshold = float(
        dev.with_columns(composite.alias("buy_pressure"))["buy_pressure"].quantile(0.70)
    )
    with_composite = with_composite.with_columns(
        (pl.col("buy_pressure") >= threshold).alias("buy_pressure_top30")
    )
    buy_pressure = []
    for period in ("development", "validation", "stress", "extension"):
        frame = with_composite.filter(pl.col("period") == period)
        if frame.height == 0:
            continue
        mask = frame["buy_pressure_top30"].to_numpy()
        diff, low, high = bootstrap_diff(
            frame["date_str"].to_numpy(),
            frame["tail20"].to_numpy().astype(float),
            mask,
            samples=samples,
        )
        buy_pressure.append(
            {
                "period": period,
                "n": int(mask.sum()),
                "tail": float(frame["tail20"].to_numpy()[mask].mean()),
                "tail_rest": float(frame["tail20"].to_numpy()[~mask].mean()),
                "diff": diff,
                "ci_low": low,
                "ci_high": high,
            }
        )

    return {
        "version": VERSION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "periods": PERIODS,
        "tail_threshold": TAIL,
        "stop_threshold": STOP,
        "coverage": coverage,
        "baseline": baseline,
        "score_gradient": score_gradient,
        "score_tests": score_tests,
        "amplitude_quintiles": amplitude,
        "selection_tests": selection,
        "tail_rule_vs_rest": rule_vs_rest,
        "gap_buckets": gap,
        "gap_tests": gap_tests,
        "opening_tests": opening,
        "opening_confirmation": confirmation,
        "bar_return_threshold": bar_threshold,
        "buy_pressure": {"threshold": threshold, "stats": stats, "results": buy_pressure},
        "warnings": [
            "Conditional event study; no shared-capital portfolio simulation.",
            "Right tail is MFE >= 20% within 20 sessions from the next-day open.",
            "Tail-before-stop compares first touch of +20% and -6% on daily bars.",
            "2026-07 auction partitions are missing; extension covers 2026-08/09 only.",
            "Score gradient and gap tests are exploratory and multiplicity is not adjusted.",
            "The candidate pool reproduces the T74 rules; production fills still differ slightly.",
        ],
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def write_summary(results: dict, path: Path) -> None:
    lines = [
        f"# {results['version']}",
        "",
        f"generated_at: {results['generated_at']}",
        "",
        "## Coverage",
        "",
        f"- candidates: {results['coverage']['candidates']}",
        f"- executable: {results['coverage']['executable']}",
        f"- auction result: {results['coverage']['auction_result']}",
        f"- fresh preopen: {results['coverage']['preopen_fresh']}",
        f"- opening bar: {results['coverage']['opening_bar']}",
        "",
        "## Baseline (executable candidates with auction result)",
        "",
        "| period | n | tail20 | tail-before-stop | mfe20 | ret20 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for period, row in results["baseline"].items():
        lines.append(
            f"| {period} | {row['n']} | {_pct(row['tail20'])} | "
            f"{_pct(row['tail_before_stop'])} | {_pct(row['mfe20'])} | {_pct(row['ret20'])} |"
        )
    lines += [
        "",
        "## A. 331 (3F) score buckets and the right tail",
        "",
        "| period | bucket | n | tail20 | tail-before-stop | mae20 | ret20 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results["score_gradient"]:
        lines.append(
            f"| {row['period']} | {row['score_bucket']} | {row['n']} | "
            f"{_pct(row['tail20'])} | {_pct(row['tail_before_stop'])} | "
            f"{_pct(row['mae20'])} | {_pct(row['ret20'])} |"
        )
    lines += [
        "",
        "Bucket 0 = lowest 3F score, 2 = highest. Differences vs the rest of the same period:",
        "",
        "| period | bucket | n | tail | diff | 95% CI |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in results["score_tests"]:
        lines.append(
            f"| {row['period']} | {row['bucket']} | {row['n']} | {_pct(row['tail'])} | "
            f"{row['diff_vs_rest']:+.2%} | [{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += [
        "",
        "### Amplitude quintiles (descriptive)",
        "",
        "| feature | quintile | n | tail20 | mae20 | ret20 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in results["amplitude_quintiles"]:
        lines.append(
            f"| {row['feature']} | {row['bucket']} | {row['n']} | "
            f"{_pct(row['tail20'])} | {_pct(row['mae20'])} | {_pct(row['ret20'])} |"
        )
    lines += [
        "",
        "## B. Within-day auction TailStrength ranking",
        "",
        "| period | selection | n | tail20 | mfe20 | diff vs 331 Top3 | 95% CI |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["selection_tests"]:
        if "diff" in row:
            lines.append(
                f"| {row['period']} | {row['selection']} | {row['n']} | n/a | n/a | "
                f"{row['diff']:+.2%} | [{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
            )
        else:
            lines.append(
                f"| {row['period']} | {row['selection']} | {row['n']} | "
                f"{_pct(row['tail20'])} | {_pct(row['mfe20'])} | n/a | n/a |"
            )
    lines += [
        "",
        "TailStrength rule passers vs the other candidates (same days):",
        "",
        "| period | n | tail | tail rest | diff | 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["tail_rule_vs_rest"]:
        lines.append(
            f"| {row['period']} | {row['n']} | {_pct(row['tail'])} | "
            f"{_pct(row['tail_rest'])} | {row['diff']:+.2%} | "
            f"[{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += [
        "",
        "## C. Entry-day auction gap",
        "",
        "| bucket | n | tail20 | mfe20 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in results["gap_buckets"]:
        lines.append(
            f"| {row['gap_bucket']} | {row['n']} | {_pct(row['tail20'])} | {_pct(row['mfe20'])} |"
        )
    lines += [
        "",
        "2%-4% gap vs the rest:",
        "",
        "| period | n | tail | tail rest | diff | 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["gap_tests"]:
        lines.append(
            f"| {row['period']} | {row['n']} | {_pct(row['tail'])} | {_pct(row['tail_rest'])} | "
            f"{row['diff']:+.2%} | [{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += [
        "",
        "## D. Opening five-minute information",
        "",
        f"First-bar return top quintile threshold (development only): {results['bar_return_threshold']:.4f}",
        "",
        "| period | test | n | tail | tail rest | diff | 95% CI |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["opening_tests"]:
        lines.append(
            f"| {row['period']} | {row['test']} | {row['n']} | {_pct(row['tail'])} | "
            f"{_pct(row['tail_rest'])} | {row['diff']:+.2%} | "
            f"[{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += [
        "",
        "Confirmation variant: wait for a strong first bar and buy the 09:35 close.",
        "",
        "| period | n strong | n weak | tail strong | tail weak | diff | 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["opening_confirmation"]:
        lines.append(
            f"| {row['period']} | {row['n_strong']} | {row['n_weak']} | "
            f"{_pct(row['tail_strong'])} | {_pct(row['tail_weak'])} | "
            f"{row['diff']:+.2%} | [{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += [
        "",
        "## Negative control: buy-pressure composite (0.5*imbalance + 0.25*growth - 0.25*volume)",
        "",
        "| period | n | tail | tail rest | diff | 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results["buy_pressure"]["results"]:
        lines.append(
            f"| {row['period']} | {row['n']} | {_pct(row['tail'])} | {_pct(row['tail_rest'])} | "
            f"{row['diff']:+.2%} | [{row['ci_low']:+.2%}, {row['ci_high']:+.2%}] |"
        )
    lines += ["", "## Warnings", ""]
    lines += [f"- {warning}" for warning in results["warnings"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    data_dir: Path, minute_dir: Path, output: Path, start_year: int, end_year: int, samples: int
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "events.parquet"
    if events_path.exists():
        events = pl.read_parquet(events_path)
    else:
        events = build_events(data_dir, start_year, end_year)
        events.write_parquet(events_path)
    panel_path = output / "panel.parquet"
    if panel_path.exists():
        panel = pl.read_parquet(panel_path)
    else:
        panel = attach_features(data_dir, minute_dir, events, panel_path)
    aggregated = aggregate(panel)
    aggregated.write_parquet(output / "events_aggregated.parquet")
    results = analyze(aggregated, samples)
    (output / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_summary(results, output / "SUMMARY.md")
    print(
        json.dumps(
            {
                "coverage": results["coverage"],
                "baseline": results["baseline"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--minute-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args()
    run(
        args.data_dir,
        args.minute_dir,
        args.output,
        args.start_year,
        args.end_year,
        args.bootstrap_samples,
    )


if __name__ == "__main__":
    main()
