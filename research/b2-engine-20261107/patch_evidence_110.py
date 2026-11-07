"""把 evidence_build.py 从 108 口径切到 110 口径 (B4 日历包落地后的第二次过期断言更新)。

只做文本替换, 每处替换都断言「恰好命中 1 次」, 避免静默改错。
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
    'pt = load("pytest_after_108_run.json")\niso = load("isolation_recheck_108.json")',
    'pt = load("pytest_after_110_run.json")\niso = load("isolation_recheck_110.json")\n'
    'PT_ART = "pytest_after_110_run.json"\n'
    'ISO_ART = "isolation_recheck_110.json"\n'
    'CATALOG_NOW = 110',
)

rep(
    '''TESTS_NOTE = (
    "backend/tests/** — B2 编码期内未改任何测试; 但 2026-11-07 20:48:59 本部门按「catalog 93→108」口径更新了 "
    "2 个测试文件的过期断言 (过期断言更新, 非回归): "
    f"test_factor_registry.py {reg_f['bytes']} B / {reg_f['lines']} 行 / {reg_f['sha256']}; "
    f"test_factor_store.py {sto_f['bytes']} B / {sto_f['lines']} 行 / {sto_f['sha256']}; "
    "未改断言条数: `assert ` 45→45 (test_factor_registry.py)、20→20 (test_factor_store.py), 0 删除。"
    "详见 test_status.test_files_changed。"
)''',
    '''TESTS_NOTE = (
    "backend/tests/** — B2 编码期内未改任何测试。但本部门在 2026-11-07 两次更新了同一组 2 个测试文件的"
    "过期计数断言 (过期断言更新, 非回归; 未删任何断言): "
    "① 20:48:59 按「catalog 93→108」(B0 14 + B2 in_universe); "
    "② 22:01:47 按「catalog 108→110」(B4 的 month_end / week_end 随日历包注册即进目录, 与本批 5 文件套件同一目录口径)。"
    f"现盘: test_factor_registry.py {reg_f['bytes']} B / {reg_f['lines']} 行 / {reg_f['sha256']}; "
    f"test_factor_store.py {sto_f['bytes']} B / {sto_f['lines']} 行 / {sto_f['sha256']}; "
    "未改断言条数: `assert ` 45→45 (test_factor_registry.py)、20→20 (test_factor_store.py), 0 删除。"
    "详见 test_status.test_files_changed (含两次各步骤的字节/行/sha)。"
)''',
)

rep(
    '''        "has_universe_pack": pr.get("has_universe_pack"),
        "catalog_size": pr.get("catalog_size"),''',
    '''        "has_universe_pack": pr.get("has_universe_pack"),
        "has_calendar_pack": pr.get("has_calendar_pack"),
        "catalog_size": pr.get("catalog_size"),''',
)

rep(
    '''        "artifact": f"logs/catalog_support_{tag}.json",
    }


ISO_STATES = [iso_state(t) for t in ("none", "b0_only", "all_on")]

_f_none = set(((iso.get("states") or {}).get("none") or {}).get("failed_tests") or [])
_f_b0 = set(((iso.get("states") or {}).get("b0_only") or {}).get("failed_tests") or [])
SAME_RED_SET = (_f_none == _f_b0 and len(_f_none) == 6)''',
    '''        "artifact": f"logs/catalog_support_{tag}.json",
    }


ISO_TAGS = ("none", "b0_only", "calendar_only", "all_on")
ISO_STATES = [iso_state(t) for t in ISO_TAGS]
ISO_BY_TAG = {s["tag"]: s for s in ISO_STATES}

_f_none = set(((iso.get("states") or {}).get("none") or {}).get("failed_tests") or [])
_f_b0 = set(((iso.get("states") or {}).get("b0_only") or {}).get("failed_tests") or [])
_f_cal = set(((iso.get("states") or {}).get("calendar_only") or {}).get("failed_tests") or [])
_f_all = set(((iso.get("states") or {}).get("all_on") or {}).get("failed_tests") or [])
SAME_RED_SET = (_f_none == _f_b0 == _f_cal and len(_f_none) == 6 and not _f_all)''',
)

rep(
    '''    dict(id="T-A", gate="目录/矩阵能力隔离: none 全绿 -> b0_only 转红 -> 全开零新增", command=CMD_PROBE,
         evidence=[art("catalog_support_none.json"), art("catalog_support_b0_only.json"),
                   art("catalog_support_all_on.json")],
         observed={
             "none": {"catalog": load("catalog_support_none.json").get("catalog_size"),
                      "matrix_unsupported": load("catalog_support_none.json").get("matrix_unsupported")},
             "b0_only": {"catalog": load("catalog_support_b0_only.json").get("catalog_size"),
                         "matrix_unsupported": load("catalog_support_b0_only.json").get("matrix_unsupported")},
             "all_on": {"catalog": load("catalog_support_all_on.json").get("catalog_size"),
                        "matrix_unsupported": load("catalog_support_all_on.json").get("matrix_unsupported")},
         },
         verdict="PASS" if (
             load("catalog_support_none.json").get("catalog_size") == 93
             and load("catalog_support_b0_only.json").get("catalog_size") == 107
             and load("catalog_support_all_on.json").get("catalog_size") == 108
             and load("catalog_support_none.json").get("matrix_unsupported") == 14
             and load("catalog_support_b0_only.json").get("matrix_unsupported") == 22
             and load("catalog_support_all_on.json").get("matrix_unsupported") == 23
         ) else "FAIL",
         note="矩阵不可物化数 14(none) -> 22(B0 的 8 个 frame 因子) -> 23(B2 的 in_universe)。"
              "B2 只加 1, 不是「B2 弄坏了矩阵路径」; 矩阵路径代码本批未改 (materialize_matrix_field 仍为基类默认 None)。"),''',
    '''    dict(id="T-A", gate="目录/矩阵能力隔离 (四态): none 93 -> calendar_only 95 -> b0_only 109 -> 全开 110", command=CMD_PROBE,
         evidence=[art("catalog_support_none_110.json"), art("catalog_support_calendar_only_110.json"),
                   art("catalog_support_b0_only_110.json"), art("catalog_support_all_on_110.json")],
         observed={s["tag"]: {"catalog": s["catalog_size"], "matrix_supported": s["matrix_supported"],
                              "matrix_unsupported": s["matrix_unsupported"]} for s in ISO_STATES},
         verdict="PASS" if (
             [s["catalog_size"] for s in ISO_STATES] == [93, 95, 109, 110]
             and [s["matrix_unsupported"] for s in ISO_STATES] == [14, 16, 24, 25]
         ) else "FAIL",
         note="四态实测 (pack 目录 mv 出 app/custom 再放回, 试验后已完整还原): "
              "93(无 pack) -> 95(+B4 日历 2) -> 109(+B0 14) -> 110(+B2 in_universe)。"
              "矩阵不可物化数 14 -> 16(+month_end/week_end) -> 24(+B0 的 8 个 frame 因子) -> 25(+in_universe), "
              "每步只加该包自己的 id, 没有互相放大; 矩阵路径代码本批未改 (materialize_matrix_field 仍为基类默认 None)。"),''',
)

rep(
    '''    dict(id="T-B", gate="factor 套件红/绿只由目录条数决定; B2 实现代码零红灯 (三态实测)", command=CMD_SUITE,
         evidence={"suite_now": art("pytest_after_108_run.json"),
                   "isolation": art("isolation_recheck_108.json"),
                   "all_on_log": art("pytest_factor_suite_all_on.log"),
                   "b0_only_log": art("pytest_factor_suite_b0_only.log")},
         observed={"all_on_108": (ISO_STATES[2]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "b0_only_107": (ISO_STATES[1]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "none_93": (ISO_STATES[0]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "same_red_set_in_none_and_b0_only": SAME_RED_SET,
                   "catalog_sizes": {s["tag"]: s["catalog_size"] for s in ISO_STATES}},
         verdict="PASS" if (len(ISO_STATES) == 3 and ISO_STATES[2]["failed_tests"] == []
                            and SAME_RED_SET) else "FAIL",
         note="三态都跑同一组 5 文件 (108 口径测试现盘版本): 93 与 107 下失败的永远是同一 6 条计数断言 "
              "(test id 逐字相同), 108 下 74 passed / 0 failed => 任何红灯都只由目录条数决定, 与哪个 pack 在场无关, "
              "也没有一条失败来自 B2 的实现代码。改前那 6 条红的根因经逐条比对全是 count 断言, 无一条属于其他根因; "
              "已按开发经理裁定更新为 108 (未删断言/skip/xfail), 现盘 74P/0F。"),''',
    '''    dict(id="T-B", gate="factor 套件红/绿只由目录条数决定; 实现代码零红灯 (四态实测)", command=CMD_SUITE,
         evidence={"suite_now": art(PT_ART),
                   "isolation": art(ISO_ART),
                   "all_on_log": art("pytest_factor_suite_all_on.log"),
                   "b0_only_log": art("pytest_factor_suite_b0_only.log")},
         observed={"all_on_110": ISO_BY_TAG["all_on"]["factor_suite"],
                   "b0_only_109": ISO_BY_TAG["b0_only"]["factor_suite"],
                   "calendar_only_95": ISO_BY_TAG["calendar_only"]["factor_suite"],
                   "none_93": ISO_BY_TAG["none"]["factor_suite"],
                   "same_red_set_in_three_red_states": SAME_RED_SET,
                   "catalog_sizes": {s["tag"]: s["catalog_size"] for s in ISO_STATES}},
         verdict="PASS" if (len(ISO_STATES) == 4 and ISO_BY_TAG["all_on"]["failed_tests"] == []
                            and SAME_RED_SET) else "FAIL",
         note="四态都跑同一组 5 文件 (110 口径测试现盘版本): 93 / 95 / 109 下失败的永远是同一 6 条计数断言 "
              "(test id 逐字相同), 110 下 74 passed / 0 failed => 任何红灯都只由「目录条数 != 断言里的数」决定, "
              "与哪些 pack 在场无关, 也没有一条失败来自实现代码。断言数已两次按新事实更新 (93→108→110), "
              "未删断言/未 skip/未 xfail, 见 test_status.test_files_changed 与 assertion_coverage_preserved。"),''',
)

print(f"prepared {len(EDITS)} edits")

for old, new in EDITS:
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: anchor matched {n} times, expected 1:\n{old[:120]!r}")
    src = src.replace(old, new)

P.write_text(src, encoding="utf-8")
print("patched", P, len(orig), "->", len(src), "chars;", src.count("\n") + 1, "lines")
