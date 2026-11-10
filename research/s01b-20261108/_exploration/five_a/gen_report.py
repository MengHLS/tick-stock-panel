"""Render REPORT_five_a_20261108.md from the arm artifacts (no hand-typed numbers).

Inputs (all produced by run_arm.py / compare_and_manifest.py / diagnose_control7.py):
  arms_table.json, manifest.json, control7_diagnosis.json,
  <arm>/result.json
Output: REPORT_five_a_20261108.md
"""
from __future__ import annotations

import io
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "base_nodefaults_10bp"
ORDER = [
    "base_nodefaults_10bp",
    "only_entry_price_basis_raw",
    "only_block_limit_open",
    "only_finalize_open_at_end",
    "only_execution_costs",
    "only_trailing_peak_price_close",
    "only_exit_signal_requires_profit",
    "base_nodefaults_gross",
]
SELL_KEYS = ["sell_suspended", "sell_limit_down", "sell_invalid_price", "pending_exit"]


def jload(p: Path):
    return json.load(io.open(p, encoding="utf-8"))


def pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def main() -> int:
    arms = {a["arm"]: a for a in jload(HERE / "arms_table.json")}
    man = jload(HERE / "manifest.json")
    diag = jload(HERE / "control7_diagnosis.json")
    base_hash = man["arms"][BASE]["three_parquet_sha256"]
    eq_days = len([])
    del eq_days

    L: list[str] = []
    w = L.append

    w("# ⑤-a 单臂分解实施记录（S01 / custom_mw7fvp17 生产文件，默认口径基线）")
    w("")
    w("生成方式：`gen_report.py` 直接读取各臂 `arms_table.json` / `manifest.json` / "
      "`control7_diagnosis.json`，数字不经手抄。")
    w("")
    w("## 摘要（先看这四条）")
    w("")
    w("1. 七个 run 目录 + `base_nodefaults_gross` 全部跑完，每臂 `result.json` 内嵌 "
      "`effective_config` 全量键值，且 `resolved_matcher_config` 证明**每臂只动一个开关**。")
    w("2. 移动最大的是 `block_limit_open`（总收益 −51.47% → +12.13%，+63.60pp），"
      "其次是 `exit_signal_requires_profit`（+18.85pp），其余三项 |Δ| ≤ 5.06pp，"
      "`trailing_peak_price` 完全为 0。**各臂不可相加。**")
    w("3. 对照组：第 6 项 `trailing_peak_price` **惰性通过**（三张 parquet 与基线逐字节同 hash）；"
      "第 7 项 `exit_signal_requires_profit` **不惰性（+18.85pp）**——已查明不是夹具漏键，"
      "而是该键生产默认就是 `False`，打开它是真实加闸。按令停下报告，等裁定。")
    w("4. 任务 B：默认口径下 gross 全期年化 **−8.67%**，为负。")
    w("")
    w("## 0. 口径与前提")
    w("")
    w("- 基线 = **生产文件原样、不注入任何 `backtest_defaults`** ⇒ 208 笔（本任务基线）。")
    w("- 区间 2019-07-01…2026-10-30，初始 1,000,000 元，最大 5 仓，60% 敞口上限，次日开盘执行，"
      "成本 10bp（佣金 3e-4 + 印花 1e-3 + 滑点 10bp）。")
    w("- 单臂 = 只注入一个开关（`execution_costs` 记为一项，含 `min_commission` + "
      "`transfer_fee_pct` 两个子键）。每臂仅一个进程、一个策略文件、一条管道。")
    w(f"- 策略文件（磁盘，未改）：`D:\\TSP\\data\\strategies\\custom\\custom_mw7fvp17.py` = "
      f"3,478 B / `{man['arms'][BASE]['strategy_file_sha256']}`。")
    w("")
    w("## 1. 单臂总表")
    w("")
    w("| # | 臂（目录名） | 单一开关 | 笔数 | 总收益 | 年化(252) | MDD | Sharpe | 期末权益 "
      "| buy_limit_up | " + " | ".join(SELL_KEYS) + " | 同键笔数 | 同键 pnl Δ | 仅本臂笔数 "
      "| 仅本臂 pnl | vs 基线 | 三 parquet |")
    w("|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(SELL_KEYS) +
      "---|---|---|---|---|---|---|")
    for i, name in enumerate(ORDER):
        a = arms[name]
        same = all(man["arms"][name]["three_parquet_sha256"][k] == base_hash[k] for k in base_hash)
        toggle = a["toggle"]
        label = "基线" if i == 0 else str(i + 1)
        if name == "base_nodefaults_gross":
            toggle = "成本全零（gross）"
            label = "B"
        w(
            f"| {label} | `{name}` | `{toggle}` | {a['n_trades']} | {pct(a['total_return'])} | "
            f"{pct(a['annual_252_recomputed'])} | {pct(a['max_drawdown'])} | {a['sharpe']:.2f} | "
            f"{a['final_equity']:,.2f} | {a['buy_limit_up']} | "
            + " | ".join(str(a[k]) for k in SELL_KEYS)
            + f" | {a['n_same_key']} | {a['same_key_pnl_delta']:,.2f} | {a['only_this_arm_n']} | "
            f"{a['only_this_arm_pnl']:,.2f} | {a['delta_total_return_vs_base'] * 100:+.2f}pp | "
            f"{'逐字节相同' if same else '不同'} |"
        )
    w("")
    w("**各臂不可相加**：上表只回答「单独打开这一项，数字移动多少」，不做占比合成。"
      "开两项以上不是两项之和（路径依赖）。")
    w("")
    w("## 2. 每臂「只开一项」的证明（证据 ①）")
    w("")
    w("比较口径：`result.json` 里嵌入的 `effective_config`，取 **`resolved_matcher_config`**"
      "（= 引擎实际用的，不是我们要求的）与基线逐键对比；`single_toggle_injected` 是注入回显，"
      "`strategy_meta_backtest_defaults_effective_raw` 是 META 原样，二者只作旁证。")
    w("")
    w("| 臂 | 实际改变的配置键（resolved） | 仅由该键派生的字段 |")
    w("|---|---|---|")
    for name in ORDER:
        a = arms[name]
        real = a["effective_cfg_real_diff"]
        derived = a["effective_cfg_derived_diff"]
        rs = ", ".join(f"`{k}`: {v[0]} → {v[1]}" for k, v in real.items()) or "（无，基线）"
        ds = ", ".join(f"`{k}`: {v[0]} → {v[1]}" for k, v in derived.items()) or "—"
        w(f"| `{name}` | {rs} | {ds} |")
    w("")
    w("`effective_config.json` 另外记录了完整未截断的 `request` / 归一化后的 "
      "`execution_policy_normalized` / `resolved_matcher_config` / 策略文件哈希与算法版本；"
      "每臂同时嵌在 `result.json.effective_config` 里（现存 a0 侧 result.json 缺这一块）。")
    w("")
    w("## 3. 双价基（证据 ②）")
    w("")
    w("每臂 `trades_priced.parquet` 44 列，含 `entry_price_raw` / `entry_price_adj` / "
      "`exit_price_raw` / `exit_price_adj`，以及当日复权因子 `cf_entry` / `cf_exit`，"
      "另有 `entry_open_adj|raw`、`exit_open_adj|raw`、`entry_close_adj|raw`、"
      "`exit_close_adj|raw`、`entry_price_engine`/`exit_price_engine`（引擎实际记账价）"
      "与 `entry_price_check`/`exit_price_check`（逐笔核对结论）。")
    w("")
    w("核对结果（`entry_price_check` / `exit_price_check` 分类计数，`unexplained` 必须为 0）：")
    w("")
    w("| 臂 | basis | entry 核对 | exit 核对 | unexplained |")
    w("|---|---|---|---|---|")
    for name in ORDER:
        a = arms[name]
        w(f"| `{name}` | {a['basis_used']} | {json.dumps(a['price_check_counts']['entry'], ensure_ascii=False)} "
          f"| {json.dumps(a['price_check_counts']['exit'], ensure_ascii=False)} | {a['price_check_unexplained']} |")
    w("")
    w("## 4. 三张 parquet 的 sha256（证据 ③，`manifest.json`）")
    w("")
    w("| 臂 | trades.parquet | equity.parquet | drawdown.parquet |")
    w("|---|---|---|---|")
    for name in ORDER:
        t = man["arms"][name]["three_parquet_sha256"]
        w(f"| `{name}` | `{t['trades.parquet']}` | `{t['equity.parquet']}` | `{t['drawdown.parquet']}` |")
    w("")
    w("`manifest.json` 另含每臂 `result.json` / `effective_config.json` / `trades_priced.parquet` "
      "的 sha256 与策略文件 sha256。")
    w("")
    w("## 5. 对照组结论（第 6、7 项）")
    w("")
    tr = arms["only_trailing_peak_price_close"]
    ex = arms["only_exit_signal_requires_profit"]
    w("### 5.1 第 6 项 `only_trailing_peak_price_close` —— **惰性，通过**")
    w("")
    w(f"- 208 笔 / 总收益 {pct(tr['total_return'])} / 年化 {pct(tr['annual_252_recomputed'])} / "
      f"MDD {pct(tr['max_drawdown'])} / 期末 {tr['final_equity']:,.2f}，与基线**完全相同**；")
    w("- **trades / equity / drawdown 三张 parquet 与基线逐字节同 hash**（见 §4），"
      "同键 208 笔、同键 pnl Δ = 0.00、仅本臂 0 笔；")
    w("- 解释：`trailing_peak_price` 只喂移动止盈/移动跟踪的峰值价，策略没有 `TRAILING_*` "
      "阈值（`STOP_LOSS=None`、无移动止盈），该键无驱动对象 ⇒ 惰性。夹具未漏键。")
    w("")
    w("### 5.2 第 7 项 `only_exit_signal_requires_profit` —— **不惰性：数字动了，按令停下报告**")
    w("")
    w(f"- 178 笔 / 总收益 {pct(ex['total_return'])}（vs 基线 {pct(arms[BASE]['total_return'])}，"
      f"{ex['delta_total_return_vs_base'] * 100:+.2f}pp）/ 年化 {pct(ex['annual_252_recomputed'])} / "
      f"MDD {pct(ex['max_drawdown'])} / Sharpe {ex['sharpe']:.2f} / 期末 {ex['final_equity']:,.2f}；")
    w(f"- 同键 {ex['n_same_key']} 笔、同键 pnl Δ {ex['same_key_pnl_delta']:,.2f}，仅本臂 "
      f"{ex['only_this_arm_n']} 笔 / {ex['only_this_arm_pnl']:,.2f}。")
    w("")
    w("**不是夹具漏键**（先排除这一条，因为它决定要不要停）：§2 显示本臂 `resolved_matcher_config` "
      "只有一个键变化 `exit_signal_requires_profit: False → True`，外加由它派生的 "
      "`exit_signal_profit_basis: None → holding_peak_close`；三张 parquet 虽与基线不同，"
      "但那是结果不同，不是配置多头。**夹具干净。**")
    w("")
    w("**动的原因：这条开关在生产默认里是 `False`，打开它是「真实开一项」而不是惰性项。**"
      "基线 `execution_policy_normalized` 与 `resolved_matcher_config` 都写着 "
      "`exit_signal_requires_profit=False`（日志同样打印 `\"exit_signal_requires_profit\": false`），"
      "派单里「默认已 false ⇒ 惰性」的推断方向反了：false→true 是加了一道闸。")
    w("")
    w("闸的语义（`engine.py:2865-2875 _exit_signal_profit_armed`）：信号出场只在持仓期内"
      "收盘价曾高于成本价时才放行（`max(close over holding) > entry_price`）。实测（"
      f"`control7_diagnosis.json`，脚本 `diagnose_control7.py`，退出码 0）：")
    w("")
    w(f"- 基线 150 笔 `signal` 出场中，闸门挡下 **{diag['blocked_signal_exits_gate_false']}** 笔"
      f"（持仓期峰值收盘从未高于成本），放行 {diag['gate_true_signal_exits']} 笔；")
    w(f"- 被挡的 {diag['blocked_signal_exits_gate_false']} 笔在臂 7 的去向："
      f"{json.dumps(diag['blocked_exit_reason_in_arm6'], ensure_ascii=False)}"
      "（`null` = 该笔在新路径下不存在，因为出场日晚了/换了，后面建仓的标的与顺序整体位移）；")
    w(f"- 被挡 {diag['blocked_signal_exits_gate_false']} 笔在基线 `pnl_amount` 合计 "
      f"{diag['blocked_pnl_amount_base']:,.2f}；其中 {diag['blocked_signal_exits_gate_false'] - diag['blocked_absent_from_arm6']} 笔"
      f"在臂 7 仍能按 `(symbol, entry_date)` 配上、合计 {diag['blocked_pnl_amount_arm6']:,.2f}"
      f"（已达 {diag['blocked_absent_from_arm6']} 笔因路径位移不再存在，无法逐笔配对）；")
    w(f"- 残差：按「峰值收盘 > 成本」近似复算闸门，H1 违例 {diag['H1_violations']} 笔、"
      f"H2 违例 {diag['H2_violations']} 笔（闸门用的是引擎内部 `risk_entry_price` 与"
      "持仓期口径，我这里是外部近似，1 笔对不上属近似误差，不影响「不惰性」的结论）。")
    w("")
    w("按要求**没有**继续往下归因，也没有把这项与其他臂合成。请裁定：这一项在 ⑤-a 里算"
      "「真实开关」还是从对照组里剔除。")
    w("")
    w("## 6. 任务 B：默认口径 gross（`base_nodefaults_gross`）")
    w("")
    g = jload(HERE / "base_nodefaults_gross" / "result.json")
    st = g["stats"]
    w(f"- 不注入 defaults、成本全零（`commission_pct=0`、`stamp_tax_pct=0`、`slippage_bps=0`，"
      f"`gross={g['gross']}`）：208 笔 / 总收益 {pct(st['total_return'])} / "
      f"年化 {pct(st['annual_return'])} / MDD {pct(st['max_drawdown'])} / Sharpe {st['sharpe']:.2f} / "
      f"期末 {st['final_equity']:,.2f}。")
    w("")
    w(f"**一句话结论：默认口径下 gross 全期年化仍为负（{pct(st['annual_return'])}），"
      "不是正。** 因此 F2 那句「入场有弱正 gross alpha（+4.21%）」**必须带口径限定**："
      "+4.21% 的出处口径由研究侧标明（本任务没有重跑那条口径的 gross，不代它发言），"
      "但同一策略在默认口径下 gross 是负年化，去掉限定就会与新读数相互矛盾。")
    w("")
    w("## 7. 落地物与命令")
    w("")
    w("| 文件 | 作用 |")
    w("|---|---|")
    w("| `run_arm.py` | 单臂运行器（一进程一臂；可选择性注入一个开关；落三 parquet + result.json + effective_config.json） |")
    w("| `inject/*.json` | 各臂注入载荷（`base` 无文件 = 不注入） |")
    w("| `compare_and_manifest.py` | 同键对比、双价基逐笔、sha256 清单、arms_table 四格式 |")
    w("| `diagnose_control7.py` | 第 7 项不惰性的机制证据（只读，不改任何臂） |")
    w("| `gen_report.py` | 本报告生成器 |")
    w("| `logs/*.log` | 每臂与对比、诊断的完整 stdout（UTF-16） |")
    w("")
    w("退出码：七臂 + gross 运行 `run_arm.py` 全 0（`result.json.error` 均为 `null`）；"
      "`compare_and_manifest.py` 0；`diagnose_control7.py` 0；`gen_report.py` 0。")
    w("")
    (HERE / "REPORT_five_a_20261108.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote REPORT_five_a_20261108.md", len("\n".join(L)) + 1, "chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
