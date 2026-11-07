"""S09/S02 账户层对照：研究侧 vs canonical 侧，各跑一遍同一引擎，逐年对账。

目的：把「信号层 jaccard=1.000」升到「账户层是否逐笔一致」，并区分两类差异：
  (a) 口径差异（研究列 vs canonical 列）——本轮判据看这个；
  (b) 实测环境漂移（同一列今天跑 vs registry 里 36 次运行当时跑）——不是口径问题，
      但必须暴露，否则会被人误当成口径差。
只读，不写 registry。
"""
from __future__ import annotations

import json
import sys
import time
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

OUT = Path(__file__).resolve().parent
R: dict = {}


def comp(frame: pl.DataFrame, formula: str) -> pl.Series:
    c = compile_formula(formula)
    if not c.ok:
        raise RuntimeError([(e.code, e.message) for e in c.errors])
    o = c.frame_transform(frame)
    return o[FACTOR_COLUMN].cast(pl.Boolean).fill_null(False)


t0 = time.perf_counter()
market = common.open_market()
panel = common.load_panel(market)
prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
store.load_into_registry(settings.data_dir)
base = prepared.rename({"ma20": "ma20_research", "ma60": "ma60_research"})
canon = materialize_scoring_columns(base, ["ma20", "ma20_bias", "uf_prior_high_55",
                                           "uf_prior_vol_20", "uf_prior_high_20",
                                           "uf_prior_low_10"])
u = pl.col("in_universe")
e_s09 = (u & comp(canon, "close > uf_prior_high_55")
         & comp(canon, "volume > 1.5 * uf_prior_vol_20")).fill_null(False)
x_s09 = comp(canon, "close < ma20")
e_s02 = (u & comp(canon, "close > uf_prior_high_20")).fill_null(False)
x_s02 = comp(canon, "close < uf_prior_low_10")

# 直接把 canonical 信号列并进 prepared（不 join，避免行序/边界差异）
frame = prepared.with_columns(
    e_s09.alias("e_volbreak_c"), x_s09.alias("x_volbreak_c"),
    e_s02.alias("e_donchian_c"), x_s02.alias("x_donchian_c"),
)
ev = frame.filter(frame["date"] >= common.EVAL_START)
R["build_seconds"] = round(time.perf_counter() - t0, 1)
R["eval_rows"] = ev.height

registry = json.loads(
    (ROOT / "research" / "strategy-search-20261107" / "results" / "registry.json").read_text(encoding="utf-8")
)["runs"]

CASES = (
    ("S09_research_cols", "e_volbreak", "x_volbreak", "s_volbreak", "S09_volume_breakout_55@10"),
    ("S09_canonical_cols", "e_volbreak_c", "x_volbreak_c", "s_volbreak", "S09_volume_breakout_55@10"),
    ("S02_research_cols", "e_donchian", "x_donchian", "s_donchian", "S02_donchian_20_10@10"),
    ("S02_canonical_cols", "e_donchian_c", "x_donchian_c", "s_donchian", "S02_donchian_20_10@10"),
)
R["runs"] = {}
for key, entry, exitc, score, reg in CASES:
    t1 = time.perf_counter()
    strat = common.Strategy(key, "诊断", key, entry, exitc, score, 60, "对照")
    res = common.run_continuous(market, ev, strat, 10.0)
    last_eq = res["equity"][-1] if res["equity"] else {}
    R["runs"][key] = {
        "seconds": round(time.perf_counter() - t1, 1),
        "n_trades": len(res["trades"]),
        "n_equity_points": len(res["equity"]),
        "last_equity_record": {k: v for k, v in list(last_eq.items())[:12]},
        "last_equity_keys": sorted(last_eq.keys()),
        "segments": [
            {"start": s["start"], "end": s["end"], "signals": s["signals"],
             "n_trades": (s["stats"] or {}).get("n_trades") if isinstance(s["stats"], dict) else None}
            for s in res["segments"]
        ],
        "registry_total_n_trades": registry[reg]["n_trades"],
        "registry_total_return": registry[reg]["ALL"]["total_return"],
        "registry_segments": registry[reg]["segments"],
    }
    print(key, R["runs"][key]["n_trades"], "registry:", registry[reg]["n_trades"], flush=True)

# 逐笔对照：canonical vs research（同一次进程、同一帧）
R["pairwise"] = {}
for a, b in (("S09_research_cols", "S09_canonical_cols"), ("S02_research_cols", "S02_canonical_cols")):
    ta = R["runs"][a]["n_trades"]
    tb = R["runs"][b]["n_trades"]
    sa = R["runs"][a]["segments"]
    sb = R["runs"][b]["segments"]
    R["pairwise"][f"{a}_vs_{b}"] = {
        "n_trades_equal": ta == tb,
        "segments_equal": sa == sb,
        "merged_segments": [{"start": x["start"], "research": x["n_trades"], "canonical": y["n_trades"],
                             "signals_research": x["signals"], "signals_canonical": y["signals"]}
                            for x, y in zip(sa, sb)],
    }

(OUT / "ACCOUNT_CHECK.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps({"pairwise": R["pairwise"]}, ensure_ascii=False, indent=1)[:3000], flush=True)
print("DONE", flush=True)
