
## 9. 文档级补正（2026-11-08 18:0x，按开发经理 17:5x 复核意见；只追加，正文唯一的改动是 §4.1 两个列头）

本节**只追加**：§0–§8 的全部行（数字、判据、结论、措辞）**一字未改**，唯一例外是 §4.1 主表列头 `胜率` → `胜率(已平仓)`、`avg/median pnl` → `avg/median pnl(已平仓)`（见 9.2）。本节写作前的字节级基线：本报告 43,194 B / sha256 `e4b7c98fd47cf5656df5a9f6898decb761a523709487de6b7a92e0b3532dd002`，副本存 `REPORT_pre_s9_1810.md.bak`（同 sha），可直接 `diff` 复核「非 §9 改动 = 0 处（列头除外）」。

### 9.1 PREREG 时点不实（P2）：臂 0 在判据写成之前就已经算出来了

`PREREG_S01B_20261108.md` 正文第 2 条写「写死时点：四臂（臂 0/1/2/3）与 close/high 对照臂**尚未开跑**」。文件时间戳与此不符：

| 产物 | mtime（Asia/Shanghai） | 相对 PREREG（16:23:36） |
|---|---|---|
| `results/smoke_a0/` | 16:20:44 | 早 2 分 52 秒 |
| `results/a0_10bp/`（`result.json` 2,349 B / `trades.parquet` 22,854 B / `equity.parquet` 18,918 B） | **16:21:47** | 早 1 分 49 秒 |
| `PREREG_S01B_20261108.md` 本体（原始 2,871 B） | **16:23:36** | —（原始 sha256 `cf95a0b7ae2298b4c5685b2990e83be648e8cbf1bfff4608fb65b64ce158be41`） |
| `a1_10bp` / `a2_10bp` / `a3_10bp` | 16:24:00 / 16:24:16 / 16:24:33 | 全部晚于 PREREG |
| `a2h_10bp` / `a0ev_10bp` / `a3ev_10bp` | 16:25:05 / 16:25:21 / 16:25:38 | 全部晚于 PREREG |
| `a0_30bp` / `a1_30bp` / `a2_30bp` / `a3_30bp` | 16:26:57 / 16:27:13 / 16:27:30 / 16:27:47 | 全部晚于 PREREG |
| `a0_gross` / `a1_gross` / `a2_gross` / `a3_gross` | 16:29:55 / 16:30:12 / 16:30:29 / 16:30:45 | 全部晚于 PREREG |
| `a4_10bp` | 16:33:36 | 晚 10 分钟 |
| `prod_file_10bp` | 17:18:48 | 晚 55 分钟 |

事实：**臂 0 基线（含 `smoke_a0` 小样）在预注册判据写成之前就已经算出来了**，PREREG 原句「尚未开跑」对臂 0 不成立。

处置：**PREREG 原文与其原始 sha 保持不变**，只在文件末尾追加「## 时点更正（2026-11-08 18:0x 复核）」一节，写明 `a0_10bp` = 16:21:47 / PREREG = 16:23:36 两个 mtime、原始 sha `cf95a0b7…`、以及「臂 0 无风控参数、可调风控自由度为零 ⇒ F1–F4 判定不受影响」。追加后 PREREG 字节与 sha 必然变化（最终值见 §9.6），16:23:36 版可按 `PREREG_pre_timefix_1810.md.bak`（`cf95a0b7…`）逐字复核。

原句「③零」是断句失误，本意为「③ 除此之外已完成的其他工作为零（四臂回测一笔都没跑）」；按上述时间戳该陈述对臂 0 不成立，原句仅作留档。**本节不改任何判据文字与数字。**

**为什么判定不受影响**：臂 0 是「无风控出场」基线（`STOP_LOSS` / `TRAILING_STOP` / `TRAILING_TAKE_PROFIT_*` = `None`，`MAX_HOLD_DAYS` = 60），**没有任何可调的风控参数**；F1–F4 比的是臂 1/2/3 相对臂 0 的差，臂 0 提前 1 分 49 秒算出，不构成「看结果后再定判据」的自由度。臂 1/2/3 与 30bp / gross / a2h / a4 / prod_file 全部在 PREREG 之后产出（16:24:00 起）。

### 9.2 §4.1 的 `胜率` / `avg/median pnl` 是「已平仓」口径（P3）

§4.1 主表这两列取自 `result.json:stats`，而引擎的 `stats.win_rate` / `stats.avg_pnl` / `stats.median_pnl` **都不计未平仓笔**（`exit_reason="end"`）。列头已改为 `胜率(已平仓)` / `avg/median pnl(已平仓)`——这是本报告正文**唯一**的改动（两个列名，不含任何数字）。

臂 0（10bp，199 笔，其中 `end` 5 笔）：

| 口径 | 笔数 | 胜率 | avg pnl | median pnl |
|---|---|---|---|---|
| 已平仓（表内采用，= `stats`） | 194 | **33.51%**（65/194） | +1.31% | −9.64% |
| 全部 199 笔 | 199 | 32.66%（65/199） | +1.27% | −8.11% |

**两套不可混引**：报告与 `metrics.json` 一律已平仓口径；用「全部 199 笔」的 `pnl_pct > 0` 占比复算会得到 32.7% 而不是 33.5%。

```python
import polars as pl
t = pl.read_parquet("results/a0_10bp/trades.parquet")
(t["pnl_pct"] > 0).sum() / t.height                        # 65/199 = 0.3266  ← 全 199 笔
c = t.filter(pl.col("exit_reason") != "end")
(c["pnl_pct"] > 0).sum() / c.height                        # 65/194 = 0.3351  ← 表内口径
```

`metrics_table.md` 同一列也是已平仓口径（生成器列头未改，该文件哈希因此不变）。

### 9.3 `metrics.json` 里旧 `oos` 键已删除（P3，隐患）

处置：走「删掉」分支。`report_metrics.py` 原第 112 行 `out["oos"] = oos_by.get("10bp")` 整行删除，替换为三行注释（说明该键恒等于 10bp 档读数、逐档只认 `oos_by_scen`）。改后 `metrics.json` 六行的顶层键只有 `label` / `tags` / `10bp` / `30bp` / `gross` / `oos_by_scen` / `delay`，**不存在任何无标注的 `oos`**；`oos_by_scen` 三档齐全（`10bp` / `30bp` / `gross`）。

消费方核查：全目录 `grep` 只有 `report_metrics.py` 写过该键；`_audit_report_table.py` 与表格生成只读 `oos_by_scen` ⇒ 删除不影响任何对账脚本。

重跑两次（`report_metrics.py`，退出码 0 / 0）哈希一致：`metrics.json` = `282e090c5915a354a41e0a51590b8eedb604d96f7953d6418c57fd1a071d0247`（旧值 `6174f4da…` 作废，唯一差异是删掉六处 `oos` 键）；`metrics_table.md` 仍 `d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a`（表格输出未变）。

### 9.4 §2「必须改信号链」是范围约束，不是技术不可能（P2）

§2 原句保留不改（本节只追加）。**范围更正**：研究侧那 252 笔的事件式 A/B 并非「必须改信号链」才能做——把 `signal_s01_ma_golden_20_60` / `signal_s01_ma20_below_ma60` 的事件式派生列在**离线 DataFrame 里重算**、股票池按研究侧 `in_universe` 名单**写死**，即可在一份离线撮合脚本里得到 252 笔的对照，不必落回生产管道、也不必新增物化信号列。

因此 §2 那句应读作：**在本派单「不改信号链」的约束下未做**；等价性结论不依赖那 252 笔，已在生产路径两端逐笔全等证明（臂 0 无风控 199/199、臂 3 全风控 1135/1135，另 `prod_file_10bp` 与 `a3_10bp` 的 `trades.parquet` 字节相同 `3c0f27e9…`）。事实结论（事件式与水平式在金叉入场路径上等价、无需停下）不变。

### 9.5 `hold_p90` 的口径是 `polars.quantile` 默认（nearest），不是索引法、也不是 `np.percentile`（P3）

§4.1 主表 `持仓 p50/p90` 由 `report_metrics.py` 的 `dur.quantile(0.9)` 计算：**polars 默认 `interpolation="nearest"`，返回一个实测存在的整数持仓天数**。同一个 a1（519 笔）三种算法给出三个数：

| 算法 | a1 结果 | 说明 |
|---|---|---|
| `t["duration"].quantile(0.9)`（**表内采用**，p50 用 `Series.median()`） | **59** | polars 默认 nearest，返回样本值 |
| `np.percentile(duration, 90)` | 59.2 | 线性插值，不是样本值 |
| `sorted(duration)[int(n*0.9)]`，n=519 → 第 468 个 | 60 | 索引法 |

其余行三法同值（a0：199 笔 p90 = 60；a2：1,126 笔 p90 = 18），**唯一分歧是 a1 的 59 / 59.2 / 60**；按表内口径（polars nearest）复算才会得到 59。

### 9.6 本次补正后的哈希与对账

| 文件 | 变更 | 最终字节 / sha256 |
|---|---|---|
| `PREREG_S01B_20261108.md` | 末尾追加「## 时点更正（2026-11-08 18:0x 复核）」，原文（前 2,871 B）逐字节未改 | 4,446 B / `2343971950eb41728cfbbdfdde2b23414ff8a009b82692427f78eb4a02d233ca` |
| `metrics.json` | 删除旧键 `oos`（六处） | `282e090c5915a354a41e0a51590b8eedb604d96f7953d6418c57fd1a071d0247` |
| `metrics_table.md` | 无 | `d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a`（不变） |
| `report_metrics.py` | 删 `out["oos"]` 一行、加三行注释 | 7,970 B / `38a67c9fb87eed55cbeb8e0f3440947693f1585cab6d47a0bb2901c2c233f75c` |
| `REPORT.md`（本文件） | 追加本节 + §4.1 两个列头 | 自引用不写入本文件，最终 sha 见交付说明 |

字节级对照副本（本次改动前）：`REPORT_pre_s9_1810.md.bak`（`e4b7c98f…`，43,194 B）、`PREREG_pre_timefix_1810.md.bak`（`cf95a0b7…`，2,871 B）。

对账：`_audit_report_table.py` 重跑**退出码 0**，`rows checked = 12, cells mismatched = 0`（该脚本按 `|` 切分只比对以 `| 臂 ` 开头的数据行 13 个数值格，列头文字改动不影响它）。

纪律：本轮不提交、不部署、不重启服务、未碰 `engine` / 信号链 / `store.py` / 其它策略；改动仅限本目录 4 个文件（`REPORT.md`、`PREREG_S01B_20261108.md`、`metrics.json`、`report_metrics.py`）+ 2 个对照副本。