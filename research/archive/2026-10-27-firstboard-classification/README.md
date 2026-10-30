# 首板分类研究档案（2026-10-27 起）

**状态：冻结的研究过程档案，不是产品文档，也不代表当前策略或收益结论。**

入口先读 [`event-replay-v01/README.md`](event-replay-v01/README.md)：它说明 27 个事件、432 条候选分类、因子时点、复权与缺失边界，以及独立复核要求。其余文件按下面的角色查找。

## 文件地图

| 角色 | 文件 |
| --- | --- |
| 结论与口径 | `DATA-EVIDENCE.md`、`RULES-DRAFT.md`、`RULE-DECISIONS.md`、`THREE-CASE-EVIDENCE.md`、`FACTOR-INVENTORY.md` |
| 基线与演进记录 | `BASELINE-RECORD.md`、`BASELINE-CHANGE-NOTICE-*.md`、`ADJ-REBUILD-PLAN-*.md`、`ADJUSTMENT-BREAK-*.md`、`EXPERIMENT-DOWNGRADE-*.md`、`ENGINE-BASELINE-HANDOFF-*.md` |
| 交付回放 | `event-replay-v01/`、`event-replay-v011-schema/`、`event-replay-v012-schema/` |
| 数据与图表 | `cases.json`、`four-case-*`、`shape-selection-*`、`multi-scale-shape-*`、`platform-firstboard-*`、`three-case-*`、`boundary-fixtures.json`、`case-diagrams.html`、`replay-user-v012.html` |
| 脚本 | `export_*.py`、`draw_*.py`、`select_shape_examples.py`、`revise_*.py`、`replay_*.py`、`normalize_candidate_schema_v011.py`、`finish_replay_v012.py`、`review_shapes.py`、`check_materials.py` |
| 独立复核 | `verification/`、`REPLAY-REVIEW-FREEZE-20261028.json` |

## 为什么保持平铺

脚本统一用 `Path(__file__).parent` 读取同目录数据，`event-replay-*` 与冻结清单也按相对路径互相引用。把文件拆进 `data/`、`scripts/` 会同时破坏复现脚本和冻结哈希，因此本档案保持冻结时的平铺结构；新研究请在 `research/` 下使用分目录结构。

## 复现边界

- 冻结截断日为 2026-10-23；部分标的、日期和输入来自当时本机数据路径与另一个项目目录，外部环境不保证可复现。
- `REPLAY-REVIEW-FREEZE-20261028.json` 与部分脚本记录的是冻结时的 `docs/research/...` 路径；目录后来迁到 `research/archive/`，内容哈希未改动。
- 生产分类引擎、正式策略回测和未来收益结论不在此档案的验证范围内。
