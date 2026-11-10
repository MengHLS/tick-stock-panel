"""S01 跨管道差异归因（只读）。

输入（只读，不写 D:\\TSP）：
  R = research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json  (研究侧 252 笔)
  P = research/s01b-20261108/results/a0_10bp/trades.parquet                     (生产管道 199 笔)
  Panels = D:\\TSP\\data\\kline_daily_enriched (close=后复权, raw_close=原始价)

输出：
  results/gap_sets.json      差集与逐笔聚合
  results/buckets.json       逐笔归因分桶
  results/common_check.json  交集逐笔撮合一致性核对
  results/facts_diff.parquet 差集标的在信号日的面板事实（可复核）

用法：
  backend\\.venv\\Scripts\\python.exe research\\s01-caliber-gap-20261108\\gap_attribution.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RESEARCH_RUN = PROJECT / "research" / "strategy-search-20261107" / "results" / "run_S01_ma_cross_20_60_10.json"
PROD_TRADES = PROJECT / "research" / "s01b-20261108" / "results" / "a0_10bp" / "trades.parquet"
ENRICHED = Path(r"D:\TSP\data\kline_daily_enriched")
OUT = HERE / "results"

START = date(2018, 1, 8)
END = date(2026, 10, 30)

# 研究侧口径（research/strategy-search-20261107/scripts/common.py:113-121 UNIVERSE, :171-175 add_universe, :50-56 load_panel 前缀过滤）
RES_PRICE_RAW = 3.0
RES_AMOUNT20 = 1e8
RES_BARS = 120
RES_PREFIX = ("60", "00")
# 生产侧口径（research/s01b-20261108/strategies/custom/s01b_a0.py META.basic_filter）
PRD_PRICE_ADJ = 2.0


def load_research() -> pl.DataFrame:
    d = json.loads(RESEARCH_RUN.read_text(encoding="utf-8"))
    t = pl.DataFrame(d["trades"])
    return t.with_columns(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("entry_date").cast(pl.Utf8),
        pl.col("exit_date").cast(pl.Utf8),
        pl.col("entry_signal_date").cast(pl.Utf8),
        pl.col("exit_signal_date").cast(pl.Utf8),
    )


def load_prod() -> pl.DataFrame:
    return pl.read_parquet(PROD_TRADES).with_columns(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("entry_date").cast(pl.Utf8),
        pl.col("exit_date").cast(pl.Utf8),
    )


def panel_facts(symbols: list[str]) -> pl.DataFrame:
    lf = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .filter(pl.col("symbol").is_in(symbols))
        .select("symbol", "date", "open", "close", "raw_close", "volume", "amount")
        .filter((pl.col("date") >= START) & (pl.col("date") <= END))
    )
    f = lf.collect().sort(["symbol", "date"])
    f = f.with_columns(
        pl.col("date").cum_count().over("symbol").alias("observed_bars"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("prior_amount20"),
        pl.col("close").rolling_mean(20).over("symbol").alias("ma20"),
        pl.col("close").rolling_mean(60).over("symbol").alias("ma60"),
    )
    f = f.with_columns(
        pl.col("ma20").shift(1).over("symbol").alias("prev_ma20"),
        pl.col("ma60").shift(1).over("symbol").alias("prev_ma60"),
    ).with_columns(
        ((pl.col("ma20") > pl.col("ma60")) & (pl.col("prev_ma20") <= pl.col("prev_ma60")))
        .fill_null(False)
        .alias("cross_up")
    )
    return f


def buckets(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.when(pl.col("symbol").str.slice(0, 2).is_in(list(RES_PREFIX)))
            .then(pl.lit("主板"))
            .otherwise(pl.lit("非主板"))
            .alias("board"),
            (pl.col("raw_close") < RES_PRICE_RAW).alias("fail_price_raw"),
            (pl.col("prior_amount20") < RES_AMOUNT20).fill_null(True).alias("fail_amount20"),
            (pl.col("observed_bars") < RES_BARS).alias("fail_bars120"),
        )
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    r = load_research()
    p = load_prod()
    print("research trades", r.height, "prod trades", p.height)

    kr = set(zip(r["symbol"].to_list(), r["entry_date"].to_list()))
    kp = set(zip(p["symbol"].to_list(), p["entry_date"].to_list()))
    common = kr & kp
    r_only = kr - kp
    p_only = kp - kr
    print("common", len(common), "research_only", len(r_only), "prod_only", len(p_only),
          "diff", len(r_only) - len(p_only))

    r2 = r.with_columns(pl.struct("symbol", "entry_date").is_in(
        [{"symbol": s, "entry_date": d} for s, d in sorted(common)]).alias("_common"))
    p2 = p.with_columns(pl.struct("symbol", "entry_date").is_in(
        [{"symbol": s, "entry_date": d} for s, d in sorted(common)]).alias("_common"))

    def agg(df: pl.DataFrame, label: str) -> dict:
        return {
            "side": label,
            "n": df.height,
            "pnl_amount_sum": round(float(df["pnl_amount"].sum()), 2),
            "entry_value_sum": round(float(df["entry_value"].sum()), 2),
            "avg_pnl_pct": round(float(df["pnl_pct"].mean()), 6) if df.height else None,
            "win_rate": round(float((df["pnl_pct"] > 0).mean()), 4) if df.height else None,
            "median_pnl_pct": round(float(df["pnl_pct"].median()), 6) if df.height else None,
        }

    sets = {
        "research_all": agg(r, "research"),
        "research_common": agg(r2.filter(pl.col("_common")), "research"),
        "research_only": agg(r2.filter(~pl.col("_common")), "research"),
        "prod_all": agg(p, "prod"),
        "prod_common": agg(p2.filter(pl.col("_common")), "prod"),
        "prod_only": agg(p2.filter(~pl.col("_common")), "prod"),
    }
    (OUT / "gap_sets.json").write_text(json.dumps(sets, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(sets, ensure_ascii=False, indent=1))

    # ---- 交集逐笔撮合一致性 ----
    key = ["symbol", "entry_date"]
    cols = ["entry_price", "exit_date", "exit_price", "pnl_pct", "pnl_amount", "duration",
            "exit_reason", "shares"]
    j = r2.filter(pl.col("_common")).select(key + cols).join(
        p2.filter(pl.col("_common")).select(key + cols), on=key, how="inner", suffix="_p")
    chk = {}
    for c in cols:
        if c in ("symbol", "entry_date"):
            continue
        a, b = j[c], j[f"{c}_p"]
        if j.schema[c] == pl.Utf8:
            n = int((a != b).sum())
        else:
            n = int(((a - b).abs() > 1e-6).sum())
        chk[c] = {"n_diff": n}
    chk["rows"] = j.height
    (OUT / "common_check.json").write_text(json.dumps(chk, ensure_ascii=False, indent=1), encoding="utf-8")
    print("common_check", json.dumps(chk, ensure_ascii=False))

    # ---- 差集标的的面板事实 ----
    syms = sorted({s for s, _ in (r_only | p_only)})
    facts = panel_facts(syms)

    def attach(df: pl.DataFrame, signal_col: str) -> pl.DataFrame:
        left = df.select("symbol", "entry_date",
                         pl.col(signal_col).cast(pl.Utf8).str.to_date().alias("signal_date"),
                         "pnl_amount", "pnl_pct", "entry_value")
        return left.join(
            facts.select("symbol", "date", "open", "close", "raw_close", "observed_bars",
                         "prior_amount20", "ma20", "ma60", "cross_up"),
            left_on=["symbol", "signal_date"], right_on=["symbol", "date"], how="left")

    ro = attach(r2.filter(~pl.col("_common")), "entry_signal_date")
    # 生产侧无 entry_signal_date（矩阵原生），用同一交易日历取前一个交易日
    cal = facts["date"].unique().sort().to_list()
    prev = {cal[i]: cal[i - 1] for i in range(1, len(cal))}
    po = (
        p2.filter(~pl.col("_common"))
        .with_columns(
            pl.col("entry_date").str.to_date()
            .replace_strict(prev, default=None, return_dtype=pl.Date).alias("signal_date")
        )
        .select("symbol", "entry_date", "signal_date", "pnl_amount", "pnl_pct", "entry_value")
        .join(
            facts.select("symbol", "date", "open", "close", "raw_close", "observed_bars",
                         "prior_amount20", "ma20", "ma60", "cross_up"),
            left_on=["symbol", "signal_date"], right_on=["symbol", "date"], how="left")
    )

    ro = buckets(ro).with_columns(pl.lit("research_only").alias("side"))
    po = buckets(po).with_columns(pl.lit("prod_only").alias("side"))
    both = pl.concat([ro, po], how="diagonal_relaxed")
    print("facts_diff rows", both.height)
    both.write_parquet(OUT / "facts_diff.parquet")

    # 研究侧差集：生产侧是否也有金叉信号 / 是否进得了生产股票池
    ro = ro.with_columns(
        (pl.col("close") >= PRD_PRICE_ADJ).fill_null(False).alias("in_prod_pool_price"),
        pl.col("cross_up").fill_null(False).alias("prod_signal"),
    )
    print("\n=== research_only 概况 ===")
    print(ro.select(pl.len().alias("n"),
                    pl.col("prod_signal").sum().alias("prod_signal_true"),
                    pl.col("in_prod_pool_price").sum().alias("in_prod_pool_price"),
                    pl.col("pnl_amount").sum().round(2).alias("pnl_sum")))
    print(ro.group_by("in_prod_pool_price", "prod_signal").agg(
        pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl")).sort("n", descending=True))

    print("\n=== prod_only 概况 ===")
    print(po.select(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl_sum")))
    print(po.group_by("board", "fail_price_raw", "fail_amount20", "fail_bars120").agg(
        pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl")).sort("n", descending=True))

    # 生产侧在差集信号日的仓位占用（用于判定「无空位」）
    pos = p.select("symbol", "entry_date", "exit_date").with_columns(
        pl.col("entry_date").str.to_date(), pl.col("exit_date").str.to_date())
    rows = []
    for row in ro.iter_rows(named=True):
        d = row["signal_date"]
        held = pos.filter((pl.col("entry_date") <= d) & (pl.col("exit_date") > d))
        rows.append({"symbol": row["symbol"], "signal_date": d, "prod_open_positions": held.height})
    conc = pl.DataFrame(rows)
    ro = ro.join(conc, on=["symbol", "signal_date"], how="left")
    # 当日（= 信号日次一交易日）生产侧新开仓笔数
    buys = (p.with_columns(pl.col("entry_date").str.to_date())
            .group_by("entry_date").len()
            .rename({"entry_date": "entry_date_d", "len": "prod_buys_on_entry_date"}))
    ro = ro.with_columns(pl.col("entry_date").str.to_date().alias("entry_date_d")).join(
        buys, on="entry_date_d", how="left").with_columns(
        pl.col("prod_buys_on_entry_date").fill_null(0))
    # 研究侧同时点仓位占用（用于对照）
    rpos = r.select("symbol", "entry_date", "exit_date").with_columns(
        pl.col("entry_date").str.to_date(), pl.col("exit_date").str.to_date())
    rbuy = (r.with_columns(pl.col("entry_date").str.to_date())
            .group_by("entry_date").len()
            .rename({"entry_date": "signal_date", "len": "res_buys_on_sig_date"}))
    rows = []
    for row in po.iter_rows(named=True):
        d = row["signal_date"]
        held = rpos.filter((pl.col("entry_date") <= d) & (pl.col("exit_date") > d))
        rows.append({"symbol": row["symbol"], "signal_date": d, "res_open_positions": held.height})
    po = po.join(pl.DataFrame(rows), on=["symbol", "signal_date"], how="left").join(
        rbuy, on="signal_date", how="left").with_columns(pl.col("res_buys_on_sig_date").fill_null(0))
    ro.write_parquet(OUT / "research_only_classified.parquet")
    print("\n=== research_only 按仓位/当日买入分类 ===")
    print(ro.group_by(["prod_signal", "in_prod_pool_price", "prod_open_positions", "prod_buys_on_entry_date"])
          .agg(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl"))
          .sort("n", descending=True))

    po.write_parquet(OUT / "prod_only_classified.parquet")
    print("\n=== prod_only 按研究侧仓位/当日买入分类（主板研究合格子集）===")
    po_ok = po.filter((pl.col("board") == "主板") & ~pl.col("fail_price_raw")
                      & ~pl.col("fail_amount20") & ~pl.col("fail_bars120"))
    print(po.filter((pl.col("board") == "主板") & ~pl.col("fail_price_raw")
                    & ~pl.col("fail_amount20") & ~pl.col("fail_bars120"))
          .group_by(["res_open_positions", "res_buys_on_sig_date"])
          .agg(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl"))
          .sort("n", descending=True))
    print("n =", po_ok.height)
    # 研究侧池内成员：差集标的是否差在「研究侧未选」而非「研究侧不可选」
    po = po.with_columns(
        pl.when(pl.col("board") != "主板").then(pl.lit("board_outside_60_00"))
        .when(pl.col("fail_price_raw")).then(pl.lit("price_raw_lt_3"))
        .when(pl.col("fail_amount20")).then(pl.lit("amount20_lt_1e8"))
        .when(pl.col("fail_bars120")).then(pl.lit("observed_bars_lt_120"))
        .otherwise(pl.lit("in_research_pool_not_selected")).alias("gate"))
    po.write_parquet(OUT / "prod_only_classified.parquet")
    print(po.group_by("gate").agg(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl"))
          .sort("n", descending=True))


if __name__ == "__main__":
    main()
