---

## 15. 裁定补记 v1.8（2026-11-07 23:1x）：S09 重定基线的结果 —— **无需重定**，§12.4 的「不可复现」撤回

**触发**：开发经理 23:0x 派工，要求「用当前 engine 与 canonical `uf_*` 重跑 S09，结果作为新基线，旧行标 `superseded`，不要保留两个并列的当前数字」。本轮照做，结论与派工预期相反：**重跑与旧行逐值相同，因此不该 supersede，也不存在第二个当前数字。**

### 15.1 实际怎么跑的（可复现）

- **跑在提交态，不跑在脏工作树**：`git worktree add --detach C:/temp/s09-base-wt 200238ec`，`DATA_DIR=D:/TSP/data`，只读数据。脚本 `research/s09-rebaseline-20261107/rebaseline.py`，产物 `RESULT_head200238ec.json`（8,305 B）、日志 `run_head200238ec.log`。
- 入场 = `in_universe & close > uf_prior_high_55 & volume > 1.5 * uf_prior_vol_20`（DSL `compile_formula`），出场 = `close < ma20`（canonical 单侧 id），账户 = `common.ACCOUNT` 原样（10bp、5 仓、60% 敞口、`block_limit_open`），引擎 = `app/backtest/engine.py` @ `15717100`。
- 面板 `fda82b47…dfe3` / 6,422,875 行 / 3,384 只 / 2,136 日；评估窗 1,779 日。

**结果 = 旧 registry 行**（`S09_volume_breakout_55@10`）：

| 项 | 本轮（提交态 `200238ec`） | registry 行 | 差 |
| --- | ---: | ---: | ---: |
| 建仓笔数 | **732** | 732 | **0** |
| 期末权益 | **59,011.37** | 59,011.37 | **0.00** |
| 全期总收益 | **−94.098863%** | −94.098863% | **0** |
| 全期 Sharpe | **−1.534347** | −1.534347 | **0** |
| 全期最大回撤 | **−95.3650%** | −95.3650% | **0** |
| 入场信号 | **52,965** | 52,965 | **0** |
| 涨停拦截 `buy_limit_up` | **1,387** | 1,387 | **0** |
| 逐年笔数（2019→2026） | **42 / 94 / 85 / 117 / 91 / 101 / 103 / 99** | 同左 | **逐项 0** |
| 逐年信号数 | **1752 / 7756 / 7082 / 5678 / 5313 / 7812 / 10775 / 6797** | 同左 | **逐项 0** |

执行计数同值：`buy_no_slot` 36,216、`sell_limit_down` 20、`sell_suspended` 24、`buy_suspended` 0、`buy_same_day_reentry` 0。

**两条独立代码路径给出同一批成交**（排除 harness 依恋某一种写法）：同一份 canon 上，① 直接取列喂 `run_continuous`；② 先按 §12 的写法 `join` 回 `prepared` 再喂；两次都是 **732 笔**，成交集合差 **0 / 0**（`bisect_harness.py` / `bisect.log`）。

### 15.2 取舍：**旧行不标 `superseded`**，只加溯源块

派工要求「旧行标 superseded」。在数字逐值相同的情况下照做会造出两种坏结果之一：要么凭空多一个「当前」数字，要么让唯一当前数字失去「可复现」这一属性。所以改为：`registry.json` 的 S09 行**数字一个字没动**，只加 `baseline_provenance`（角色 `current_baseline`、`superseded: false` + 理由、本轮 git head / engine commit / 模块 sha256 / `rerun_delta` 全 0 / 证据路径）。对 registry 的 diff 是 **17 行纯增量**，JSON 解析后 36 条 run 不变。

### 15.3 §12.4 撤回，撤回范围逐句写清

| §12 原句 | 现判定 |
| --- | --- |
| 「S09 的 registry 数字在今天的 HEAD 上不可复现」 | **撤回**。提交态 `200238ec` 上重跑 = 732 笔 / 59,011.37，与 registry 逐值相同 |
| 「今天的数字是 −96.38% / 679 笔」 | **撤回**。那是主工作树（dirty）产物，不是提交态数字 |
| §12.3 表中 S09 一列（679 / 36,187.24 / 逐年 33·87·80·118·86·93·96·86） | **作废**，以 §15.1 为准（该表已就地加注） |
| §12.4「范围已收窄：5 条精确复现、漂移只在 S09」 | 事实部分仍成立（S01/S03/S05/S08/S02 复现），但「漂移」的**归因**作废：不是引擎改动，见 §15.4 |
| 「36 次运行没有版本锚」 | **仍成立**，且本轮**部分补上**：S09@10 现在有 `baseline_provenance`；其余 35 次仍无锚 |
| §12.2 信号层 jaccard 1.000 / 逐日零差 | **仍成立**（与本次结果不冲突，入场信号 52,965 两次一致） |
| §12.5 S09「口径层可准入、策略层判死」 | **仍成立**，见 §15.5 |

### 15.4 679 从哪来：未确证，但已排除「引擎改动」并定位到「工作树在动」

- 22:44 那次跑的是**主工作树**（`git status` 当时即有大量 backend 未提交改动），不是提交态；本轮在 clean worktree 上跑。
- 旁证（时间戳，可复核）：`backend/app/factors/store.py` mtime **23:08:05**、`gate.py` **23:08:35**、`registry.py` **23:09:50**，均**晚于**我 23:07 那次跑的结束时间（23:07:27）；`dsl.py` 22:11:19。即同一晚这些模块被反复改写，22:44 那一跑的模块状态**无快照可回溯**。
- 已被数据收窄到一处：同一次跑里 S02 与 registry 逐位相同（442 / 111,695.81）、S09 不同；S09 与 S02 唯一不共用的输入列是**出场腿 canonical `ma20`**（S02 出场用 `uf_prior_low_10`），而两次的入场信号总数与逐年数完全相同 → 差异落在出场腿，或落在当时被改写的模块上。**这两者我没法分辨**（无 22:44 的模块快照）。
- **由此得到的硬要求（属开发侧流程，不由我改）**：研究侧任何「基线」数字必须在 **clean worktree 或冻结快照**上产生，并记录 `engine` / `common.py` / `registry.json` 的 sha256；主工作树 dirty 时跑出的数字不得写进 registry。本轮已照此执行。

### 15.5 准入判定（只报判定，不重复收益结论）

**不变 —— 仍是「口径层可准入、策略层判死」，答「否」。** 新基线下逐条：全期总收益 **−94.0989% < 0**（判死）；`buy_limit_up` **1,387 > 1,000**（绝对门成立）；E1 = FAIL → 上限只能是 HOLD。数字与旧行相同，所以判定与 §12.5 逐字相同，没有任何一条被新基线翻过来。

### 15.6 只在文档里标、**未改任何数字**的两点

1. `market_breadth` 注册（§13 走法 ②）已被开发经理采纳并派因子工程师执行（单侧 id、`warmup_bars = 120`、禁止再做截面算子）→ §13 维持原样。
2. 排期 v7 三处已落（L82 `CAL-observed_bars` → 已裁 D10；掩码 → 已裁不立号；`caliber` 指纹 `cp23e908` 笔误 → 本文件 v1.8 指纹）→ 本文件不再复述，也不因排期改动而改任何口径数字。

### 15.7 本轮没有触碰的

12 条阈值；任何策略的 `void` / `void_reason`；重验顺序 S07 → S11 → S12 → S10 → S06；D1 / D2 / D4 / D10 的裁定；S02 的结果（未重跑，沿用 §12.3 的 442 / 111,695.81）。

**本轮跑了什么、是否改变策略状态**：只跑了 **S09 一条**（2 次账户回放：提交态 1 次、主工作树脏树 1 次，另 1 次路径对照），**没有**跑 S02 及其余 10 条，**没有**改任何阈值或状态 → **不产生任何会改变 12 条策略状态的判定**。

### 15.8 复现命令

```bash
cd /c/work/sourcecode/tick-stock-panel
git worktree add --detach C:/temp/s09-base-wt 200238ec
cd C:/temp/s09-base-wt && mkdir -p research/s09-rebaseline-20261107
# 把主树的 rebaseline.py 复制进来，然后：
DATA_DIR="D:/TSP/data" PYTHONUTF8=1 /c/work/sourcecode/tick-stock-panel/backend/.venv/Scripts/python.exe \
  research/s09-rebaseline-20261107/rebaseline.py     # 期望 n_trades=732, final_equity=59011.37, delta 全 0
```

### 15.9 未确证

- **679 的成因**：最可能是 22:44 时工作树里的 `store.py` / `registry.py` 与现在不同（mtime 显示这些文件之后又被改过），**无当时快照，无法回溯确认**。
- **本基线只对 `200238ec` 成立**：若当前 dirty 的 `store.py` / `registry.py` / `gate.py` / `dsl.py` 被提交，S09 基线需在新提交上再跑一次同一脚本；若数字变了，那就是那次提交的改动，不是本基线错。
- `common.py` 工作树 sha256 `523986f1…` ≠ HEAD blob sha256 `580f1588…`：已核是**行尾差异**（`git diff HEAD -- research/strategy-search-20261107/scripts/common.py` 为空），内容相同；引用 sha 时注明是工作树字节还是 git blob。
- `RESULT_head200238ec.json` 里 `engine_py_sha256 = ecc3d826…` 对应 `backend/app/backtest/engine.py` @ `15717100`；`app/strategy/scoring.py` 未在本轮哈希清单内单列（其 sha `ab40da59…` 与 HEAD 相同）。
