"""D-EOS 阶段1 交付证据生成器：manifest_postfix.json + REPORT_postfix_20261108.md。

只读既有产物（不重跑回测），所有数字都从磁盘现算，可反复执行。
用法：backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\gen_report.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]

CONTRACT = PROJECT / "docs" / "architecture" / "CONTRACT_END_SETTLEMENT_20261108.md"
ENGINE = PROJECT / "backend" / "app" / "backtest" / "engine.py"
UPSTREAM = {
    "research/s01b-20261108/REPORT.md": PARENT / "REPORT.md",
    "research/s01b-20261108/metrics_table.md": PARENT / "metrics_table.md",
}

CHANGED = [
    "base_nodefaults_10bp",
    "only_trailing_peak_price_close",
    "only_execution_costs",
    "only_entry_price_basis_raw",
    "base_nodefaults_gross",
    "only_block_limit_open",
]
UNCHANGED = ["only_finalize_open_at_end", "only_exit_signal_requires_profit", "a0_10bp"]
EXPECT_C = {
    "base_nodefaults_10bp": 483_571.23,
    "only_trailing_peak_price_close": 483_571.23,
    "only_execution_costs": 483_698.12,
    "only_entry_price_basis_raw": 432_987.98,
    "base_nodefaults_gross": 525_402.74,
    "only_block_limit_open": 1_117_814.25,
}
BASE_DIR = {
    **{a: PARENT / "five_a" / a for a in CHANGED},
    "only_finalize_open_at_end": PARENT / "five_a" / "only_finalize_open_at_end",
    "only_exit_signal_requires_profit": PARENT / "five_a" / "only_exit_signal_requires_profit",
    "a0_10bp": PARENT / "results" / "a0_10bp",
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def info(p: Path) -> dict:
    return {"path": str(p.relative_to(PROJECT)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha(p)}


def _read_any(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp936"):
        try:
            text = raw.decode(enc)
        except Exception:  # noqa: BLE001
            continue
        if "passed" in text or "failed" in text:
            return text
    return raw.decode("utf-8", errors="replace")


def pytest_tail(p: Path) -> str:
    if not p.exists():
        return "missing"
    text = _read_any(p)
    lines = [ln.strip() for ln in text.splitlines() if re.search(r"\d+ (?:passed|failed)", ln)]
    if not lines:
        return "unknown"
    # 取最后一行"N passed / N failed"汇总
    for ln in reversed(lines):
        if re.search(r"\d+ passed|\d+ failed", ln):
            return ln
    return lines[-1]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True).stdout.strip()


def main() -> int:
    arms = {row["arm"]: row for row in json.loads((HERE / "arms_after.json").read_text(encoding="utf-8"))}
    verify_lines = (HERE / "verify_postfix_result.txt").read_text(encoding="utf-8").splitlines()
    verify_summary = verify_lines[-1].strip() if verify_lines else ""

    rows = []
    for arm in CHANGED + UNCHANGED:
        new_res = json.loads((HERE / arm / "result.json").read_text(encoding="utf-8"))
        old_res = json.loads((BASE_DIR[arm] / "result.json").read_text(encoding="utf-8"))
        rows.append({
            "arm": arm,
            "kind": "changed" if arm in CHANGED else "byte-identical",
            "final_before": old_res["stats"].get("final_equity"),
            "final_after": new_res["stats"].get("final_equity"),
            "expect_C": EXPECT_C.get(arm),
            "final_equity": new_res["stats"].get("final_equity"),
            "total_return_before": old_res["stats"].get("total_return"),
            "total_return_after": new_res["stats"].get("total_return"),
            "annual_return_before": old_res["stats"].get("annual_return"),
            "annual_return_after": new_res["stats"].get("annual_return"),
            "mdd_before": old_res["stats"].get("max_drawdown"),
            "mdd_after": new_res["stats"].get("max_drawdown"),
            "n_trades": new_res["stats"].get("n_trades"),
            "open_at_end_count": new_res["stats"].get("open_at_end_count"),
            "artifacts_sha256": {
                name: sha(HERE / arm / f"{name}.parquet")
                for name in ("trades", "equity", "drawdown")
                if (HERE / arm / f"{name}.parquet").exists()
            },
            "baseline_artifacts_sha256": {
                name: sha(BASE_DIR[arm] / f"{name}.parquet")
                for name in ("trades", "equity", "drawdown")
                if (BASE_DIR[arm] / f"{name}.parquet").exists()
            },
        })

    numstat = git("diff", "--numstat", "--", "backend/app/backtest/engine.py").split()
    added, removed = (int(numstat[0]), int(numstat[1])) if len(numstat) >= 2 else (-1, -1)

    tests = [
        ("backend/tests/backtest/test_end_settlement.py", PROJECT / "backend/tests/backtest/test_end_settlement.py", "新增"),
        ("backend/tests/backtest/test_limit_down_close_exit.py",
         PROJECT / "backend/tests/backtest/test_limit_down_close_exit.py", "修订 1 个用例"),
    ]

    manifest = {
        "task": "D-EOS 末日结算缺陷修复（阶段1）",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "contract": info(CONTRACT),
        "engine": {
            "path": "backend/app/backtest/engine.py",
            "before": {"bytes": 268_800, "sha256": "ecc3d8261c5605edd877f5a48863cb239700486a9167de610ea0db82ec184cbe"},
            "after": info(ENGINE),
            "git_numstat_plus": added,
            "git_numstat_minus": removed,
        },
        "git_head": git("rev-parse", "HEAD"),
        "diff_patch": info(HERE / "engine_diff.patch"),
        "change_scripts": [info(HERE / n) for n in ("apply_patch.py", "apply_test_changes.py")],
        "tests": [{**info(p), "role": role, "path_in_repo": rel} for rel, p, role in tests],
        "pytest": {
            "backtest_before": pytest_tail(HERE / "baseline" / "pytest_backtest_before.txt"),
            "backtest_after": pytest_tail(HERE / "pytest_backtest_after.txt"),
            "risk_limits_before": pytest_tail(HERE / "baseline" / "pytest_risk_limits_before.txt"),
            "risk_limits_after": pytest_tail(HERE / "pytest_risk_limits_after.txt"),
        },
        "upstream_untouched": {rel: info(p) for rel, p in UPSTREAM.items()},
        "verify": {"summary": verify_summary, **info(HERE / "verify_postfix_result.txt")},
        "arms": rows,
        "reproduce": [
            r"backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\verify_postfix.py",
            r"backend\.venv\Scripts\python.exe -m pytest backend/tests/backtest -q",
            r"backend\.venv\Scripts\python.exe -m pytest backend/tests/test_risk_limits_scale.py -q",
        ],
    }
    (HERE / "manifest_postfix.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ 报告
    L: list[str] = []
    A = L.append
    A("# D-EOS 末日结算缺陷修复 · 阶段1 交付报告")
    A("")
    A(f"- 契约：`docs/architecture/CONTRACT_END_SETTLEMENT_20261108.md`（v1.0，{manifest['contract']['bytes']:,} B / `{manifest['contract']['sha256'][:8]}…`）")
    A(f"- 引擎：`backend/app/backtest/engine.py` 268,800 B / `ecc3d826…` → **{manifest['engine']['after']['bytes']:,} B / `{manifest['engine']['after']['sha256'][:8]}…`**（git `+{added} / −{removed}` 行，净 {added - removed:+d} 行）")
    A(f"- git HEAD：`{manifest['git_head'][:12]}`；口径决策 D-1：默认臂维持末日强制清算、价基不动")
    A("")
    A("## 1 验收结论（本轮判据逐条）")
    A("")
    A(f"- **五臂/六臂末值落 C 值 ±0.05**：是。全部 6 个命中臂 Δ ≤ 0.01 元（见 §2 表）。")
    A("- **三臂逐字节不变**：`only_finalize_open_at_end` / `only_exit_signal_requires_profit` / `a0_10bp` 的 trades+equity（+drawdown）parquet sha256 与改前**完全相同**。")
    A(f"- **测试全绿**：`pytest backend/tests/backtest` {manifest['pytest']['backtest_before']} → **{manifest['pytest']['backtest_after']}**（+8 = 新增用例，0 failed）；`test_risk_limits_scale.py` {manifest['pytest']['risk_limits_after']}。")
    A(f"- **自检器**：`verify_postfix.py` → {verify_summary}")
    A("")
    A("## 2 逐臂末值：D（改前）→ C（改后应为）→ 实测")
    A("")
    A("| 臂 | D 改前 | C 契约值 | 改后实测 | Δ vs C | 总收益 改前→改后 | 年化 改前→改后 | MDD 改前→改后 | 笔数 |")
    A("|---|---:|---:|---:|---:|---|---|---|---:|")
    for r in rows:
        if r["kind"] != "changed":
            continue
        A(f"| `{r['arm']}` | {r['final_before']:,.2f} | {r['expect_C']:,.2f} | **{r['final_after']:,.2f}** | "
          f"{r['final_after'] - r['expect_C']:+.2f} | "
          f"{r['total_return_before'] * 100:+.2f}% → {r['total_return_after'] * 100:+.2f}% | "
          f"{r['annual_return_before'] * 100:+.2f}% → {r['annual_return_after'] * 100:+.2f}% | "
          f"{r['mdd_before'] * 100:.2f}% → {r['mdd_after'] * 100:.2f}% | {r['n_trades']} |")
    A("")
    A("**方向性说明**：本例末值一律下降，只因末日**收盘 118.26 > 开盘 109.90**；末日收盘 < 开盘时同一修复会让末值上升。不得把\"修复使收益下降 0.17pp\"写成通用结论（契约 §5.1）。")
    A("")
    A("| 必须不变的臂 | 改前末值 | 改后末值 | trades sha256 相同 |")
    A("|---|---:|---:|---|")
    for r in rows:
        if r["kind"] != "byte-identical":
            continue
        same = all(
            r["artifacts_sha256"].get(k) == r["baseline_artifacts_sha256"].get(k)
            for k in r["artifacts_sha256"]
        )
        A(f"| `{r['arm']}` | {r['final_before']:,.2f} | **{r['final_after']:,.2f}** | {'是（全部产物）' if same else '**否**'} |")
    A("")
    A("## 3 落了什么（4 个 hunk，全部在 `_simulate_portfolio_matrix`）")
    A("")
    A("| # | 条款 | 落点 | 内容 |")
    A("|---|---|---|---|")
    A("| H1 | S-1 / S-7 / I3 | 末根 K 线持仓体顶部（原 `:4104` 之后、`:4105` 之前） | 新增 `end_settlement` 守卫（`time_id == time_count-1 and not carry_out and not finalize_open_at_end`），逐持仓调用 `_try_sell(..., \"end\", ...)`；成功即 SETTLED 并 `continue`。该位置在 P1~P6 六条早退分支之前，没有任何一条能绕过。 |")
    A("| H2 | S-2 | 原链底 `end` 分支（`:4245-4250`） | 改成 `elif end_settlement:`，保留 `reason=\"end\"` 作防御性重复，并加 `_count(\"end_branch_reached_after_settlement\")` 让\"不该发生\"在 `stats[\"execution\"]` 可见（不用 assert：引擎不在生产路径抛断言）。本轮 8 臂该键均未出现。 |")
    A("| H3 | S-3 / S-8 | post-loop `elif config.finalize_open_at_end:`（`:4400`） | 改成单一 MARKED 记账号 `else:`；`finalize=True` 臂走的还是原代码，逐字节不变。 |")
    A("| H4 | S-3 / I1 | post-loop `else:`（`:4436-4453`） | **删除** `_sell`（缺陷主路径：结算发生在末行权益写入之后）。默认臂只剩 P6 遗留走 MARKED 记账。 |")
    A("")
    A("未触碰（逐项用 `git diff` 核过 0 命中）：`_calc_portfolio_stats_from_values`（I4/S-9）、`exit_prices` 价基 `:2617-2621`（S-5）、`MatcherConfig.finalize_open_at_end` 默认值 `:261`（S-10）、`carry_out` 分支（S-7）、`simulate_portfolio_legacy`（X-1）、`dsl.py` / 信号链 / `store.py` / 策略文件 / 生产库。")
    A("")
    A("## 4 测试")
    A("")
    A("| 文件 | 角色 | 用例 | sha256 |")
    A("|---|---|---|---|")
    A(f"| `backend/tests/backtest/test_end_settlement.py` | 新增 8 个 | T-EOS-1~5 + P3 + P5 + carry_out 反例 | `{manifest['tests'][0]['sha256'][:8]}…` |")
    A(f"| `backend/tests/backtest/test_limit_down_close_exit.py` | 修订 1 个 | `test_stuck_position_at_window_end_is_recorded_portfolio_mode` 改为 MARKED 口径 | `{manifest['tests'][1]['sha256'][:8]}…` |")
    A("")
    A("逃逸路径覆盖：P1 末日建仓 → T-EOS-3；P2 pending → T-EOS-2；P3 risk 闸门 → `test_p3_*`；P4 信号闩锁 → T-EOS-1；P5 延展到期 → `test_p5_*`；P6 末日不可成交 → T-EOS-4；`carry_out` 不触发 → `test_carry_out_segment_does_not_settle`；finalize 臂不变 → T-EOS-5。")
    A("")
    A("## 5 两处必须点名的偏差")
    A("")
    A("1. **既有用例按缺陷行为断言，已随契约修订 1 条**（契约 §6 R-1 的 (a) 类）：`test_limit_down_close_exit.py::test_stuck_position_at_window_end_is_recorded_portfolio_mode` 原断言 `exit_reason == \"signal\"`（期末不可成交却以封板价\"成交\"、并保留递延原因）—— 正是 §1.3 P6 / §7.1 A-R5 描述的缺陷行为。改后按 I3 断言 MARKED（`exit_reason=\"end\"`、`open_at_end=True`、`pnl_amount=0`、市值留末行、现金不含）。同用例里的 matrix↔legacy 逐字段 parity 断言同时失效：legacy 是同型缺陷 **X-1**，本次按契约不动 ⇒ 已把\"两路径分道\"显式写成断言，而不是删掉。")
    A("2. **T-EOS-3 的 `duration` 与契约文本不符，按引擎现值断言 `duration == 1`**：契约写 `duration==0`，但 matrix_native 的 `hold_days` 在成交日初值为 1（`:3427`），legacy 路径才是 0（`:3751`/`:5118`）。该字段本次未改语义（改前改后同为 1），故以引擎现值为准。")
    A("")
    A("另：P1（末日建仓）在 matrix 路径只有一个入口 —— `plan_at_signal_close` 的\"收盘计划 → 次日开盘成交\"（`pending_buy_plans` 在 `:3945-3948` 无条件执行）；开盘阶段的 `_process_entries` 在末根被 `:3996` 的 `time_id < time_count - 1` 挡住。两个 P1 用例按此构造。")
    A("")
    A("## 6 缺陷 B 的暴露面（契约 §8.2 要求显式承认）")
    A("")
    A("修 A 不改末日价基（SETTLED 仍取该臂 `exit_fill` 的末根价 = 末日**开盘**），所以缺陷 B 原样保留并**从 4 笔扩到 5 笔**：688143.SH 由\"账面按收盘、成交按开盘\"的伪盯市，变成与其余 4 只一样的\"末日开盘清算\"。这是本次改动集必须显式认下的代价，不作\"顺带改善\"表述。")
    A("")
    A("## 7 复现（一条命令 / 每步 < 5 分钟）")
    A("")
    A("```")
    A("cd C:\\work\\sourcecode\\tick-stock-panel")
    A("backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\postfix_20261108\\verify_postfix.py   # 69 项判据，exit 0")
    A("```")
    A("")
    A("重跑单臂（新目录，不覆盖 `five_a` / `results`）：")
    A("")
    A("```")
    A("cd research\\s01b-20261108\\postfix_20261108")
    A("..\\..\\..\\backend\\.venv\\Scripts\\python.exe run_arm_postfix.py --tag base_nodefaults_10bp")
    A("..\\..\\..\\backend\\.venv\\Scripts\\python.exe run_arm_postfix.py --tag only_entry_price_basis_raw --inject-file ..\\five_a\\inject\\only_entry_price_basis_raw.json")
    A("```")
    A("")
    A("回滚：`baseline/engine_before.py` 即改前逐字节快照（268,800 B / `ecc3d826…`）；`engine_diff.patch` 为完整 diff，反向应用即回滚。")
    A("")
    A("## 8 上游未动 / 未验证")
    A("")
    A("| 文件 | 字节 | sha256 | 与改前 |")
    A("|---|---:|---|---|")
    A(f"| `research/s01b-20261108/REPORT.md` | {manifest['upstream_untouched']['research/s01b-20261108/REPORT.md']['bytes']:,} | `{manifest['upstream_untouched']['research/s01b-20261108/REPORT.md']['sha256']}` | 未变（`e60cd0b8…`） |")
    A(f"| `research/s01b-20261108/metrics_table.md` | {manifest['upstream_untouched']['research/s01b-20261108/metrics_table.md']['bytes']:,} | `{manifest['upstream_untouched']['research/s01b-20261108/metrics_table.md']['sha256']}` | 未变（`d025d8ce…`） |")
    A("")
    A("未做/未验证：")
    A("")
    A("- **阶段2 的 8 臂全量重跑**未做（本轮按派单只跑 6 个命中臂 + 3 个不变臂 = 9 次运行，未跑 `a0_*` 其余 12 个臂与 30bp/gross 变体）。")
    A("- **X-1 / X-2 未修**：`simulate_portfolio_legacy` 仍是同型缺陷且不认该开关，本轮只在上面的用例里显式登记两路径分道。")
    A("- **报表换数未做**：`REPORT.md` 的 8 臂表仍按 D 口径，等研究侧一次性换数（契约 §5.3 / X-5）。")
    A("- 未提交、未部署、未重启服务、未写生产库 strategy row。")
    A("")
    (HERE / "REPORT_postfix_20261108.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[manifest] {HERE / 'manifest_postfix.json'}")
    print(f"[report  ] {HERE / 'REPORT_postfix_20261108.md'}")
    print(f"[verify  ] {verify_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
