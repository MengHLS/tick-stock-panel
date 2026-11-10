"""独立核验：8 臂 + a0 的 I1/I3/价基/前 1777 行不变。只读。"""
import json, os
from pathlib import Path
import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
POST = ROOT / "research/s01b-20261108/postfix_20261108"
FIVE = ROOT / "research/s01b-20261108/five_a"
ARMS = ["base_nodefaults_10bp","base_nodefaults_gross","only_block_limit_open",
        "only_entry_price_basis_raw","only_execution_costs",
        "only_exit_signal_requires_profit","only_finalize_open_at_end",
        "only_trailing_peak_price_close"]
out = {}
for arm in ARMS + ["results_all/a0_10bp"]:
    pd_ = POST / arm if (POST/arm/"trades.parquet").exists() else POST/"results_all"/arm.split("/")[-1]
    pre = (FIVE/arm) if (FIVE/arm/"trades.parquet").exists() else ROOT/"research/s01b-20261108/results"/arm.split("/")[-1]
    r = {"post_dir": str(pd_.relative_to(ROOT)), "pre_dir": str(pre.relative_to(ROOT)) if pre.exists() else None}
    te, tp = pl.read_parquet(pd_/"equity.parquet"), pl.read_parquet(pd_/"trades.parquet")
    last, prev = te.row(-1, named=True), te.row(-2, named=True)
    r["last_row"] = last
    oae = tp.filter(pl.col("open_at_end") == True)
    r["n_trades"] = tp.height; r["n_oae"] = oae.height
    r["positions_vs_oae"] = [int(last["positions"]), oae.height]
    r["I1_residual"] = round(float(last["value"]) - float(last["cash"]) - float(oae["exit_value"].sum()), 2)
    r["cash_eq_value_when_flat"] = (abs(float(last["value"]) - float(last["cash"])) < 0.005) if last["positions"] == 0 else None
    # 价基: 每笔 end 的 exit_price 与当日 execution_open/close 对比由 engine 复算, 这里只记末笔
    e = tp.filter(pl.col("exit_reason") == "end")
    r["end_trades"] = e.select(["symbol","exit_date","exit_price","shares","pnl_amount","open_at_end"]).to_dicts() if e.height <= 8 else e.height
    if pre.exists():
        pe, pt = pl.read_parquet(pre/"equity.parquet"), pl.read_parquet(pre/"trades.parquet")
        r["equity_head_identical"] = te.head(te.height-1).equals(pe.head(pe.height-1)) if te.height == pe.height else "HEIGHT_DIFF"
        r["pre_last_row"] = pe.row(-1, named=True)
        cols = ["symbol","entry_date","exit_date","exit_price","shares","pnl_amount","exit_reason","open_at_end"]
        key = lambda d: sorted([tuple(str(x) for x in row) for row in d.select(cols).iter_rows()])
        r["trades_multiset_identical"] = key(tp) == key(pt)
        r["pre_last_1399_trades"] = None
    out[arm] = r
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
