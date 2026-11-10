"""Write SUPPLEMENT_phase1_20261108.md + append a pointer line to REPORT + PROGRESS.log.

Only reads the engine/test artifacts on disk; appends one section pointer to the report
and never edits an existing number.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_any(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp936"):
        try:
            return raw.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return raw.decode("utf-8", "replace")


eng = REPO / "backend/app/backtest/engine.py"
ab_path = HERE / "ab_old_engine_tests.txt"
ab = read_any(ab_path)
ab_tail = [
    line
    for line in ab.splitlines()
    if line.startswith("FAILED") or "failed" in line or line.startswith("exit=")
]
rerun_t = read_any(HERE / "pytest_backtest_after_rerun.txt")
rerun_line = [ln for ln in rerun_t.splitlines() if "passed" in ln][-1].strip()

body = f"""# 阶段1 补充验证（只追加，不改动 REPORT_postfix_20261108.md 的任何原有数字）

生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}
引擎（本文所有实验同一份）：{eng.stat().st_size:,} B / `{sha(eng)}`

## S1 新用例对旧引擎的 A/B（用例是否真的守得住缺陷）

做法：把 `baseline/engine_before.py`（268,800 B / `ecc3d826…`）临时覆盖到
`backend/app/backtest/engine.py`，跑新增的 8 个用例，`finally` 里恢复改后版本并按 sha256 校验恢复成功。
产物：`ab_old_engine_tests.txt`（{ab_path.stat().st_size:,} B / `{sha(ab_path)}`）

结果（旧引擎）：**6 failed, 2 passed** ⇒ 新用例确实钉住缺陷，不是恒真断言。

```
{chr(10).join(ab_tail)}
```

两个在旧引擎下也通过的用例属设计如此，不是漏网：
- `test_t_eos_5_finalize_open_at_end_still_marks`：守的是 finalize 臂**不变**（S-8），旧引擎本来就对；
- `test_carry_out_segment_does_not_settle`：守的是 carry_out **不触发**（S-7），旧引擎同样不触发。

恢复校验：engine.py 回到 `4243fe97723dad20d01bd440783cf71ea6ef05c55a9ffd4652492031e40d8386`（same=True）。

## S2 `a0_10bp` 是**真重跑**，不是拷贝

`postfix_20261108/a0_10bp/` 的 `result.json` 与 `results/a0_10bp/result.json` **不同**
（`e7503e1b…` vs `b9dbf332…`，run_id `cf35b2e6b4` vs `d1487abc07`，elapsed 10.5s vs 44.1s），
而 `trades.parquet`（22,854 B / `639be869…`）与 `equity.parquet`（`1fa5003b…`）与改前**逐字节相同**，
`final_equity` 1,242,725.28、`open_at_end_count` 5、`execution` 13 键全部一致。
⇒ S-8 有实测证据（重跑后产物不变），不是「复制一份说它没变」。

更正 REPORT §1/§2 的一处措辞：`a0_10bp` 三个产物里**只有 trades + equity**——该臂目录历来无
`drawdown.parquet`，verify 的「字节不变 a0_10bp/drawdown.parquet」一项据此记 skip（不是漏检）。

## S3 一次偶发失败的处置记录（不隐瞒）

改后第一次全量复跑（本轮 22:0x）：**1 failed, 745 passed** ——
`test_worker_process.py::test_spawn_mining_writes_four_artifacts_and_returns_compact_summary`，
失败点是子进程退出码 `3221225477`（0xC0000005，原生访问冲突），不是任何断言逻辑。
判为环境偶发，依据三条：
1. 同一引擎字节在 21:43 的全量跑里通过（746 passed）；
2. 该用例单独跑通过（1 passed），该模块单独跑 13 passed；
3. 紧接着的第二次全量复跑 **746 passed, 0 failed**（159.88s）。
与本次改动的关系：改动是纯 Python 记账位置调整，不触碰线程/进程/原生缓冲；崩溃发生在 mining 子进程内。
本条作为「已知偶发」登记；未改该用例、未放宽任何断言。

## S4 本轮复跑的退出码

| 命令 | 结果 | 退出码 |
|---|---|---|
| `pytest backend/tests/backtest -q`（第二次复跑） | 746 passed, 13 warnings in 159.88s | 0 |
| `pytest backend/tests/test_risk_limits_scale.py -q` | 22 passed in 3.07s | 0 |
| `pytest test_end_settlement.py test_limit_down_close_exit.py test_continuous_account.py -q` | 39 passed in 4.51s | 0 |
| `pytest backend/tests/backtest -q`（第一次复跑，偶发） | 1 failed(0xC0000005), 745 passed | 1 |

（第二次复跑的原样末行：`{rerun_line}`）

## S5 审计口径的独立复算（不经 verify 脚本）

直接从 parquet 读末行：六臂 `value == cash`、`positions == 0`、`exposure == 0.0000`，
与契约 C 值差 −0.01/0.00；`trades.parquet` 按 `(entry_date, symbol)` 排序后与 `five_a` 同名臂
**逐单元格相同**（208/208/208/208/208/198 行，22 列）。688143.SH 由 `pending_exit` 的伪盯市变为
`exit_reason="end"` / `open_at_end=False` / `exit_value=21,929.45` / `exit_date=2026-10-30`。

## S6 范围声明

本次改动集只动三处：`backend/app/backtest/engine.py`（+28/−24 行）、新增
`backend/tests/backtest/test_end_settlement.py`、修订 `backend/tests/backtest/test_limit_down_close_exit.py`
中的一个用例。`dsl.py`(36,785 B, 11-07 22:11)、`store.py`(21,104 B, 11-07 23:08)、信号链、其它策略文件、
生产库（`D:\\TSP` 最近写入 15:53，早于本轮 21:25 窗口）均未触碰；未提交、未部署、未重启。
"""

p = HERE / "SUPPLEMENT_phase1_20261108.md"
p.write_text(body, encoding="utf-8", newline="\r\n")
print("wrote", p, p.stat().st_size, "B", sha(p))

rp = HERE / "REPORT_postfix_20261108.md"
t = rp.read_text(encoding="utf-8")
ptr = (
    "\n## 9 补充验证（只追加，不改上文任何数字）\n"
    "见同目录 `SUPPLEMENT_phase1_20261108.md`：新用例对旧引擎 A/B（6/8 失败，证明用例钉住缺陷）、"
    "`a0_10bp` 真重跑证据与一处措辞更正（该臂无 drawdown 产物）、一次子进程 0xC0000005 偶发失败的处置记录、"
    "本轮四次复跑的退出码、不经 verify 脚本的独立复算。\n"
)
if "SUPPLEMENT_phase1_20261108.md" not in t:
    rp.write_text(t.rstrip("\r\n") + "\n" + ptr, encoding="utf-8", newline="\r\n")
print("report now", rp.stat().st_size, "B", sha(rp))

with (HERE / "PROGRESS.log").open("a", encoding="utf-8", newline="\r\n") as f:
    f.write(
        f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} STEP2 supplement written "
        "(A/B old-engine 6/8 fail; a0 rerun verified; 1 flake 0xC0000005 cleared on rerun)\r\n"
    )
print("progress appended")

# addendum manifest covering the files produced after gen_report.py ran
add = {
    "generated_at": f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
    "note": "gen_report.py 之后新增/更新的证据文件；manifest_postfix.json 保持原样（可复现）",
    "files": {},
}
for name in [
    "SUPPLEMENT_phase1_20261108.md",
    "REPORT_postfix_20261108.md",
    "ab_old_engine_tests.txt",
    "pytest_backtest_after_rerun.txt",
    "baseline/engine_after.py",
    "write_supplement.py",
]:
    fp = HERE / name
    if fp.exists():
        add["files"][name] = {"bytes": fp.stat().st_size, "sha256": sha(fp)}
(HERE / "manifest_addendum_phase1.json").write_text(
    json.dumps(add, ensure_ascii=False, indent=1), encoding="utf-8", newline="\r\n"
)
print(json.dumps(add["files"], ensure_ascii=False, indent=1))
