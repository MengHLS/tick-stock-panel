"""给 evidence_build.py 的 test_status 补三方隔离矩阵 (none / b0_only / b2_all_on)。

每个状态都是实测: 把 pack 目录移出/移回 (mv), 跑同一组 pytest, 记录红点集合。
one-shot 补丁。
"""
from __future__ import annotations

from pathlib import Path

p = Path("research/b2-engine-20261107/evidence_build.py")
s = p.read_text(encoding="utf-8")

anchor = '''        "note": "本批未修改该测试 (一度加过 FRAME_ONLY_FACTOR_IDS 排除+失效断言, 因 8 个 B0 id 仍红、无法变绿且会掩盖 B0b 缺口, 已 git checkout 还原)。",
    },'''

assert anchor in s, "anchor missing"

block = '''        "note": "本批未修改该测试 (一度加过 FRAME_ONLY_FACTOR_IDS 排除+失效断言, 因 8 个 B0 id 仍红、无法变绿且会掩盖 B0b 缺口, 已 git checkout 还原)。",
        "isolation": {
            "why": "区分「B2 引入」与「既有」: 把 pack 目录 mv 出 app/custom 后重跑同一组 pytest。",
            "states": [
                {
                    "tag": "none",
                    "setup": "两个 pack 目录都移出 (无 B0、无 B2)",
                    "catalog_size": 93,
                    "matrix_supported": 79,
                    "matrix_unsupported": 14,
                    "factor_suite": "74 passed / 0 failed",
                    "matrix_catalog_test": "PASSED (30 passed)",
                    "artifact": "logs/catalog_support_none.json",
                },
                {
                    "tag": "b0_only",
                    "setup": "只留 research_factor_pack (B0 14 个), 无 research_universe_pack",
                    "catalog_size": 107,
                    "matrix_supported": 85,
                    "matrix_unsupported": 22,
                    "factor_suite": "6 failed / 68 passed (与全开时同一 6 条)",
                    "matrix_catalog_test": "FAILED — ValueError: unsupported matrix feature: prior_amount_20",
                    "artifact": "logs/catalog_support_b0_only.json",
                },
                {
                    "tag": "all_on",
                    "setup": "B0 + B2 全在 (工作区现状)",
                    "catalog_size": 108,
                    "matrix_supported": 85,
                    "matrix_unsupported": 23,
                    "factor_suite": "6 failed / 68 passed (与 b0_only 同一 6 条)",
                    "matrix_catalog_test": "FAILED — ValueError: in_universe 缺少必需列: ['raw_close']",
                    "artifact": "logs/catalog_support_all_on.json",
                },
            ],
            "conclusion": "6 条 factor 红灯在 b0_only 状态下已经是同一 6 条 => B0 引入, B2 未新增。"
                          "矩阵目录测试在 none 状态全绿、在 b0_only 即红 => B0 引入; B2 只是让首个失败点从 "
                          "prior_amount_20 前移到 in_universe (仍有 8 个 B0 frame 因子在前)。"
                          "故本批对既有红灯零新增, 也未擅自改测试或目录。",
        },
    },'''

s = s.replace(anchor, block, 1)
p.write_text(s, encoding="utf-8")
print("patched test_status.isolation")
