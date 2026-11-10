"""S01 跨管道差异 —— 反事实实验：只把「股票池口径」换掉，其余（引擎/撮合/成本/排序/仓位）不动。

C0 = 研究侧复现（原 in_universe：主板 60/00 + raw_close>=3 + prior_amount20>=1e8 + observed_bars>=120 + !ST）
C1 = 研究侧引擎 + 生产侧股票池（close(后复权)>=2.0 + st_flag==0 + volume>0，全板块；exclude_new_days 在
     matrix 侧无实现，见 REPORT §2.7）

判据：C0 应复现 registry 的 252 笔 / -32.09%；C1 与生产管道 199 笔 / +24.27% 的差应只剩
期初共享 warmup 与 carry_out 语义带来的少量残差。

只读：不改 common.py、不改任何策略文件、不写 D:\\TSP。
用法：
  backend\\.venv\\Scripts\\python.exe research\\s01-caliber-gap-20261108\\counterfactual.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / "research" / "strategy-search-20261107" / "scripts"))
sys.path.insert(0, str(PROJECT / "backend"))

import common as rc  # noqa: E402
from app.indicators.pipeline import compute_limit_signals  # noqa: E402
from app.price_limits import polars_price_limit_pct  # noqa: E402
from app.tickflow.security_status import attach_st_history  # noqa: E402

OUT = HERE / "results"
S01 = next(s for s in rc.STRATEGIES if s.key == "S01_ma_cross_20_60")
PROD_TRADES = PROJECT / "research" / "s01b-20261108" / "results" / "a0_10bp" / "trades.parquet"


def load_full_panel() -> pl.DataFrame:
    """common.load_panel 去掉 60/00 前缀过滤 —— 其余步骤逐行照抄。"""
    m = rc.open_market()
    frame = m.market.get_daily_batch([], rc.WARMUP_START, rc.EVAL_END, rc.COLUMNS)
    frame = frame.sort(["symbol", "date"])
    dup = frame.select(pl.struct("symbol", "date").is_duplicated().sum()).item()
    if dup:
        raise ValueError(f"duplicate symbol/date rows: {dup}")
    frame = attach_st_history(frame, m.st_history)
    frame = compute_limit_signals(
        frame, m.instruments, needed={"limit_up_price", "limit_down_price"},
    ).with_columns(
        (pl.col("raw_close") >= pl.col("limit_up_price")).fill_null(False).alias("signal_limit_up"),
        (pl.col("raw_close") <= pl.col("limit_down_price")).fill_null(False).alias("signal_limit_down"),
        polars_price_limit_pct(pl.col("symbol"), pl.col("date"), pl.col("st_flag")).alias("price_limit_pct"),
    )
    return m, frame


def add_cross_section(frame: pl.DataFrame) -> pl.DataFrame:
    """common.add_universe 的截面部分（market_breadth + rk_*），但不改 in_universe。

    build_signals 需要 rk_ret5/rk_ret20/rk_vol60/rk_ret60/rk_near_high 五列；S01 只用
    e_ma_cross/x_ma_cross/s_ma_cross，不消费这些名列，故 C1 里它们的取值不影响 S01 结果，
    但必须存在。这里按 add_universe 原文逐行计算，唯一区别是池掩码来自调用方已设好的 in_universe。
    """
    f = frame.with_columns(
        pl.when(pl.col("in_universe") & pl.col("ma60").is_not_null())
        .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
        .otherwise(None)
        .mean().over("date").alias("market_breadth"),
    )
    for col, name in (("ret5", "rk_ret5"), ("ret20", "rk_ret20"), ("vol60", "rk_vol60"),
                      ("ret60", "rk_ret60"), ("dist_52w_high", "rk_near_high")):
        f = f.with_columns(
            pl.when(pl.col("in_universe") & pl.col(col).is_not_null())
            .then(pl.col(col).rank("average").over("date")
                  / pl.col("in_universe").sum().over("date"))
            .otherwise(None)
            .alias(name),
        )
    return f


def summarize(name: str, res: dict) -> dict:
    st = rc.summarize(res, rc.EVAL_START, rc.EVAL_END, "ALL")
    st.pop("returns", None)
    return {
        "name": name,
        "n_trades": res["trades"].__len__(),
        "final_positions": res["final_positions"],
        "ALL": st,
        "exit_reason": pl.DataFrame(res["trades"]).group_by("exit_reason").len().to_dicts()
        if res["trades"] else [],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    m, panel = load_full_panel()
    print(f"[panel] rows={panel.height} symbols={panel['symbol'].n_unique()} "
          f"dates={panel['date'].min()}..{panel['date'].max()} load={time.perf_counter()-t0:.0f}s", flush=True)
    ind = rc.add_indicators(panel)
    print(f"[ind] {time.perf_counter()-t0:.0f}s", flush=True)
    del panel

    out: dict = {"panel": {"rows": ind.height, "symbols": ind["symbol"].n_unique(),
                           "date_min": str(ind["date"].min()), "date_max": str(ind["date"].max())}}

    # ---- C0：研究侧原口径 ----
    f0 = ind.filter(pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00"))
    f0 = rc.build_signals(rc.add_universe(f0)).filter(pl.col("date") >= rc.EVAL_START)
    print(f"[C0] signals={int(f0[S01.entry].sum())} {time.perf_counter()-t0:.0f}s", flush=True)
    res0 = rc.run_continuous(m, f0, S01, 10.0)
    out["C0_research_gate"] = summarize("C0_research_gate", res0)
    print("[C0]", json.dumps(out["C0_research_gate"]["ALL"], ensure_ascii=False)[:300], flush=True)
    pl.DataFrame(res0["trades"]).write_parquet(OUT / "C0_trades.parquet")
    del f0

    # ---- C1：生产侧股票池 + 同一引擎 ----
    f1 = ind.with_columns(
        ((pl.col("close") >= 2.0) & (pl.col("st_flag") == 0) & (pl.col("volume") > 0))
        .fill_null(False).alias("in_universe")
    )
    f1 = add_cross_section(f1)   # build_signals 需要 rk_* / market_breadth（S01 不消费其值）
    f1 = rc.build_signals(f1)
    # build_signals 不改 in_universe；其余策略列用不到
    f1 = f1.filter(pl.col("date") >= rc.EVAL_START)
    print(f"[C1] signals={int(f1[S01.entry].sum())} {time.perf_counter()-t0:.0f}s", flush=True)
    res1 = rc.run_continuous(m, f1, S01, 10.0)
    out["C1_production_gate"] = summarize("C1_production_gate", res1)
    print("[C1]", json.dumps(out["C1_production_gate"]["ALL"], ensure_ascii=False)[:300], flush=True)
    tr1 = pl.DataFrame(res1["trades"])
    tr1.write_parquet(OUT / "C1_trades.parquet")

    # ---- 与生产管道逐笔对照 ----
    p = pl.read_parquet(PROD_TRADES).select("symbol", "entry_date", "pnl_amount", "exit_reason")
    k1 = set(zip(tr1["symbol"].to_list(), tr1["entry_date"].to_list()))
    kp = set(zip(p["symbol"].to_list(), p["entry_date"].to_list()))
    out["C1_vs_production"] = {
        "n_C1": len(k1), "n_prod": len(kp), "intersection": len(k1 & kp),
        "C1_only": len(k1 - kp), "prod_only": len(kp - k1),
        "jaccard": round(len(k1 & kp) / max(1, len(k1 | kp)), 4),
    }
    print("[C1 vs prod]", json.dumps(out["C1_vs_production"], ensure_ascii=False), flush=True)
    out["elapsed_s"] = round(time.perf_counter() - t0, 1)
    (OUT / "counterfactual.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                             encoding="utf-8")
    print("done", out["elapsed_s"], "s", flush=True)


if __name__ == "__main__":
    main()
