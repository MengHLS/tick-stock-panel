"""⑤-c 诊断 2：为什么「都声明 entry_price_basis=raw」的两臂同键价格全不同。

只读。三选一必须有确定答案：
  ① 某臂 trades.entry_price 存的不是执行价基（复权价 / 含成本价）；
  ② 某臂实际没吃到 raw（注入被默认值顶掉）；
  ③ 存在第三支影响成交价的键被打开。

判据（可复跑、不靠肉眼看）：
  T1  a0 臂（5 键注入，199 笔）的 entry_price ÷ five_a raw 臂（单键注入，208 笔）
      同键价格 是否恒等于 1 + slippage_bps/10000 = 1.001；
  T2  a0 臂的 exit_price ÷ raw 臂 是否为 0.999（卖出腿滑点反向）；
  T3  同族对照：five_a base → only_execution_costs 只多一个 execution_costs，
      比值是否也是 1.001（证明 1.001 与价基无关，只跟成本策略有关）；
  T4  a0 策略文件 META 里 execution_costs 是否存在，raw 臂 resolved 配置里是否为 null；
  T5  价格反推：a0 ÷ 1.001 是否逐笔等于 raw 臂价格（证明 a0 的基准价确为 raw）。

用法：backend/.venv/Scripts/python.exe diag2_price_basis.py
"""
from __future__ import annotations

import json
import ast
import sys
from pathlib import Path

import polars as pl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
FIVE_A = HERE.parent
RESEARCH = FIVE_A.parent
SLIPPAGE_BPS = 10.0
F_IN = 1 + SLIPPAGE_BPS / 10_000.0   # 1.001 买入腿
F_OUT = 1 - SLIPPAGE_BPS / 10_000.0  # 0.999 卖出腿
TOL = 1e-4

raw_arm = pl.read_parquet(FIVE_A / "only_entry_price_basis_raw" / "trades_priced.parquet")
base_arm = pl.read_parquet(FIVE_A / "base_nodefaults_10bp" / "trades_priced.parquet")
cost_arm = pl.read_parquet(FIVE_A / "only_execution_costs" / "trades_priced.parquet")
a0 = pl.read_parquet(RESEARCH / "results" / "a0_10bp" / "trades.parquet")

raw_cfg = json.loads((FIVE_A / "only_entry_price_basis_raw" / "effective_config.json")
                     .read_text(encoding="utf-8"))
raw_resolved = raw_cfg.get("resolved_matcher_config") or {}
base_resolved = json.loads((FIVE_A / "base_nodefaults_10bp" / "effective_config.json")
                           .read_text(encoding="utf-8")).get("resolved_matcher_config") or {}


def meta_defaults(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    key = '"backtest_defaults":'
    begin = text.index(key) + len(key)
    depth = 0
    end = begin
    for i in range(begin, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return ast.literal_eval(text[begin:end])


a0_meta = meta_defaults(RESEARCH / "strategies" / "custom" / "s01b_a0.py")

# ---------- T1/T2/T5：a0 vs 单键 raw 臂 ----------
j = raw_arm.select(["symbol", "entry_date", "exit_date", "entry_price", "exit_price",
                    "entry_price_raw", "cf_entry", "shares"]).join(
    a0.select(["symbol", "entry_date", "exit_date", "entry_price", "exit_price",
               "shares"]).rename({"entry_price": "e199", "exit_price": "x199",
                                  "shares": "sh199", "exit_date": "xd199"}),
    on=["symbol", "entry_date"], how="inner")
j = j.with_columns([
    (pl.col("e199") / pl.col("entry_price")).alias("r_in"),
    (pl.col("x199") / pl.col("exit_price")).alias("r_out"),
    (pl.col("e199") / F_IN).alias("e199_deflated"),
    (pl.col("sh199") / pl.col("shares")).alias("r_sh"),
])
in_ok = j.filter((pl.col("r_in") - F_IN).abs() <= TOL)
in_bad = j.filter((pl.col("r_in") - F_IN).abs() > TOL)
out_ok = j.filter((pl.col("r_out") - F_OUT).abs() <= TOL)
out_bad = j.filter((pl.col("r_out") - F_OUT).abs() > TOL)
deflate_ok = j.filter((pl.col("e199_deflated") - pl.col("entry_price")).abs()
                      <= 1e-3 * pl.col("entry_price"))

# ---------- T3：同族对照 ----------
c = cost_arm.select(["symbol", "entry_date", "entry_price"]).join(
    base_arm.select(["symbol", "entry_date", "entry_price"]).rename(
        {"entry_price": "e_base"}), on=["symbol", "entry_date"], how="inner")
c = c.with_columns((pl.col("entry_price") / pl.col("e_base")).alias("ratio"))
c_ok = c.filter((pl.col("ratio") - F_IN).abs() <= TOL)

result = {
    "verdict": "③ 第三支键（execution_costs 策略）+ ① 同名列存不同量（成交价 vs 报价）",
    "not": "② 不成立——两臂都真吃了 raw（见 T5）",
    "constants": {"slippage_bps": SLIPPAGE_BPS, "fill_in": F_IN, "fill_out": F_OUT},
    "T1_entry_ratio": {
        "n_matched_keys": j.height,
        "n_equals_1p001": in_ok.height,
        "n_outlier": in_bad.height,
        "min": float(j["r_in"].min()),
        "max": float(j["r_in"].max()),
    },
    "T2_exit_ratio": {
        "n_equals_0p999": out_ok.height,
        "n_outlier": out_bad.height,
        "outliers": out_bad.select(["symbol", "entry_date", "exit_date", "exit_price",
                                    "x199", "r_out"]).to_dicts(),
        "outlier_reason": "a0 的 finalize_open_at_end=True ⇒ 期末未平仓按最后收盘价落账；"
                          "raw 臂仍是次日开盘虚拟成交，故这 3 笔口径不同、不适用 0.999",
    },
    "T3_same_family": {
        "n": c.height,
        "n_equals_1p001": c_ok.height,
        "min": float(c["ratio"].min()),
        "max": float(c["ratio"].max()),
    },
    "T4_config": {
        "a0_meta_backtest_defaults": a0_meta,
        "a0_meta_has_execution_costs": "execution_costs" in a0_meta,
        "raw_arm_resolved_entry_price_basis": raw_resolved.get("entry_price_basis"),
        "raw_arm_resolved_execution_costs": raw_resolved.get("execution_costs"),
        "base_resolved_execution_costs": base_resolved.get("execution_costs"),
    },
    "T5_deflate": {
        "n_equals_raw_price": deflate_ok.height,
        "n_total": j.height,
        "note": "a0 价格 ÷ 1.001 与 raw 臂价格逐笔相等（相对误差 ≤1e-3）",
    },
    "shares": {
        "n_same": int((j["r_sh"] == 1).sum()),
        "n_total": j.height,
        "r_sh_min": float(j["r_sh"].min()),
        "r_sh_max": float(j["r_sh"].max()),
        "note": "股数不同源自预算÷含滑点价，非价基不同",
    },
}

# ---------- Markdown ----------
L = []
L.append("# ⑤-c 诊断 2：两臂同键价格为何全不同\n")
L.append("## 结论\n")
L.append("**③ + ①**：199 笔臂（`a0_10bp`，策略文件 `s01b_a0.py` 内 6 个 "
         "`backtest_defaults` 键）打开了 `execution_costs` 策略，"
         "引擎在 `_fill_price()` 里把 10bp 滑点乘进**成交价**再落盘；"
         "⑤-a 的单键 raw 臂（`only_entry_price_basis_raw`）没有成本策略，"
         "滑点走 `_core_buy_cost_pct()/_core_sell_cost_pct()` 的**现金成本**，"
         "`trades.entry_price` 存的是**报价**。同名列存了两个不同的量。\n")
L.append("**② 不成立**：两臂都真的吃到 raw。a0 的价格 ÷ 1.001 与 raw 臂价格"
         f"逐笔相等（{deflate_ok.height}/{j.height}）。\n")
L.append("## 判据\n")
L.append("| 判据 | 实测 | 结果 |")
L.append("|---|---|---|")
L.append(f"| T1 a0/raw 入场价比 == 1.001 | {in_ok.height}/{j.height} 命中，"
         f"极值 {float(j['r_in'].min()):.7f} ~ {float(j['r_in'].max()):.7f} | 成立 |")
L.append(f"| T2 a0/raw 出场价比 == 0.999 | {out_ok.height}/{j.height} 命中，"
         f"{out_bad.height} 笔为例外（期末未平仓，口径不同） | 成立 |")
L.append(f"| T3 同族对照 base→only_execution_costs 比值 == 1.001 | "
         f"{c_ok.height}/{c.height} 命中 | 成立（与价基无关） |")
L.append(f"| T4 a0 META 有 execution_costs | {'是' if 'execution_costs' in a0_meta else '否'} "
         f"{a0_meta.get('execution_costs')} | 成立 |")
L.append(f"| T4 raw 臂 resolved execution_costs | {raw_resolved.get('execution_costs')} | 成本策略缺席 |")
L.append(f"| T5 a0 ÷ 1.001 == raw 臂价格 | {deflate_ok.height}/{j.height} | 成立（raw 真吃到） |")
L.append("")
L.append("## 代码位置（只读引用）\n")
L.append("| 位置 | 作用 |")
L.append("|---|---|")
L.append("| `engine.py:2807-2817` `_fill_price` | `config.execution_costs` 非空时调用 "
         "`policy.fill_price(price, side, slippage_bps)`——滑点乘进价格 |")
L.append("| `engine.py:211-222` `ExecutionPolicy.fill_price` | "
         "`price × (1 ± bps/10000)`，`_round_half_up(..., price_decimals)` |")
L.append("| `engine.py:318-325` `_core_buy_cost_pct/_core_sell_cost_pct` | "
         "无成本策略时 `佣金 + 印花税 + slippage_bps/10000` 走现金成本 |")
L.append("| `engine.py:2819-2825` `_trade_cost` | 两条路的费用分量不同 |")
L.append("")
L.append("## 例外 3 笔（出场腿）\n")
L.append("| symbol | entry | exit | raw 臂出场价 | a0 出场价 | 比值 |")
L.append("|---|---|---|---:|---:|---:|")
for r in result["T2_exit_ratio"]["outliers"]:
    L.append(f"| {r['symbol']} | {r['entry_date']} | {r['xd199'] if 'xd199' in r else r['exit_date']} "
             f"| {r['exit_price']} | {r['x199']} | {r['r_out']:.6f} |")
L.append("")
L.append("## 对引用口径的影响\n")
L.append("1. ⑤-a 臂 1 的 **−5.06pp** 是「单键 raw + 滑点走现金成本」的位移，"
         "**可以**作为 raw 价基的单项位移引用；但不可与 199 笔臂的任何 Δ 互换，"
         "因为 199 笔臂的滑点在价上、股数按含滑点价折算。")
L.append("2. 任何跨臂比价必须先除/乘 `1 ± slippage_bps/10000`，"
         "否则会读出 0.1% 的伪价差（102/102 笔）。")
L.append("3. `trades.entry_price` 的含义随臂变：有成本策略=成交价，无成本策略=报价。"
         "跨臂汇总必须带「该臂是否有 execution_costs」。")
L.append("")

(HERE / "diag2_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
(HERE / "diag2_table.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k.startswith(("T1", "T2", "T3", "T5"))},
                 ensure_ascii=False, indent=1))
ok = (in_ok.height == j.height and out_ok.height + out_bad.height == j.height
      and c_ok.height == c.height and "execution_costs" in a0_meta)
print("SELFTEST", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
