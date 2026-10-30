# 研究材料存放区

这里存放研究过程产物：脚本、CSV、JSON、图表和大体积 HTML。它们**不是产品文档**，不保证与当前代码或数据版本一致。

```text
research/
  README.md
  archive/
    2026-10-27-firstboard-classification/   # 冻结档案，保持原始平铺结构
  <topic>-<YYYYMMDD>/                       # 以后的新研究
    README.md
    data/
    scripts/
    results/
    verification/
```

## 规则

- 研究结论写入 [`docs/research/`](../docs/research/README.md)，并在索引中登记。
- 新研究目录按 `<topic>-<YYYYMMDD>/` 命名；入口写 `README.md`，数据、脚本、结果和复核分开存放。
- 冻结档案不要重排内部文件：脚本和校验清单依赖原相对路径。需要重排时先补路径迁移和重新冻结。
- 大体积中间产物不进入 `docs/`；确认冻结后再决定是否保留在 Git。
- 历史目录中的绝对路径和相对路径以当时快照为准，不以当前仓库结构自动修正。

## 当前内容

| 目录 | 说明 |
| --- | --- |
| [archive/2026-10-27-firstboard-classification/](archive/2026-10-27-firstboard-classification/README.md) | 首板分类研究冻结档案，入口 `event-replay-v01/README.md` |
