"""第二段: 把 test_status / rework / not_done / decisions_needed 切到 110 口径。

同样每处断言命中 1 次。
"""
from __future__ import annotations

import sys
from pathlib import Path

P = Path(__file__).with_name("evidence_build.py")
src = P.read_text(encoding="utf-8")
orig = src

EDITS: list[tuple[str, str]] = []


def rep(old: str, new: str) -> None:
    EDITS.append((old, new))


rep(
    '''    "rework": {
        "defect": "B-1 (独立审核 B2_ACCEPTANCE_20261107.md: 实现侧 6/6 PASS, 证据包 FAIL)",
        "why": "旧包的 test_status 仍记 6 failed / 68 passed, 且 unchanged_on_purpose 第 4 条写「本批未改任何测试」; "
               "而 20:48:59 两个测试文件已按 108 口径更新, 现盘实测 74 passed / 0 failed, 与旧包不符。",
        "fixes": [
            "test_status 换成现盘实测: 原命令 + ran_at (起止时刻) + pytest/python 版本 + 74 passed / 0 failed, 完整 stdout 落 artifact",
            "unchanged_on_purpose 第 4 条改写为「20:48:59 本部门按 108 口径更新过期断言 (基线更新非回归)」, 附两文件字节/行/sha 与 assert 45→45 / 20→20",
            "isolation 三态重测 (108 口径测试): 93/107/108 + 同一 6 条红集合 (已重跑并落 isolation_recheck_108.json)",
            "49 条断言逐条重跑后重新汇总; 生成器仍无 generated_at、dump 仍排序固定",
        ],
    },''',
    '''    "rework": {
        "defect": "B-1 (独立审核 B2_ACCEPTANCE_20261107.md: 实现侧 6/6 PASS, 证据包 FAIL) + B-1b (本轮自查)",
        "why": "旧包的 test_status 仍记 6 failed / 68 passed, 且 unchanged_on_purpose 第 4 条写「本批未改任何测试」; "
               "而 20:48:59 两个测试文件已按 108 口径更新, 现盘实测 74 passed / 0 failed, 与旧包不符。"
               "B-1b: 21:50 重生成的包里 test_status 记的是 108 口径测试 (de3ce0ad/07cf3dc2), "
               "但同批第 3 件 B4 的日历包 (month_end/week_end) 注册即进目录, 22:01:47 测试再按 110 更新, "
               "若不重生成, 证据与现盘又会差一步 —— 同一缺陷的第二次发生, 故一并收在同一次重生成里。",
        "fixes": [
            "test_status 换成现盘实测: 原命令 + ran_at (起止时刻) + pytest/python 版本 + 74 passed / 0 failed, 完整 stdout 落 artifact",
            "unchanged_on_purpose 第 4 条如实写两次过期断言更新 (93→108 于 20:48:59; 108→110 于 22:01:47), 附现盘两文件字节/行/sha 与 assert 45→45 / 20→20",
            "isolation 四态重测 (110 口径测试): 93 / 95 / 109 / 110 + 三红态同一 6 条红集合 + 全开 74P/0F (落 isolation_recheck_110.json)",
            "49 条断言逐条重跑后重新汇总 (E3 / E3-A4 / E2 fixtures / E2 full / E1 / W / wiring / refs / canonical / calibers / xs_a3 全部重跑, 日志已刷新); 生成器仍无 generated_at、dump 仍排序固定",
        ],
    },''',
)

rep(
    '''    "test_status": {
        "command": pt.get("command"),
        "ran_at": {"started_at": pt.get("started_at"), "finished_at": pt.get("finished_at")},
        "tooling": {"pytest": pt.get("pytest_version"), "python": pt.get("python_version")},
        "result": "74 passed / 0 failed",
        "returncode": pt.get("returncode"),
        "summary_line": (pt.get("stdout_tail", "").strip().splitlines() or [""])[-1],
        "artifact": art("pytest_after_108_run.json"),
        "note": "现盘实测: 上方 command 原样执行一次, 起止时刻与完整 stdout 均落在 artifact。"
                "同一命令改前为 6 failed / 68 passed (用例总数同为 74), 差异全部来自 test_files_changed "
                "里那两个文件的计数断言更新, 不是实现改动。",
        "test_files_changed": [
            {"path": "backend/tests/test_factor_registry.py",
             "change": "+22/−6 (git diff --numstat), 只动计数断言与 GOLDEN_COLUMNS 追加",
             "why": "catalog 93→108 的既定基线更新: GOLDEN_COLUMNS 追加 15 条 (B0 14 + B2 in_universe), "
                    "计数断言 93→108 四处、70→85 两处",
             "mtime": "2026-11-07 20:48:59",
             "assert_statements": {"before": 45, "after": 45},
             **reg_f},
            {"path": "backend/tests/test_factor_store.py",
             "change": "+3/−3 (git diff --numstat), 只动断言数字与同步注释",
             "why": "builtin_count 93→108 与两处 == 93 → == 108",
             "mtime": "2026-11-07 20:48:59",
             "assert_statements": {"before": 20, "after": 20},
             **sto_f},
        ],
        "assertion_coverage_preserved": "未删任何断言、未加 skip/xfail、未用 -k 排除、未把精确计数改成 >=93 "
                                        "这类无判别力写法; `assert ` 语句数 45→45 / 20→20 (0 删除)。",
        "classification": "改前那 6 条红的根因已核实: 全部是「目录条数硬编码 93」类断言 "
                          "(test_factor_registry 5 条 + test_factor_store 1 条), 无一条属于其他根因。"
                          "按开发经理裁定「不重定基线、按新事实更新过期断言值」已改为 108, 现盘全绿。",''',
    '''    "test_status": {
        "command": pt.get("command"),
        "ran_at": {"started_at": pt.get("started_at"), "finished_at": pt.get("finished_at")},
        "tooling": {"pytest": pt.get("pytest_version"), "python": pt.get("python_version")},
        "result": "74 passed / 0 failed",
        "returncode": pt.get("returncode"),
        "summary_line": (pt.get("stdout_tail", "").strip().splitlines() or [""])[-1],
        "artifact": art(PT_ART),
        "note": "现盘实测: 上方 command 原样执行一次 (本包同时把这条命令写进 artifact 的 argv), "
                "起止时刻与完整 stdout 均落在 artifact。同一命令改前 (93 口径) 为 6 failed / 68 passed "
                "(用例总数同为 74), 差异全部来自 test_files_changed 里那两个文件的计数断言更新, 不是实现改动。"
                "另: 2026-11-07 22:06 起 74 passed 状态被独立复算过一次 (见 isolation.all_on 态), 两次一致。",
        "test_files_changed": [
            {"path": "backend/tests/test_factor_registry.py",
             "change": "+25/−6 (git diff --numstat vs HEAD 65c6e42f), 只动计数断言与 GOLDEN_COLUMNS 追加",
             "why": "两步基线更新合并在同一个工作区改动里: ① GOLDEN_COLUMNS 追加 15 条 (B0 14 + B2 in_universe), "
                    "计数断言 93→108 四处、70→85 两处 (2026-11-07 20:48:59); "
                    "② B4 日历包的 month_end/week_end 注册即进目录, 计数断言 108→110 三处 (22:01:47)。"
                    "两步都只改数字与追加 golden 行, 未改任何断言逻辑。",
             "mtime": "2026-11-07 22:01:47",
             "assert_statements": {"before": 45, "after": 45},
             **reg_f},
            {"path": "backend/tests/test_factor_store.py",
             "change": "+3/−3 (git diff --numstat vs HEAD 65c6e42f), 只动断言数字与同步注释",
             "why": "builtin_count 与两处 == 93 先改 108 (20:48:59), 再随 B4 改 110 (22:01:47); 未改断言逻辑。",
             "mtime": "2026-11-07 22:01:47",
             "assert_statements": {"before": 20, "after": 20},
             **sto_f},
        ],
        "assertion_coverage_preserved": "未删任何断言、未加 skip/xfail、未用 -k 排除、未把精确计数改成 >=93 "
                                        "这类无判别力写法 (仍用确定值 110); `assert ` 语句数 45→45 / 20→20 (0 删除)。",
        "classification": "改前那 6 条红的根因已核实: 全部是「目录条数硬编码 93」类断言 "
                          "(test_factor_registry 5 条 + test_factor_store 1 条), 无一条属于其他根因。"
                          "按开发经理裁定「不重定基线、按新事实更新过期断言值」先改为 108; "
                          "同批 B4 日历包落地后目录为 110, 再按同一裁定改为 110。现盘全绿。",''',
)

rep(
    '''        "isolation": {
            "why": "把 pack 目录 mv 出 app/custom 三态重跑同一组 5 文件 (108 口径测试现盘版本) + 目录探针, "
                   "证明「红/绿的唯一决定因素是目录条数」, 且三态都能完整还原。",
            "measured_at": iso.get("measured_at"),
            "tests_version": iso.get("tests_version"),
            "artifact": art("isolation_recheck_108.json"),
            "states": ISO_STATES,
            "same_red_set_in_none_and_b0_only": SAME_RED_SET,
            "restored_after_experiment": iso.get("restored"),
            "matrix_catalog_test_per_state": {
                "source": "19:47–19:54 实测, 与本批测试文件更新无关 (tests/backtest/test_matrix_strategy.py 未改动), "
                          "目录内容 93/107/108 未变, 故仍成立",
                "none": "PASSED (30 passed)",
                "b0_only": "FAILED — ValueError: unsupported matrix feature: prior_amount_20",
                "all_on": "FAILED — ValueError: in_universe 缺少必需列: ['raw_close']",
            },
            "conclusion": "none(93) 与 b0_only(107) 两态失败的永远是同一 6 条计数断言 (test id 逐字相同), "
                          "all_on(108) 为 74 passed / 0 failed => 红/绿只由目录条数决定, 与哪个 pack 在场无关, "
                          "也没有任何一条失败来自 B2 的实现代码。推论: 两个 pack 目录若不进版本库, 干净检出=93, "
                          "这 6 条会一直红 => 故本批将其 git add (只 add, 不 commit)。",
        },''',
    '''        "isolation": {
            "why": "把 pack 目录 mv 出 app/custom 四态 (none / calendar_only / b0_only / all_on) 重跑同一组 5 文件 "
                   "(110 口径测试现盘版本) + 目录探针, 证明「红/绿的唯一决定因素是目录条数」, 且四态都能完整还原。",
            "measured_at": iso.get("measured_at"),
            "tests_version": iso.get("tests_version"),
            "artifact": art(ISO_ART),
            "states": ISO_STATES,
            "same_red_set_in_three_red_states": SAME_RED_SET,
            "restored_after_experiment": iso.get("restored"),
            "matrix_catalog_test_per_state": {
                "source": "19:47–19:54 实测 (none/b0_only/all_on 三态), 与测试文件更新无关 "
                          "(tests/backtest/test_matrix_strategy.py 未改动), 故仍成立; "
                          "B4 落地后 all_on 目录由 108 变 110, 该测试失败点仍是第一个不可物化 id, 结论不变",
                "none": "PASSED (30 passed)",
                "b0_only": "FAILED — ValueError: unsupported matrix feature: prior_amount_20",
                "all_on": "FAILED — ValueError: in_universe 缺少必需列: ['raw_close']",
            },
            "conclusion": "none(93) / calendar_only(95) / b0_only(109) 三态失败的永远是同一 6 条计数断言 "
                          "(test id 逐字相同), all_on(110) 为 74 passed / 0 failed => 红/绿只由目录条数决定, "
                          "与哪些 pack 在场无关, 也没有任何一条失败来自实现代码。推论: pack 目录若不进版本库, "
                          "干净检出=93, 这 6 条会一直红 => 故本批把三个 pack 目录 git add (只 add, 不 commit)。",
        },''',
)

rep(
    '''        {"id": "D-B2-2", "topic": "in_universe 是否进 /api/factors 目录",
         "detail": "Provider 注册即进目录 (扩展点既定行为, B0 的 14 个同理), 故 /api/factors 由 107 变 108。若要求 E3 掩码不进对外目录, 需改扩展点语义 (影响 B0)。"},''',
    '''        {"id": "D-B2-2", "topic": "in_universe 是否进 /api/factors 目录",
         "detail": "Provider 注册即进目录 (扩展点既定行为, B0 的 14 个同理), 故 /api/factors 由 107 变 108 (B4 之后 110)。若要求 E3 掩码不进对外目录, 需改扩展点语义 (影响 B0 与 B4 日历列)。"},''',
)

rep(
    '''        "E4 (month_end / rebalance 轴) 不在本批范围",''',
    '''        "E4 (month_end / week_end 轴) 不在 B2 范围内: 已由同批 B4 另行实现并交付 (research/b4-calendar-20261107, docs/factors/E4_CALENDAR_20261107.md), 只走 frame 路径, 矩阵路径同 B2 归 B0b",''',
)

rep(
    '''        "6 条「目录=93」测试已于 2026-11-07 20:48:59 按 108 口径更新断言, 现盘 74 passed / 0 failed (见 test_status)",''',
    '''        "6 条「目录=93」测试已两次按新事实更新断言 (2026-11-07 20:48:59 → 108; 22:01:47 → 110), 现盘 74 passed / 0 failed (见 test_status)",''',
)

print(f"prepared {len(EDITS)} edits")
for old, new in EDITS:
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: anchor matched {n} times, expected 1:\n{old[:160]!r}")
    src = src.replace(old, new)

P.write_text(src, encoding="utf-8")
print("patched", P, len(orig), "->", len(src), "chars;", src.count("\n") + 1, "lines")
