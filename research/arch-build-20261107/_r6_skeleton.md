# 契约修订对照 R6（D5 必修 / 矩阵路径交付范围 / F-A11 判据裁定）

- 版本：R6 · 2026-11-07 · 作者：系统架构师
- 对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`（**本次未落盘**，理由见 §5.5）
- 基准（三份本轮逐字节未改，四元组已复算）：v0.5 `FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`（138,729 B / 1,298 行 / 全文 `c7740508…c4a21a`）；v0.4 `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B / 1,226 行 / 全文 `5bd81a74…c5531`）；v0.3 冻结副本 `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（89,833 B / 914 行 / 全文 `5eb97724…565903`）
- 边界：不写业务实现、不改因子口径与策略规格、不改任何既有判据的其余语义、不动 `backend/**`、不提交、不部署
- 与开发经理 17:0x 定论的关系：(a) 契约继续在 `#因子缺口：引擎与执行器接口契约` 线程产出，排期只引用不复制；(b) E2 按决定四 v1.2 的 `xs_rank_pool`（池内排名 ÷ 池内家数）落地，本文不重议；(c) D1/D2 按 13:58 定稿引用；(d) E4 日历来源 = 行情库 distinct `trade_date`；(e) X1 成本同源复用 `MatcherConfig`；(f) 冻结仍由独立审核 PASS 触发，绑定只用归档四元组。

---

## 0. 前置事实（本轮实测，全部可复跑）

| # | 项 | 实测值 | 命令 / 落点 |
| --- | --- | --- | --- |
| 1 | HEAD / 工作区 | `65c6e42f`；`git status --porcelain` = 28 项 | `git rev-parse --short HEAD`；`git status --porcelain | wc -l` |
| 2 | v0.3 冻结副本 | 89,833 B / 914 行 / 全文 `5eb9772411f72357…565903` / 正文 `head -c 89350` → `b082d902e08df2dc…f9bfef` | `wc -c -l` + `sha256sum` + `head -c 89350 | sha256sum` |
| 3 | v0.4（活文件） | 128,007 B / 1,226 行 / 全文 `5bd81a74…c5531` / 正文 `head -c 127043` → `71708877…d16bc` | 同上 |
| 4 | v0.5（活文件） | 138,729 B / 1,298 行 / 全文 `c7740508…c4a21a` / 正文 `head -c 137598` → `082d26fa…af7fae` | 同上 |
| 5 | 引擎默认（与 G2 相反） | `matching="close_t"`（`engine.py:229`）；`entry_price_basis="adjusted"`（`:258`）；`entry_fill is None` → 回退 `matching`（`:280-283`） | 读码 |
| 6 | 两个 HTTP 入口默认不同 | `BacktestRequest.matching="close_t"`（`api/backtest.py:95`）；`StrategyBacktestRequest.matching="open_t+1"`（`:357-359`），**且该请求模型没有 `entry_price_basis` 字段** | 读码 |
| 7 | 服务层同样回退 | `StrategyBacktestConfig.matching="open_t+1"`、`entry_fill=None`（`strategy.py:717-719`），`__post_init__` 回退（`:743-747`） | 读码 |
| 8 | `entry_price_basis` 的唯一来源是策略 META，缺省静默 | `execution_policy.py:78` 默认 `"adjusted"`；`:141-144` `payload.get("entry_price_basis", "adjusted")` | 读码 |
| 9 | 已有 fail-closed 先例 | `engine.py:296`：`plan_at_signal_close and entry_fill != "open_t+1"` → `ValueError`；`strategy.py:1578-1580`：full 模式在**读数据前**校验不支持规则 | 读码 |
| 10 | full 模式与 G2 不相容 | `_FULL_UNSUPPORTED_RULES` 含 `("entry_price_basis", "原始价入场口径")`（`engine.py:341-356`） | 读码 |
| 11 | 分钟路径硬编码 | `_run_minute_backtest` 里 `entry_fill="close_t"`（`strategy.py:2613`，函数定义在 `:2427`） | 读码 |
| 12 | 迁移面 | `backend/app/strategy/seeds/` 10 个种子**无一**含 `backtest_defaults`（命中 0）；`D:/TSP/data/user_data` 下无 `strategies` 目录 | `grep -rl backtest_defaults backend/app/strategy/seeds | wc -l` |
| 13 | 矩阵路径能力（14 个研究基线因子） | **6 可算 / 8 抛错**：`ma20` `ma60` `ma120` `ma200` `boll_upper` `boll_lower` 可算；`sd20` `prior_high_20` `prior_low_10` `prior_high_55` `prior_vol_20` `prior_high_250` `vol60` `prior_amount_20` → `ValueError: unsupported matrix feature` | 见 §3.1 复现脚本与输出 |
| 14 | 白名单规模 | `_MATRIX_COMPUTED_FEATURES` = **60** 个名（`matrix.py:4183-4204`）；另有 5 条前缀启发式（`:4217-4222`） | AST 计数 |
| 15 | Provider 基类静默 | `FactorProvider.materialize_matrix_field` → `return None`（`app/extensions/factors.py:86-88`） | 读码 |
| 16 | float32 面 | `dtype=np.float32` **71** 处（`matrix.py`）；`float32` 引用 **160** 处（`backend/app`）；基础行情字段 float32（`matrix.py:1005-1009`）；财务因子 float32（`fundamentals.py:143-146`）；磁盘缓存上限 **512 MB**（`matrix.py:66`） | `grep -c` |
| 17 | float32 量化（n = 1,753,345 行） | 8 个因子 + `ma20`/`boll_*` 的 `max abs(f64−f32)`：2.94e-05 / 1.17e-04 / 1.17e-04 / 5.86e-05 / 2.93e-05 / 2.00e+00 / 7.41e-09 / 2.03e+03 / 1.19e-04 / 1.20e-04 / 1.07e-04；相对误差 max **每列都是 5.96e-08 = 2^-24** | 见 §4.2 |
| 18 | 决策等价（float64 判定 vs float32 判定） | 3 个谓词（`close >= prior_high_20`、`close/prior_high_250-1 >= -0.03`、`vol60 <= 0.10`）：jaccard **1.0000**、翻转 **0** 行 | 见 §4.6 |
| 19 | 语义错的可判别性（反例） | `prior_high_20` 漏 `shift(1)` → 相对误差 max **0.6682**、绝对 max **678**、`close >= prior_high_20` jaccard **0.1975** | 见 §4.6 |

**数据与样本**：`D:/TSP/data/kline_daily` 共 2,141 个日分区；量化样本取最近 **320** 个分区、**5,612** 只标的，列 `symbol/close/high/low/volume/amount`，逐 symbol 按日期升序做滚动统计（polars `over("symbol")`），float64 计算后 cast float32 比差。**样本不是全历史**，但结论只用其量级（`2^-24` 量化），不外推为全历史极值。

---

## 1. 结论（三件，逐件可判定）

1. **D5 已定则**：`entry_fill` / `entry_price_basis` / `exit_fill` **必须显式传入，缺省即报错**（`FS08`），不回退默认、不告警降级；三条例外（full 模式、分钟路径、legacy 信号回测）必须**显式打标**而不是靠默认值。判据 `F-A34`（4 条）。
2. **矩阵路径已点名并前置**：把 6/14 的现状写进契约交付范围，点名 8 个未同步因子；把「未实现」的失败点从**回测中途 `ValueError`** 前移到**准入 400 `FS10`**；能力来源由「白名单 + 前缀启发式」收敛为一张显式映射表。判据 `F-A35`（4 条）。
3. **`F-A11` 已裁定替换**：`1e-10` 在 float32 存储下**不可能**（量化下界 `2^-24·|x|`），且**连 6 个「已覆盖」因子也过不了**（`ma20` 1.19e-04）→ 原判据实际是 14/14 不成立。替换为 `F-A11a`（NaN 结构，零容忍）/ `F-A11b`（相对 `2^-23`）/ `F-A11c`（决策等价）/ `F-A11d`（**面板路径为唯一权威**）。

**契约文件状态：v0.3 / v0.4 / v0.5 一份未改，v0.6 未落盘。** 本文承载三段可直接机械合并的追加文本（§2.3、§3.3、§4.5）与三条登记行（§5），合并方式与合并后四元组见 §6。

---

## 2. D5 修文（G2 的子条款 `G2.1`）

### 2.1 原句（v0.5 §1，`:50-51`，未改）

> **G2 as-of 语义**
> 信号在 T 日**收盘后**产生，只用 T 日及以前可知的信息；最早成交在 T+1 开盘（`entry_fill="open_t+1"`，`entry_price_basis="raw"`）。任何在 T 日使用 T+1 数据的实现，验收直接不通过。

### 2.2 为什么原句不足（缺的是「怎么传进来」，不是「什么值」）

原句定义了**正确值**，没定义**传不进来时怎么办**；而全链路的默认值与它相反，且**三处默认互不相同**（§0 第 5–8 项）：

- 引擎 `MatcherConfig` 默认 `close_t` / `adjusted`，且 `entry_fill=None` 时**回退**到 `matching`；
- 两个 HTTP 入口默认不同（`close_t` vs `open_t+1`），且 `entry_price_basis` **根本不在策略回测请求模型里**（只从 META 读，缺省 `adjusted`）；
- 服务层 `StrategyBacktestConfig` 再回退一次。

于是「漏传」不产生任何信号：`entry_fill` 会静默变成 `close_t`（T 日收盘成交），`entry_price_basis` 静默变成 `adjusted`（复权价成交）。**这是本契约里唯一一处「违反 G2 不会报错」的路径**，因此必须以拒绝条件收口，而不是以文档约定。

补充事实（不修，只登记）：`mode="full"` 与 `entry_price_basis="raw"` **不相容**（`_FULL_UNSUPPORTED_RULES`，`engine.py:341-356`）——即 full 模式**无法**满足 G2，只能拒绝或改用 `position`。

### 2.3 新句（待插入 §1，G2 段落之后；逐字节，含行尾 CRLF）

```markdown
%%A%%
```

### 2.4 依据与代价

- **依据**：G2 本身（「最早成交在 T+1 开盘」）+ 三处默认的实测（§0 第 5–8 项）+ 两条既有 fail-closed 先例（§0 第 9 项）。这不是新增口径，是把既有口径改成**可判定的拒绝条件**。
- **代价（必须写在排期里）**：本条款生效后，**所有未补 META 的策略全部 `FS08`**（现状 10 个种子无一含 `backtest_defaults`）。修复属**数据变更**：每个策略 `META.backtest_defaults` 补 `"entry_price_basis": "raw"`、`"entry_fill": "open_t+1"`。**禁止**用「代码默认值改成 raw」代偿——那会把「必须显式」重新变回「靠默认」。
- **被否决的更软写法**：「缺省时告警 + 标 `g2_defaulted=true`」——告警在批处理/worker 里没人看，且 `g2_defaulted` 的结果与合规结果混在同一结果表里，后续无法区分；与「回测-模拟盘逐日一致率」这类验收直接冲突。
- **错误码选择**：用 `FS08`（`FS` 族第 8 个，`FS01`–`FS07` 已占用），不占用 DSL 的 `E0xx`（那是编译期语言错误码，`E001`–`E018` 已定义/预留）。

---

## 3. 矩阵路径（新增 §7.12）

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

输出（本机实测，11 行有效）：6 个 `OK float32`；8 个 `RAISE ValueError: unsupported matrix feature: <id>`，即 `sd20`、`prior_high_20`、`prior_low_10`、`prior_high_55`、`prior_vol_20`、`prior_high_250`、`vol60`、`prior_amount_20`。

**注意这条结论的边界**：它证明的是「`matrix_feature` 单点解析这 8 个 id 会抛错」，**不等于**「引用这些因子的策略一定跑不了」——策略若走面板路径仍可跑。矩阵路径不可用是**能力缺口**，不是数值错误。

### 3.2 缺陷的真实位置

1. **失败得太晚**：`ValueError` 出在评分列物化时（`matrix.py:4557`），此时已加载全市场矩阵并算过前序因子 → 一次回测白跑。
2. **「未实现」被编码成「无值」**：`FactorProvider.materialize_matrix_field` 基类 `return None`（`extensions/factors.py:86-88`），新 Provider 默认继承 → 缺口不会在注册时暴露。

### 3.3 新句（待插入 §7.11 之后、§8 之前；逐字节，含行尾 CRLF）

```markdown
%%B12%%
```

### 3.4 取舍

- **为什么不继续加前缀规则**：现有 5 条前缀规则里，`maN`/`emaN`/`rsi_N`/`momentum_Nd` 让 `ma20`、`ma120` 这类「恰好长得像」的名字通过，而 `vol60`、`sd20`、`prior_*` 恰好长得不像 → 同一个语义类（滚动统计）被名字拼写决定支持与否。继续加规则只会让「支持矩阵」变成拼写游戏。
- **为什么是映射表而不是 `FactorSpec.matrix_kernel` 字段（长期应该走后者）**：加字段要动 `registry.py` 的 `FactorSpec`（与 `status` / `alias_of` 同批的 P2 工作，见 v0.5 §9 末两条），会与本批 B0b 的排期耦合。**裁定**：B0b 先落 `MATRIX_KERNELS` 映射表；P2 落 `FactorSpec` 字段时把该表降为「编译期派生表」，并要求二者用一致性断言锁死（§7.12.3-4）——双写期只允许一个来源判定「支持与否」。
- **依赖声明**：`prior_amount_20` 需要矩阵侧有 `amount` 字段。现有多个核已依赖它（`matrix.py:4335`、`:4441`、`:4463`、`:4540` 等 5 处），但**是否可用取决于调用方的 `field_columns`**。故新核必须在映射表里同时声明 `requires_fields`，准入时与 `market.fields` 求交后判 `FS10`，不得在核内 `KeyError`。

---

## 4. `F-A11` 判据裁定（新增 §7.13）

### 4.1 原判据（v0.5 §8.1，`:1267`）

> `F-A11` | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致

### 4.2 量化实测（n = 1,753,345 行，320 个交易日 × 5,612 只）

| factor_id | 中位量级 | `max abs(f64−f32)` | 超 1e-10 行数 | 相对误差 max |
| --- | ---: | ---: | ---: | ---: |
| `sd20` | 0.62 | 2.94e-05 | 1,634,581 | 5.96e-08 |
| `prior_high_20` | 17.4 | 1.17e-04 | 1,495,506 | 5.72e-08 |
| `prior_low_10` | 14.6 | 1.17e-04 | 1,567,839 | 5.72e-08 |
| `prior_high_55` | 18.8 | 5.86e-05 | 1,302,134 | 5.72e-08 |
| `prior_high_250` | 23.0 | 2.93e-05 | 330,832 | 5.71e-08 |
| `prior_vol_20` | 1.00e+05 | 2.00e+00 | 1,312,767 | 5.96e-08 |
| `vol60` | 0.0277 | 7.41e-09 | 1,280,905 | 5.96e-08 |
| `prior_amount_20` | 1.50e+08 | 2.03e+03 | 1,630,376 | 5.96e-08 |
| `ma20`（已「覆盖」） | 15.6 | 1.19e-04 | 1,633,553 | 5.96e-08 |
| `boll_upper`（已「覆盖」） | 17.1 | 1.20e-04 | 1,646,509 | 5.96e-08 |
| `boll_lower`（已「覆盖」） | 14.1 | 1.07e-04 | 1,646,451 | 5.96e-08 |

三处读法：
1. **相对误差 max 每列都是 `5.96e-08`（= `2^-24`）**，且绝对值随量级线性放大（`prior_amount_20` 到 2.03e+03）→ 这是 **float32 存储量化**，不是算法差；
2. **这是下界**：只算了「同一 float64 值存成 float32」的舍入，没算 float32 累加误差 → 真实双路径差只会更大；
3. **连 6 个「已覆盖」的也过不了**（`ma20` 1.19e-04）→ `F-A11` 按字面是 **14/14 不成立**，不是「8 个缺能力、6 个合格」。这两件事必须分开记账：**能力缺口 = 8 个；判据不可达 = 14 个。**

### 4.3 为什么「改容差」不是放水（三个候选的取舍）

| 候选 | 做法 | 代价 | 结论 |
| --- | --- | --- | --- |
| A 矩阵侧全改 float64 | 所有字段 float64 | 每字段 48.1 MB → 96.1 MB（12.0M 格 = 2,141 日 × 5,612 只），20 字段 0.96 GB → 1.92 GB；磁盘缓存上限 512 MB 被压穿（`matrix.py:66`）；`dtype=np.float32` 71 处 + `float32` 引用 160 处逐个复核；8 个新核按 float64 重验 | **否决** |
| B 面板侧 cast 成 float32 再比 | 两侧同精度 | 差异归零，但判据变成自证；同时**摧毁 `F-A10`**（对研究侧 float64 的 `1e-10` 锚） | **否决** |
| C 分层判据（采纳） | 结构零容忍 + 数值相对容差 + 决策等价 + 权威路径 | 容差从 1e-10 放宽到相对 1.19e-07；新增一条「决策等价」断言（工作量 +1 个脚本） | **采纳** |

### 4.4 新句（待插入 §7.12 之后、§8 之前；逐字节，含行尾 CRLF）

```markdown
%%B13%%
```

### 4.5 判别力证明（为什么放宽后仍抓得住真错）

同一套样本、同一个谓词 `close >= prior_high_20`：

| 情形 | 相对误差 max | 绝对误差 max | jaccard | 翻转行数 |
| --- | ---: | ---: | ---: | ---: |
| float32 量化（真实存在的误差） | 5.96e-08 | 1.17e-04 | **1.0000** | **0** |
| 语义错：漏 `shift(1)`（`rolling_max(high,20)`） | **0.6682** | **678** | **0.1975** | 仅正确侧 64,565 / 仅错侧 339（union 80,876） |

量化误差与语义误差差 **4 个数量级**；`F-A11b`（相对 2^-23）与 `F-A11c`（jaccard ≥ 0.9999）都不会把语义错当成噪声放过。

### 4.6 权威路径（这条比容差更重要）

**面板路径（float64）是唯一权威**：台账数值、`F-A10` 对账、研究复核只取面板；矩阵值**不得**回写台账/证据；矩阵回测结果必须标 `matrix_path=true`、`tolerance="eps32"`。理由：一旦允许矩阵值进台账，台账的数字来源就随「这次跑的是哪条路径」漂移，而台账是可追溯性的锚。

---

## 5. 登记行与合并步骤

### 5.1 修订记录表 +1 行（待插入 v0.5 修订记录表末，`v0.5（追认）` 行之后）

```markdown
%%D%%
```

### 5.2 §9「未覆盖与依赖」表 +1 行（待插入该表末，`| 实现与验收 |` 行之后）

```markdown
%%C%%
```

### 5.3 footer 整行替换（v0.5 末行 → 新末行）

```markdown
%%E%%
```

### 5.4 合并步骤（可机械执行；每一步都有断言）

```bash
cd C:/work/sourcecode/tick-stock-panel
# 0) 前置断言：三份基准未变
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md   # c7740508…c4a21a
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md        # 5bd81a74…c5531
sha256sum docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md  # 5eb97724…565903
# 1) 用构建器合并（内置锚点唯一性断言，锚点漂移即退出）
./backend/.venv/Scripts/python.exe -X utf8 research/arch-build-20261107/build_contract_r6.py \
    --out docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md
# 2) 复算四元组，必须等于 §6.2
wc -c -l docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md
head -c 150008 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md | sha256sum
# 3) 确认 v0.3 / v0.4 / v0.5 仍是第 0 步的三个值
```

构建器只做三件事：在第 2 个锚点后插 `G2.1`；在 §7.11 之后、§8 之前插 §7.12+§7.13；在修订记录与 §9 表各插 1 行；最后按新正文重算 footer 的 sha。**它不改任何既有行**（除末行 footer）。

### 5.5 本次为什么不把 v0.6 落盘

三条理由，逐条可查：
1. **v0.5 是 `F-A30`–`F-A33` 的绑定对象**：v0.5 §9.3 自述「自本文件定稿起不再就地改写，任何改动须升版并重算四元组」。就地追加会把它的四元组改掉 → 正在进行的 V3 校验绑定失效。
2. **再加一份活契约就是第三份**：`docs/architecture/` 现有 v0.4 + v0.5 两份活契约（v0.3 在 `archive/`）。派单明确禁止新建第三份。
3. **R6 已把文本与合并方式都固定**：三块文本逐字节给出（含行尾 CRLF），合并后四元组已在临时副本上实测（§6.2），任何人跑 §5.4 都能复得同一组数值。落盘时机交给排期（与独立审核 PASS 同批），不占本轮。

---

## 6. 四元组与 `+/-` diff 统计

### 6.1 三份基准（本轮复算，均未变）

| 对象 | 字节 | 行 | 正文前缀 | 正文 sha | 全文 sha |
| --- | ---: | ---: | --- | --- | --- |
| v0.3 `archive/…_v0.3_FROZEN.md` | 89,833 B | 914 | `head -c 89350` | `b082d902…f9bfef` | `5eb97724…565903` |
| v0.4 `FACTOR_ENGINE_CONTRACTS_20261107.md` | 128,007 B | 1,226 | `head -c 127043` | `71708877…d16bc` | `5bd81a74…c5531` |
| v0.5 `…_v0.5.md` | 138,729 B | 1,298 | `head -c 137598` | `082d26fa…af7fae` | `c7740508…c4a21a` |

### 6.2 合并后 v0.6（**未落盘**；数值由构建器在临时副本上实测，临时文件已删）

| 项 | 值 |
| --- | --- |
| 目标路径 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md` |
| 总字节 | **%%V06_BYTES%%** |
| 行数 | **%%V06_LINES%%** |
| 正文前缀 | `head -c %%V06_BODY_BYTES%%` |
| 正文 sha256 | **`%%V06_BODY_SHA%%`** |
| 全文 sha256 | **`%%V06_FULL_SHA%%`** |
| `git diff --no-index --numstat`（v0.5 → v0.6） | **%%NUMSTAT%%** |
| 相对 v0.5 的净变化 | 行 %%V06_LINES%% − 1,298 = **+%%NET_LINES%%**；字节 %%V06_BYTES%% − 138,729 = **+%%NET_BYTES%%** |

**逐块统计（合并内容 = 4 处插入 + 1 行替换）**

| 块 | 位置 | 行数 | 说明 |
| --- | --- | ---: | --- |
| A `G2.1` | §1 G2 段落之后 | %%BLOCK_A_LINES%% | 含 6 条硬约束 + `F-A34` 判据表 |
| B §7.12 + §7.13 | §7.11 之后、§8 之前 | %%BLOCK_AB_LINES%% | 能力清单 14 行 + 硬要求 5 条 + `F-A35` 4 条 + `F-A11a`–`d` + 否决表 |
| C §9 表行 | §9 表末 | 1 | 登记 |
| D 修订记录行 | 修订记录表末 | 1 | 登记 |
| E footer | 末行 | 1（替换） | 含新正文 sha |
| **合计** | — | **+%%ADDED%% / −1** | 与 `numstat` 一致 |

### 6.3 本文件（R6）四元组

本文件自身的字节数 / 行数 / 正文 sha / 全文 sha **只写在末行 footer**（不写进 §6，避免自指）。校验：

```bash
wc -c -l docs/architecture/CONTRACT_REVISION_R6_20261107.md
sha256sum docs/architecture/CONTRACT_REVISION_R6_20261107.md
head -c %%R6_BODY_BYTES%% docs/architecture/CONTRACT_REVISION_R6_20261107.md | sha256sum
```
