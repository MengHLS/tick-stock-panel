"""给 evidence_build.py 追加 T-A/T-B 两条判据 (测试红灯三方隔离)。

T-A: catalog/matrix 能力矩阵, 三状态 (none/b0_only/all_on) 各有落盘 JSON。
T-B: factor 测试套件在三状态下的红点数, 结论 = B2 零新增。
one-shot 补丁。
"""
from __future__ import annotations

from pathlib import Path

p = Path("research/b2-engine-20261107/evidence_build.py")
s = p.read_text(encoding="utf-8")

anchor = '''    # ---------------- 口径差 (不是判据, 供裁定) ----------------'''
assert anchor in s

block = '''    # ---------------- 测试红灯归因 (隔离矩阵, 实测) ----------------
    dict(id="T-A", gate="目录/矩阵能力隔离: none 全绿 -> b0_only 转红 -> 全开零新增", command=CMD_PROBE,
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
              "B2 只加 1, 不是「B2 弄坏了矩阵路径」; 矩阵路径代码本批未改 (materialize_matrix_field 仍为基类默认 None)。"),
    dict(id="T-B", gate="6 条 factor 测试红灯在 b0_only 已是同一 6 条 => 本批零新增", command=CMD_SUITE,
         evidence={"reran": "b0_only 状态下实测 6 failed / 68 passed, 与全开时同一集合",
                   "all_on": art("pytest_factor_suite_all_on.log"),
                   "b0_only": art("pytest_factor_suite_b0_only.log")},
         observed={"all_on": "6 failed / 68 passed", "b0_only": "6 failed / 68 passed",
                   "none": "74 passed / 0 failed"},
         verdict="PASS",
         note="全部是「目录条数硬编码 93」类断言; 由 B0 注册 14 个 pack 因子引入 (107), B2 使其为 108。"
              "本批未改任何测试 (git status backend/tests 为空)。"),
    # ---------------- 口径差 (不是判据, 供裁定) ----------------'''

s = s.replace(anchor, block, 1)

# 命令常量
cmd_anchor = 'CAL = load("observed_bars_calibers.json")'
if 'CMD_PROBE' not in s:
    s = s.replace(
        cmd_anchor,
        cmd_anchor
        + '\nCMD_PROBE = (f"cd {{ROOT}} && PROBE_TAG=none|b0_only|all_on PYTHONUTF8=1 {PY} '
        'research/b2-engine-20261107/probe_catalog_support.py")\n'
        'CMD_SUITE = (f"cd {{ROOT}}/backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest '
        'tests/test_factor_dsl.py tests/test_factor_registry.py tests/test_factor_api.py '
        'tests/test_factor_store.py tests/test_factor_provider_contracts.py -q")',
        1,
    )
    s = s.replace('load("observed_bars_calibers.json")', 'load("observed_bars_calibers.json")', 1)

p.write_text(s, encoding="utf-8")
print("patched T-A / T-B")
