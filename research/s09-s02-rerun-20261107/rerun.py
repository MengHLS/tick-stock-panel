"""S09 -> S02 解冻重跑（D1 定稿后）：canonical 因子 id 走 frame 路径，与研究侧逐信号对账。

口径：
  * canonical id 一律 store 侧 uf_*（ID-CANON-1）：uf_prior_high_55 / uf_prior_vol_20 /
    uf_prior_high_20 / uf_prior_low_10；单侧 canonical 直接用 ma20 / ma20_bias。
  * 研究侧 = scripts/common.py 原样（未经改动的 36 次运行的同一套表达式）。
  * 股票池两侧共用 prepared.in_universe（隔离因子口径，不把 E3 池子差混进来）。
只读：不写库、不注册新因子、不改 backend。产出 RESULT.json。
"""
from __future__ import annotations

import json
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
EVAL_START, EVAL_END = common.EVAL_START, common.EVAL_END
R: dict = {}


def jac(a: pl.Series, b: pl.Series) -> float:
    a = a.fill_null(False).cast(pl.Boolean)
    b = b.fill_null(False).cast(pl.Boolean)
    inter = int((a & b).sum())
    union = int((a | b).sum())
    return 1.0 if union == 0 else inter / union


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


def diffstats(name: str, a: pl.Series, b: pl.Series) -> dict:
    both = pl.DataFrame({"a": a, "b": b}).filter(
        pl.col("a").is_not_null() & pl.col("b").is_not_null()
    )
    nul = pl.DataFrame({"a": a, "b": b}).filter(
        pl.col("a").is_null() != pl.col("b").is_null()
    ).height
    d = (both["a"] - both["b"]).abs() if both.height else None
    return {
        "n_both": both.height,
        "null_mismatch": nul,
        "max_abs_diff": float(d.max()) if both.height else None,
        "n_diff_gt_0": int((d > 0).sum()) if both.height else 0,
    }


def counts(sig: pl.DataFrame, col: str) -> dict:
    g = sig.filter(pl.col(col)).group_by("date").len().sort("date")
    dates = sig.select("date").unique()
    v = g["len"] if g.height else pl.Series("len", [], dtype=pl.Int64)
    return {
        "n_days_with_signals": g.height,
        "n_days_total": dates.height,
        "total_signals": int(v.sum()) if len(v) else 0,
        "mean": float(v.mean()) if len(v) else 0.0,
        "median": float(v.median()) if len(v) else 0.0,
        "min": int(v.min()) if len(v) else 0,
        "max": int(v.max()) if len(v) else 0,
    }


def perday_delta(sig: pl.DataFrame, ca: str, ra: str) -> dict:
    days = sig.select("date").unique().sort("date")
    a = sig.filter(pl.col(ca)).group_by("date").len().rename({"len": "c"}).sort("date")
    b = sig.filter(pl.col(ra)).group_by("date").len().rename({"len": "r"}).sort("date")
    j = days.join(a, on="date", how="left").join(b, on="date", how="left").fill_null(0)
    d = (j["c"] - j["r"]).abs()
    return {
        "days_with_count_diff": int((d > 0).sum()),
        "max_day_abs_diff": int(d.max()) if j.height else 0,
        "mean_day_abs_diff": float(d.mean()) if j.height else 0.0,
    }


def series_hash(s: pl.Series) -> str:
    import hashlib

    return hashlib.sha256(s.cast(pl.Boolean).fill_null(False).to_numpy().tobytes()).hexdigest()


try:
    t0 = time.perf_counter()
    print("[1] panel / prepared ...", flush=True)
    market = common.open_market()
    panel = common.load_panel(market)
    prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
    R["panel"] = {
        "rows": panel.height,
        "symbols": panel["symbol"].n_unique(),
        "dates": panel["date"].n_unique(),
        "min_date": str(panel["date"].min()),
        "max_date": str(panel["date"].max()),
        "panel_hash": common.fingerprint(panel),
        "load_seconds": round(time.perf_counter() - t0, 1),
    }
    print("   ", R["panel"], flush=True)

    print("[2] store -> registry (canonical uf_*) ...", flush=True)
    loaded = store.load_into_registry(settings.data_dir)
    R["store_loaded_ids"] = sorted(loaded)

    print("[3] materialize canonical columns ...", flush=True)
    t1 = time.perf_counter()
    base = prepared.rename({"ma20": "ma20_research", "ma60": "ma60_research"})
    canon = materialize_scoring_columns(
        base,
        [
            "ma20", "ma20_bias",
            "uf_prior_high_20", "uf_prior_high_55", "uf_prior_low_10", "uf_prior_vol_20",
            "uf_prior_high_250", "uf_vol60",
        ],
    )
    R["materialize_seconds"] = round(time.perf_counter() - t1, 1)
    R["canon_has_columns"] = {
        c: bool(c in canon.columns and canon[c].null_count() < canon.height)
        for c in ["ma20", "ma20_bias", "uf_prior_high_20", "uf_prior_high_55",
                  "uf_prior_low_10", "uf_prior_vol_20", "uf_prior_high_250", "uf_vol60"]
    }

    print("[4] factor-level parity (canonical vs research) ...", flush=True)
    R["factor_parity"] = {
        "uf_prior_high_55_vs_prior_high55": diffstats("h55", canon["uf_prior_high_55"], canon["prior_high55"]),
        "uf_prior_vol_20_vs_prior_vol20": diffstats("v20", canon["uf_prior_vol_20"], canon["prior_vol20"]),
        "uf_prior_high_20_vs_prior_high20": diffstats("h20", canon["uf_prior_high_20"], canon["prior_high20"]),
        "uf_prior_low_10_vs_prior_low10": diffstats("l10", canon["uf_prior_low_10"], canon["prior_low10"]),
        "ma20_vs_ma20_research": diffstats("ma20", canon["ma20"], canon["ma20_research"]),
        "uf_prior_high_250_vs_prior_high250": diffstats("h250", canon["uf_prior_high_250"], canon["prior_high250"]),
        "uf_vol60_vs_vol60": diffstats("vol60", canon["uf_vol60"], canon["vol60"]),
    }

    print("[5] canonical signals (DSL, canonical ids only) ...", flush=True)
    u = pl.col("in_universe")
    hi55_c = comp(canon, "S09_hi55", "close > uf_prior_high_55")
    vol20_c = comp(canon, "S09_vol20", "volume > 1.5 * uf_prior_vol_20")
    e_s09_c = (u & hi55_c & vol20_c).fill_null(False)
    ma20_c = comp(canon, "S09_exit_ma20", "close < ma20")
    ma20bias_c = comp(canon, "S09_exit_ma20_bias", "ma20_bias < 0")
    hi20_c = comp(canon, "S02_hi20", "close > uf_prior_high_20")
    lo10_c = comp(canon, "S02_lo10", "close < uf_prior_low_10")
    e_s02_c = (u & hi20_c).fill_null(False)

    sig = canon.with_columns(
        hi55_c.alias("hi55_c"),
        vol20_c.alias("vol20_c"),
        ma20_c.alias("x_volbreak_c"),
        ma20bias_c.alias("x_volbreak_c_alt"),
        hi20_c.alias("hi20_c"),
        lo10_c.alias("x_donchian_c"),
        e_s09_c.alias("e_volbreak_c"),
        e_s02_c.alias("e_donchian_c"),
    ).filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))

    print("   eval rows:", sig.height, flush=True)

    print("[6] signal-level jaccard ...", flush=True)
    R["signal_jaccard"] = {
        "S09_entry": jac(sig["e_volbreak_c"], sig["e_volbreak"]),
        "S09_leg_high55": jac(sig["hi55_c"], sig["prior_high55"].is_not_null() & (sig["close"] > sig["prior_high55"])),
        "S09_leg_vol": jac(sig["vol20_c"], sig["volume"] > 1.5 * sig["prior_vol20"]),
        "S09_exit_ma20": jac(sig["x_volbreak_c"], sig["x_volbreak"]),
        "S09_exit_ma20bias_alt": jac(sig["x_volbreak_c_alt"], sig["x_volbreak"]),
        "S02_entry": jac(sig["e_donchian_c"], sig["e_donchian"]),
        "S02_exit": jac(sig["x_donchian_c"], sig["x_donchian"]),
    }
    R["signal_counts"] = {
        "S09_entry_canonical": counts(sig, "e_volbreak_c"),
        "S09_entry_research": counts(sig, "e_volbreak"),
        "S09_exit_canonical": counts(sig, "x_volbreak_c"),
        "S09_exit_research": counts(sig, "x_volbreak"),
        "S02_entry_canonical": counts(sig, "e_donchian_c"),
        "S02_entry_research": counts(sig, "e_donchian"),
        "S02_exit_canonical": counts(sig, "x_donchian_c"),
        "S02_exit_research": counts(sig, "x_donchian"),
    }
    R["perday_delta"] = {
        "S09_entry": perday_delta(sig, "e_volbreak_c", "e_volbreak"),
        "S09_exit": perday_delta(sig, "x_volbreak_c", "x_volbreak"),
        "S02_entry": perday_delta(sig, "e_donchian_c", "e_donchian"),
        "S02_exit": perday_delta(sig, "x_donchian_c", "x_donchian"),
    }
    R["signal_hash"] = {
        "S09_entry_canonical": series_hash(sig["e_volbreak_c"]),
        "S09_entry_research": series_hash(sig["e_volbreak"]),
        "S09_exit_canonical": series_hash(sig["x_volbreak_c"]),
        "S09_exit_research": series_hash(sig["x_volbreak"]),
        "S02_entry_canonical": series_hash(sig["e_donchian_c"]),
        "S02_entry_research": series_hash(sig["e_donchian"]),
        "S02_exit_canonical": series_hash(sig["x_donchian_c"]),
        "S02_exit_research": series_hash(sig["x_donchian"]),
    }

    print("[7] account-level rerun (canonical entry/exit, same engine) ...", flush=True)
    run_frame = prepared.join(
        sig.select("symbol", "date", "e_volbreak_c", "x_volbreak_c", "e_donchian_c", "x_donchian_c"),
        on=["symbol", "date"], how="left",
    ).with_columns(
        pl.col("e_volbreak_c").fill_null(False),
        pl.col("x_volbreak_c").fill_null(False),
        pl.col("e_donchian_c").fill_null(False),
        pl.col("x_donchian_c").fill_null(False),
    )
    ev = run_frame.filter(run_frame["date"] >= common.EVAL_START)
    registry = json.loads(
        (Path(common.PROJECT) / "research" / "strategy-search-20261107" / "results" / "registry.json")
        .read_text(encoding="utf-8")
    )["runs"]
    R["account"] = {}
    for key, entry, exitc, score, hold, reg in (
        ("S09_canonical", "e_volbreak_c", "x_volbreak_c", "s_volbreak", 60, "S09_volume_breakout_55@10"),
        ("S02_canonical", "e_donchian_c", "x_donchian_c", "s_donchian", 60, "S02_donchian_20_10@10"),
    ):
        t2 = time.perf_counter()
        strat = common.Strategy(key, "诊断", key, entry, exitc, score, hold, "重跑诊断")
        res = common.run_continuous(market, ev, strat, 10.0)
        trades = res["trades"]
        eq = res["equity"]
        last = eq[-1] if eq else {}
        old = registry[reg]
        R["account"][key] = {
            "seconds": round(time.perf_counter() - t2, 1),
            "n_trades": len(trades),
            "signals": int(ev[entry].sum()),
            "final_equity": last.get("equity"),
            "old_signals": old["signals"],
            "old_n_trades": old["n_trades"],
            "old_final_equity": old["ALL"]["final_equity"],
            "old_total_return": old["ALL"]["total_return"],
        }
        print("   ", key, R["account"][key], flush=True)

    R["ok"] = True
except Exception:  # noqa: BLE001
    R["ok"] = False
    R["traceback"] = traceback.format_exc()
    print(R["traceback"], flush=True)

R["finished_at"] = date.today().isoformat()
(OUT / "RESULT.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("\n=== DONE ok=%s ===" % R.get("ok"), flush=True)
print(json.dumps({k: R[k] for k in ("signal_jaccard", "perday_delta", "account") if k in R},
                 ensure_ascii=False, indent=1, default=str), flush=True)
