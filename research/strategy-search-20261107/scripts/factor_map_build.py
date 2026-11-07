"""因子化映射核对器（只读）。

用途：把 STRATEGIES.md v2 的 12 条策略，逐条翻译成「注册因子 id + 截面/时序算子」表达式，
用生产侧的 compiler (app.factors.dsl.compile_formula) 判定是否可以编译，并核对每个被引用的
因子 id 是否真的在注册表(app.factors.registry)里。

本脚本不实现策略、不跑回测、不产生任何收益数字。
它只回答两个可证伪的问题：
  Q1 表达式是否被 DSL 接受（语法+算子+窗口范围）
  Q2 表达式中引用的每个因子 id 是否已注册

输出：factor_map_v1.json（同目录上一级）+ stdout 表。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
REPO = RESEARCH.parents[1]
BACKEND = REPO / "backend"

sys.path.insert(0, str(BACKEND))

from app.factors import registry as R  # noqa: E402
from app.factors.dsl import compile_formula  # noqa: E402

# ---------------------------------------------------------------- 12 条映射
# entry/exit/score 均为 DSL 文本；rebalance 为引擎侧日历要求（非因子）。
SPEC = [
    {
        "id": "S01",
        "name": "双均线 20/60 金叉",
        "entry": "ma20_bias < ma60_bias and ts_delay(ma20_bias, 1) >= ts_delay(ma60_bias, 1)",
        "exit": "ma20_bias > ma60_bias",
        "score": "momentum_20d",
        "score_dir": "desc",
        "rebalance": "event",
        "note": "ma20>ma60 等价于 ma20_bias<ma60_bias（同一 close 相除，序不变）",
    },
    {
        "id": "S02",
        "name": "唐奇安 20/10 突破",
        "entry": "close > ts_delay(ts_max(high, 20), 1)",
        "exit": "close < ts_delay(ts_min(low, 10), 1)",
        "score": "momentum_20d",
        "score_dir": "desc",
        "rebalance": "event",
        "note": "prior_high20 == ts_delay(ts_max(high,20),1) 逐位等价（同为 t-20..t-1 的最大值）",
    },
    {
        "id": "S03",
        "name": "时序动量 60 日 + 月末",
        "entry": "momentum_60d > 0 and close > ts_mean(close, 120) and ma20_bias < ma60_bias",
        "exit": "momentum_60d <= 0 or close < ts_mean(close, 120)",
        "score": "momentum_60d",
        "score_dir": "desc",
        "rebalance": "month_end",
        "note": "close>ma120 用 ts_mean(close,120) 表达；注册表最大只有 ma60_bias，无 ma120 级别因子",
    },
    {
        "id": "S04",
        "name": "RSI(14) 超卖反转",
        "entry": "rsi_14 < 30",
        "exit": "rsi_14 > 55",
        "score": "rsi_14",
        "score_dir": "asc",
        "rebalance": "event",
        "note": "口径风险：v0 用 ewm(alpha=1/14, adjust=False) 近似 Wilder，注册 rsi_14 的实现未核对",
    },
    {
        "id": "S05",
        "name": "布林带 (20,2) 下轨反转",
        "entry": "boll_position < 0",
        "exit": "boll_position > 0.5",
        "score": "boll_position",
        "score_dir": "asc",
        "rebalance": "event",
        "note": "前提：boll_position 定义=(close-lower)/(upper-lower)。注册表只写「下轨到上轨之间的位置」，标度未定，需确认",
    },
    {
        "id": "S06",
        "name": "截面 5 日反转",
        "entry": "rank(momentum_5d) <= 0.05",
        "exit": None,
        "score": "momentum_5d",
        "score_dir": "asc",
        "rebalance": "week_end",
        "note": "截面算子语义风险：DSL rank 分母=当日非空样本数，v0 分母=当日 in_universe 样本数",
    },
    {
        "id": "S07",
        "name": "截面 60 日低波动",
        "entry": "rank(ts_std(close / prev_close - 1, 60)) <= 0.10",
        "exit": None,
        "score": "ts_std(close / prev_close - 1, 60)",
        "score_dir": "asc",
        "rebalance": "month_end",
        "note": "vol60 未注册；prev_close 语义（复权昨收 vs 交易所昨收）未核对",
    },
    {
        "id": "S08",
        "name": "52 周新高附近",
        "entry": "distance_to_high_250d >= -0.03 and close > ts_mean(close, 120)",
        "exit": None,
        "score": "distance_to_high_250d",
        "score_dir": "desc",
        "rebalance": "month_end",
        "note": "注册表只有 240 日口径（distance_to_high_240d，且是收盘价口径，v0 用 high 的 250 日 rolling max）",
    },
    {
        "id": "S09",
        "name": "55 日新高 + 1.5 倍量能",
        "entry": "close > ts_delay(ts_max(high, 55), 1) and volume > 1.5 * ts_delay(ts_mean(volume, 20), 1)",
        "exit": "ma20_bias < 0",
        "score": "momentum_60d",
        "score_dir": "desc",
        "rebalance": "event",
        "note": "close<ma20 等价于 ma20_bias<0；vol_ratio_20d 未注册（现有 5d/10d）",
    },
    {
        "id": "S10",
        "name": "截面 20 日反转",
        "entry": "rank(momentum_20d) <= 0.10",
        "exit": None,
        "score": "momentum_20d",
        "score_dir": "asc",
        "rebalance": "month_end",
        "note": "全部因子已注册，仅剩 rank 分母语义风险",
    },
    {
        "id": "S11",
        "name": "低波动 + 20 日反转复合",
        "entry": "rank(ts_std(close / prev_close - 1, 60)) <= 0.30 and rank(momentum_20d) <= 0.30",
        "exit": None,
        "score": "rank(ts_std(close / prev_close - 1, 60)) + rank(momentum_20d)",
        "score_dir": "asc",
        "rebalance": "month_end",
        "note": "复合排序用两个 rank 相加表达（等价于 v0 的 -(rk_vol60+rk_ret20) 升序）",
    },
    {
        "id": "S12",
        "name": "低波动 + 市场宽度择时",
        "entry": "rank(ts_std(close / prev_close - 1, 60)) <= 0.10 and market_breadth >= 0.5",
        "exit": None,
        "score": "ts_std(close / prev_close - 1, 60)",
        "score_dir": "asc",
        "rebalance": "month_end",
        "note": "market_breadth 是市场级（按日聚合）字段，不是逐股因子；DSL 无截面均值算子 → 需引擎能力",
    },
]

# 逐条声明「必须新增/确认的因子 id」，用于缺口表
REQUIRED_NEW = {
    "S01": [],
    "S02": ["breakout_dist_20d", "breakdown_dist_10d"],
    "S03": ["ma120_bias"],
    "S04": [],
    "S05": [],
    "S06": [],
    "S07": ["vol60"],
    "S08": ["distance_to_high_250d"],
    "S09": ["vol_ratio_20d", "breakout_dist_55d"],
    "S10": [],
    "S11": ["vol60"],
    "S12": ["vol60", "market_breadth(市场级)"],
}

MARKET_LEVEL = {"market_breadth"}


def main() -> int:
    registered = {s.id: s for s in R.all_factors()}
    out = {
        "generated_by": "scripts/factor_map_build.py",
        "registry": {
            "n_factors": len(registered),
            "n_base": sum(1 for s in registered.values() if s.kind == "base"),
            "n_virtual": sum(1 for s in registered.values() if s.kind == "virtual"),
        },
        "strategies": [],
        "summary": {},
    }

    rows = []
    for sp in SPEC:
        rec = {"id": sp["id"], "name": sp["name"], "rebalance": sp["rebalance"],
               "note": sp["note"], "fields": {}}
        for field in ("entry", "exit", "score"):
            text = sp[field]
            if text is None:
                rec["fields"][field] = {"text": None, "status": "no_signal"}
                continue
            c = compile_formula(text)
            refs = sorted(getattr(c, "referenced_factors", []) or [])
            missing = [r for r in refs if r not in registered]
            # 表达式内出现的裸标识符（含未注册的）
            import re
            idents = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
            idents -= {"and", "or", "not", "close", "high", "low", "open", "volume",
                       "amount", "turnover_rate", "prev_close", "raw_close"}
            from app.factors.dsl import OPERATORS
            idents -= set(OPERATORS)
            unreg = sorted(i for i in idents if i not in registered)
            rec["fields"][field] = {
                "text": text,
                "ok": bool(c.ok),
                "errors": [{"code": e.code, "message": e.message} for e in c.errors],
                "warmup_bars": int(getattr(c, "warmup_bars", 1) or 1),
                "cross_sectional": bool(getattr(c, "cross_sectional", False)),
                "referenced_factors": refs,
                "unregistered_idents": unreg,
            }
        rec["missing_factor_ids"] = sorted({u for f in rec["fields"].values()
                                            for u in f.get("unregistered_idents", [])})
        rec["required_new_factors"] = REQUIRED_NEW.get(sp["id"], [])
        out["strategies"].append(rec)
        e = rec["fields"]["entry"]
        rows.append((
            sp["id"], sp["name"], e["ok"], e["warmup_bars"], e["cross_sectional"],
            ",".join(e["referenced_factors"]) or "-",
            ",".join(rec["missing_factor_ids"]) or "-",
            sp["rebalance"],
        ))

    compile_all = all(s["fields"]["entry"]["ok"] for s in out["strategies"])
    out["summary"] = {
        "all_entries_compile": compile_all,
        "n_with_missing_factor_id": sum(1 for s in out["strategies"] if s["missing_factor_ids"]),
        "strategies_missing": [s["id"] for s in out["strategies"] if s["missing_factor_ids"]],
        "rebalance_calendars_required": sorted({s["rebalance"] for s in out["strategies"]}),
    }

    (RESEARCH / "factor_map_v1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'ID':4} {'编译':4} {'预热':>4} {'截面':4} {'引用因子':28} {'缺因子id':22} 调仓")
    for r in rows:
        print(f"{r[0]:4} {'OK' if r[2] else 'ERR':4} {r[3]:>4} {str(r[4]):4} {r[5]:28} {r[6]:22} {r[7]}")
    print()
    print("registry:", out["registry"])
    print("ALL_ENTRIES_COMPILE:", compile_all)
    print("MISSING_ID_STRATEGIES:", out["summary"]["strategies_missing"])
    print("REBALANCE_CALENDARS:", out["summary"]["rebalance_calendars_required"])
    return 0 if compile_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
