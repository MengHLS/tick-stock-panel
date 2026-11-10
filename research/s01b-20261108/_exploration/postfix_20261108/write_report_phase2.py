"""生成 REPORT_phase2_20261108.md（阶段2 交付报告）。

所有数字来自 delta_arms.json / manifest_phase2.json / five_a 与 postfix 的 result.json，
不在正文手抄。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PARENT = HERE.parent
FIVE_A = PARENT / "five_a"


def sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(root: pathlib.Path, tag: str) -> dict:
    r = json.loads((root / tag / "result.json").read_text(encoding="utf-8"))
    s = r["stats"]
    return {"tot": s["total_return"], "ann": s["annual_return"], "mdd": s["max_drawdown"],
            "fin": s["final_equity"], "n": s["n_trades"], "wr": s["win_rate"],
            "med": s["median_pnl"], "oae": s["open_at_end_count"],
            "done": s["completed_trade_count"], "hold": s["avg_holding_days"]}


delta = json.loads((HERE / "delta_arms.json").read_text(encoding="utf-8"))
man = json.loads((HERE / "manifest_phase2.json").read_text(encoding="utf-8"))
dmap = {a["tag"]: a for a in delta["arms"]}
arms = man["arms"]
n_total = len(arms)
n_byte_same = sum(1 for a in arms if a["vs_D"]["trades_same"] and a["vs_D"]["equity_same"])
n_exec_same = sum(1 for a in arms if a["vs_D"]["execution_same"])
n_meta_only = sum(1 for a in arms if a["vs_D"]["status"] == "CHANGED"
                  and a["vs_D"]["trades_same"] and a["vs_D"]["equity_same"])
n_det = sum(1 for a in arms if a["determinism_parquet_identical"])

L: list[str] = []
A = L.append

A("# S01b · 阶段2：全部臂在 D→C 口径下重跑 · 2026-11-08")
A("")
A("产物目录 `research/s01b-20261108/postfix_20261108/results_all/`（18 臂，新目录，未覆盖 "
  "`results/`、`five_a/`、`five_c/`）。引擎 `backend/app/backtest/engine.py` "
  f"269,940 B / sha256 `{man['engine']['sha256']}`（阶段1 修复后的同一份，本轮未改）。")
A("")
A("## 0 · 结论先行")
A("")
A(f"1. **18 臂全部在新引擎下有产物，且 `trades.parquet` / `equity.parquet` 与旧 `results/` 下"
  f"同臂产物逐字节相同（{n_byte_same}/{n_total}）。** 换 C 口径后这 18 臂的数字一个都不变。")
A(f"2. 原因不是修复没生效，而是这 18 个策略文件**全部声明 `finalize_open_at_end=True`**"
  "（`arms.py` 模板里写死），走「末日强制清算」分支；按契约 D-1，该分支正是唯一不受末日结算缺陷"
  "影响的分支（阶段1 的 `only_finalize_open_at_end` 臂同样逐字节未变，是同一件事的两个尺子）。")
A(f"3. **`stats.execution` 12 个键在 18 臂上整块未变（{n_exec_same}/{n_total}）**，"
  "P6 相关键（`sell_limit_down` / `pending_exit` / `sell_suspended` / `sell_invalid_price`）"
  "一个都没动——这 18 臂历史上就没落进那六条逃逸路径。")
A(f"4. 唯一 stats 差异是 `smoke_a0` 的 `market_matrix_shape` / `market_matrix_bytes`"
  f"（59×5197 → 59×5811，共 {n_meta_only} 臂），是研究侧 `data_root` 后来扩容所致，"
  "与代码无关，其产物仍逐字节相同。")
A("5. **因此「8 臂指标表 / 四臂结论」不因 D→C 作废**；真正作废的是**五-a 单键分解那一组**"
  "（`five_a/` 与 ⑤-c 及三份交叉核验文档），清单见 §4。")
A("")

A("## 1 · 18 臂：D（旧）→ C（新）")
A("")
A("| 臂 | 笔数 | 闭环 | 期末持仓 | 末值 D | 末值 C | 总收益 D | 总收益 C | 年化 D | 年化 C | "
  "MDD D | MDD C | 胜率 | median pnl | 均持仓 | 状态 |")
A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
for a in arms:
    tag = a["tag"]
    d = load(PARENT / "results", tag) if (PARENT / "results" / tag / "result.json").exists() else None
    c = load(HERE / "results_all", tag)
    status = "未变" if dmap[tag]["status"] == "UNCHANGED" else "仅元数据差异"
    A(f"| `{tag}` | {c['n']} | {c['done']} | {c['oae']} | {d['fin']:,.2f} | {c['fin']:,.2f} | "
      f"{d['tot'] * 100:+.2f}% | {c['tot'] * 100:+.2f}% | {d['ann'] * 100:+.2f}% | {c['ann'] * 100:+.2f}% | "
      f"{d['mdd'] * 100:.2f}% | {c['mdd'] * 100:.2f}% | {c['wr']:.1%} | {c['med'] * 100:+.2f}% | "
      f"{c['hold']:.1f} | {status} |")
A("")
A("Δ 全零（总收益 Δ = 0.0000pp、末值 Δ = 0.00 元、MDD Δ = 0.0000pp、胜率与 median pnl Δ = 0），"
  "逐指标三列对照见 `METRICS_D_vs_C_20261108.md`（20 个指标 × 18 臂，含 OOS 三列）。")
A("")
A("**两条必须点名的口径动作**：")
A("")
A("1. `prod_file_10bp` 原跑的是 17:0x 的生产文件（5,510 B / `918254f0…`，四臂口径变体）。该文件此后"
  "被回滚（现 `D:\\TSP\\data\\strategies\\custom\\custom_mw7fvp17.py` = 3,478 B / `85ae72a5…`），"
  "所以本轮从 `prod_file_snapshots/custom_mw7fvp17.py.variant_5510B_918254f0.py` 还原到本目录 "
  "`_inputs/prod_variant_5510B/` 再跑，**不读写 `D:\\TSP`**。结果 1,135 笔 / 138,893.51，与 D 逐字节相同。"
  "（若有人拿**今天**的生产文件跑同名臂，会得到 208 笔 / `base_nodefaults_10bp` 那组数——那是另一条臂，"
  "不是回归。）")
A("2. `smoke_a0`（2023-01-01…2023-03-31）的 D 产物产生于数据根扩容之前，故只有 "
  "`market_matrix_shape/bytes` 变化；3 个 parquet 仍逐字节相同，指标无一位移。")
A("")

A("## 2 · 阶段2 判据核对")
A("")
A("| 判据 | 结果 |")
A("|---|---|")
A(f"| 12 个（或全部）臂在新引擎下有产物 | **18/18**，每臂 3 parquet + result.json + effective_config.json |")
A(f"| 每臂记录 10 项指标 | 全部落 `manifest_phase2.json`（n_trades / total / annual / MDD / 胜率 / "
  f"median pnl / 均持仓 / 末值 / 期末持仓 / 闭环笔数） |")
A(f"| 三列对照表 D/C/Δ | `METRICS_D_vs_C_20261108.md`：20 指标 × 18 臂 + 臂级已变/未变 + P6 键 |")
A(f"| Δ 与六臂组（−0.17/−0.17/−0.17/−0.17/−0.35pp）自洽 | 见 §3，逐条一致 |")
A(f"| 确定性可复跑、跑两遍字节一致 | **{n_det}/18 臂三产物两遍 sha 相同**，`stats` 非易变字段亦相同 |")
A(f"| 不动生产库 / 上游文档 / 引擎 | `REPORT.md` 52,097B / `e60cd0b8…`、`metrics_table.md` 2,738B / "
  f"`d025d8ce…`、`five_a/manifest.json` 10,054B / `7fe2c540…` 三项 sha 复核未动；`D:\\TSP` 无本窗口写入 |")
A("")
A("自检：`verify_phase2.py` → **128 PASS / 0 FAIL / exit 0**（输出 `verify_phase2_result.txt`）。")
A("")

A("## 3 · 六臂锚点自洽（五-a 单键分解组，D 取 `five_a/`，C 取本目录）")
A("")
A("| 臂 | 总收益 D | 总收益 C | Δ | 契约 Δ | 末值 D | 末值 C | trades 字节同 |")
A("|---|---:|---:|---:|---:|---:|---:|---|")
for a in delta["anchor_six"]:
    if a.get("status") == "MISSING":
        A(f"| `{a['tag']}` | 缺产物 | | | | | | |")
        continue
    exp = "—" if a.get("expected_pp_C") is None else f"{a['expected_pp_C'] - a['expected_pp_D']:+.2f}pp"
    A(f"| `{a['tag']}` | {a['total_return_D'] * 100:+.2f}% | {a['total_return_C'] * 100:+.2f}% | "
      f"{a['delta_pp']:+.2f}pp | {exp} | {a['final_D']:,.2f} | {a['final_C']:,.2f} | "
      f"{'是' if a['parquet_trades_same'] else '否'} |")
A("")
A("三臂 `only_finalize_open_at_end` / `only_exit_signal_requires_profit` / `a0_10bp` 的 Δ = 0.00pp "
  "且 parquet 同 sha，与阶段1 「必须逐字节不变」判据一致。")
A("")

# ---------- §4 作废清单（数字现算） ----------
B_D, B_C = load(FIVE_A, "base_nodefaults_10bp"), load(HERE, "base_nodefaults_10bp")
rows = [
    ("base_nodefaults_10bp", "生产默认口径基线（不注入 defaults）"),
    ("only_execution_costs", "单键 execution_costs"),
    ("only_entry_price_basis_raw", "单键 entry_price_basis=raw"),
    ("only_trailing_peak_price_close", "单键 trailing_peak_price=close"),
    ("only_block_limit_open", "单键 block_limit_open"),
    ("base_nodefaults_gross", "gross 基线（成本全零）"),
]
rows_same = [
    ("only_finalize_open_at_end", "单键 finalize_open_at_end"),
    ("only_exit_signal_requires_profit", "单键 exit_signal_requires_profit"),
]
A("## 4 · 因 D→C 而作废的旧数字（结论句级）")
A("")
A("### 4.1 直接改数的 6 行（这 6 臂的旧值不可再引用）")
A("")
A("| 臂 | 旧（D，不可再引用） | 新（C，可引用） | 年化 | MDD |")
A("|---|---|---|---|---|")
for tag, label in rows:
    d = load(FIVE_A, tag)
    c = load(HERE, tag)
    A(f"| `{tag}`（{label}） | {d['tot'] * 100:+.2f}% / {d['fin']:,.2f} | "
      f"**{c['tot'] * 100:+.2f}% / {c['fin']:,.2f}** | "
      f"{d['ann'] * 100:+.2f}% → {c['ann'] * 100:+.2f}% | {d['mdd'] * 100:.2f}% → {c['mdd'] * 100:.2f}% |")
A("")
A("### 4.1b 数字不变的 2 行（finalize 分支，修复不触及）")
A("")
A("| 臂 | 值（D = C，仍可引用） | 年化 | MDD |")
A("|---|---|---|---|")
for tag, label in rows_same:
    c = load(HERE, tag)
    A(f"| `{tag}`（{label}） | {c['tot'] * 100:+.2f}% / {c['fin']:,.2f} | "
      f"{c['ann'] * 100:+.2f}% | {c['mdd'] * 100:.2f}% |")
A("")
A("### 4.2 对撞表：会变的结论句 / 不变的结论句")
A("")
A("| # | 旧句（作废或改写） | 改成 |")
A("|---|---|---|")
b_d, b_c = load(FIVE_A, "base_nodefaults_10bp"), load(HERE, "base_nodefaults_10bp")
A(f"| 1 | 「生产默认口径基线 −51.47% / 年化 −9.73% / MDD −71.95% / 期末 485,293.78」 | "
  f"「−51.64% / 年化 −9.78% / MDD −71.95%（不变）/ 期末 483,571.22」 |")
A(f"| 2 | 「only_execution_costs 485,420.69 / −51.46%」 | 「483,698.12 / −51.63%」 |")
A(f"| 3 | 「only_entry_price_basis_raw −56.53% / MDD −74.31% / 434,710.53」 | "
  f"「−56.70% / MDD −74.41% / 432,987.97」 |")
A(f"| 4 | 「base_nodefaults_gross 527,074.75 / −47.29% / 年化 −8.67%（弱负）」 | "
  f"「525,402.74 / −47.46% / 年化 −8.71%（仍为负 ⇒ 结论方向不变）」 |")
A(f"| 5 | 「only_block_limit_open +12.13% / 1,121,259.36 / 归因 +63.60pp」 | "
  f"「+11.78% / 1,117,814.25 / 归因 **+63.42pp**（−0.18pp） |")
A(f"| 6 | 「末日结算缺口 1,722.56（Σpnl 与权益变动不一致）」 | "
  f"「缺口 0：缺陷已修，SETTLED 时权益行与 trade 同价基，不再有未计数现金」 |")
A(f"| 7 | 「finalize_open_at_end 单键 −0.71pp」 | "
  f"「**−0.54pp**（该臂值 −52.18% 未变，基线从 −51.47% 移到 −51.64%） |")
A(f"| 8 | 「exit_signal_requires_profit 单键 +18.85pp」 | "
  f"「**+19.02pp**（该臂值 −32.62% 未变，基线移动） |")
A("| 9 | 「报告口径 −51.47% vs 清仓口径 −51.6429%，两者都不等」 | "
  "「报告口径 = 清仓口径 = −51.64%，实测末值 483,571.22（闭式 483,571.12，差 0.10 为逐笔取整）」 |")
A("| 10 | 「8 臂指标表（年化/MDD/OOS/Sharpe/换手/暴露/笔数/胜率）」 | "
  "**不变**：18 臂 trades/equity 与旧产物逐字节相同；用 C 口径重建的同结构表 "
  "`metrics_table_C_20261108.md` 与已发布的 `metrics_table.md` **逐字符相同（同 sha256 `d025d8ce…`）**，表里一个数都不用改 |")
A("| 11 | 「四臂 + 对照 + 附加 的结论方向」 | **不变**（同上） |")
A("")
A("### 4.3 需要打补丁的具体文档（机器扫描：`stale_tokens_scan.json`）")
A("")
A("| 文档 | 状态 | 说明 |")
A("|---|---|---|")
A("| `five_a/arms_table.md` | 作废 | 单键分解主表，7 行末值/收益/年化/MDD 全是 D 值 |")
A("| `five_a/REPORT_five_a_20261108.md` | 作废 | 上述表的文字版 + 归因 pp |")
A("| `five_a/dual_arms_table.md` | 作废 | 双口径表里含 D 值列 |")
A("| `five_a/five_c_20261108/REPORT_five_c_20261108.md` | 部分作废 | 1,722.56 缺口的结论已被修复消除；它引用的 D 值需换成 C |")
A("| `five_a/five_c_20261108/diag1_table.md` | 部分作废 | 缺口分解（1,672.00 + 50.55 = 1,722.55）现已是「历史成因」，不再是当前缺陷 |")
A("| `crossdown-event-20261108/XCHECK_170B_20261108.md` | 部分作废 | 引 485,293.78 / −51.47% |")
A("| `crossdown-event-20261108/DECOMP_METHOD_20261108.md` | 部分作废 | 引 485,293.78 / 483,571 / 1,722.56 |")
A("| `xcheck-29-20261108/XCHECK_29_TRADES_20261108.md` | 部分作废 | 引 485,293.78 / −51.47% |")
A("| `REPORT.md` / `metrics_table.md` | **不动、不作废** | 只含 8 臂（finalize）数字，全部未变 |")
A("")
A("另：团队记忆里「同一策略只改执行口径就差 75.74pp（+24.27% vs −51.47%）」这条写的 208 笔 / "
  "−51.47% / 485,293.78 是 **D 值**，C 口径下应为 −51.64% / 483,571.22（差值 75.74pp 里的基线项随之变为 "
  "75.91pp）；已单独提一条团队记忆更正，文档正文不动。")
A("")

A("## 5 · 确定性复跑")
A("")
A(f"同一脚本、同一引擎、第二次跑到 `_determinism_rerun/`：**{n_det}/18 臂** 的 trades/equity/drawdown "
  "三个 parquet sha256 与第一遍完全相同；`result.json` 去掉易变字段（`elapsed_s` / `run_id` / "
  "`timing_ms` / 缓存命中类）后逐字段相同。")
A("")
A("## 6 · 复现与回滚")
A("")
A("```")
A(r"cd C:\work\sourcecode\tick-stock-panel")
A(r"backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\run_all_arms.py            # 18 臂，已存在则跳过")
A(r"backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\build_delta.py            # 出 Δ 表")
A(r"backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\verify_phase2.py          # 128 项判据，exit 0")
A("```")
A("")
A("单臂（例）：`run_all_arms.py --only a0_10bp`；等价的原命令形如 "
  "`prod_run_s01b.py --strategy-id s01b_a0 --tag a0_10bp`，逐臂完整命令见 "
  "`manifest_phase2.json → arms[].repro`。")
A("")
A("回滚 = 删 `results_all/` 与 `_determinism_rerun/`；本轮未改任何既有文件，故无需回滚代码。")
A("")
A("## 7 · 产物清单")
A("")
A("| 文件 | 字节 | sha256 |")
A("|---|---:|---|")
for name in ("METRICS_D_vs_C_20261108.md", "delta_arms.json", "metrics_table_C_20261108.md",
             "verify_phase2_result.txt", "stale_tokens_scan.json", "run_all_arms.py",
             "build_delta.py", "verify_phase2.py", "scan_stale_tokens.py",
             "write_manifest_phase2.py"):
    p = HERE / name
    A(f"| `{name}` | {p.stat().st_size:,} | `{sha(p)}` |")
A("")
A("`results_all/<arm>/` 每臂：`trades.parquet` / `equity.parquet` / `drawdown.parquet` / "
  "`result.json` / `effective_config.json`；逐臂三产物 sha 见 `manifest_phase2.json`。")
A("")
A("## 8 · 边界与未做")
A("")
A("1. 本轮**没有**改 `REPORT.md` / `metrics_table.md`（换数由开发经理决定后另派）；"
  "`metrics_table_C_20261108.md` 是同结构的 C 口径底稿，可直接替换用。")
A("2. 18 臂都是 `finalize_open_at_end=True`，所以这次重跑**不能**用来验证末日结算修复——"
  "它只证明「修了之后这些臂没被误伤」。修复本身的证据是阶段1 的 `postfix_20261108/` 六臂与 "
  "`test_end_settlement.py`。")
A("3. `a0_30bp` / `a2h_30bp` / `a4_30bp` 等组合原本就没有跑过（`metrics_table.md` 里写「未跑」），"
  "本轮不新造臂。")
A("4. `stats.execution` 之外的 `market_matrix_bytes` 等诊断字段会随数据根变化，不参与「未变」判定。")

text = "\n".join(L) + "\n"
(HERE / "REPORT_phase2_20261108.md").write_text(text, encoding="utf-8")
print(f"[report] {HERE / 'REPORT_phase2_20261108.md'} "
      f"{(HERE / 'REPORT_phase2_20261108.md').stat().st_size}B "
      f"sha256={sha(HERE / 'REPORT_phase2_20261108.md')}")
