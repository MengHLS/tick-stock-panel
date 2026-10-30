# 分区重写对冻结回放副本的影响

生成时间：2026-10-28T18:42:39

当前 generation：`449e60cbb0dc442781cb5d3745416ab5`

| 冻结文件 | 行数 | 股票 | 面板比对行 | 缺行 | 数值不一致 |
|---|---:|---:|---:|---:|---:|
| shape-selection-paths.csv | 22642 | 53 | 22642 | 0 | 0 |
| four-case-paths.csv | 2952 | 4 | 2952 | 0 | 0 |

## 结论

verified equal on every covered row; the generation change has no value-level effect inside the replay window, so the 27-event results stay reproducible

## 边界

- proves current == frozen, not pre-rewrite == frozen
- the rewritten 2026-10-27/28 partitions are outside the replay cutoff and are not assessed
- only the columns the replay reads are compared
