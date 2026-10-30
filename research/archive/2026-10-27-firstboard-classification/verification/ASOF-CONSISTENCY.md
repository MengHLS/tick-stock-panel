# 首板历史标签·截断一致性与未来扰动检查

生成时间：2026-10-28T17:18:33

## 口径

- 内核：`app.factors.event_chain.compute_event_chain_outputs`（lookback=250，min_pullback=0.05，require_new_high_after_anchor=True）
- 固定输入：`four-case-paths.csv` / `four-case-events.csv`，快照上界 2026-10-23
- 事件数：63；股票：000810.SZ, 002354.SZ, 002687.SZ, 600785.SH
- 比对字段：9 个事件链字段

## 结果

- 截断一致性：567 项字段比对，**0 项不一致**
- 未来扰动：1701 项比对，**0 项不一致**

## 文件哈希

| 文件 | SHA256 | 与清单一致 |
|---|---|---|
| four-case-paths.csv | `5b6e657d956cb8f1…` | True |
| four-case-events.csv | `fefaedd74f4df8a3…` | True |
| event_chain.py | `8aa42c52aca07756…` | 记录用 |
| verify_asof_consistency.py | `1d790d5aa4a905a4…` | 记录用 |

## 覆盖边界

- 未覆盖：new classification rules (P/L/path-state) - event table not delivered at run time
- 未覆盖：factor snapshots
- 未覆盖：first-board identity / historical ST / board regime
- 未覆盖：adjusted-vs-raw basis comparison on this basket (no ex-rights inside these windows)

## 复权覆盖

| 股票 | 复权价≠原始价的行数 |
|---|---:|
| 000810.SZ | 0 |
| 002687.SZ | 0 |
| 600785.SH | 0 |
| 002354.SZ | 0 |

四只股票窗口内无除权，故本批**不能**检验复权口径；含除权样本需另列。

## 复跑

```powershell
cd backend
uv run --frozen python ../docs/research/firstboard-classification-draft-20261027/verification/verify_asof_consistency.py
```
