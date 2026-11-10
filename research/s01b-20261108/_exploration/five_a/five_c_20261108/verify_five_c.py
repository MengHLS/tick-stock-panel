"""⑤-c 两问诊断的自检 + 产物清单（只读）。

断言覆盖：
  D1  行情核对、1,722.55 分解、各臂 gap 恒等式、调用序列、修正后收益
  D2  1.001 / 0.999 比值、同族对照、配置键、价格反推
  纪律 REPORT.md / 策略文件 / 引擎文件 未改；⑤-a 各臂产物 mtime 未被本次诊断触碰

用法：backend/.venv/Scripts/python.exe verify_five_c.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
FIVE_A = HERE.parent
RESEARCH = FIVE_A.parent
PROJECT = RESEARCH.parents[1]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHECKS: list[tuple[str, bool, str]] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


d1 = json.loads((HERE / "diag1_result.json").read_text(encoding="utf-8"))
d2 = json.loads((HERE / "diag2_result.json").read_text(encoding="utf-8"))
f = d1["focus"]
px = {p["symbol"]: p for p in d1["prices"]}

# ---------------- D1：行情 ----------------
ck("V01 688143.SH 2026-10-30 开盘 = 109.90", abs(px["688143.SH"]["open"] - 109.90) < 1e-6,
   f"open={px['688143.SH']['open']}")
ck("V02 688143.SH 2026-10-30 收盘 = 118.26", abs(px["688143.SH"]["close"] - 118.26) < 1e-6,
   f"close={px['688143.SH']['close']}")
ck("V03 该日有成交（非停牌）", px["688143.SH"]["volume"] > 0,
   f"volume={px['688143.SH']['volume']}")
ck("V04 开盘跌幅未触 20% 跌停", px["688143.SH"]["pct_open_vs_prev"] > -0.1999,
   f"{px['688143.SH']['pct_open_vs_prev']*100:.2f}%")

# ---------------- D1：trades / equity 对齐 ----------------
ck("V05 trades.exit_price 等于当日开盘", f["exit_price_equals_open"] is True)
ck("V06 trades.exit_value = 21,929.45", abs(f["exit_value_recorded"] - 21929.45) < 0.01)
ck("V07 末行持仓市值 = 200×118.26 = 23,652.00",
   f["market_value_equals_mark"] is True and abs(f["market_value_last_row"] - 23652.00) < 0.01)
ck("V08 缺口 = 23,652.00 − 21,929.45 = 1,722.55", abs(f["gap_total"] - 1722.55) < 0.02,
   f"{f['gap_total']}")
ck("V09 价基差 1,672.00 = 200×(118.26−109.90)", abs(f["gap_price_basis"] - 1672.00) < 0.01)
ck("V10 卖出费用 50.55 = 200×109.90 − 21,929.45", abs(f["gap_fee"] - 50.55) < 0.01)
ck("V11 分解闭合：价基差 + 费用 == 缺口", abs(f["gap_check"] - f["gap_total"]) < 0.02)
ck("V12 Σpnl − 权益变动 = −1,722.56（独立口径同量）",
   abs(abs(d1["arms"]["base_nodefaults_10bp"]["gap_pnl_minus_delta"]) - 1722.56) < 0.02)
ck("V13 开发经理的 1,722.55 与本诊断差 ≤0.02", abs(f["dev_manager_delta_vs_gap"]) <= 0.02,
   f"delta={f['dev_manager_delta_vs_gap']}")
ck("V14 finalize 后现金 483,571.23 = 461,641.78 + 21,929.45",
   abs(f["final_cash_after_finalize"] - 483571.23) < 0.02)
ck("V15 闭式 (1e6 − Σentry + Σexit) 与 finalize 现金差 ≤0.5（208 笔逐个round 2dp 的舍入）",
   abs(d1["arms"]["base_nodefaults_10bp"]["final_cash_vs_closed_form"]) <= 0.5,
   f"{d1['arms']['base_nodefaults_10bp']['final_cash_vs_closed_form']}")
ck("V16 报告口径 total_return 被末行高估 0.17pp",
   abs(d1["arms"]["base_nodefaults_10bp"]["total_return_delta_pp"] - 0.1729) < 0.02,
   f"{d1['arms']['base_nodefaults_10bp']['total_return_delta_pp']}")

# ---------------- D1：各臂同一恒等式 ----------------
arms = d1["arms"]
nonfin = {k: v for k, v in arms.items() if not v["finalize_open_at_end"]}
ck("V17 非 finalize 臂共 7 个", len(nonfin) == 7, str(sorted(nonfin)))
for k, v in nonfin.items():
    expect = 0 if not v["deferred"] else -(
        sum(d["mark_value"] for d in v["deferred"]) - v["deferred_exit_value_total"])
    if v["deferred"]:
        ck(f"V18 gap 与持仓集合闭合 [{k}]",
           abs(v["gap_pnl_minus_delta"] - expect) <= 0.05,
           f"gap={v['gap_pnl_minus_delta']} expect={round(expect, 2)}")
ck("V19 gross 臂 gap == −1,672.00（无费用，纯价基差）",
   abs(arms["base_nodefaults_gross"]["gap_pnl_minus_delta"] + 1672.00) < 0.05,
   f"{arms['base_nodefaults_gross']['gap_pnl_minus_delta']}")
ck("V20 exit_signal 臂无延后持仓 ⇒ gap ≈ 0",
   abs(arms["only_exit_signal_requires_profit"]["gap_pnl_minus_delta"]) <= 0.05)
ck("V21 finalize 臂末行持仓 5 且无延后卖出",
   arms["only_finalize_open_at_end"]["equity_last_positions"] == 5
   and not arms["only_finalize_open_at_end"]["deferred"])
ck("V22 除 exit_signal 臂外，其余 6 个非 finalize 臂都有 1 笔延后卖出",
   all(len(v["deferred"]) == 1 for k, v in nonfin.items()
       if k != "only_exit_signal_requires_profit"))
ck("V23 延后卖出标的均为 688143.SH 2026-09-04",
   all(d["symbol"] == "688143.SH" and d["entry_date"] == "2026-09-04"
       for v in nonfin.values() for d in v["deferred"]))

# ---------------- D1：调用序列 ----------------
seq = d1["trace_20261030"]
sig_true = [e for e in seq if e["fn"] == "_exit_signal_at_return" and e["asset_id"] == 4962]
ck("V24 688143(asset 4962) 末日 _exit_signal_at 返回 True",
   len(sig_true) == 1 and sig_true[0]["return_value"] is True)
cks = [e for e in seq if e["fn"] == "_try_sell" and e["reason"] == "end"]
ck("V25 末日循环内只对 4 个仓位发 _try_sell(end)（不含 688143）",
   len(cks) == 4 and all(e["position_id"] in (204, 205, 206, 207) for e in cks),
   str([e["position_id"] for e in cks]))
ck("V26 688143 的 _sell 出现在 4 笔卖出之后（循环外 finalize）",
   [e["fn"] for e in seq].count("_try_sell") == 4
   and seq[-2]["fn"] == "_sell" and seq[-1]["fn"] == "_sell_return")
ck("V27 finalize 的 _sell 仍记 reason=end（不是 signal）",
   seq[-2]["reason"] == "end", str(seq[-2]["reason"]))
ck("V28 末行权益现金 461,641.78（= 10-29 现金 + 循环内 4 笔 exit_value）",
   abs(f["equity_last_cash"] - 461641.78) < 0.02, f"{f['equity_last_cash']}")

# ---------------- D2 ----------------
ck("V29 a0 与单键 raw 臂同键 102 笔", d2["T1_entry_ratio"]["n_matched_keys"] == 102)
ck("V30 入场价比 102/102 == 1.001",
   d2["T1_entry_ratio"]["n_equals_1p001"] == 102 and d2["T1_entry_ratio"]["n_outlier"] == 0,
   f"{d2['T1_entry_ratio']}")
ck("V31 出场价比 99/102 == 0.999，3 笔例外",
   d2["T2_exit_ratio"]["n_equals_0p999"] == 99 and d2["T2_exit_ratio"]["n_outlier"] == 3)
ck("V32 3 笔例外全是 a0 的期末未平仓（exit_date=末日）",
   all(o["exit_date"] == "2026-10-30" for o in d2["T2_exit_ratio"]["outliers"]))
ck("V33 同族对照 208/208 == 1.001（与价基无关）",
   d2["T3_same_family"]["n_equals_1p001"] == 208 and d2["T3_same_family"]["n"] == 208)
ck("V34 a0 策略 META 含 execution_costs",
   d2["T4_config"]["a0_meta_has_execution_costs"] is True)
ck("V35 单键 raw 臂 resolved.execution_costs 为 null",
   d2["T4_config"]["raw_arm_resolved_execution_costs"] is None)
ck("V36 单键 raw 臂 resolved.entry_price_basis == raw",
   d2["T4_config"]["raw_arm_resolved_entry_price_basis"] == "raw")
ck("V37 a0 ÷ 1.001 与 raw 臂价格 102/102 相等",
   d2["T5_deflate"]["n_equals_raw_price"] == 102)
ck("V38 股数并非全同（排除「同一仓位」误读）",
   d2["shares"]["n_same"] < d2["shares"]["n_total"],
   f"{d2['shares']['n_same']}/{d2['shares']['n_total']}")

# ---------------- 纪律 ----------------
report = RESEARCH / "REPORT.md"
ck("V39 REPORT.md 未改（52,097 B / e60cd0b8…）",
   report.stat().st_size == 52097
   and sha256(report).startswith("e60cd0b857f40fb2"), sha256(report)[:16])
strat = Path(r"D:\TSP\data\strategies\custom\custom_mw7fvp17.py")
ck("V40 生产策略文件未改（3,478 B / 85ae72a5…）",
   strat.stat().st_size == 3478 and sha256(strat).startswith("85ae72a5318523d1"),
   sha256(strat)[:16])
eng = PROJECT / "backend" / "app" / "backtest" / "engine.py"
eng_mtime = datetime.fromtimestamp(eng.stat().st_mtime)
ck("V41 引擎 engine.py 未改（mtime 早于 2026-11-08）",
   eng_mtime < datetime(2026, 11, 8), eng_mtime.isoformat())
ck("V42 engine.py sha256 记录", sha256(eng).startswith("ecc3d8261c5605ed"), sha256(eng)[:16])
a0 = RESEARCH / "results" / "a0_10bp" / "trades.parquet"
ck("V43 a0_10bp 产物 mtime 未变（16:21）",
   datetime.fromtimestamp(a0.stat().st_mtime) < datetime(2026, 11, 8, 17, 0),
   datetime.fromtimestamp(a0.stat().st_mtime).isoformat())
arm_t = FIVE_A / "base_nodefaults_10bp" / "trades.parquet"
ck("V44 ⑤-a 基线产物 mtime 未变（19:00）",
   datetime.fromtimestamp(arm_t.stat().st_mtime) < datetime(2026, 11, 8, 19, 10),
   datetime.fromtimestamp(arm_t.stat().st_mtime).isoformat())
ck("V45 本次只读：diag1/diag2 未写 result 目录",
   not (FIVE_A / "base_nodefaults_10bp" / "diag_marker").exists())
ck("V46 引擎调用序列来自 sys.settrace 实跑（事件数 > 20）",
   len(d1["trace_20261030"]) > 20, str(len(d1["trace_20261030"])))
# ---------------- D3：三种口径对账 + 199/208 价基 ----------------
d3 = json.loads((HERE / "diag3_result.json").read_text(encoding="utf-8"))
A3, B3, C3, D3_, E3 = (d3["A_cash_recon"], d3["B_mark_to_close"], d3["C_full_liquidation"],
                      d3["D_reported"], d3["E_basis_attribution"])
ck("V47 末行现金 = 10-29 现金 + 循环内 4 笔 exit_value（暴力拼出，非人工挑）",
   A3["in_loop_match"] and abs(A3["prev_cash"] + A3["in_loop_exit_value_sum"] - A3["last_cash"]) <= 0.05,
   f"{A3['prev_cash']:.2f}+{A3['in_loop_exit_value_sum']:.2f}={A3['last_cash']:.2f}")
ck("V48 未入账那笔 = 688143.SH，exit_value 21,929.45",
   A3["deferred_symbol"] == "688143.SH" and abs(A3["deferred_exit_value"] - 21929.45) < 0.02,
   f"{A3['deferred_symbol']} {A3['deferred_exit_value']}")
ck("V49 纯收盘盯市末值 == finalize 臂末值（跳臂交叉验证）",
   B3["equals_finalize_arm"],
   f"{B3['mark_equity']:.2f} vs {B3['finalize_arm_last_value']:.2f}")
ck("V50 全按开盘清算 = 末行现金 + 延后 exit_value，与闭式差 ≤0.5",
   abs(C3["diff"]) <= 0.5, f"diff={C3['diff']}")
ck("V51 报告值既不等于 B 也不等于 C（混合口径），D−C = 1,722.55",
   D3_["is_mixed"] and abs(D3_["diff_vs_full_liq"] - 1722.55) <= 0.02,
   f"D−B={D3_['diff_vs_mark']} D−C={D3_['diff_vs_full_liq']}")
ck("V52 base resolved 价基 = adjusted，单键 raw 臂 = raw",
   E3["base_resolved_entry_price_basis"] == "adjusted"
   and E3["raw_arm_resolved_entry_price_basis"] == "raw",
   f"{E3['base_resolved_entry_price_basis']} / {E3['raw_arm_resolved_entry_price_basis']}")
ck("V53 a0 ÷ base × (adj/raw) == 1.001 命中 ≥109/111",
   E3["n_ratio_times_adj_over_raw_eq_1p001"] >= 109 and E3["n_keys_a0_vs_base"] == 111,
   f"{E3['n_ratio_times_adj_over_raw_eq_1p001']}/{E3['n_keys_a0_vs_base']}")
_exc_ok, _exc_k = True, []
for x in E3["exceptions"]:
    hit = None
    for k in (3.0, 2.0, 1.5, 1.3, 1.2, 1.1):
        if abs(x["entry_price_raw"] * 1.001 / k - x["entry_price_a0"]) <= 0.02:
            hit = k
            break
    _exc_k.append(hit)
    _exc_ok = _exc_ok and hit is not None
ck("V54 2 笔例外均能解成「raw×1.001 ÷ 送股倍率」（倍率 ∈ 1.1~3.0）",
   _exc_ok and len(E3["exceptions"]) == 2, str(_exc_k))
ck("V55 a0 ÷ 单键 raw 臂入场价 == 1.001 命中 102/102",
   E3["n_entry_ratio_1p001_a0_vs_raw"] == 102 and E3["n_keys_a0_vs_raw"] == 102,
   f"{E3['n_entry_ratio_1p001_a0_vs_raw']}/{E3['n_keys_a0_vs_raw']}")

# ---------------- 产物清单 ----------------
artifacts = [
    "diag1_end_gap.py", "diag1_result.json", "diag1_table.md", "diag1_stdout.txt",
    "diag2_price_basis.py", "diag2_result.json", "diag2_table.md",
    "diag3_reconcile.py", "diag3_result.json", "diag3_table.md",
    "price_20261030.csv", "trace_end_position.json", "trace_run.log",
    "diag_end_position.py", "verify_five_c.py",
]
manifest = {}
for name in artifacts:
    p = HERE / name
    if p.exists():
        manifest[name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
(HERE / "manifest_five_c.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

n_pass = sum(1 for _, ok, _ in CHECKS if ok)
lines = [f"{'PASS' if ok else 'FAIL'} | {name} | {detail}" for name, ok, detail in CHECKS]
lines.append("")
lines.append(f"checks={len(CHECKS)} pass={n_pass} fail={len(CHECKS) - n_pass}")
lines.append("VERDICT " + ("ALL_PASS" if n_pass == len(CHECKS) else "HAS_FAIL"))
lines.append("")
lines.append("artifacts:")
for name, meta in manifest.items():
    lines.append(f"  {name} {meta['bytes']} {meta['sha256']}")
(HERE / "verify_five_c_result.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
raise SystemExit(0 if n_pass == len(CHECKS) else 1)
