# -*- coding: utf-8 -*-
"""R7 追加块的确定性构建器（只追加；不改 v0.3/v0.4/v0.5/v0.6）。

默认不落盘：--out 指向临时目录并自动删除，只打印合并后的四元组与 diff。
落盘需显式 --land（本批未使用，理由见 CONTRACT_REVISION_R7_20261107.md §5）。
"""
from __future__ import annotations
import argparse, hashlib, os, subprocess, sys, tempfile

ROOT = r"C:\work\sourcecode\tick-stock-panel"
V06 = os.path.join(ROOT, "docs", "architecture", "FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md")
V05 = os.path.join(ROOT, "docs", "architecture", "FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md")
OUT_NAME = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md"
R7_NAME = "docs/architecture/CONTRACT_REVISION_R7_20261107.md"
MARK = "本文件正文 sha256："


def crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- 块 A：G2.1
A_G21 = crlf("""**G2.1 执行口径必须显式传入（v0.7 追加；G2 的子条款，不增加 §1 的 G1–G8 条数）**

G2 只定义了**结果口径**（「最早成交在 T+1 开盘」），没有定义**口径怎么传进来**。实测三处默认值与 G2 相反，且互不相同：

- 引擎 `MatcherConfig.matching="close_t"`（`app/backtest/engine.py:229`）、`entry_price_basis="adjusted"`（`:258`）；`entry_fill` / `exit_fill` 为 `None` 时在 `__post_init__` **回退到 `matching`**（`:280-283`）；
- 服务层 `StrategyBacktestConfig.matching="open_t+1"`，`entry_fill` / `exit_fill` 同样回退（`app/backtest/strategy.py:717-719`、`:744-747`）；
- `entry_price_basis` 在策略回测请求模型里**没有字段**（`app/api/backtest.py:358` 只有 `matching` / `entry_fill` / `exit_fill`），唯一来源是策略 META，缺省 `"adjusted"`（`app/backtest/execution_policy.py:78`、`:141-144`）。

于是「漏传」**不产生任何信号**：成交时点静默变成 T 日收盘、成交价静默变成复权价。这是本契约中唯一一处「违反 G2 却不报错」的路径，故必须以**拒绝条件**收口，不以文档约定收口。

1. **必须显式传入**：`entry_fill`、`exit_fill`、`entry_price_basis`。缺任一个 → **报错**。禁止回退默认、禁止告警降级、禁止「等于默认值即视为未传」的启发式（显式传 `close_t` 与不传必须可区分）。
2. **判定方式**：`MatcherConfig` 与 `StrategyBacktestConfig` 的上述三字段改为 sentinel 缺省（`_UNSET`）；`__post_init__` 见到 `_UNSET` 即抛 `G2CaliberError`，**不得**进入 `matching` 回退分支。
3. **校验时机**：在**读任何行情之前**（构造 cfg 之后、parquet 读取之前）。位置对齐两条既有先例：full 模式 fail-closed（`strategy.py:1578-1580`）、`plan_at_signal_close` 校验（`engine.py:296`）。
4. **错误契约**：HTTP 400，`detail = {"code": "FS08", "missing": [<缺失字段名>...], "mode": "position|full|minute", "hint": "<补 META 的具体路径>"}`。`FS08` 取 `FS` 族下一个空位（`FS01`–`FS07` 已占用），**不占用** DSL 的 `E0xx`（编译期语言错误码，`E001`–`E017` 已定义/预留）。
5. **例外必须显式标记，不得靠默认值**：
   - `mode="full"` 与 `entry_price_basis="raw"` 不相容（`_FULL_UNSUPPORTED_RULES`，`engine.py:341-356`）→ 拒绝并带 `FS08`，**不得**改判 `adjusted` 续跑；
   - 分钟路径硬编码 `entry_fill="close_t"`（`strategy.py:2615`）→ 结果标 `execution_caliber="minute_t"`，**不进** G2 验收面（回测-模拟盘逐日一致率）；
   - legacy 信号回测 `POST /api/backtest/run`（`BacktestRequest.matching="close_t"`，`api/backtest.py:95`）→ 标 `g2_exempt=true, reason="legacy_signal_backtest"`，不得被策略/因子回测复用。
6. **迁移属数据变更、不属代码默认**：为每个策略 `META.backtest_defaults` 显式写 `"entry_price_basis": "raw"`、`"entry_fill": "open_t+1"`、`"exit_fill": "open_t+1"`。现状实测：`backend/app/strategy/seeds/` **25** 个种子文件**无一**含 `backtest_defaults`（`grep -rl backtest_defaults backend/app/strategy/seeds | wc -l` → `0`），`D:/TSP/data/user_data` 下**无 `strategies` 目录** → 本条款生效后，未补 META 的策略**全部** `FS08`。**禁止**把代码默认值改成 `raw` 代偿——那会把「必须显式」重新变回「靠默认」。

判据 **F-A40**（可写成 5 个 pytest 用例）

| # | 断言 |
| --- | --- |
| F-A40-1 | 只缺 `entry_fill` → `G2CaliberError`，`detail["code"]=="FS08"`，`detail["missing"]==["entry_fill"]` |
| F-A40-2 | 只缺 `entry_price_basis` → 同上，`detail["missing"]==["entry_price_basis"]` |
| F-A40-3 | 只缺 `exit_fill` → 同上，`detail["missing"]==["exit_fill"]` |
| F-A40-4 | 三字段全部显式（含显式传 `close_t` + `adjusted`）→ 构造成功；`research` 模式结果标 `g2_override=true`，`production` 模式 400 `FS08` |
| F-A40-5 | 校验在读盘之前：monkeypatch 行情读取入口与 `repo.*` 读调用，计数 == 0 |""")

# ------------------------------------------------------- 块 B：§7.13 矩阵路径
B_713 = crlf("""### 7.13 矩阵回测路径的能力清单与准入前置（v0.7 追加；交付范围点名）

**7.13.1 现状（实测 2026-11-07 17:2x 复跑，可独立复现）**

14 个研究基线因子（`backend/app/custom/research_factor_pack/factor_specs.py`）在矩阵路径的解析结果：

| # | factor_id | 面板路径 | 矩阵路径 | 机制 |
| --- | --- | --- | --- | --- |
| 1 | `ma20` | 可算 | 可算 | 前缀启发式 `name[2:].isdigit()`（`matrix.py:4220`） |
| 2 | `ma60` | 可算 | 可算 | 同上 |
| 3 | `ma120` | 可算 | 可算 | 同上 |
| 4 | `ma200` | 可算 | 可算 | 同上 |
| 5 | `boll_upper` | 可算 | 可算 | 白名单 `_MATRIX_COMPUTED_FEATURES` |
| 6 | `boll_lower` | 可算 | 可算 | 同上 |
| 7 | `sd20` | 可算 | **不可算** | 不在白名单，不匹配任何前缀 |
| 8 | `prior_high_20` | 可算 | **不可算** | 同上 |
| 9 | `prior_low_10` | 可算 | **不可算** | 同上 |
| 10 | `prior_high_55` | 可算 | **不可算** | 同上 |
| 11 | `prior_vol_20` | 可算 | **不可算** | 同上 |
| 12 | `prior_high_250` | 可算 | **不可算** | 同上 |
| 13 | `vol60` | 可算 | **不可算** | 同上（`vol_ma5` / `vol_ma10` 在白名单，`vol60` 不是） |
| 14 | `prior_amount_20` | 可算 | **不可算** | 同上 |

覆盖率 **6/14**。**未同步的 8 个（点名，列入本批交付范围）**：`sd20`、`prior_high_20`、`prior_low_10`、`prior_high_55`、`prior_vol_20`、`prior_high_250`、`vol60`、`prior_amount_20`。

**7.13.2 失败方式与真正的缺陷位置**

8 个缺失因子在 `matrix_feature` 里 fail-closed（`matrix.py:4557` 抛 `ValueError: unsupported matrix feature: <id>`），**不产生静默错值** —— 这一点比「悄悄给 null」好，不能算缺陷。真正的缺陷是三处：

1. **失败得太晚**：抛错点在评分列物化时，此时已加载全市场矩阵、算过前序因子 → 一次回测白跑。
2. **「未实现」被编码成「无值」**：`FactorProvider.materialize_matrix_field` 基类直接 `return None`（`app/extensions/factors.py:86-88`），任何新 Provider 都继承这个默认 → 缺口不在注册时暴露。
3. **支持与否由名字拼写决定**：白名单 **60** 个名（`matrix.py:4184-4204`）+ 6 条前缀启发式（`:4216-4223`）。`ma20` 因为「长得像」通过，`vol60` / `sd20` / `prior_*` 因为「长得不像」被拒 —— 同一语义类（滚动统计）的支持性由拼写决定。

**7.13.3 硬要求（字段级，5 条）**

1. **准入前置**：策略/因子回测与 X1 计划生成，必须在**消费行情之前**判所引用因子集的 `matrix_supported`。有 false → HTTP 400，`detail = {"code":"FS10","factor_id":"<id>","matrix_supported":false,"panel_supported":true}`。禁止把判定留到 `matrix_feature` 中途抛错。
2. **能力来源收敛为一张显式映射表** `MATRIX_KERNELS: dict[str, {kernel, requires_fields}]>`，白名单与前缀启发式降为「该表的派生视图」；双写期只允许一个来源判定「支持与否」，并用一致性断言锁死（`F-A41-3`）。长期由 `FactorSpec.matrix_kernel` 字段取代该表（与 `status` / `alias_of` 同批的 P2 工作）。
3. **`requires_fields` 必须声明并可判**：核依赖的行情字段（如 `amount`）在准入时与 `market.fields` 求交，缺失 → `FS10` 且 `detail["missing_fields"]` 非空；**不得**在核内 `KeyError`。
4. **8 个核的语义锚**（与面板路径同名同义，逐条写死）：
   - `sd20` = `close` 的 20 日滚动样本标准差（`ddof=1`，与面板 `rolling_std` 一致），requires `close`；
   - `prior_high_20` = `high` 的 20 日滚动最大值 `shift(1)`，requires `high`；
   - `prior_low_10` = `low` 的 10 日滚动最小值 `shift(1)`，requires `low`；
   - `prior_high_55` = `high` 的 55 日滚动最大值 `shift(1)`，requires `high`；
   - `prior_high_250` = `high` 的 250 日滚动最大值 `shift(1)`，requires `high`；
   - `prior_vol_20` = `volume` 的 20 日滚动样本标准差，requires `volume`；
   - `vol60` = 日收益率（`close / close.shift(1) - 1`）的 60 日滚动样本标准差，requires `close`；
   - `prior_amount_20` = `amount` 的 20 日滚动均值 `shift(1)`，requires `amount`。
   `shift(1)` 是 D1 定稿口径（`prior_X_N = ts_delay(ts_max(high,N),1)`），**核内不得省**；窗口不足必须是 `NaN`（不能填 0、不能前向填充）。
5. **数值口径**：新核输出 `float32`（与既有字段一致），与面板 `float64` 的比较**按 §7.14 的 `F-A11a`–`F-A11d` 判，不按 `1e-10`**。矩阵侧不因本条款改 `float64`（理由见 §7.14.3 候选 A）。

**7.13.4 判据 F-A41（5 条，可写成 5 个 pytest 用例）**

| # | 断言 |
| --- | --- |
| F-A41-1 | 14 个基线 id 逐个 `matrix_supported` 与 §7.13.1 表一致（6 true / 8 false），且 14/14 的 `panel_supported` 为 true |
| F-A41-2 | 引用任一 `matrix_supported=false` 因子的回测/X1 请求 → 400 `FS10`，且**发生在读盘之前**（monkeypatch 行情读取与 `repo.*` 计数 == 0） |
| F-A41-3 | 一致性：映射表每个 true 的 id 经 `matrix_feature` 得 `float32` 且形状 == `market.shape`；每个 false 的 id 抛 `ValueError`。白名单/前缀派生视图与表逐项相等（差异集为空） |
| F-A41-4 | `requires_fields` 未满足（如 `field_columns` 不含 `amount` 而请求 `prior_amount_20`）→ 400 `FS10`，`detail["missing_fields"]==["amount"]`，不抛 `KeyError` |
| F-A41-5 | 基类 `FactorProvider.materialize_matrix_field` 未被覆写时 → `NotImplementedError`；全仓不再存在「返回 `None` 表示未实现」的路径（`grep` 断言 + 单测） |

**7.13.5 本条款不做什么**

不改矩阵侧 `float32`（理由见 §7.14.3）；不改面板路径与既有 6 个因子；不提供「缺能力时悄悄给 `null` 继续跑」的降级；不把 8 个核的实现写进契约（实现归系统开发工程师）。""")


# --------------------------------------------- 块 C：§7.14 F-A11 分层判据
B_714 = crlf("""### 7.14 `F-A11` 裁定：分层判据（v0.7 裁定；原判据在 `float32` 存储下不可达）

**7.14.1 原判据（同一句，三处出现：v0.4 `:1198` / v0.5 `:1267` / v0.6 `:1421`）**

> `F-A11` | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致

**7.14.2 为什么不可达（事实，不是意见）**

矩阵侧字段的存储精度是 `float32`：基础行情字段（`matrix.py:1006-1010`）、财务因子（`fundamentals.py:146-195`，注释写明「每个因子只物化一张 float32 TxN 矩阵」）、Provider 核输出一致。`float32` 的相对表示误差上界是 `2^-24 = 5.96e-08`，所以**任何**非零量级的列都必然超过绝对 `1e-10` —— 与算法对不对无关。

本机实测（2026-11-07 17:2x 复跑，319 个日分区 2025-07-14…2026-11-06、5,612 只标的、1,747,777 行；`date=2026-10-26` 分区缺 `part.parquet`，故 319 而非 320）：

| factor_id | 中位量级 | `max abs(f64−f32)` | 超 `1e-10` 行数 | 有限样本数 | 相对误差 max |
| --- | ---: | ---: | ---: | ---: | ---: |
| `sd20` | 0.6193 | 2.943e-05 | 1,629,065 | 1,641,292 | 5.956e-08 |
| `prior_high_20` | 17.37 | 1.172e-04 | 1,490,407 | 1,635,694 | 5.719e-08 |
| `prior_low_10` | 14.59 | 1.172e-04 | 1,562,686 | 1,691,702 | 5.720e-08 |
| `prior_high_55` | 18.80 | 5.859e-05 | 1,297,082 | 1,440,413 | 5.719e-08 |
| `prior_high_250` | 22.99 | 2.930e-05 | 326,042 | 369,736 | 5.714e-08 |
| `prior_vol_20` | 3.886e+04 | 8.429e-01 | 1,641,291 | 1,641,292 | 5.957e-08 |
| `vol60` | 0.02769 | 7.406e-09 | 1,275,905 | 1,412,607 | 5.955e-08 |
| `prior_amount_20` | 1.505e+08 | 2.033e+03 | 1,624,799 | 1,635,694 | 5.960e-08 |
| `ma20`（已「覆盖」） | 15.64 | 1.191e-04 | 1,628,048 | 1,641,292 | 5.912e-08 |
| `boll_upper`（已「覆盖」） | 17.06 | 1.202e-04 | 1,640,951 | 1,641,292 | 5.953e-08 |
| `boll_lower`（已「覆盖」） | 14.09 | 1.073e-04 | 1,640,887 | 1,641,292 | 5.956e-08 |

三处读法：

1. **相对误差 max 每列都是 `5.96e-08 = 2^-24`**，绝对差随量级线性放大（`prior_amount_20` 到 2.03e+03）→ 这是 `float32` 存储量化，不是算法差；
2. **这只是下界**：只算了「同一 `float64` 值存成 `float32`」的舍入，未计 `float32` 累加误差 → 真实双路径差只会更大；
3. **连 6 个「已覆盖」的因子也过不了**（`ma20` 1.19e-04）→ 原 `F-A11` 按字面是 **14/14 不成立**，不是「8 个缺能力、6 个合格」。**能力缺口 = 8 个；判据不可达 = 14 个**，这两件事必须分开记账。

**7.14.3 三个候选与取舍**

| 候选 | 做法 | 代价 | 结论 |
| --- | --- | --- | --- |
| A 矩阵侧全改 `float64` | 所有字段与核输出 `float64` | 单字段内存翻倍：全历史 2,141 日 × 5,612 只 = 12.0M 格，`float32` 48.1 MB → `float64` 96.2 MB；20 个字段 0.96 GB → 1.92 GB，压穿磁盘缓存上限 **512 MB**（`matrix.py:66`）；`dtype=np.float32` 71 处 + `float32` 引用 160 处逐个复核；8 个新核按 `float64` 重验；回测内存峰值与 mmap 布局改变属性能回归面 | **否决** |
| B 面板侧 cast 成 `float32` 再比 | 两侧同精度，差异归零 | 判据变成自证；同时**摧毁 `F-A10`**（面板对研究侧 `float64` 的 `1e-10` 锚），台账复现靶值失去依据 | **否决** |
| C 分层判据（采纳） | 结构零容忍 + 数值相对容差 + 决策等价 + 权威路径 | 容差从绝对 `1e-10` 改为相对 `2^-23`；新增 1 个「决策等价」脚本 | **采纳** |

**7.14.4 裁定文本：`F-A11` 由四条组成（替换原单条，编号沿用 `F-A11` 以便对照）**

| # | 名称 | 断言（可直接写成测试） |
| --- | --- | --- |
| F-A11a | 结构一致（零容忍） | 面板与矩阵的 `isnan` / `isinf` 掩码**逐位相等**（对称差元素数 == 0），形状与轴标签相等 |
| F-A11b | 数值一致（相对容差） | 逐列 `rel = max\|p−m\| / max(\|p\|, 1e-12) ≤ 2^-23 = 1.192e-07`；且逐列 `max\|p−m\| ≤ 2^-23 × max\|p\|`。样本必须同时覆盖 NaN 与非 NaN 行 |
| F-A11c | 决策等价 | 对该因子参与的每个判据谓词（如 `close >= prior_high_20`、`vol60 <= 0.10`），面板判定与矩阵判定的 jaccard ≥ 0.9999 **且翻转行数 == 0** |
| F-A11d | 权威路径 | **面板路径（`float64`）是唯一权威**：台账数值、`F-A10` 对账、研究复核只取面板；矩阵值**不得**回写台账/证据/清单；矩阵回测结果必须标 `matrix_path=true`、`tolerance=\"eps32"`、`f_a11=\"a/b/c\"` |

容差 `2^-23`（而非实测的 `2^-24`）是留一倍余量：实测只覆盖「单次舍入」，不含 `float32` 累加与 `mmap` 落盘往返。**该容差只适用于「面板 vs 矩阵」这一对**；面板 vs 研究侧仍是 `1e-10`（`F-A10` 不变）。

**7.14.5 判别力：放宽后仍抓得住真错**

同一样本、同一谓词 `close >= prior_high_20`：

| 情形 | 相对误差 max | 绝对误差 max | jaccard | 翻转行数 |
| --- | ---: | ---: | ---: | ---: |
| `float32` 量化（真实存在的误差） | 5.96e-08 | 1.17e-04 | **1.0000** | **0** |
| 语义错：`prior_high_20` 漏 `shift(1)` | **0.6682** | **678.01** | **0.1973** | 64,815（union 80,750；正确侧 80,413 / 错侧 16,272） |

量化误差与语义误差差 **约 4 个数量级**；`F-A11b`（相对 `2^-23`）与 `F-A11c`（jaccard ≥ 0.9999 且零翻转）都不会把语义错当噪声放过。另一条实测：`vol60 <= 0.10` 在量化下 jaccard 1.0000、翻转 0（命中 1,412,259 行）。

**7.14.6 与 `F-A10` 的边界**

`F-A10`（面板 vs 研究侧 `float64`，`1e-10`）**不变**，也不受本裁定影响；本裁定只解决「面板 `float64` vs 矩阵 `float32`」这一对路径的比较口径。两条判据的**权威方向相反**：`F-A10` 证明实现与研究同源，`F-A11d` 规定一旦两条实现路径不一致，以面板为准。""")

# ---------------------------------------------------------------- 登记行
D_ROW = crlf("""| v0.7（裁定） | 2026-11-07 | **R7（只追加；不改冻结 v0.3、不改 v0.4/v0.5/v0.6 正文）**：①§1 插入 **`G2.1`**（`entry_fill`/`exit_fill`/`entry_price_basis` 必须显式传入，缺省即 `FS08`；3 条例外显式打标；判据 `F-A40`）；②新增 **§7.13** 矩阵路径能力清单与准入前置（6/14，**点名 8 个未同步因子**：`sd20`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`prior_high_250`/`vol60`/`prior_amount_20`；准入 `FS10`；判据 `F-A41`）；③新增 **§7.14** 把 `F-A11` 的 `1e-10` 绝对容差替换为 `F-A11a`–`F-A11d` 分层判据（结构零容忍 / 相对 `2^-23` / 决策等价 / 面板 `float64` 为唯一权威）。逐条原句、新句与实测见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` | 开发经理 G-A2 开门条件（D5）+ B0b 交付范围（矩阵路径点名）+ 架构师本机实测（14 个 id 矩阵解析、1.75M 行 `float32` 量化、语义错反例）|""")

C_ROW = crlf("""| **R7（D5 / 矩阵路径点名 / `F-A11` 分层判据）** | 见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md`：§1 新增 `G2.1`（`FS08`，`F-A40`）；新增 §7.13（矩阵 6/14，点名 8 个，`FS10`，`F-A41`）；新增 §7.14（`F-A11` → `F-A11a`–`F-A11d`，权威 = 面板 `float64`）。**条款级新增 + 1 条判据替换**，不改其余判据语义；本行在 v0.7 落盘前仅为登记位 |""")

ROW_F11_NEW = crlf("""| `F-A11`（v0.7 已替换为分层判据） | 双路径一致 | 见 §7.14：`F-A11a` 结构零容忍 / `F-A11b` 相对 `2^-23` / `F-A11c` 决策等价 / `F-A11d` 面板 `float64` 为唯一权威。原「逐位 `max_abs_diff < 1e-10`」在 `float32` 存储下 14/14 不可达（§7.14.2 实测）|""")

H1_OLD = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.5（2026-11-07）"
H1_NEW = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.7（2026-11-07）"

F11_ANCHOR = "| F-A11 | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致 |"
G2_ANCHOR = "任何在 T 日使用 T+1 数据的实现，验收直接不通过。"
S8_ANCHOR = "## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）"
C_ANCHOR = "| 实现与验收 | 分别由系统开发工程师、独立审核工程师承担；**本文件不下验收结论** |"
D_ANCHOR = "| v0.6（追认） | 2026-11-07 |"

E_TPL = (
    "本文件正文 sha256：`@BODY_SHA@`（校验：`head -c @BODY_LEN@ \"@NAME@\" | sha256sum`）· "
    "正文 `@BODY_LEN@ B` · 行数 `@LINES@` · 版本 **v0.7（2026-11-07 R7 裁定，未冻结）**· "
    "冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` §7（不写进正文，避免自指）· "
    "生成 2026-11-07 v0.7 = **v0.6 逐字节为底** + R7 只追加：§1 新增 `G2.1` / 新增 §7.13 矩阵路径能力清单与准入前置 / 新增 §7.14 `F-A11` 分层判据 / §8.1 `F-A11` 行替换 / 修订记录与 §9 各 +1 行 / 标题版本号 v0.5→v0.7 · "
    "**v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象；"
    "v0.5（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…c4a21a`）为 `F-A30`–`F-A33` 绑定对象；"
    "v0.6（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）为清单 v2（`F-A34`–`F-A39`）绑定对象** · "
    "v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
)


def _one(lines, needle):
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    if len(hits) != 1:
        sys.exit("锚点不唯一/缺失: %r -> %r" % (needle, hits))
    return hits[0]


def merge(raw: str, name: str):
    idx = raw.index(MARK)
    body = raw[:idx]
    lines = body.split("\r\n")
    if lines[0] != H1_OLD:
        sys.exit("H1 不是预期值: %r" % lines[0])
    lines[0] = H1_NEW
    i = _one(lines, G2_ANCHOR)
    lines[i + 2:i + 2] = A_G21.rstrip("\r\n").split("\r\n") + [""]
    j = _one(lines, S8_ANCHOR)
    lines[j:j] = (B_713 + "\r\n\r\n" + B_714).rstrip("\r\n").split("\r\n") + [""]
    f = _one(lines, F11_ANCHOR)
    lines[f:f + 1] = [ROW_F11_NEW]
    k = _one(lines, C_ANCHOR)
    lines[k + 1:k + 1] = [C_ROW]
    d = _one(lines, D_ANCHOR)
    lines[d + 1:d + 1] = [D_ROW]
    body_new = "\r\n".join(lines)
    bb = body_new.encode("utf-8")
    footer = crlf(
        E_TPL.replace("@BODY_SHA@", sha(bb))
        .replace("@BODY_LEN@", str(len(bb)))
        .replace("@LINES@", str(body_new.count("\n") + 1))
        .replace("@NAME@", name)
    ) + "\r\n"
    return body_new, footer


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "v07_candidate.md"))
    ap.add_argument("--land", action="store_true")
    a = ap.parse_args()
    out = os.path.join(ROOT, OUT_NAME) if a.land else a.out
    raw = open(V06, "rb").read().decode("utf-8")
    body_new, footer = merge(raw, OUT_NAME)
    v07 = (body_new + footer).encode("utf-8")
    bb = body_new.encode("utf-8")
    open(out, "wb").write(v07)
    r = subprocess.run(["git", "diff", "--no-index", "--numstat", V06, out], cwd=ROOT, capture_output=True, text=True)
    print("V07_BYTES", len(v07))
    print("V07_LINES", (body_new + footer).count("\n"))
    print("V07_BODY_BYTES", len(bb))
    print("V07_BODY_SHA", sha(bb))
    print("V07_FULL_SHA", sha(v07))
    print("NUMSTAT", r.stdout.strip())
    print("BLOCK_A_LINES", A_G21.rstrip("\r\n").count("\n") + 1)
    print("BLOCK_B_LINES", (B_713 + "\r\n\r\n" + B_714).rstrip("\r\n").count("\n") + 1)
