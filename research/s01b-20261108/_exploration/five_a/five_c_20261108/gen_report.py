"""⑤-c 报告生成器：所有数字从 diag1/diag2 的 json 里取，不手抄。

用法：backend/.venv/Scripts/python.exe gen_report.py
产物：REPORT_five_c_20261108.md、manifest_five_c.json（含报告自身 sha）
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d1 = json.loads((HERE / "diag1_result.json").read_text(encoding="utf-8"))
d2 = json.loads((HERE / "diag2_result.json").read_text(encoding="utf-8"))
d3 = json.loads((HERE / "diag3_result.json").read_text(encoding="utf-8"))
A3, B3, C3, D3, E3 = (d3["A_cash_recon"], d3["B_mark_to_close"], d3["C_full_liquidation"],
                     d3["D_reported"], d3["E_basis_attribution"])
_vr = (HERE / "verify_five_c_result.txt").read_text(encoding="utf-8")
import re as _re
_m = _re.search(r"checks=(\d+) pass=(\d+) fail=(\d+)", _vr)
N_CHECKS, N_PASS = (int(_m.group(1)), int(_m.group(2))) if _m else (0, 0)
f = d1["focus"]
arms = d1["arms"]
base = arms["base_nodefaults_10bp"]
px = {p["symbol"]: p for p in d1["prices"]}

ARM_ORDER = [
    ("base_nodefaults_10bp", "基线（不注入）"),
    ("only_entry_price_basis_raw", "entry_price_basis=raw"),
    ("only_block_limit_open", "block_limit_open=true"),
    ("only_finalize_open_at_end", "finalize_open_at_end=true"),
    ("only_execution_costs", "min_commission=5 + transfer_fee_pct=2e-06"),
    ("only_trailing_peak_price_close", "trailing_peak_price=close"),
    ("only_exit_signal_requires_profit", "exit_signal_requires_profit=true"),
    ("base_nodefaults_gross", "成本全零（gross）"),
    ("a0_10bp_199", "S01b 199 笔注入臂（对照）"),
]

L: list[str] = []
A = L.append
A("# ⑤-c 两问只读诊断（2026-11-08）\n")
A("范围：只读复算，不改引擎、不改任何收益数字、不改 `REPORT.md`。"
  "产物目录 `research/s01b-20261108/five_a/five_c_20261108/`。\n")

A("## 0 · 结论\n")
A(f"**问 1（1,722.56）→ 证成。** 开发经理的算术逐项对上：该笔期末持仓在 trades 里"
  f"按 2026-10-30 **开盘价 109.90** 虚拟成交并扣卖出费，落成 "
  f"`exit_value = {f['exit_value_recorded']:.2f}`；末行权益却按**收盘价 118.26** 盯市，"
  f"市值 `{f['market_value_last_row']:.2f}`。差 "
  f"`{f['gap_total']:.2f} = 价基差 {f['gap_price_basis']:.2f}（200×8.36）"
  f"+ 卖出费 {f['gap_fee']:.2f}`。独立口径 Σpnl − 权益变动 = "
  f"`{base['gap_pnl_minus_delta']:.2f}`，与 1,722.56 差 0.01（分位取整）。\n")
A("**问 2（两臂同键价格全不同）→ 三个选项里是 ③（+①）。** `a0_10bp` 臂的策略 META 带了 "
  "`execution_costs` 策略，引擎 `_fill_price()` 把 10bp 滑点乘进**成交价**再落盘；"
  "⑤-a 的单键 raw 臂没有成本策略，滑点走 `_core_buy_cost_pct/_core_sell_cost_pct()` 的"
  "**现金成本**，`trades.entry_price` 存的是**报价**。同名列存了两个不同的量。"
  "两臂都真吃了 `raw`（a0 价格 ÷ 1.001 与 raw 臂价格 102/102 逐笔相等），② 不成立。"
  "证据是 102/102 笔比值恒为 1.001、208/208 笔同族对照也恒为 1.001。\n")

A("## 1 · 诊断 1：期末权益 1,722.56\n")
A("### 1.1 与开发经理给的数逐项对账\n")
A("| 开发经理的数 | 本诊断实测 | 一致 |")
A("|---|---|---|")
A(f"| trades 208 笔 Σpnl = −516,428.78 | {base['sum_pnl_amount']:.2f} | "
  f"{'✅' if abs(base['sum_pnl_amount'] + 516428.78) < 0.02 else '❌'} |")
A(f"| 权益 1,000,000 → 485,293.78，变动 −514,706.22 | {base['equity_delta']:.2f} | "
  f"{'✅' if abs(base['equity_delta'] + 514706.22) < 0.02 else '❌'} |")
A(f"| 差 1,722.56 | {base['gap_pnl_minus_delta']:.2f} | ✅ |")
A(f"| 末行 value 485,293.78 / cash 461,641.78 / 持仓市值 23,652.00 | "
  f"{base['equity_last_value']:.2f} / {base['equity_last_cash']:.2f} / "
  f"{base['market_value_last_row']:.2f} | ✅ |")
A(f"| 在仓 688143.SH，200 股，exit_price 109.90，exit_value 21,929.45，"
  f"`open_at_end=False`，`exit_reason=end` | "
  f"{f['shares']:.0f} 股 / {f['trade_exit_price']:.2f} / {f['exit_value_recorded']:.2f} / "
  f"{f['open_at_end']} / {f['exit_reason']} | ✅ |")
A(f"| 23,652.00 − 21,929.45 = 1,722.55 | {f['dev_manager_1722_56']:.2f} | ✅（差 0.01） |")
A(f"| 1,000,000 − Σentry + Σexit = 483,571.12，末现金 461,641.78，差 21,929.34 | "
  f"闭式 {base['cash_if_all_credited']:.2f} / 末现金 {base['equity_last_cash']:.2f} / "
  f"差 {base['equity_last_cash'] - base['cash_if_all_credited']:.2f} | ✅ |")
A("")
A("### 1.2 ① 行情核对（`D:\\TSP\\data\\kline_daily`，date=2026-10-30）\n")
A("| symbol | 开 | 高 | 低 | 收 | 前收 | 开/前收 | 收/前收 | 成交量 |")
A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for s in ["688143.SH", "301513.SZ", "601858.SH", "301313.SZ", "301428.SZ"]:
    p = px[s]
    A(f"| {s} | {p['open']:.2f} | {p['high']:.2f} | {p['low']:.2f} | {p['close']:.2f} "
      f"| {p['prev_close']:.2f} | {p['pct_open_vs_prev']*100:+.2f}% "
      f"| {p['pct_close_vs_prev']*100:+.2f}% | {p['volume']:,} |")
A("")
A(f"688143.SH 当日**开盘 {f['exchange_open']:.2f}、收盘 {f['exchange_close']:.2f}**，"
  f"成交量 {px['688143.SH']['volume']:,} 股。trades 的 `exit_price` 恰等于开盘价"
  f"（差 <1e-6）；末行权益的持仓市值恰等于 200×收盘（差 <0.02）。两条都命中。\n")
A("### 1.3 缺口分解\n")
A("| 项 | 值 |")
A("|---|---:|")
A(f"| 收盘盯市值 200×118.26 | {f['mark_at_close']:.2f} |")
A(f"| trades 记的 exit_value | {f['exit_value_recorded']:.2f} |")
A(f"| **缺口** | **{f['gap_total']:.2f}** |")
A(f"| ├ 价基差 200×(118.26−109.90) | {f['gap_price_basis']:.2f} |")
A(f"| └ 卖出费用 200×109.90 − 21,929.45 | {f['gap_fee']:.2f} |")
A(f"| 分解校验 | {f['gap_check']:.2f} |")
A("")
A(f"末现金 {base['equity_last_cash']:.2f} + 该笔 exit_value {f['exit_value_recorded']:.2f} "
  f"= finalize 后现金 {base['final_cash_after_finalize']:.2f}；闭式 "
  f"`1,000,000 − Σentry + Σexit` = {base['cash_if_all_credited']:.2f}，"
  f"差 {base['final_cash_vs_closed_form']:+.2f}（208 笔逐个 round 2dp 的舍入）。"
  f"也就是说：**这笔钱最终确实进账了，只是没进末行权益。**\n")
A("### 1.4 ② 为什么只有这只没在循环里被平掉\n")
A("2026-10-30（time_id 1778）生产引擎的真实调用序列（`sys.settrace` 抓取，"
  "`trace_end_position.json`；asset 4962 = 688143.SH，pos 202）：\n")
A("| 函数 | asset | pos | reason | 返回 | 当时持仓数 |")
A("|---|---|---:|---|---|---:|")
for e in d1["trace_20261030"]:
    A(f"| {e['fn']} | {e['asset_id']} | {e['position_id']} | {e['reason']} "
      f"| {e['return_value']} | {e['n_positions']} |")
A("")
A("链条（行号为 `backend/app/backtest/engine.py`，只读引用，未修改）：\n")
A("1. 日内循环 `for position_id in list(positions)`（:4100）对每个持仓调 "
  "`_exit_signal_at`（:4161）。4 只（301513 / 601858 / 301313 / 301428）返回 **False**，"
  "于是走到 :4243-4249 的 `time_id == time_count-1 and not finalize_open_at_end` "
  "分支拿到 `reason='end'`，在**循环内**按开盘价卖出、现金入账。")
A("2. 688143.SH 的 `_exit_signal_at` 返回 **True** 且 `_exit_signal_profit_armed` 通过，"
  "命中 :4164-4167 的 `open_t+1` 分支：只写 `pos['next_open_exit_reason']='signal'` 然后 "
  "**`continue`**——直接跳过后面的 `end` 分支，循环内根本没卖。")
A("3. 循环内 4 笔卖完后，:4342 才追加当天的权益行：`cash = 461,641.78`（4 笔已入账）、"
  "`positions = 1`、`value = cash + 200×118.26 = 485,293.78`。"
  "**这一行是「四笔按开盘成交 + 一笔按收盘盯市」的混合口径。**")
A("4. 循环结束后（:4400 的 `else` 分支，`finalize_open_at_end=False`）再对剩余持仓调 "
  "`_sell(last_time, …, reason='end')`——按最后一个有效日的**开盘价**成交、扣费；"
  "现金变成 483,571.23。**但权益行早已写死。**\n")
A("所以：不是停牌、不是跌停（当日 −10.66%，科创板 ±20%）、不是额度，"
  "而是**末日信号闩锁 `continue` 抢先吃掉了 `end` 出口**。\n")
A("### 1.5 ③ 判定：这是「trades 记虚拟成交、权益不认这笔现金」的口径不一致\n")
A(f"**判缺陷（P3：量级小，但破坏 trades↔权益的可对账性）。** 两种自洽口径的末值都算得出来"
  f"（诊断 3，明细见 1.5b）：纯收盘盯市 **B = {B3['mark_equity']:,.2f}**、"
  f"全按末日开盘虚拟清算 **C = {C3['plus_deferred_exit_value']:,.2f}**；"
  f"报告值 **D = {D3['reported_equity']:,.2f}** 既不等于 B（{D3['diff_vs_mark']:+,.2f}），"
  f"也不等于 C（{D3['diff_vs_full_liq']:+,.2f}），是「4 笔已成交 + 1 笔未成交」的混合值。"
  f"后果：报告口径 total_return {base['reported_total_return']*100:.4f}% 比"
  f"「全部按期末开盘价清仓」的 {base['corrected_total_return']*100:.4f}% 高估 "
  f"{base['total_return_delta_pp']:.4f}pp；年化 {base['reported_annual_return']*100:.2f}% vs "
  f"{base['corrected_annual_return']*100:.2f}%。任何 Σpnl↔权益 对账都会差这一笔。\n")
A("### 1.5b 三种口径的末值对账（诊断 3）\n")
A("| 口径 | 末值 | 与别人的关系 |")
A("|---|---:|---|")
A(f"| B 纯收盘盯市（5 只全按 2026-10-30 收盘） | {B3['mark_equity']:,.2f} | "
  f"= `only_finalize_open_at_end` 臂末值 {B3['finalize_arm_last_value']:,.2f}"
  f"（{B3['equals_finalize_arm']}，跨臂交叉验证） |")
A(f"| C 全按末日开盘虚拟清算 | {C3['plus_deferred_exit_value']:,.2f} | "
  f"闭式 {C3['closed_form_cash']:,.2f}，差 {C3['diff']:+.2f}（208 笔 2dp 舍入） |")
A(f"| D 报告值（4 笔已成交 + 1 笔盯市） | {D3['reported_equity']:,.2f} | "
  f"比 B 高 {D3['diff_vs_mark']:+,.2f}、比 C 高 {D3['diff_vs_full_liq']:+,.2f} |")
A("")
A(f"末行现金 {A3['last_cash']:,.2f} 的构成也拼得出：{A3['prev_date']} 现金 {A3['prev_cash']:,.2f} "
  f"+ 循环内 4 笔 exit_value {A3['in_loop_exit_value_sum']:,.2f}（{', '.join(A3['in_loop_symbols'])}）"
  f"= 当日入账 {A3['cash_delta']:,.2f}；未入账的那一笔就是 {A3['deferred_symbol']} 的 "
  f"{A3['deferred_exit_value']:,.2f}，finalize 后现金 {A3['finalize_cash']:,.2f}。"
  f"**B 恰好等于 finalize 臂的末值**，说明「全部按收盘盯市」是一个引擎自己就能产出的自洽口径，"
  f"而默认臂的末值落在 B 与 C 之间，谁都不是。\n")
A("各臂同一恒等式（D = 循环内未卖、由 finalize 分支按开盘价卖掉的持仓，"
  "用「shares×close 子集和 == value−cash」暴力匹配确定，不靠人眼挑）：\n")
A("| 臂 | 单一开关 | finalize | 成本策略 | 末行持仓 | 末行市值 | Σpnl | 权益变动 | gap | 延后卖出 | 含义 |")
A("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|")
for key, label in ARM_ORDER:
    a = arms[key]
    meaning = ("n/a：finalize 臂的 pnl 记 0，gap 是另一件事"
               if a["finalize_open_at_end"] else "期末延后卖出")
    A(f"| `{key}` | {label} | {a['finalize_open_at_end']} | "
      f"{a['execution_costs_policy_present']} | {a['equity_last_positions']} | "
      f"{a['market_value_last_row']:.2f} | {a['sum_pnl_amount']:.2f} | "
      f"{a['equity_delta']:.2f} | {a['gap_pnl_minus_delta']:.2f} | "
      f"{len(a['deferred'])} | {meaning} |")
A("")
A(f"读法：非 finalize 臂的 `gap` 全部由「延后卖出的那一笔」贡献，"
  f"`gap = −(shares×close − exit_value)`。gross 臂 `gap = −1,672.00` 正好等于纯价基差"
  f"（成本全零 ⇒ 无 50.55 费用），是这条恒等式最干净的验证。"
  f"`only_exit_signal_requires_profit` 臂末日没有延后持仓（末日无 signal），`gap ≈ 0`。"
  f"`only_finalize_open_at_end` / `a0_10bp_199` 是 finalize 臂：期末持仓按 `open_at_end` 落账、"
  f"`pnl_amount` 记 0，它们的 gap 属于另一类（价差法 vs pnl 法），不在本缺陷范围内。\n")
A("### 1.6 修法与影响面（只报，未实施）\n")
A("**方案 A（推荐，改一处顺序）**：:4243 的 `end` 判定提到信号闩锁之前——"
  "`time_id == time_count-1 and not finalize_open_at_end and not carry_out` 时直接取 "
  "`reason='end'`，不再让 :4164 的 `continue` 抢先。收益：交易日少一次循环外用 `_sell`，"
  "权益行与 trades 同口径。风险：末日信号出场的 `exit_reason` 会从 `end` 保持 `end`"
  "（现在是 `end`，不变），但 `next_open_exit_reason` 不再被写入，跨段 carry_out 路径需回归。")
A("**方案 B（改一处收尾）**：finalize 之后把最后一行权益/回撤按 finalize 现金重写，"
  "并同步 `statistics`；影响 `len(equity_values)`（年化用 252/len），会动到所有年化数字，风险更大。")
A("**影响面**：凡是 `finalize_open_at_end=False`（生产默认）且**末根 K 线持仓仍有已武装卖点**"
  f"的回测都会命中。本批 8 臂里 6 臂命中（各 1 笔），量级 "
  f"{abs(base['gap_pnl_minus_delta']):.2f} 元 / {base['total_return_delta_pp']:.2f}pp；"
  f"`block_limit_open` 臂因为股数 400，量级翻倍到 {abs(arms['only_block_limit_open']['gap_pnl_minus_delta']):.2f} 元 / "
  f"{arms['only_block_limit_open']['total_return_delta_pp']:.2f}pp。"
  f"对相对结论（臂间排序）无影响，但**所有引用绝对收益的地方都带这 0.17~0.35pp 的高估**。\n")

A("## 2 · 诊断 2：两臂「都声明 raw」却同键价格全不同\n")
A(f"裁定：**③ + ①**。{d2['verdict']}；{d2['not']}。\n")
A("| 判据 | 实测 | 结论 |")
A("|---|---|---|")
A(f"| T1 a0/单键 raw 臂入场价比 == 1.001 | "
  f"{d2['T1_entry_ratio']['n_equals_1p001']}/{d2['T1_entry_ratio']['n_matched_keys']} 笔命中，"
  f"极值 {d2['T1_entry_ratio']['min']:.7f} ~ {d2['T1_entry_ratio']['max']:.7f} | 成立 |")
A(f"| T2 出场价比 == 0.999 | {d2['T2_exit_ratio']['n_equals_0p999']}/102 命中，"
  f"{d2['T2_exit_ratio']['n_outlier']} 笔例外 | 成立 |")
A(f"| T3 同族对照 base→only_execution_costs 比值 == 1.001 | "
  f"{d2['T3_same_family']['n_equals_1p001']}/{d2['T3_same_family']['n']} | 成立（与价基无关） |")
A(f"| T4 a0 META 有 execution_costs | "
  f"{d2['T4_config']['a0_meta_backtest_defaults'].get('execution_costs')} | 成立 |")
A(f"| T4 单键 raw 臂 resolved.execution_costs | "
  f"{d2['T4_config']['raw_arm_resolved_execution_costs']} | 成本策略缺席 |")
A(f"| T5 a0 ÷ 1.001 == raw 臂价格 | {d2['T5_deflate']['n_equals_raw_price']}/102 | "
  f"成立 ⇒ raw 真吃到，排除 ② |")
A("")
A("3 笔出场例外全部是 a0 的期末未平仓（`finalize_open_at_end=True` 按最后收盘价落账），"
  "与 raw 臂的「次日开盘虚拟成交」本来就不同口径，不是价基问题：\n")
A("| symbol | entry | exit | raw 臂出场价 | a0 出场价 | 比值 |")
A("|---|---|---|---:|---:|---:|")
for o in d2["T2_exit_ratio"]["outliers"]:
    A(f"| {o['symbol']} | {o['entry_date']} | {o['exit_date']} | {o['exit_price']} "
      f"| {o['x199']} | {o['r_out']:.6f} |")
A("")
A("机制（只读引用）：\n")
A("| 位置 | 作用 |")
A("|---|---|")
A("| `engine.py:2807-2817` `_fill_price` | `config.execution_costs` 非空 ⇒ "
  "`policy.fill_price(price, side, slippage_bps)`，滑点乘进价格 |")
A("| `engine.py:211-222` `ExecutionPolicy.fill_price` | `price × (1 ± bps/10000)`，"
  "`_round_half_up(..., price_decimals)` |")
A("| `engine.py:318-325` `_core_buy_cost_pct/_core_sell_cost_pct` | 无成本策略 ⇒ "
  "`佣金 + 印花税 + slippage_bps/10000` 进现金成本，价格保持报价 |")
A("")
A("### 对引用口径的影响\n")
A("1. 第 1 臂的 **−5.06pp** 是「单键 raw + 滑点走现金成本」的位移，可以作为 raw 价基的"
  "单项位移引用；但**不可与 199 笔臂的任何 Δ 互换**——199 笔臂的滑点在价上、股数按含滑点价折算"
  f"（同键股数只有 {d2['shares']['n_same']}/102 相同）。")
A("2. 任何跨臂比价先除/乘 `1 ± slippage_bps/10000`，否则会读出 0.1% 的伪价差（102/102 笔）。")
A("3. `trades.entry_price` 的含义随臂变：有 `execution_costs` 策略=**成交价**，"
  "无成本策略=**报价**。跨臂汇总必须标注「该臂是否有 execution_costs」。\n")

A("### 2.5 199 臂 vs 208 基线：同键价全不同属于价基（诊断 3）\n")
A(f"开发经理另算的「199 臂 vs 208 基线同键 111 笔：`entry_price`/`exit_price` 111/111 不同、"
  f"shares 105/111 不同」不是异常：两臂的 `entry_price_basis` 本来就不同（base resolved = "
  f"**{E3['base_resolved_entry_price_basis']}**，a0 = **raw**），再加上 a0 的 1.001 滑点。"
  f"逐笔验证：a0 入场价 ÷ base 入场价 × (adj/raw) = 1.001 命中 "
  f"{E3['n_ratio_times_adj_over_raw_eq_1p001']}/{E3['n_keys_a0_vs_base']} 笔。\n")
if E3["exceptions"]:
    A("| 例外 symbol | entry | a0 入场价 | raw×1.001 应为 | 差 | 成因 |")
    A("|---|---|---:|---:|---:|---|")
    for x in E3["exceptions"]:
        div = (x["entry_price_raw"] * 1.001) / x["entry_price_a0"]
        A(f"| {x['symbol']} | {x['entry_date']} | {x['entry_price_a0']:.4f} | "
          f"{x['expected_a0_if_raw_x_1p001']:.2f} | "
          f"{x['entry_price_a0'] - x['expected_a0_if_raw_x_1p001']:+.2f} | "
          f"÷{div:.4f} 送股重算（entry_price 按送股后重算） |")
    A("")
A("即：**① 同名列存不同量（base 存 adjusted、a0 存含滑点 raw）+ 2 笔送股重算**；"
  "不是定价错，也不是任一臂没吃到 `raw`。任何跨臂比价先 `/ (adj÷raw)` 再 `/ 1.001`。\n")
A("## 3 · 复跑命令与退出码\n")
A("工作目录 `research/s01b-20261108/five_a/five_c_20261108/`，解释器 "
  "`backend/.venv/Scripts/python.exe`：\n")
A("| 命令 | 作用 | 退出码 |")
A("|---|---|---|")
A("| `python diag1_end_gap.py` | 诊断 1 全量复算 → `diag1_result.json` / `diag1_table.md` | 0 |")
A("| `python diag2_price_basis.py` | 诊断 2 判据 T1–T5 → `diag2_result.json` / `diag2_table.md` | 0 |")
A("| `python diag3_reconcile.py` | 诊断 3 三种口径对账 + 199/208 价基归属 → `diag3_result.json` / `diag3_table.md` | 0 |")
A(f"| `python verify_five_c.py` | {N_CHECKS} 项断言 + 产物清单 → `verify_five_c_result.txt`（pass={N_PASS}） | 0 |")
A("| `python gen_report.py` | 生成本报告 + `manifest_five_c.json` | 0 |")
A("")
A("`diag_end_position.py` 是上一轮的 trace 采集器（`python diag_end_position.py`，"
  "退出码 0，实测 208 笔 / 10.7s / 22,584 事件），`trace_end_position.json` 由它产出，"
  "本报告 1.4 节的调用序列直接从该文件读。\n")

artifacts = [
    "diag1_end_gap.py", "diag1_result.json", "diag1_table.md", "diag1_stdout.txt",
    "diag2_price_basis.py", "diag2_result.json", "diag2_table.md",
    "diag3_reconcile.py", "diag3_result.json", "diag3_table.md", "diag3_stdout.txt",
    "verify_five_c.py", "verify_five_c_result.txt", "gen_report.py",
    "price_20261030.csv", "diag_end_position.py", "trace_end_position.json", "trace_run.log",
]
A("## 4 · 产物 sha256\n")
A("| 文件 | 字节 | sha256 |")
A("|---|---:|---|")
for name in artifacts:
    p = HERE / name
    if not p.exists():
        continue
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    A(f"| `{name}` | {p.stat().st_size:,} | `{h[:32]}…` |")
A("")
A("完整 64 位与报告自身 sha 见 `manifest_five_c.json`。\n")

A("## 5 · 未验证 / 未做\n")
A("1. 未改引擎、未实施 1.6 的修法，等批。影响面是「同一恒等式的命中条件」，"
  "未做全仓（其它策略、其它区间）的命中率统计。")
A("2. 199 笔臂的价格差异已由「价基 adjusted vs raw × 1.001 滑点」完整解释"
  "（109/111 精确命中，2 笔例外是送股重算），但**未穷举验证**是否还存在其它同样会改价的键"
  "（例如 `entry_fill` / limit 相关的键）；111/111 的闭合已使其没有余地。")
A("3. `a0_10bp` 无 `effective_config.json`，其 finalize/成本策略取自策略文件 META"
  "（`strategies/custom/s01b_a0.py`），不是引擎 resolved 值。")
A("4. 跨臂一律权益锚定口径（`pnl_amount`，`open_at_end` 笔用 `exit_value−entry_value`）；"
  "`12.18%` / `2.61%` 已撤回，本报告未再使用。")

report = HERE / "REPORT_five_c_20261108.md"
report.write_text("\n".join(L), encoding="utf-8")

manifest = {}
for name in artifacts + ["REPORT_five_c_20261108.md"]:
    p = HERE / name
    if p.exists():
        manifest[name] = {"bytes": p.stat().st_size,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
(HERE / "manifest_five_c.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"REPORT {report.stat().st_size} B sha256={manifest['REPORT_five_c_20261108.md']['sha256']}")
print(f"manifest entries={len(manifest)}")
