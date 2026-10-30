# 27事件/432条候选分类·独立复核

生成时间：2026-10-28T17:19:04

方法：按规则文字独立重实现，与 `event-replay-v01/candidate-classifications.json` 逐字段比对。

- 比对行数：432
- 比对字段：6288
- 数值/标签不一致：0
- 交付行缺字段（早退分支未写 null）：170

## 交付方自检的局限

交付的 `self_check_prefix_comparisons=432` 比较的是 `classify(prefix)` 与 `classify(batch)`，而 `batch` 与 `prefix` 是同一批行，只能证明确定性，不能证明因果性。因此需要本次独立重算。

## 文件指纹

| 文件 | SHA256 前16 | 与终审记录一致 |
|---|---|---|
| engine.py | `FBC27443DF15AC3C` | True |
| strategy.py | `9AB50B399D1F5C89` | True |
| event_chain.py | `8AA42C52ACA07756` | 记录用 |

## 未覆盖

- forward outcomes and daily tracking tables (evaluated separately)
- factor point-in-time integrity beyond the sampled fields
- first-board identity / historical ST / board regime
