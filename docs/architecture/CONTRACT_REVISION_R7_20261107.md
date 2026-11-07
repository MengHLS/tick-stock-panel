# 契约修订对照 R7（D5 必修 / 矩阵路径点名 / `F-A11` 判据裁定）

- 版本：**R7** · 2026-11-07 17:2x · 作者：系统架构师
- 底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`（**一字未改**，162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）
- 产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（**已落盘 2026-11-07 17:5x**，四元组见 §7.2；并入了本批四处，见 §7.4）
- 边界：不写业务实现、不改因子口径与策略规格、不动 `backend/**`、不提交、不部署、不改 v0.3/v0.4/v0.5/v0.6 任何字节

> **编号说明（先读）**：派单要求文件名 `CONTRACT_REVISION_R6_20261107.md`、产物 `v0.6`。但 **R6 与 v0.6 已在 17:15 被「清单 v2 规格」占用**（`docs/architecture/CONTRACT_REVISION_R6_20261107.md`、`FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`，`F-A34`–`F-A39`）。为不覆盖已落盘修订、不撕 v0.6 的四元组，本批按 **R7 / v0.7** 编号，判据接 `F-A40`。派单里「不改 v0.4 正文」也据此更新为「不改 v0.4/v0.5/v0.6 正文」。逐条说明见 §5。

---

## 0. 前置事实（本轮实测，全部可复跑）

| # | 项 | 实测值 | 命令 / 落点 |
| --- | --- | --- | --- |
| 1 | HEAD / 工作区 | `65c6e42f`；`git status --porcelain` = 28 项 | `git rev-parse --short HEAD` |
| 2 | v0.3 冻结副本 | 89,833 B / 914 行 / 全文 `5eb97724…565903` / 正文 `head -c 89350` → `b082d902…f9bfef` | `wc -c -l` + `sha256sum` + `head -c 89350 \| sha256sum` |
| 3 | v0.4（活） | 128,007 B / 1,226 行 / 全文 `5bd81a74…c5531` / 正文 `head -c 127043` → `71708877…d16bc` | 同上 |
| 4 | v0.5（活） | 138,729 B / 1,298 行 / 全文 `c7740508…c4a21a` / 正文 `head -c 137598` → `082d26fa…af7fae` | 同上 |
| 5 | v0.6（活） | 162,361 B / 1,454 行 / 全文 `946a1d86…616810` / 正文 `head -c 160819` → `e3a4db17…2576ec` | 同上 |
| 6 | 引擎默认（与 G2 相反） | `matching="close_t"`（`engine.py:229`）；`entry_price_basis="adjusted"`（`:258`）；`entry_fill`/`exit_fill` 为 `None` → `__post_init__` 回退 `matching`（`:280-283`） | 读码 |
| 7 | 服务层同样回退 | `StrategyBacktestConfig.matching="open_t+1"`、`entry_fill`/`exit_fill=None`（`strategy.py:717-719`），回退（`:744-747`） | 读码 |
| 8 | `entry_price_basis` 不在请求模型里 | `StrategyBacktestRequest` 只有 `matching`/`entry_fill`/`exit_fill`（`api/backtest.py:358-360`）；唯一来源是 META，缺省 `"adjusted"`（`execution_policy.py:78`、`:141-144`） | 读码 |
| 9 | 既有 fail-closed 先例 | `engine.py:296`（`plan_at_signal_close` 且 `entry_fill != "open_t+1"` → `ValueError`）；`strategy.py:1578-1580`（full 模式在**读数据前**校验） | 读码 |
| 10 | full 模式与 G2 不相容 | `_FULL_UNSUPPORTED_RULES` 含 `("entry_price_basis", "原始价入场口径")`（`engine.py:341-356`） | 读码 |
| 11 | 分钟路径硬编码 | `entry_fill="close_t"`（`strategy.py:2615`） | 读码 |
| 12 | 迁移面 | `backend/app/strategy/seeds/` **25** 个种子文件**无一**含 `backtest_defaults`（命中 0）；`D:/TSP/data/user_data` 下**无 `strategies` 目录** | `grep -rl backtest_defaults backend/app/strategy/seeds \| wc -l` |
| 13 | 矩阵路径能力（14 个基线因子） | **6 可算 / 8 抛 `ValueError: unsupported matrix feature`**（本轮脚本复跑，见 §3.1） | 见 §3.1 |
| 14 | 白名单规模 | `_MATRIX_COMPUTED_FEATURES` = **60** 个名（`matrix.py:4184-4204`）；另有 6 条前缀启发式（`:4216-4223`） | AST/读码 |
| 15 | Provider 基类静默 | `FactorProvider.materialize_matrix_field` → `return None`（`app/extensions/factors.py:86-88`） | 读码 |
| 16 | `float32` 面 | 基础行情字段（`matrix.py:1006-1010`）、财务因子（`fundamentals.py:146-195`，注释「每个因子只物化一张 float32 TxN 矩阵」）、Provider 核输出；磁盘缓存上限 **512 MB**（`matrix.py:66`） | 读码 + `grep -c` |
| 17 | `float32` 量化（n = 1,747,777 行 / 319 分区 / 5,612 只） | 8 个因子 + `ma20`/`boll_*` 的相对误差 max **每列都 ≈ `2^-24` = 5.96e-08**；`ma20` 绝对差 1.19e-04 也超 `1e-10` | 见 §4.2 |
| 18 | 决策等价（`float64` 判定 vs `float32` 判定） | `close >= prior_high_20`：jaccard **1.0000**、翻转 **0**（正例 80,413）；`vol60 <= 0.10`：jaccard **1.0000**、翻转 **0**（命中 1,412,259） | 见 §4.5 |
| 19 | 语义错可判别（反例） | `prior_high_20` 漏 `shift(1)`：相对误差 max **0.6682**、绝对 max **678.01**、jaccard **0.1973**、翻转 64,815 | 见 §4.5 |

**样本边界**：`D:/TSP/data/kline_daily` 共 2,141 个日分区；量化样本取最近 **320** 个目录，其中 `date=2026-10-26` **缺 `part.parquet`**（另有分区 schema 漂移，多 `quote_ts` 列，逐文件按列读取规避），实际 **319** 个分区。**样本不是全历史**；结论只用其量级（`2^-24` 量化与决策等价），不外推为全历史极值。上一轮（17:0x）同脚本取 320 分区得 n = 1,753,345，与本轮同量级、结论相同。

---

## 1. 结论（三件，逐件可判定）

1. **D5 已定则**：`entry_fill` / `exit_fill` / `entry_price_basis` **必须显式传入，缺省即报错（`FS08`）**，不回退默认、不告警降级；三条例外（full 模式、分钟路径、legacy 信号回测）必须**显式打标**而非靠默认值。判据 `F-A40`（5 条）。
2. **矩阵路径已点名并前移失败点**：6/14 的现状写进交付范围，**点名 8 个未同步因子**；失败点从「回测中途 `ValueError`」前移到「准入 400 `FS10`」；能力来源由「白名单 + 前缀启发式」收敛为一张显式映射表。判据 `F-A41`（5 条）。
3. **`F-A11` 已裁定分层**：`1e-10` 绝对容差在 `float32` 存储下 **14/14 不可达**（连 6 个「已覆盖」的也过不了），替换为 `F-A11a`（结构零容忍）/ `F-A11b`（相对 `2^-23`）/ `F-A11c`（决策等价，零翻转）/ `F-A11d`（**面板 `float64` 为唯一权威**）。

**契约文件状态：v0.3 / v0.4 / v0.5 / v0.6 一份未改；v0.7 已落盘（未冻结）。** 本文承载三段可机械合并的逐字节文本（§2.3、§3.2、§4.3）与三条登记行（§6），合并后四元组见 §7.2。

---

## 2. D5 修文（G2 的子条款 `G2.1`）

### 2.1 原句（v0.6 §1，`:50-51`，未改）

> **G2 as-of 语义**
> 信号在 T 日**收盘后**产生，只用 T 日及以前可知的信息；最早成交在 T+1 开盘（`entry_fill="open_t+1"`，`entry_price_basis="raw"`）。任何在 T 日使用 T+1 数据的实现，验收直接不通过。

### 2.2 为什么原句不足：缺的是「怎么传进来」，不是「什么值」

原句定义了**正确值**，没定义**传不进来时怎么办**；而全链路默认值与它相反，且**三处默认互不相同**（§0 第 6–8 项）：引擎 `close_t` / `adjusted` 且 `None` 回退 `matching`；服务层 `open_t+1` 再回退一次；`entry_price_basis` 根本不在策略回测请求模型里，只从 META 读、缺省 `adjusted`。于是「漏传」不产生任何信号：成交时点静默变成 T 日收盘、成交价静默变成复权价。**这是本契约里唯一一处「违反 G2 却不报错」的路径**，故必须以拒绝条件收口。

补充事实（登记，不修）：`mode="full"` 与 `entry_price_basis="raw"` **不相容**（`_FULL_UNSUPPORTED_RULES`），即 full 模式**无法**满足 G2，只能拒绝或改用 `position`。

### 2.3 新句（待插入 §1，G2 段落之后；逐字节，含行尾 CRLF；源 = `build_contract_r7.py` 的 `A_G21`，29 行）

```markdown
**G2.1 执行口径必须显式传入（v0.7 追加；G2 的子条款，不增加 §1 的 G1–G8 条数）**

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
| F-A40-5 | 校验在读盘之前：monkeypatch 行情读取入口与 `repo.*` 读调用，计数 == 0 |
```

### 2.4 依据、代价与一处超清单说明

- **依据**：G2 本身 + 三处默认的实测（§0 第 6–8 项）+ 两条既有 fail-closed 先例（§0 第 9 项）。这不是新增口径，是把既有口径改成**可判定的拒绝条件**。
- **代价（必须写进排期）**：本条款生效后，**所有未补 META 的策略全部 `FS08`**（现状 25 个种子文件无一含 `backtest_defaults`，且盘上无 `strategies` 目录）。修复属**数据变更**：每个策略 `META.backtest_defaults` 补三个字段。**禁止**用「把代码默认值改成 raw」代偿。
- **被否决的更软写法**：「缺省时告警 + 标 `g2_defaulted=true`」——告警在批处理/worker 里没人看，且 `g2_defaulted` 的结果与合规结果混在同一结果表里，后续无法区分；与「回测-模拟盘逐日一致率」这类验收直接冲突。
- **错误码**：`FS08`（`FS` 族第 8 个，`FS01`–`FS07` 已占用）。全仓 `backend/` 目前没有任何 `FS0x` 常量（`grep` 命中 0，这些码只存在于契约文本），故属纯契约侧预留，不占实现面。
- **超清单一处（明示，不改口径）**：派单只点 `entry_fill` 与 `entry_price_basis` 两个字段，我把 **`exit_fill` 也纳入必填**。理由可判定：`__post_init__` 的同一段回退逻辑同时覆盖 `exit_fill`（`engine.py:280-283`、`strategy.py:744-747`），只堵两个会留下同类静默路径——清仓口径可静默变成 T 日收盘，而 G2 只约束了入场。若研究侧认为清仓时点不在 G2 管辖内，请回批；我未改任何口径定义，只把「静默」改成「报错」。

---

## 3. 矩阵路径（新增 §7.13，交付范围点名）

### 3.1 现状复现（单点解析，不是整轮回测）

```bash
cd C:/work/sourcecode/tick-stock-panel
./backend/.venv/Scripts/python.exe -X utf8 - <<'PY'
import sys, numpy as np
sys.path.insert(0, "backend")
from app.backtest import matrix as M
from app.extensions.factors import ensure_factor_providers
ensure_factor_providers()
targets = ["ma20","ma60","ma120","ma200","boll_upper","boll_lower",
           "sd20","prior_high_20","prior_low_10","prior_high_55",
           "prior_vol_20","prior_high_250","vol60","prior_amount_20"]
class Fake:
    shape = (2, 3); fields = {}; valid_bars = None
    def field(self, name): raise KeyError(name)
    @property
    def close(self): return np.zeros(self.shape, dtype=np.float32)
    @property
    def high(self): return self.close
    @property
    def low(self): return self.close
    @property
    def volume(self): return self.close
m = Fake()
for t in targets:
    try: print(t, "OK", M.matrix_feature(m, t).dtype)
    except Exception as e: print(t, "RAISE", type(e).__name__, e)
PY
```

本轮输出（17:2x 复跑）：`OK_COUNT 6`（`ma20`/`ma60`/`ma120`/`ma200`/`boll_upper`/`boll_lower`，均 `float32`）；8 个 `RAISE ValueError: unsupported matrix feature: <id>`，即 `sd20`、`prior_high_20`、`prior_low_10`、`prior_high_55`、`prior_vol_20`、`prior_high_250`、`vol60`、`prior_amount_20`；`WHITELIST 60`。

**这条结论的边界**：它证明的是「`matrix_feature` 单点解析这 8 个 id 会抛错」，**不等于**「引用这些因子的策略一定跑不了」——走面板路径仍可跑。矩阵路径不可用是**能力缺口**，不是数值错误。

### 3.2 新句（待插入 §7.12 之后、§8 之前；逐字节，含行尾 CRLF；源 = `build_contract_r7.py` 的 `B_713`）

```markdown
### 7.13 矩阵回测路径的能力清单与准入前置（v0.7 追加；交付范围点名）

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

不改矩阵侧 `float32`（理由见 §7.14.3）；不改面板路径与既有 6 个因子；不提供「缺能力时悄悄给 `null` 继续跑」的降级；不把 8 个核的实现写进契约（实现归系统开发工程师）。
```

### 3.3 取舍（为什么不继续加前缀规则 / 为什么先落映射表）

- **继续加前缀规则**会让「支持矩阵」变成拼写游戏：`ma20` 恰好长得像就通过，`vol60` 恰好长得不像就被拒，同一语义类的支持性由名字决定。**否决**。
- **直接加 `FactorSpec.matrix_kernel` 字段**（长期正解）需动 `registry.py` 的 `FactorSpec`，与 P2 的 `status` / `alias_of` 同批，会与本批 B0b 排期耦合。**裁定**：B0b 先落 `MATRIX_KERNELS` 映射表，P2 落字段时把该表降为编译期派生表，双写期用 `F-A41-3` 锁死「只有一个来源判定支持与否」。
- **`prior_amount_20` 的字段依赖**：矩阵侧多个核已用 `amount`（`matrix.py:4335`、`:4441`、`:4463`、`:4540` 等），但**能否用取决于调用方的 `field_columns`**。故核必须在表里声明 `requires_fields`，准入时求交后判 `FS10`，不得在核内 `KeyError`。

---

## 4. `F-A11` 判据裁定（新增 §7.14）

### 4.1 原判据与三处出现

> `F-A11` | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致

v0.4 `:1198`、v0.5 `:1267`、v0.6 `:1421` 为同句（**派单引用的 `:1198` 是 v0.4 行号**，见 §5 关于派单基线的说明）。

### 4.2 量化实测（n = 1,747,777 行，319 个交易日 × 5,612 只）

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

读法三条：① 相对误差 max 每列都 ≈ `2^-24`，绝对差随量级线性放大（`prior_amount_20` 到 2.03e+03）→ **存储量化**，不是算法差；② 这只是**下界**（只算单次舍入，未计 `float32` 累加）→ 真实双路径差只会更大；③ **连 6 个「已覆盖」的也过不了**（`ma20` 1.19e-04）→ 原判据按字面 **14/14 不成立**。**能力缺口 = 8 个；判据不可达 = 14 个**，两件事分开记账。

复跑脚本要点（可复现）：读最近 320 个 `date=*` 目录（`date=2026-10-26` 缺 `part.parquet` → 319；分区有 `quote_ts` 列漂移 → 逐文件 `read_parquet(columns=[...])`，`volume` dtype 漂移 → 统一 `cast(Float64)`），按 `symbol` 排序后 `rolling_*(...).over("symbol")` 算 `float64`，再 `astype(np.float32).astype(np.float64)` 比差。

### 4.3 新句（待插入 §7.13 之后、§8 之前；逐字节，含行尾 CRLF；源 = `build_contract_r7.py` 的 `B_714`）

```markdown
### 7.14 `F-A11` 裁定：分层判据（v0.7 裁定；原判据在 `float32` 存储下不可达）

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
| F-A11d | 权威路径 | **面板路径（`float64`）是唯一权威**：台账数值、`F-A10` 对账、研究复核只取面板；矩阵值**不得**回写台账/证据/清单；矩阵回测结果必须标 `matrix_path=true`、`tolerance="eps32"`、`f_a11="a/b/c"` |

容差 `2^-23`（而非实测的 `2^-24`）是留一倍余量：实测只覆盖「单次舍入」，不含 `float32` 累加与 `mmap` 落盘往返。**该容差只适用于「面板 vs 矩阵」这一对**；面板 vs 研究侧仍是 `1e-10`（`F-A10` 不变）。

**7.14.5 判别力：放宽后仍抓得住真错**

同一样本、同一谓词 `close >= prior_high_20`：

| 情形 | 相对误差 max | 绝对误差 max | jaccard | 翻转行数 |
| --- | ---: | ---: | ---: | ---: |
| `float32` 量化（真实存在的误差） | 5.96e-08 | 1.17e-04 | **1.0000** | **0** |
| 语义错：`prior_high_20` 漏 `shift(1)` | **0.6682** | **678.01** | **0.1973** | 64,815（union 80,750；正确侧 80,413 / 错侧 16,272） |

量化误差与语义误差差 **约 4 个数量级**；`F-A11b`（相对 `2^-23`）与 `F-A11c`（jaccard ≥ 0.9999 且零翻转）都不会把语义错当噪声放过。另一条实测：`vol60 <= 0.10` 在量化下 jaccard 1.0000、翻转 0（命中 1,412,259 行）。

**7.14.6 与 `F-A10` 的边界**

`F-A10`（面板 vs 研究侧 `float64`，`1e-10`）**不变**，也不受本裁定影响；本裁定只解决「面板 `float64` vs 矩阵 `float32`」这一对路径的比较口径。两条判据的**权威方向相反**：`F-A10` 证明实现与研究同源，`F-A11d` 规定一旦两条实现路径不一致，以面板为准。
```

### 4.4 为什么「改容差」不是放水（判别力论证）

量化误差与语义误差差 4 个数量级（5.96e-08 vs 0.6682），且 `F-A11c` 用的是**决策等价**而不是数值等价：漏 `shift(1)` 这种错会让 `close >= prior_high_20` 的正例从 80,413 变成 16,272、jaccard 掉到 0.1973，任何一层都拦得住。相反，如果坚持 `1e-10`，实际效果是「14 个因子全部不合格」，判据失效而不是更严。

### 4.5 权威路径（这条比容差更重要）

**面板路径（`float64`）是唯一权威**：台账数值、`F-A10` 对账、研究复核只取面板；矩阵值**不得**回写台账/证据/清单；矩阵回测结果必须标 `matrix_path=true`、`tolerance="eps32"`。理由：一旦允许矩阵值进台账，台账的数字来源就随「这次跑的是哪条路径」漂移，而台账是可追溯性的锚。

---

## 5. 编号冲突与「v0.7 为什么不落盘」（必读，影响排期引用）

### 5.1 事实

| 时间 | 事件 | 落盘物 |
| --- | --- | --- |
| 16:52 | R5：v0.4 → v0.5（§7.4.2 允许面 + §7.11 V3 校验，`F-A30`–`F-A33`） | `CONTRACT_REVISION_R5_20261107.md`、`FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md` |
| 17:15 | **R6：v0.5 → v0.6（清单 v2 规格：粒度 / 记录身份 / canonical digest / `summary` 分层，`F-A34`–`F-A39`）** | `CONTRACT_REVISION_R6_20261107.md`、`FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md` |
| 17:2x | **R7（本批）：v0.6 → 候选 v0.7（D5 `G2.1` / §7.13 矩阵 / §7.14 `F-A11` 分层，`F-A40`、`F-A41`）** | 本文；候选 v0.7 **未落盘** |

派单要求的是「R6 + 产物 v0.6」。这两个名字**已在 17:15 被清单 v2 占用**，且派单引用的是 **v0.4 行号** `F-A11 :1198`（v0.5 为 `:1267`、v0.6 为 `:1421`）——说明派单写在 16:52 之前。据此：

1. **不覆盖 R6/v0.6**：覆盖会撕掉 v0.6 的四元组，而清单 v2 的 `F-A34`–`F-A39` 正绑在它上面。
2. **本批编号顺延为 R7 / 候选 v0.7**，判据接 `F-A40`/`F-A41`（`F-A34`–`F-A39` 已占用），节号接 §7.13/§7.14（§7.12 已占用）。
3. **派单里「不改 v0.4 正文」更新为「不改 v0.4 / v0.5 / v0.6 正文」**（v0.4 早于本批两个版本）。

### 5.2 为什么不落盘（三条理由，逐条可查）

1. **派单明确禁止新建第三份契约文件**。`docs/architecture/` 现有 v0.4 / v0.5 / v0.6 三份活契约 + v0.3 归档；再加 v0.7 就是第四份活契约，且 v0.6 本身 17:15 才落、尚未冻结，一小时内堆两份未冻结版本会让「哪个是现行」无从判定。
2. **v0.6 是清单 v2 的绑定对象**（`F-A34`–`F-A39`）。它能被替换的时机是独立审核对清单 v2 出 PASS 之后，不该由我这份 D5/矩阵修订顺手顶掉。
3. **文本与合并方式已逐字节固定**：`build_contract_r7.py` 内置 5 条锚点唯一性断言（锚点漂移即退出）、H1 版本号断言，任何人跑一遍都能复得 §7.2 的四元组。落盘只需 `--land`，由排期决定，不由本批决定。

### 5.3 若排期要求落盘，一条命令

```bash
cd C:/work/sourcecode/tick-stock-panel
./backend/.venv/Scripts/python.exe -X utf8 research/arch-build-20261107/build_contract_r7.py --land
wc -c -l docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md   # 须等于 §7.2
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md
head -c 178631 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md | sha256sum
```

落盘后 §9 的登记行才从「登记位」变成事实；在此之前，**F-A40/F-A41 与 `F-A11a`–`d` 只在本文有效**，不得被引用为「已进契约」。

---

## 6. 登记行与合并步骤

### 6.1 修订记录表 +1 行（插在 `| v0.6（追认） |` 行之后）

```markdown
| v0.7（裁定） | 2026-11-07 | **R7（只追加；不改冻结 v0.3、不改 v0.4/v0.5/v0.6 正文）**：①§1 插入 **`G2.1`**（`entry_fill`/`exit_fill`/`entry_price_basis` 必须显式传入，缺省即 `FS08`；3 条例外显式打标；判据 `F-A40`）；②新增 **§7.13** 矩阵路径能力清单与准入前置（6/14，**点名 8 个未同步因子**：`sd20`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`prior_high_250`/`vol60`/`prior_amount_20`；准入 `FS10`；判据 `F-A41`）；③新增 **§7.14** 把 `F-A11` 的 `1e-10` 绝对容差替换为 `F-A11a`–`F-A11d` 分层判据（结构零容忍 / 相对 `2^-23` / 决策等价 / 面板 `float64` 为唯一权威）。逐条原句、新句与实测见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` | 开发经理 G-A2 开门条件（D5）+ B0b 交付范围（矩阵路径点名）+ 架构师本机实测（14 个 id 矩阵解析、1.75M 行 `float32` 量化、语义错反例）|
```

### 6.2 §9「未覆盖与依赖」表 +1 行（插在 `| 实现与验收 |` 行之后）

```markdown
| **R7（D5 / 矩阵路径点名 / `F-A11` 分层判据）** | 见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md`：§1 新增 `G2.1`（`FS08`，`F-A40`）；新增 §7.13（矩阵 6/14，点名 8 个，`FS10`，`F-A41`）；新增 §7.14（`F-A11` → `F-A11a`–`F-A11d`，权威 = 面板 `float64`）。**条款级新增 + 1 条判据替换**，不改其余判据语义；本行在 v0.7 落盘前仅为登记位 |
```

### 6.3 §8.1 的 `F-A11` 行整行替换（唯一一处判据语义变更，明示）

```markdown
| `F-A11`（v0.7 已替换为分层判据） | 双路径一致 | 见 §7.14：`F-A11a` 结构零容忍 / `F-A11b` 相对 `2^-23` / `F-A11c` 决策等价 / `F-A11d` 面板 `float64` 为唯一权威。原「逐位 `max_abs_diff < 1e-10`」在 `float32` 存储下 14/14 不可达（§7.14.2 实测）|
```

### 6.4 标题行与 footer

- 标题：`# … 接口契约 v0.5（2026-11-07）` → `# … 接口契约 v0.7（2026-11-07）`。改动理由：v0.6 的追加没同步 H1，读文件的人第一行看到的是落后两个版本的版本号；**只改版本号，不改任何内容**。
- footer：整行替换，写入新正文 sha、行数、四元组指引与四份绑定对象（v0.4 `F-A5` / v0.5 `F-A30`–`F-A33` / v0.6 清单 v2 / v0.3 归档）。模板见 `build_contract_r7.py` 的 `E_TPL`。

### 6.5 合并做的事（构建器逐条断言锚点唯一；落盘版含本批四处并入，共 9 件）

1. H1 版本号替换（1 行，断言原文完全相等）；
2. §1 G2 段落后插 `G2.1`（锚点 `任何在 T 日使用 T+1 数据的实现，验收直接不通过。` 唯一）；
3. `## 8. 改动性质总表` 前插 §7.13 + §7.14 + §7.15（锚点唯一）；
4. §8.1 `F-A11` 行替换（锚点唯一）+ §9 表 +1 行 + 修订记录 +1 行；
5. footer 按新正文重算。

**不改任何其它既有行**：`git diff --no-index --numstat` 实际 **+250 / −8**（8 = 八处替换行：H1 / §2.6 `A7` / §2.6 注 2 窗口行 / §2.6 注 2 代价行 / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer 自指哈希）。

---

## 7. 四元组与 `+/-` diff 统计

### 7.1 四份基准（本轮逐字节复算，均未变）

| 对象 | 字节 | 行 | 正文前缀 | 正文 sha | 全文 sha |
| --- | ---: | ---: | --- | --- | --- |
| v0.3 `archive/…_v0.3_FROZEN.md` | 89,833 B | 914 | `head -c 89350` | `b082d902…f9bfef` | `5eb97724…565903` |
| v0.4 `FACTOR_ENGINE_CONTRACTS_20261107.md` | 128,007 B | 1,226 | `head -c 127043` | `71708877…d16bc` | `5bd81a74…c5531` |
| v0.5 `…_v0.5.md` | 138,729 B | 1,298 | `head -c 137598` | `082d26fa…af7fae` | `c7740508…c4a21a` |
| **v0.6 `…_v0.6.md`（本批底本）** | **162,361 B** | **1,454** | `head -c 160819` | `e3a4db17…2576ec` | **`946a1d86…616810`** |

### 7.2 v0.7（**已落盘**；下列四元组由本机原生 `wc` / `head -c` / `sha256sum` 独立复算，不取自构建器自报）

| 项 | 值 |
| --- | --- |
| 目标路径 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` |
| 总字节 | **193,586 B** |
| 行数 | **1,696** |
| 正文前缀 | `head -c 191933` |
| 正文 sha256 | **`73e15ddc4d8e4a780d02f72cd4e06342834e28fbc77c284b34476e91f8efd6d0`** |
| 全文 sha256 | **`5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8`** |
| `git diff --no-index --numstat`（v0.6 → v0.7） | **+250 / −8** |
| 相对 v0.6 的净变化 | 行 1,696 − 1,454 = **+242**；字节 193,586 − 162,361 = **+31,225** |

**逐块统计**

| 块 | 位置 | 行数 | 说明 |
| --- | --- | ---: | --- |
| A `G2.1` | §1，G2 段落之后 | 29 | 6 条硬约束 + `F-A40` 5 条断言 |
| B §7.13 + §7.14 + §7.15 | §7.12 之后、§8 之前 | 180 | 能力清单 14 行 + 硬要求 5 条 + `F-A41` 5 条 + 否决表 + `F-A11a`–`d` + §7.15 canonical 表 14 行 |
| C 修订记录行 | 修订记录表末 | 1 | 登记 |
| D §9 表行 | §9 表内 | 1 | 登记 |
| E 替换 8 行 | H1 / §2.6 `A7` / §2.6 注 2 窗口行 / §2.6 注 2 代价行 / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer | 8 | 各自 1 进 1 出；注 2 两行 = 落盘后自检发现「注 2 仍写死 8 天、与 `A7` 的 14 天冲突」，同版修补，未另开版本 |
| **合计** | — | **+250 / −8** | 与 `numstat` 一致（242 净增 + 8 替换：H1 / `A7` / 注 2 两行 / `B1` / `B2` / `F-A11` / footer 自指哈希） |

### 7.3 本文件（R7）四元组

本文件自身的字节 / 行 / 正文 sha / 全文 sha 只写在**末行 footer**（不写进 §7，避免自指），`head -c` 的上界由 footer 自己给出。

### 7.3b 落盘后自检发现并同版修补的一处（未另开版本）

- 现象：`§2.3` 注 2 的**代价行**仍写「窗口 8 个交易日内整池不可判定」，而 `§2.6 A7` 已改为「至数据末端、当前 14 天（8 + 6）」；两处并存会让实施者按 8 天排期，并漏掉 `10-30`…`11-06` 的 6 天。
- 同源问题：注 2 上方的 `st_unknown_windows` 规范行只写默认区间 8 天，未说明它**不等于**窗口总数。
- 处置：两行均按 `A7` 口径重写（合计 14 天 = 8 + 6，且明文**禁止硬编码 8 或 14**，必须按「`st_unknown_windows` ∩ 评估窗」＋「`date > coverageEnd` ∩ 评估窗」现算）。同一版 v0.7 内修补，`numstat` 由 +248/−6 变为 **+250/−8**。
- 未改：§2.2 参数表 `st_unknown_windows` 默认值 `(("2026-10-20","2026-10-29"),)` 本身正确，不动。

### 7.4 本批并入的四处（同一版 v0.7，不另开 R8；行号 = 落盘后 v0.7 实际行号）

落盘决定来自开发经理 17:33 派单。四处与 R7 原三段在同一次合并里写入，**没有产生第二份文件**。逐条：

| # | 位置 | v0.7 行号 | 原句（v0.6） | 新句要点 |
| --- | --- | --- | --- | --- |
| ① 标题版本号 | H1 | **:1** | `# … 接口契约 v0.5（2026-11-07）` —— v0.6 追加时漏同步，落后两版 | `# … 接口契约 v0.7（2026-11-07）` |
| ② §4.6 `B1`/`B2` + 新增 §4.6.1 | §4.6 | **:497**、**:498**、新增 **:504**（§4.6.1 块 :504–:524） | `B1`：「1,779 个交易日 `max_abs_diff < 1e-12`；全期均值 **0.540742**」；`B2`：「`month_end` 日通过率 **53.4%**」 | 收窄为「**两侧均非 `null`**」：`B1` 子集 `n_days = 1,770`、均值 **0.542252**，`null` 日单列清单（当前 9 天）；`B2` `n_month_end = 87`、通过 47、通过率 **0.540230**，`null` 月末不按 fail 计。否决 `treat_non_st` 路线并写清理由 |
| ③ §2.6 `A7` + 新增注 2b | §2.6 / §2.3 | **:221**（`A7` 行）、新增 **:185**（注 2b，:185–:193） | `A7`：「`2026-10-20`…`2026-10-29` 共 **8** 个交易日」 | 窗口终点 = **数据末端**，当前 **14** 天（8 = `st_unknown_windows`，6 = `date > coverageEnd`）。**计数由两条规则现算，禁止硬编码 8 或 14**；证据 `docs/factors/E3_DATA_AVAILABILITY_20261107.md` |
| ④ §7.15 canonical id 表 | 新增节 | **:1522**（表 :1526–:1550，硬约束 ① :1552、② :1559） | 无（只在决策文件 §2.1） | 14 个口径逐行 + 读表规则 4 条 + `vol60` 两式 `1.11e-16` **禁止写「逐位相同」** + 登记元数据缺口 P2 |

**②的实测依据（本机复跑，可独立复现）**

用 `research/strategy-search-20261107/scripts/common.py` 的 `load_panel` → `add_indicators` → `add_universe` 复算研究侧逐日 `market_breadth`：`n_days = 1779`、均值 `0.5407417151801761`，与 `docs/factors/evidence/xs_rank_stats.json#market_breadth.mean_research` **逐位相同**（说明研究侧值本身没错，错的是「它可以直接当逐日一致判据的靶值」）。生产侧在评估窗内必为 `null` 的 9 天：`2026-10-20`…`2026-10-29`（8 天，`st_unknown_windows`）＋ `2026-10-30`（`date > coverageEnd`）。剔除这 9 天后：`n_days = 1770`、均值 `0.5422520639953171`；月末 `88 → 87`、通过 `47`、通过率 `0.5402298850574713`。这 9 天研究侧宽度全部 **0.184562**–**0.303326**（都低于 0.5），其中 `2026-10-30` 恰是月末 —— 所以 `B2` 的 53.4% 与 `B1` 的 1,779 天**同源**，必须一起改，只改 `B1` 会留下一条同样不可达的判据。

**③的实测依据**

行情数据工程师 `docs/factors/E3_DATA_AVAILABILITY_20261107.md`：`flag_date=2026-10-20` 一次写入 198 行 `st_flag=False`，此后到 `10-29` 只有 4 条 `False`、0 条 `True`；末端 ST=True 由 **218 → 20 家**并维持到 **`2026-11-06`**。本架构师用 `D:/TSP/data/kline_daily_enriched` 2,141 个分区独立复算交易日轴：`2026-10-20`…`2026-11-06` = **14** 天，`2026-10-20`…`2026-10-29` = **8** 天。若按旧文本只判 8 天，`10-30`…`11-06` 这 6 天里「198 只真 ST 被当非 ST」会**通过**判据（198 只/日 × 6 日 = **1,188 标的日**漏检）。

**④与派单描述不一致的一处（按实测写，不按转述写）**

派单说「pack-only 的 6 个 canonical 缺 `status`/`version`/`unit`/`scale_free`」。本机在 `backend/.venv` 下 `store.load_into_registry(Path("D:/TSP/data"))`（注册表 192 → **207**，装载 15 个盘上定义）实测：

| 项 | 实测 | 与派单 |
| --- | --- | --- |
| 6 只 pack 单侧件的 `version`/`unit`/`scale_free` | `ma20`/`ma60`/`sd20`/`boll_lower`/`boll_upper` → `unit='currency'`、`scale_free=False`；`prior_amount_20` → `'currency'`；`prior_vol_20` → `'count'`；`version` 全 `1` | **三项不成立，已齐全** |
| `status` | `FactorSpec` 数据类**没有** `status` 字段（21 个字段里无它）；store 侧只在盘上 JSON 里，15 个文件全 `"status":"draft"` | 成立，但**范围是 14 只全部**，不是 6 只 |
| 8 只 `uf_*` 的 `unit`/`scale_free` | 盘上 JSON 键集 11 个，**无 `unit`/`scale_free`** → registry 取默认值：8 只全 `unit='none'`、`scale_free=True`（`uf_ma120` 实为价格类，应 `False`） | **反向**：缺元数据的是 canonical 侧 |

故 §7.15.3 写成「14 只全无 `status`（生产全被 `FS01` 拒）+ 8 只 `uf_*` 缺 `unit`/`scale_free`」，并把「6 只缺三项」更正掉。这属 P2，不阻塞 B2，不进本批验收。

**v0.6 的降级方式**：文件**保留、不删**（`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`，162,361 B / 1,454 行 / 全文 `946a1d86…616810` 一字未改），只改**引用状态**——v0.7 footer 写明「v0.6 自 v0.7 落盘起降为历史版本，其 `F-A34`–`F-A39` 判定对象不变」。v0.3（冻结）/ v0.4（`F-A5` 绑定）/ v0.5（`F-A30`–`F-A33` 绑定）的绑定关系全部不变。

---

## 8. 未确证（不圆）

- **`F-A40` / `F-A41` / `F-A11a`–`F-A11d` 均未实跑**（验收归独立审核工程师）。本文只给判据与实测靶值。
- **`MATRIX_KERNELS` 映射表与 `FS10` 尚不存在**，`gate.py` 也不存在；§7.13 是规格，不是现状。
- **量化样本不是全历史**：319 个分区、末 320 个交易日；`sd20`/`vol60` 的 `ddof` 与面板 `rolling_std` 是否完全一致**未逐位比对**（我只用了 `ddof=1` 复算量级与 `2^-24`）。故 §4.2 的结论只用于「量级与容差」，不用于「实现已对齐」。
- **`prior_vol_20` 中位量级 3.886e+04** 与上一轮（1.00e+05）不同：两轮都用 `volume` 的 20 日滚动标准差，差异来自样本末 320 日不同（本轮 319 分区 + 更末端的低量期），**未定位到单因子原因**；不影响 `2^-24` 结论（相对误差仍是 5.957e-08）。
- **`boll_upper` / `boll_lower` 的复算是按 `ma20 ± 2*sd20` 拼的**，未读面板实现内部参数（`k` 是否 2、`ddof` 是否 1）；只用于量级与容差论证。
- **`F-A11b` 的 `2^-23` 是工程余量**，不是从面板实测标定出来的：实测最大相对误差 5.96e-08，`2^-23 = 1.19e-07` 恰好一倍。若独立审核要求更紧，可降到 `2^-24 × 1.01`，但那会把「`float32` 累加」排除在外。
- **「池内排名」相关口径未涉及**：E2 按决定四 v1.2 的 `xs_rank_pool` 落地（见 v0.6 §3），本批不动。
- **派单基线漂移**：派单按 v0.4 行号（`F-A11 :1198`）派发，实际现行是 v0.6（`:1421`）。我只按文本内容匹配锚点，未按行号定位，故锚点在 v0.6 上仍唯一——但排期若仍在用 v0.4 行号，需同步更新。
- **`B1`/`B2` 的新靶值（1,770 / 0.542252 / 87 / 0.540230）只有研究侧一只脚**：生产侧 `market_breadth` 尚未实现，我只复算了研究侧逐日值并做减法；「两侧均非 `null`」这句话在实现出来之前**无法端到端验证**。
- **§7.15.3 的元数据实测依赖 `D:/TSP/data` 当前盘面**：`load_into_registry(Path("D:/TSP/data"))` 装载 15 个定义；若盘上新增/删除定义，`192 → 207` 这两个数会变。`status`/`unit` 的结论只对今天这 15 个文件成立。

---

## 9. 边界

`docs/factors/**`、`docs/research/**`、`backend/**` **一字未改**（只读引用）；v0.3 / v0.4 / v0.5 / v0.6 **一字未改**（四元组已复算）；未新建第三份契约文件（v0.7 是 v0.6 的追加版，不是新契约）；未 add、未提交、未部署；未创建 `gate.py`；`docs/architecture/evidence/referenced_factor_inventory.json` 未读未改。新增文件：`FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（落盘）、`research/arch-build-20261107/build_contract_r7.py`、`build_contract_r7b.py`（落盘构建器，含 8 条锚点唯一性断言 + H1 断言）。

---

本文件正文 sha256：`ed7ff1a9983690a180d39db6498515b85b8dfabe9408327f5339ee51f5195a04`（校验：`head -c 49599 "docs/architecture/CONTRACT_REVISION_R7_20261107.md" | sha256sum`）· 正文 `49599 B` · 行数 `502` · 版本 **R7（2026-11-07，D5 / 矩阵路径点名 / `F-A11` 分层判据 / 并入四处）**· 底本 v0.6 一字未改（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）· **v0.7 已落盘**（193073 B / 1696 行 / 正文 `head -c 191420` → `f824cfba…0c3c01` / 全文 `f7b6adb2…002908`，原生工具复算）· 构建器 `research/arch-build-20261107/build_contract_r7b.py`（8 条锚点唯一性断言 + H1 断言；`--land` 才落盘）
