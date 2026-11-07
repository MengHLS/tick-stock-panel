"""把 B2 交付文档从 108 口径/旧证据 sha 同步到 110 口径/新证据 sha (v2: 避开被脱敏的片段)。"""
from __future__ import annotations

import sys
from pathlib import Path

P = Path(r"C:\work\sourcecode\tick-stock-panel\docs\factors\B2_IMPLEMENTATION_20261107.md")
src = P.read_text(encoding="utf-8")
orig = src
EDITS: list[tuple[str, str]] = []


def rep(old: str, new: str) -> None:
    EDITS.append((old, new))


# --- 头部: 字节 + sha ---
rep(
    "56,866 B，sha256 `580824ea9e175d00342f8c08ce7e98cca8fef75be84466c5dbf2b3e646ed4923`",
    "60,242 B，sha256 `e986f22a5a571ba02bca93f8c735bfaf390c3d4dc3062bcfa3b8a58fbc4126d1`",
)
rep(
    "实测「全部判据重跑 → 重建」三轮 sha 完全相同（`580824ea…` ×3），可复算。",
    "实测重建两次 sha 完全相同（`e986f22a…` ×2，连续两次跑 `evidence_build.py`），可复算。",
)
rep(
    "**本版为 B-1 返工版**：旧版 49,293 B / `020ff5c3…` 的 `test_status` 与 `unchanged_on_purpose` "
    "停在测试更新前（20:37 冻结），已作废",
    "**本版为 B-1b 再返工版**：① 49,293 B / `020ff5c3…`（20:37 冻结）的 `test_status` 与 "
    "`unchanged_on_purpose` 停在测试更新前，作废；② 56,866 B / `580824ea…`（21:50）记的是「catalog=108」时的"
    "测试与隔离矩阵，而同批 B4 的日历包（`month_end` / `week_end`）注册即进目录使 catalog 变 110、"
    "测试于 22:01:47 再更新一次，故该版也随之作废（同一缺陷 B-1 的第二次发生，收在本次重生成里）；"
    "③ 现版 = 110 口径，见 §6",
)

# --- 头部: 未做 ---
rep(
    "测试文件于 2026-11-07 20:48:59 由本部门按「catalog 93→108」口径更新过 2 个的**过期计数断言**"
    "（过期断言更新，非回归；`assert ` 条数 45→45 / 20→20，0 删除、无 skip/xfail），详见 §6 与证据 `test_status`。",
    "测试文件本部门**两次**更新过 2 个的**过期计数断言**：20:48:59 按「catalog 93→108」"
    "（B0 14 + B2 `in_universe`）、22:01:47 按「catalog 108→110」（B4 的 `month_end`/`week_end`）；"
    "两次都只动计数数字与 `GOLDEN_COLUMNS` 追加，`assert ` 条数 45→45 / 20→20，0 删除、无 `skip`/`xfail`/`-k`，"
    "仍用确定值 110（未改成 `>=93` 这类无判别力写法），详见 §6 与证据 `test_status`。",
)

# --- §6 表头 ---
rep(
    "**下表是 21:38 用「已按 108 口径更新的现盘测试」重测的结果**（`logs/isolation_recheck_108.json`，"
    "`measured_at 2026-11-07T21:38:26+08:00`）：",
    "**下表是 22:04 用「已按 110 口径更新的现盘测试」重测的四态结果**（`logs/isolation_recheck_110.json`，"
    "`measured_at 2026-11-07T22:04:54+08:00`，试验后四态均已还原、`restored=true`）：",
)

# --- §6 表格 ---
rep(
    "| `none`（无 B0、无 B2） | 93 | 14 | **6 failed / 68 passed** | **PASSED**（30 passed） |\n"
    "| `b0_only`（仅 B0） | 107 | 22 | **6 failed / 68 passed**（**同一 6 条**） | "
    "FAILED — `unsupported matrix feature: prior_amount_20` |\n"
    "| `all_on`（B0+B2，现状） | 108 | 23 | **74 passed / 0 failed** | "
    "FAILED — `in_universe 缺少必需列: ['raw_close']` |",
    "| `none`（无任何 pack） | 93 | 14 | **6 failed / 68 passed** | **PASSED**（30 passed） |\n"
    "| `calendar_only`（仅 B4 日历包） | 95 | 16 | **6 failed / 68 passed**（**同一 6 条**） | — |\n"
    "| `b0_only`（仅 B0） | 109 | 24 | **6 failed / 68 passed**（**同一 6 条**） | "
    "FAILED — `unsupported matrix feature: prior_amount_20` |\n"
    "| `all_on`（B0+B2+B4，现状） | 110 | 25 | **74 passed / 0 failed** | "
    "FAILED — `in_universe 缺少必需列: ['raw_close']` |",
)

# --- §6 口径提醒 ---
rep(
    "测试于 20:48:59 按 108 更新后方向反过来：**押 108 的测试只在 `all_on`(108) 绿**，"
    "`none`(93) 与 `b0_only`(107) 都红，且红的永远是同一 6 条（test id 逐字相同）。别把这张表当回归看。",
    "测试按新事实更新断言后方向反过来：**押 110 的测试只在 `all_on`(110) 绿**，"
    "`none`(93) / `calendar_only`(95) / `b0_only`(109) 三态都红，且红的永远是同一 6 条"
    "（test id 逐字相同，见证据 `isolation.same_red_set_in_three_red_states`）。"
    "别把这张表当回归看 —— 它是「断言里的数与目录条数是否相符」的指示器，不是代码质量指示器。",
)

# --- §6 结论 1 ---
rep(
    "也没有任何一条失败来自 B2 的实现代码：`none`(93) 与 `b0_only`(107) 各 6 红，`all_on`(108) 0 红。",
    "也没有任何一条失败来自 B2 的实现代码：`none`(93) / `calendar_only`(95) / `b0_only`(109) 各 6 红"
    "（同一 6 条），`all_on`(110) 0 红。",
)

# --- §6 结论 2 ---
rep(
    "- 因此**两个 pack 目录必须进版本库**：不进库的干净检出 = 93，这 6 条会一直红。本批据此把它们 `git add`"
    "（只 add，不 commit、不 push），`git status --porcelain` 前后对比见 §8。",
    "- 因此**pack 目录必须进版本库**：不进库的干净检出 = 93，而断言是 110，这 6 条会一直红。本批据此把三个 "
    "pack 目录（`research_factor_pack/`、`research_universe_pack/`、`research_calendar_pack/`，共 9 个文件）"
    "`git add`（只 add，不 commit、不 push；HEAD 仍 `65c6e42f`），`git status --porcelain` 前后对比见 §8。"
    "第 3 个目录是第 3 件 B4 的产物：只 add 前两个则干净检出 = 108，而断言 110，同样 6 红。",
)

# --- §6 证据清单 ---
rep(
    "- 归因证据：`logs/isolation_recheck_108.json`（三态 + 失败 test id 逐字 + 目录探针）、"
    "`logs/catalog_support_{none,b0_only,all_on}.json`、`logs/pytest_factor_suite_{all_on,b0_only}.log`。",
    "- 归因证据：`logs/isolation_recheck_110.json`（四态 + 失败 test id 逐字 + 目录探针）、"
    "`logs/catalog_support_{none,calendar_only,b0_only,all_on}_110.json`、"
    "`logs/pytest_after_110_run.json`（现盘 74 passed 的 argv / 起止时刻 / 完整 stdout）。",
)

# --- §6 测试改动 ---
rep(
    "- 测试**改过**（20:48:59，按开发经理裁定「不重定基线、按新事实更新过期断言值」）：只动计数数字与 `GOLDEN_COLUMNS` 追加；"
    "`assert ` 条数 `test_factor_registry.py` 45→45、`test_factor_store.py` 20→20，0 删除、无 `skip`/`xfail`/`-k`、"
    "未把精确计数改成 `>=93`。逐文件字节/行/sha 见证据 `test_status.test_files_changed`。",
    "- 测试**改过两次**（20:48:59 → 108；22:01:47 → 110，均按开发经理裁定「不重定基线、按新事实更新过期断言值」）："
    "只动计数数字与 `GOLDEN_COLUMNS` 追加；`assert ` 条数 `test_factor_registry.py` 45→45、"
    "`test_factor_store.py` 20→20，0 删除、无 `skip`/`xfail`/`-k`、未把精确计数改成 `>=93`、仍用确定值 110。"
    "现盘 `test_factor_registry.py` 28,187 B / 403 行 / `81e4b1f9…` / `+25−6`；"
    "`test_factor_store.py` 6,793 B / 171 行 / `79de1eca…` / `+3−3`（`git diff --numstat` vs HEAD）。"
    "明细见证据 `test_status.test_files_changed`。",
)

# --- 决策表 D-B2-2 ---
rep(
    "故 107→108 | 若要它不进目录，需改扩展点语义（会影响 B0） |",
    "故 107→108；B4 日历包落地后 110 | 若要它不进目录，需改扩展点语义（会影响 B0 与 B4 的日历列） |",
)

# --- §10 ---
rep(
    "3. `E4`（`month_end` / `rebalance` 轴）不在本批范围。",
    "3. `E4`（`month_end` / `week_end` 轴）**不在 B2 范围**：已由同批第 3 件 B4 另行实现并交付，"
    "见 `docs/factors/E4_CALENDAR_20261107.md`（只走 frame 路径；矩阵路径同本批归 B0b）。",
)
rep(
    "5. 6 条「目录=93」测试 + 矩阵目录测试仍红——**既有**（见 §6），需裁定：重定基线，或由 B0b 补矩阵能力。",
    "5. 6 条计数断言已两次按新事实更新（93→108→110），现盘 74 passed / 0 failed；矩阵目录测试仍红——**既有**"
    "（见 §6），需裁定：由 B0b 补矩阵能力，或由架构出排除表。",
)

print(f"prepared {len(EDITS)} edits")
bad = [(o[:80], src.count(o)) for o, _ in EDITS if src.count(o) != 1]
if bad:
    for o, n in bad:
        print(f"MISS({n}): {o!r}")
    sys.exit("ABORT: some anchors did not match exactly once")
for old, new in EDITS:
    src = src.replace(old, new)
P.write_text(src, encoding="utf-8")
print("patched", P, len(orig), "->", len(src), "chars;", src.count("\n") + 1, "lines")
