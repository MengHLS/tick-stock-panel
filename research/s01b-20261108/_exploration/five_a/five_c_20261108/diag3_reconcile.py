"""⑤-c 诊断 3：期末三种口径的对账 + 199/208 价基归属（只读）。

解决的问题（开发经理追加口径）：
  A. 末行权益的现金到底由哪几笔构成（10-29 现金 + 循环内 4 笔）；
  B. 「纯收盘盯市」的末值是多少，是否等于 finalize 臂的末值（跨臂交叉验证）；
  C. 「全按开盘虚拟清算」的末值是多少，是否等于闭式 (1e6 − Σentry + Σexit)；
  D. 报告口径 485,293.78 是否等于 B 或 C（都不等 ⇒ 混合口径）；
  E. 「199 臂 vs 208 基线」同键价格全不同的归属：base 的 resolved 价基是 adjusted，
     故比值应为 adj/raw × 1.001，逐笔验证并列出例外。

只读：不写任何 run 目录，不改引擎，不改报告数字。
用法：backend/.venv/Scripts/python.exe diag3_reconcile.py
产物：diag3_result.json、diag3_table.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIVE_A = HERE.parent
RESEARCH = FIVE_A.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def r2(x: float) -> float:
    return round(float(x), 2)


def key(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(
        k=df["symbol"].astype(str) + "|" + df["entry_date"].astype(str).str[:10]
    )


out: dict = {"inputs": {}}

# ---------------------------------------------------------------- A/B/C/D
base_dir = FIVE_A / "base_nodefaults_10bp"
eq = pd.read_parquet(base_dir / "equity.parquet")
tr = pd.read_parquet(base_dir / "trades.parquet")
tp = pd.read_parquet(base_dir / "trades_priced.parquet")
fin_eq = pd.read_parquet(FIVE_A / "only_finalize_open_at_end" / "equity.parquet")

eq = eq.sort_values("date").reset_index(drop=True)
last = eq.iloc[-1]
prev = eq.iloc[-2]
last_date = str(last["date"])[:10]
prev_date = str(prev["date"])[:10]

sells_last = tr[tr["exit_date"].astype(str).str[:10] == last_date].copy()
# 循环内卖出的 4 笔：exit_reason=end 且不是循环外 finalize 那一笔。
# 判据用「末行现金能否由 10-29 现金 + 其中某 4 笔 exit_value 精确拼出」暴力确定，不靠人工挑。
in_loop_sum = None
in_loop_symbols: list[str] = []
deferred_symbol = None
import itertools

cands = sells_last["exit_value"].round(2).tolist()
syms = sells_last["symbol"].astype(str).tolist()
target = last["cash"] - prev["cash"]
for combo in itertools.combinations(range(len(cands)), len(cands) - 1):
    s = sum(cands[i] for i in combo)
    if abs(s - target) <= 0.02:
        in_loop_sum = s
        in_loop_symbols = [syms[i] for i in combo]
        deferred_symbol = [syms[i] for i in range(len(cands)) if i not in combo][0]
        break

closed_form_cash = 1_000_000.0 - float(tr["entry_value"].sum()) + float(tr["exit_value"].sum())
# 收盘盯市：10-29 现金 + 5 只持仓 × 各自末日收盘
shares = {r.symbol: float(r.shares) for r in sells_last.itertuples()}
_px = key(tp[["symbol", "entry_date", "exit_close_raw"]]).merge(
    key(sells_last[["symbol", "entry_date"]]), on="k", suffixes=("", "_s")
)
close = {str(r.symbol): float(r.exit_close_raw) for r in _px.itertuples()}
mark_items = {s: shares[s] * close[s] for s in shares}
mark_total = sum(mark_items.values())
mark_equity = prev["cash"] + mark_total

deferred_row = sells_last[sells_last["symbol"] == deferred_symbol].iloc[0] if deferred_symbol else None
finalize_cash = last["cash"] + (float(deferred_row["exit_value"]) if deferred_row is not None else 0.0)

out["A_cash_recon"] = {
    "prev_date": prev_date,
    "prev_cash": r2(prev["cash"]),
    "last_date": last_date,
    "last_cash": r2(last["cash"]),
    "cash_delta": r2(target),
    "n_sells_last_day": int(len(sells_last)),
    "in_loop_symbols": in_loop_symbols,
    "in_loop_exit_value_sum": r2(in_loop_sum) if in_loop_sum is not None else None,
    "in_loop_match": in_loop_sum is not None,
    "deferred_symbol": deferred_symbol,
    "deferred_exit_value": r2(deferred_row["exit_value"]) if deferred_row is not None else None,
    "finalize_cash": r2(finalize_cash),
}
out["B_mark_to_close"] = {
    "shares": {k: float(v) for k, v in shares.items()},
    "close": {k: float(v) for k, v in close.items()},
    "mark_items": {k: r2(v) for k, v in mark_items.items()},
    "mark_total": r2(mark_total),
    "mark_equity": r2(mark_equity),
    "finalize_arm_last_value": r2(fin_eq.sort_values("date").iloc[-1]["value"]),
    "equals_finalize_arm": bool(abs(mark_equity - float(fin_eq.sort_values("date").iloc[-1]["value"])) <= 0.02),
}
out["C_full_liquidation"] = {
    "cash_last_row": r2(last["cash"]),
    "plus_deferred_exit_value": r2(finalize_cash),
    "closed_form_cash": r2(closed_form_cash),
    "diff": r2(finalize_cash - closed_form_cash),
}
out["D_reported"] = {
    "reported_equity": r2(last["value"]),
    "mark_equity": r2(mark_equity),
    "full_liq_equity": r2(finalize_cash),
    "diff_vs_mark": r2(last["value"] - mark_equity),
    "diff_vs_full_liq": r2(last["value"] - finalize_cash),
    "is_mixed": bool(
        abs(last["value"] - mark_equity) > 0.02 and abs(last["value"] - finalize_cash) > 0.02
    ),
}

# ---------------------------------------------------------------- E/F 价基归属
base_cfg = json.loads((base_dir / "effective_config.json").read_text(encoding="utf-8"))
base_basis = base_cfg["resolved_matcher_config"].get("entry_price_basis")
base_costs = base_cfg["resolved_matcher_config"].get("execution_costs")
raw_cfg = json.loads(
    (FIVE_A / "only_entry_price_basis_raw" / "effective_config.json").read_text(encoding="utf-8")
)
raw_basis = raw_cfg["resolved_matcher_config"].get("entry_price_basis")
raw_costs = raw_cfg["resolved_matcher_config"].get("execution_costs")

a0 = pd.read_parquet(RESEARCH / "results" / "a0_10bp" / "trades.parquet")
raw_arm = pd.read_parquet(FIVE_A / "only_entry_price_basis_raw" / "trades_priced.parquet")

m_raw = key(a0).merge(
    key(raw_arm[["symbol", "entry_date", "entry_price"]]), on="k", suffixes=("_a0", "_raw")
)
r_in = (m_raw["entry_price_a0"] / m_raw["entry_price_raw"]).astype(float)
n_in = int(((r_in - 1.001).abs() < 1e-4).sum())

m_base = key(a0).merge(
    key(tp[["symbol", "entry_date", "entry_price", "entry_price_raw", "entry_price_adj"]]),
    on="k",
    suffixes=("_a0", "_base"),
)
adj_over_raw = (m_base["entry_price_adj"] / m_base["entry_price_raw"]).astype(float)
q = (m_base["entry_price_a0"] / m_base["entry_price_base"]) * adj_over_raw
ok = (q - 1.001).abs() < 1e-3
bad = m_base.loc[~ok, ["symbol_a0", "entry_date_a0", "entry_price_raw", "entry_price_adj",
                       "entry_price_base", "entry_price_a0", "exit_date"]]

out["E_basis_attribution"] = {
    "base_resolved_entry_price_basis": base_basis,
    "base_resolved_execution_costs": base_costs,
    "raw_arm_resolved_entry_price_basis": raw_basis,
    "raw_arm_resolved_execution_costs": raw_costs,
    "n_keys_a0_vs_raw": int(len(m_raw)),
    "n_entry_ratio_1p001_a0_vs_raw": n_in,
    "ratio_a0_vs_raw_min": float(r_in.min()),
    "ratio_a0_vs_raw_max": float(r_in.max()),
    "n_keys_a0_vs_base": int(len(m_base)),
    "n_ratio_times_adj_over_raw_eq_1p001": int(ok.sum()),
    "n_exceptions": int((~ok).sum()),
    "exceptions": [
        {
            "symbol": r.symbol_a0,
            "entry_date": str(r.entry_date_a0)[:10],
            "exit_date": str(r.exit_date)[:10],
            "entry_price_raw": float(r.entry_price_raw),
            "entry_price_adj": float(r.entry_price_adj),
            "entry_price_base": float(r.entry_price_base),
            "entry_price_a0": float(r.entry_price_a0),
            "expected_a0_if_raw_x_1p001": r2(float(r.entry_price_raw) * 1.001),
        }
        for r in bad.itertuples()
    ],
    "q_min": float(q.min()),
    "q_median": float(q.median()),
    "q_max": float(q.max()),
}

out["inputs"] = {
    "base_trades": str((base_dir / "trades.parquet").relative_to(RESEARCH.parent)),
    "a0_trades": str((RESEARCH / "results" / "a0_10bp" / "trades.parquet").relative_to(RESEARCH.parent)),
}

(HERE / "diag3_result.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)

# ---------------------------------------------------------------- 表
L: list[str] = []
A = L.append
A("# ⑤-c 诊断 3：期末三种口径对账 + 199/208 价基归属\n")
A("## A · 末行现金由哪几笔构成\n")
a = out["A_cash_recon"]
A("| 项 | 值 |\n|---|---:|")
A(f"| {a['prev_date']} 权益行现金 | {a['prev_cash']:,.2f} |")
A(f"| {a['last_date']} 权益行现金 | {a['last_cash']:,.2f} |")
A(f"| 差额（当日入账现金） | {a['cash_delta']:,.2f} |")
A(f"| 循环内 4 笔 exit_value 合计 {a['in_loop_symbols']} | {a['in_loop_exit_value_sum']:,.2f} |")
A(f"| 未入账（循环外 finalize）{a['deferred_symbol']} | {a['deferred_exit_value']:,.2f} |")
A(f"| finalize 后现金 | {a['finalize_cash']:,.2f} |\n")
A("## B · 纯收盘盯市 vs C · 全按开盘清算 vs D · 报告值\n")
b, c, d = out["B_mark_to_close"], out["C_full_liquidation"], out["D_reported"]
A("| 口径 | 值 | 与其他口径的关系 |\n|---|---:|---|")
A(f"| B 纯收盘盯市（5 只全按末日收盘） | {b['mark_equity']:,.2f} | "
  f"= finalize 臂末值 {b['finalize_arm_last_value']:,.2f}：{b['equals_finalize_arm']} |")
A(f"| C 全按开盘虚拟清算 | {c['plus_deferred_exit_value']:,.2f} | "
  f"闭式 {c['closed_form_cash']:,.2f}，差 {c['diff']:+.2f} |")
A(f"| D 报告值（4 卖 + 1 盯市） | {d['reported_equity']:,.2f} | "
  f"B {d['diff_vs_mark']:+,.2f} / C {d['diff_vs_full_liq']:+,.2f} |\n")
A(f"报告值既不等于 B（差 {d['diff_vs_mark']:+,.2f}）也不等于 C（差 {d['diff_vs_full_liq']:+,.2f}），"
  f"确认是混合口径：{d['is_mixed']}。\n")
A("## E · 199 臂 vs 208 基线的价基归属\n")
e = out["E_basis_attribution"]
A("| 项 | 值 |\n|---|---|")
A(f"| base resolved entry_price_basis | {e['base_resolved_entry_price_basis']} |")
A(f"| raw 臂 resolved entry_price_basis | {e['raw_arm_resolved_entry_price_basis']} |")
A(f"| a0 ÷ raw臂 入场价比 == 1.001 | {e['n_entry_ratio_1p001_a0_vs_raw']}/{e['n_keys_a0_vs_raw']} |")
A(f"| a0 ÷ base × (adj/raw) == 1.001 | {e['n_ratio_times_adj_over_raw_eq_1p001']}/{e['n_keys_a0_vs_base']} |")
A(f"| 例外笔数 | {e['n_exceptions']} |\n")
if e["exceptions"]:
    A("| symbol | entry | a0 入场价 | raw×1.001 应为 | 差 |\n|---|---|---:|---:|---:|")
    for x in e["exceptions"]:
        A(f"| {x['symbol']} | {x['entry_date']} | {x['entry_price_a0']:.4f} | "
          f"{x['expected_a0_if_raw_x_1p001']:.2f} | "
          f"{x['entry_price_a0'] - x['expected_a0_if_raw_x_1p001']:+.2f} |")
    A("")
(HERE / "diag3_table.md").write_text("\n".join(L), encoding="utf-8")

print(json.dumps(out, ensure_ascii=False, indent=1))
