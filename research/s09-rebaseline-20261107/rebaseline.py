"""S09 重定基线：当前 engine + canonical uf_* 因子，产出唯一当前基线。

口径（与 §12 的 S09 重跑一致，不新增任何口径）：
  * 入场 = in_universe & close > uf_prior_high_55 & volume > 1.5 * uf_prior_vol_20   （DSL compile_formula）
  * 出场 = close < ma20（canonical 单侧 id）
  * 账户 = common.ACCOUNT（初始 1,000,000 / 最多 5 仓 / 60% 敞口 / 10bp 滑点 / block_limit_open）
  * 引擎 = 当前 HEAD 的 app.engine（含 11-07 12:54 carry/pending_buy_plans 改动）
  * 股票池 = 研究侧 prepared.in_universe（与 36 次运行同一列）

只读 backend 与数据；只写本目录 RESULT.json。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import traceback
from datetime import date
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
REGISTRY = ROOT / "research" / "strategy-search-20261107" / "results" / "registry.json"
OLD_KEY = "S09_volume_breakout_55@10"
R: dict = {}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def comp(frame: pl.DataFrame, name: str, formula: str) -> pl.Series:
    c = compile_formula(formula)
    if not c.ok:
        raise RuntimeError(f"{name}: {[(e.code, e.message) for e in c.errors]}")
    o = c.frame_transform(frame)
    if o is None:
        raise RuntimeError(f"{name}: frame_transform None")
    R.setdefault("formulas", {})[name] = {
        "formula": formula,
        "referenced_factors": sorted(c.referenced_factors),
        "cross_sectional": bool(c.cross_sectional),
        "warmup_bars": c.warmup_bars,
    }
    return o[FACTOR_COLUMN].cast(pl.Boolean).fill_null(False)


try:
    t0 = time.perf_counter()
    print("[0] provenance ...", flush=True)
    R["provenance"] = {
        "git_branch": subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_head_subject": subprocess.check_output(["git", "log", "-1", "--pretty=%s"], cwd=ROOT, text=True).strip(),
        "git_status_porcelain": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
        "engine_py_log": subprocess.check_output(
            ["git", "log", "-1", "--pretty=%H %ad", "--date=iso", "--", "backend/app/backtest/engine.py"],
            cwd=ROOT, text=True).strip(),
        "common_py_sha256": sha(ROOT / "research" / "strategy-search-20261107" / "scripts" / "common.py"),
        "registry_json_sha256_before": sha(REGISTRY),
        "engine_py_sha256": sha(ROOT / "backend" / "app" / "backtest" / "engine.py"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version, "polars": pl.__version__,
    }
    print("   head:", R["provenance"]["git_head"][:8], "| engine:", R["provenance"]["engine_py_log"], flush=True)

    print("[1] panel / prepared ...", flush=True)
    market = common.open_market()
    panel = common.load_panel(market)
    prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
    R["panel"] = {
        "rows": panel.height, "symbols": panel["symbol"].n_unique(),
        "dates": panel["date"].n_unique(),
        "min_date": str(panel["date"].min()), "max_date": str(panel["date"].max()),
        "panel_hash": common.fingerprint(panel),
        "load_seconds": round(time.perf_counter() - t0, 1),
    }
    print("   ", R["panel"], flush=True)

    print("[2] store -> registry (canonical uf_*) ...", flush=True)
    loaded = store.load_into_registry(settings.data_dir)
    R["store_loaded_n"] = len(loaded)
    R["store_has_uf_prior_high_55"] = "uf_prior_high_55" in loaded

    print("[3] materialize canonical columns ...", flush=True)
    base = prepared.rename({"ma20": "ma20_research"})
    canon = materialize_scoring_columns(base, ["ma20", "uf_prior_high_55", "uf_prior_vol_20"])
    R["canon_columns_ok"] = {c: bool(c in canon.columns and canon[c].null_count() < canon.height)
                             for c in ("ma20", "uf_prior_high_55", "uf_prior_vol_20")}

    print("[4] canonical entry/exit via DSL ...", flush=True)
    u = pl.col("in_universe")
    hi55 = comp(canon, "S09_hi55", "close > uf_prior_high_55")
    vol20 = comp(canon, "S09_vol20", "volume > 1.5 * uf_prior_vol_20")
    exitc = comp(canon, "S09_exit_ma20", "close < ma20")
    entry = (u & hi55 & vol20).fill_null(False)
    frame = canon.with_columns(entry.alias("e_volbreak_c"), exitc.alias("x_volbreak_c"))

    ev = frame.filter(frame["date"] >= common.EVAL_START)
    R["eval"] = {"start": str(common.EVAL_START), "end": str(common.EVAL_END),
                 "rows": ev.height, "entry_signals": int(ev["e_volbreak_c"].sum()),
                 "exit_signals": int(ev["x_volbreak_c"].sum())}
    print("   ", R["eval"], flush=True)

    print("[5] account replay (current engine, canonical) ...", flush=True)
    t1 = time.perf_counter()
    strat = common.Strategy("S09_volume_breakout_55", "趋势", "55 日新高 + 1.5 倍量能突破",
                            "e_volbreak_c", "x_volbreak_c", "s_volbreak", 20,
                            "至跌破 MA20 或最长 20 交易日")
    res = common.run_continuous(market, ev, strat, 10.0)
    R["run_seconds"] = round(time.perf_counter() - t1, 1)
    R["n_trades"] = len(res["trades"])
    R["final_positions"] = res["final_positions"]
    R["segments"] = [
        {"start": s["start"], "end": s["end"], "signals": s["signals"],
         "n_trades": s["stats"].get("n_trades"),
         "total_return": s["stats"].get("total_return"),
         "max_drawdown": s["stats"].get("max_drawdown")}
        for s in res["segments"]
    ]
    R["execution"] = {
        k: sum((s["stats"].get("execution") or {}).get(k, 0) for s in res["segments"])
        for k in ("buy_limit_up", "buy_no_slot", "buy_suspended", "sell_limit_down",
                  "sell_suspended", "buy_same_day_reentry")
    }
    for label, s, e in (("IS", common.EVAL_START, common.IS_END),
                        ("OOS", date(2023, 1, 3), common.EVAL_END),
                        ("ALL", common.EVAL_START, common.EVAL_END)):
        sm = common.summarize(res, s, e, label)
        sm.pop("returns", None)
        R[label] = sm
    print("   n_trades", R["n_trades"], "| ALL", R["ALL"]["total_return"],
          "| equity", R["ALL"]["final_equity"], "| limitup", R["execution"]["buy_limit_up"], flush=True)

    print("[6] compare with old registry row ...", flush=True)
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    old = reg["runs"][OLD_KEY]
    R["old_row"] = {
        "registry_meta_created_at": reg["meta"]["created_at"],
        "registry_meta_head": reg["meta"]["head"],
        "signals": old["signals"], "n_trades": old["n_trades"],
        "final_equity": old["ALL"]["final_equity"],
        "total_return": old["ALL"]["total_return"],
        "sharpe": old["ALL"]["sharpe"], "max_drawdown": old["ALL"]["max_drawdown"],
        "buy_limit_up": old["execution"]["buy_limit_up"],
        "by_year": [{"year": s["start"][:4], "signals": s["signals"], "n_trades": s["n_trades"]}
                    for s in old["segments"]],
    }
    R["delta"] = {
        "n_trades": R["n_trades"] - old["n_trades"],
        "final_equity": None if R["ALL"]["final_equity"] is None else R["ALL"]["final_equity"] - old["ALL"]["final_equity"],
        "total_return": R["ALL"]["total_return"] - old["ALL"]["total_return"],
        "sharpe": R["ALL"]["sharpe"] - old["ALL"]["sharpe"],
        "signals": R["eval"]["entry_signals"] - old["signals"],
        "buy_limit_up": R["execution"]["buy_limit_up"] - old["execution"]["buy_limit_up"],
        "by_year": [
            {"year": a["start"][:4], "new_trades": a["n_trades"], "old_trades": b["n_trades"],
             "delta_trades": (a["n_trades"] or 0) - (b["n_trades"] or 0),
             "new_signals": a["signals"], "old_signals": b["signals"],
             "delta_signals": a["signals"] - b["signals"]}
            for a, b in zip(R["segments"], old["segments"])
        ],
    }
    R["ok"] = True
except Exception:  # noqa: BLE001
    R["ok"] = False
    R["traceback"] = traceback.format_exc()
    print(R["traceback"], flush=True)

R["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "RESULT.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("\n=== DONE ok=%s ===" % R.get("ok"), flush=True)
print(json.dumps({k: R[k] for k in ("eval", "n_trades", "ALL", "execution", "segments", "delta") if k in R},
                 ensure_ascii=False, indent=1, default=str), flush=True)
