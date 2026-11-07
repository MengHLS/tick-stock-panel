"""定位：为什么 §12 的 S09 重跑给出 679 笔，而本轮给出 732 笔（= 旧 registry 行）。

只做两件事：
  1) 按 §12 的写法重建 canon / sig / run_frame，报每一步的 height 与 (symbol,date) 重复数；
  2) 用同一批数据跑 S09 账户，报 trades 数，看是否复现 679。
不写任何正式产物。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import polars as pl

import common
from app.config import settings
from app.factors import store
from app.factors.dsl import FACTOR_COLUMN, compile_formula
from app.strategy.scoring import materialize_scoring_columns

IDS8 = ["ma20", "ma20_bias", "uf_prior_high_20", "uf_prior_high_55",
        "uf_prior_low_10", "uf_prior_vol_20", "uf_prior_high_250", "uf_vol60"]


def comp(frame, formula):
    c = compile_formula(formula)
    assert c.ok, [(e.code, e.message) for e in c.errors]
    return c.frame_transform(frame)[FACTOR_COLUMN].cast(pl.Boolean).fill_null(False)


def dup(df, name):
    d = df.group_by(["symbol", "date"]).len().filter(pl.col("len") > 1)
    print(f"  {name}: height={df.height} dup_keys={d.height} max_mult={int(d['len'].max()) if d.height else 1}", flush=True)
    return d.height


market = common.open_market()
panel = common.load_panel(market)
prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
print("prepared", prepared.height, flush=True)
dup(prepared, "prepared")

store.load_into_registry(settings.data_dir)

# A) 本轮写法：只 rename ma20，只物化 3 个 id
baseA = prepared.rename({"ma20": "ma20_research"})
canonA = materialize_scoring_columns(baseA, ["ma20", "uf_prior_high_55", "uf_prior_vol_20"])
dup(canonA, "canonA(r3)")

# B) §12 写法：rename ma20+ma60，物化 8 个 id
baseB = prepared.rename({"ma20": "ma20_research", "ma60": "ma60_research"})
canonB = materialize_scoring_columns(baseB, IDS8)
dup(canonB, "canonB(r8)")

for col in ("ma20", "uf_prior_high_55", "uf_prior_vol_20"):
    a, b = canonA[col], canonB[col]
    both = pl.DataFrame({"a": a, "b": b}).filter(pl.col("a").is_not_null() & pl.col("b").is_not_null())
    d = (both["a"] - both["b"]).abs().max() if both.height else None
    print(f"  {col}: max_abs_diff A-vs-B = {d}; nulls A={a.null_count()} B={b.null_count()}", flush=True)

print("\n== §12 路径重建 ==", flush=True)
u = pl.col("in_universe")
hi55 = comp(canonB, "close > uf_prior_high_55")
vol20 = comp(canonB, "volume > 1.5 * uf_prior_vol_20")
ma20c = comp(canonB, "close < ma20")
e = (u & hi55 & vol20).fill_null(False)
sig = canonB.with_columns(
    hi55.alias("hi55_c"), vol20.alias("vol20_c"), ma20c.alias("x_volbreak_c"), e.alias("e_volbreak_c"),
).filter((pl.col("date") >= pl.lit(common.EVAL_START)) & (pl.col("date") <= pl.lit(common.EVAL_END)))
dup(sig, "sig(eval)")

run_frame = prepared.join(
    sig.select("symbol", "date", "e_volbreak_c", "x_volbreak_c"), on=["symbol", "date"], how="left"
).with_columns(pl.col("e_volbreak_c").fill_null(False), pl.col("x_volbreak_c").fill_null(False))
dup(run_frame, "run_frame(join)")
print("  run_frame height vs prepared:", run_frame.height, prepared.height, flush=True)

ev = run_frame.filter(run_frame["date"] >= common.EVAL_START)
strat = common.Strategy("S09", "趋势", "t", "e_volbreak_c", "x_volbreak_c", "s_volbreak", 20, "h")
res = common.run_continuous(market, ev, strat, 10.0)
print("§12-path n_trades =", len(res["trades"]), flush=True)

# C) 同一 canonB，但不经过 join，直接在 canonB 上取列（本轮写法 + 8 id）
ev2 = canonB.with_columns(e.alias("e_volbreak_c"), ma20c.alias("x_volbreak_c")).filter(
    canonB["date"] >= common.EVAL_START)
res2 = common.run_continuous(market, ev2, strat, 10.0)
print("direct-canonB n_trades =", len(res2["trades"]), flush=True)

# 差在哪里：两次 trades 的集合差
a = {(t["symbol"], str(t.get("entry_date")), str(t.get("exit_date"))) for t in res["trades"]}
b = {(t["symbol"], str(t.get("entry_date")), str(t.get("exit_date"))) for t in res2["trades"]}
print("only-in-join-path:", len(a - b), "| only-in-direct:", len(b - a), flush=True)
print("sample only-in-join:", sorted(a - b)[:5], flush=True)
print("sample only-in-direct:", sorted(b - a)[:5], flush=True)
