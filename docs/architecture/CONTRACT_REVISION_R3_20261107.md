# 契约修订记录 R3（v0.3 → v0.4）：三处裁定 + 4 处自纠 + 15:51 版归属说明

作者：系统架构师 · 2026-11-07 · 只改 `docs/architecture/` 下的契约与修订记录
依据派发：开发经理 a2a5110a / 8d6b4371 批一b、批二前置三点
**本文件不含实现代码、不改策略口径、不改因子定义与台账、不下验收结论。**

---

## 0. 先回答开发经理的第一问：15:51:09 版是不是我写的

**不能证明是我写的，因此不冒领；也不能否认我参与了这段内容的撰写。** 分三层说：

| 层 | 结论 | 证据 |
| --- | --- | --- |
| 内容谱系 | **是我的**（R2 §1–§8 与收尾 S1/S2/S4 的条目，与我该轮报告逐条对应） | 我该轮报告列出的四项收尾——§2.2 `st_flag` 输入行改三态、§8 `ewm`/Wilder 缺口行、6 处 `文件:行` 引用校正、HEAD `96ba73d0→65c6e42f` 与 mtime `15:28:25→15:35:28`——在盘上 R2 的 §8 S1/S2/S4 与 §3 中逐条存在，行号与数字一致 |
| 写盘动作 | **无证据能归给我** | ① 尺寸不同：我该轮报告终态是 **89,709 B**、正文 `d8ca6de5…`、全文 `c3c41277…`、R2 **28,417 B**；盘上 15:51:09 是 **89,833 B** / R2 **29,801 B**（+124 B / +1,384 B）；② 结论相反：我该轮报告写「footer 自校验从 `head -c` **改为 `head -n 913`**」，盘上 R2 §S3 与 v0.3 footer 都是「**最终定为字节前缀 `head -c 89350`**」——这是对我自己报告结论的反转，不是我报告的状态；③ 全文无签名、无提交，盘上无法判定动作主体 |
| 处置 | **按团队冻结四元组接受它作为 v0.3 基准，不重新冻结、不改归档** | 独立审核已按其自复算的四元组绑定（`CONTRACT_REVIEW_20261107.md` §2）；归档件 `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` 我本轮复算 `5eb97724…565903` / 89,833 B / 914 行，与冻结记录一致，**逐字节未动** |

**一句话**：内容我认，写盘这一次我不认领也不否认；判据只认四元组，不认作者。若开发经理需要动作主体，只有写盘方自己能确认。

---

## 1. 绑定版本与产出（本机当场复算）

| # | 文件 | 字节 | 行数 | 正文 sha256（字节前缀） | 全文 sha256 | 状态 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 1 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`（v0.4，本轮产出） | 110,944 | 1,050 | `11bfe51fd1353f92586a62c7f707ce12200f1860a83bede931b83cb0fa27f9c3`（`head -c 110098`） | `6b8fb14c8b6dff19092151d526ca32f2191b2f5f77ca741d043443a36bff7895` | **草案，未冻结** |
| 2 | `docs/architecture/CONTRACT_REVISION_R3_20261107.md`（本文件） | 见 footer | — | — | 见 footer | 现行 |
| 3 | `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` | 89,833 | 914 | `b082d902…f9bfef`（`head -c 89350`） | `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` | **冻结（v0.3），未动** |

**前缀口径沿用 `head -c N`**（S3 定稿）。v0.4 的 `N=110098` 是本轮重算值：v0.3 的 `89350` 对 v0.4 无意义。

```bash
cd /c/work/sourcecode/tick-stock-panel
wc -lc docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md
head -c 110098 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md | sha256sum
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md
sha256sum docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md
```

---

## 2. 三处裁定逐条

### R3-1 §7.4「不动 store」→「允许面 + 禁止面」

**原句（v0.3 §7.4 末段）**

> 「要求：内容未变则返回既有定义、`version` 不变、响应标 `unchanged=true`；仅内容变化才 +1。**改动面**：不动 `store.py`，只在 API 层加判断。」

**新句（v0.4 §7.4）**

> 「**改动面（v0.4 更正，替换 v0.3 的「不动 store」）**：为落地 `F-A5`，**允许**在 `store.py` **新增幂等入口**——`content_signature(definition)` / `is_same_content(stored, incoming)` / `upsert_definition(data_dir, definition)` 三个纯新增函数（`store.py:207-257`），以及 `api/factors.py` 保存分支改为经 `upsert_definition` 落库（`api/factors.py:333-360`）。这是**唯一**允许的 store 改动面。」
> 「**同时禁止（fail-closed 语义不变）**：① 不得改 `save_one`/`load_one`/`delete_one` 的既有语义…② 不得放宽 `to_spec` 的任何校验…③ 不得改 `_STORE` 路径与 JSON 结构…④ 幂等**不得变成跳过校验**…」

**依据**：`git status` 显示 `backend/app/factors/store.py`、`backend/app/api/factors.py` 均为 `M`；`git diff --numstat` = `store.py` **+91/−1**、`api/factors.py` **+8/−16**（mtime 15:35:28）；`git show HEAD:backend/app/factors/store.py | grep -c unchanged` = **0**。

**自洽性**：v0.3 的 §7.4「不动 store」与 §7.6 `F-A5`「工作区已有 `store.py:207-257` 实现」是同版内正面矛盾；本轮在 §7.4 认下允许面、在 §7.6 `F-A5` 加一句「该实现属 §7.4 v0.4 允许面」，两侧同时消解。

```bash
git diff --numstat -- backend/app/factors/store.py backend/app/api/factors.py
git show HEAD:backend/app/factors/store.py | grep -c unchanged   # 期望 0
grep -n "def content_signature\|def is_same_content\|def upsert_definition" backend/app/factors/store.py
```

**未知（未确证）**：`+91/−1` 的那 1 行删除未逐行审阅归属（是否属批一b 允许面）→ 留给独立审核按 §7.4 四条禁止面逐条判，**本文件不下结论**。

---

### R3-2 新增 §7.8：双 id / 别名 / 不可复算因子的闸门契约

**原句（v0.3 §7.5-3，全文仅此一句，无裁决机制）**

> 「**禁止**同一口径起两个 id 并用于同一策略；研究名 ↔ `uf_` id 映射必须唯一并登记在 `docs/factors/` 台账。」

**新句（v0.4）**：§7.5-3 改为带上裁决机制的完整句（未声明 canonical 即 `FS06`）；新增 §7.8.1–§7.8.6：

| 小节 | 内容 |
| --- | --- |
| 7.8.1 | 事实 12 条（逐条可复跑） |
| 7.8.2 | **裁定 A：canonical = 台账 id（`uf_*` / `cf_*`），研究原名 = alias** + 硬规则 `A-1`–`A-5` |
| 7.8.3 | **裁定 B：闸门按「可复算性」分类，不按 `kind`** + `formula=None` 的正面回答 |
| 7.8.4 | 模式位矩阵（`production` / `research` / `diagnostic`）+ 新错误码 `FS03`–`FS06` |
| 7.8.5 | 过渡期：新写入 fail-closed、存量只告警 + `degraded=true` |
| 7.8.6 | 判据 `F-A14`–`F-A17` |

#### 2.1 对派单里三处证据的更正（结论不变，事实更准）

派单说「pack 只注册 4 个、另 10 个未注册、`formula=None`、双 id 4 组」。**实测三条都不成立**，逐条给证据：

| 派单说法 | 实测 | 命令 |
| --- | --- | --- |
| pack 只注册 `vol60`/`ma120`/`ma200`/`prior_amount_20` 4 个 | **14/14 全部注册**，`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`prior_high_250` 同样在册 | 下方 dump：`identity_pack=True`、`group='研究补充'` |
| `formula=None` | **`FactorSpec` 没有 `formula` 字段**（只有 `formula_text`）；`hasattr(spec,'formula')==False` 是「字段不存在」，不是「公式为空」。14 个的 `formula_text` 全是可编译 DSL 原文 | `[a for a in dir(spec) if "form" in a]` → `['__format__','formula_text']` |
| 同口径双 id **4 组** | **8 组**，且 `prior_amount_20` **没有** `uf_` 对应件；`uf_dist_prior_high_250` 没有 pack 对应件 | 目录 15 个 json 逐个读 `id` 配对 |

```bash
cd /c/work/sourcecode/tick-stock-panel/backend
./.venv/Scripts/python.exe -c "
from app.factors.registry import all_factors, get_factor
from app.custom.research_factor_pack.factor_specs import RESEARCH_BASELINE_FACTOR_IDS, SPEC_BY_ID
print('pack ids', len(RESEARCH_BASELINE_FACTOR_IDS), 'all_factors', len(all_factors()))
for i in sorted(RESEARCH_BASELINE_FACTOR_IDS):
    s = get_factor(i)
    print(i, s is not None, s.kind, s.lang, s.warmup_bars, s.stability, s is SPEC_BY_ID[i])
"
# 期望：pack ids 14 all_factors 192；14 行全部 True custom dsl <warmup> stable True
```

**实测 dump（本轮，2026-11-07 16:2x）**：`ma20` 21 / `ma60` 61 / `boll_lower` 21 / `boll_upper` 21 / `sd20` 21 / `prior_high_20` 21 / `prior_low_10` 11 / `prior_high_55` 56 / `prior_vol_20` 21 / `ma120` 121 / `vol60` 61 / `prior_high_250` 251 / `prior_amount_20` 21 / `ma200` 201；`kind='custom'`、`lang='dsl'`、`stability='stable'`、`identity_pack=True` 全部 14 条。

#### 2.2 双 id 的 8 组（`uf_` 侧逐文件读 `id`）

```bash
cd /c/work/sourcecode/tick-stock-panel
python -c "
import json,glob
rows=[json.load(open(p,encoding='utf-8')) for p in glob.glob('D:/TSP/data/user_data/custom_factors/*.json')]
print(len(rows), sorted(r['id'] for r in rows))
"
```

目录 = **15 个 json**（14 `uf_` + 1 `cf_auction_resonance`）。配对结果：

| # | 组 | pack 表达式 | store 表达式 | 关系 |
| --- | --- | --- | --- | --- |
| 1 | `ma120` | `ts_mean(close,120)` | 同 | **逐字相同** |
| 2 | `ma200` | `ts_mean(close,200)` | 同 | **逐字相同** |
| 3 | `vol60` | `ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60)` | `ts_std(close / ts_delay(close,1) - 1, 60)` | 1 ULP（`1.11e-16`，4.6% 行不等，`F_CLASS_PARITY_20261107.md:37`） |
| 4 | `prior_high_20` | `ts_delay(ts_max(high,20),1)` | `ts_max(ts_delay(high,1),20)` | **同窗口不同写法**，窗口同为 `[t-20,t-1]` |
| 5 | `prior_high_250` | `ts_delay(ts_max(high,250),1)` | `ts_max(ts_delay(high,1),250)` | 同上 |
| 6 | `prior_high_55` | `ts_delay(ts_max(high,55),1)` | `ts_max(ts_delay(high,1),55)` | 同上 |
| 7 | `prior_low_10` | `ts_delay(ts_min(low,10),1)` | `ts_min(ts_delay(low,1),10)` | 同上 |
| 8 | `prior_vol_20` | `ts_delay(ts_mean(volume,20),1)` | `ts_mean(ts_delay(volume,1),20)` | 同上 |

**未逐值对账**：第 4–8 组的 `max_abs_diff` 本轮**未跑**，只做了表达式对照；`F-A14` 不要求对账（它们不是同一实现的两种投影），但 §7.8.2 `A-4` 要求 alias 解析后必须重跑对账，届时一并出数。

#### 2.3 裁定 A：谁 canonical，旧 id 怎么被闸门对待

- **canonical = 台账 id（`uf_*` / `cf_*`）**，研究原名 = alias。三条机制性理由（不是偏好）：只有 store 侧能带 `status`/`version`/`created_at`；只有 store 侧有命名空间约束 `^uf_[a-z0-9_]{1,40}$`（`store.py:22`）；G7 要求口径可穷举版本化，前提是每个口径一条可版本化记录。
- **旧 id 在闸门里的待遇**：`production` 引用 alias → 拒绝 `FS03`；同一策略内 alias 与 canonical 并存 → `FS04`（`research`/`diagnostic` 也拒 `FS04`）；canonical 未裁定/冲突/别名成环 → `FS06`，fail-closed；`research` 允许 alias 但记 `deprecated_alias_used`；`diagnostic` 只标 `dual_id`。
- **解析**：`FactorSpec.alias_of`（P2，与 §7.7.2 的 `status` 同批），上限 **4 跳**、环检测、目标必须已登记；结果落 `resolved_id`，保留 `submitted_id`。
- **硬规则 A-4**：alias 生效的数值代价必须报（`vol60` 组 1 ULP）；超差即按 G8 走变更流程。

#### 2.4 裁定 B：`formula=None` 的 python 因子怎么判（派单第②问的正面回答）

**按 `lang` 分支，不按「`formula` 是否为空」**——该字段不存在（2.1 第 2 条）。三条落到判据上：

1. `dependencies` / `warmup_bars` **不由表达式推断缺失**：`lang="python"` 由 `compile_python_expression` 给出（`py_expr.py:154` 返回 `CompiledPyExpr`，`:205` 置 `warmup_bars=_window_warmup(tree)+1`），`warmup` 取 `max(declared, compiled)`。
2. `factor_columns_view()` **对 python 因子一视同仁**：`registry.py:408` 只投影 `id/label/group/formula_text`（`column_view()` 在 `:61`），不存在「不可显示」。
3. **真正不成立的是「对研究参考实现复算 `max_abs_diff`」**：python 因子没有研究侧等价物 → `reference_missing=true`，判据降级为「同输入两遍逐位一致 + 声明测试向量」；`production` 模式对 `reference_missing` 给 `FS05`。

**composite（`cf_*`）单独一支**：`formula_text` 是合成描述串（`"w*zscore(member) + …"`），**不可编译**，判据 = 成员全部 `usable`（递归）+ 权重非零 + 无环，可复算性逐个继承成员。

**现状**：`D:/TSP/data` 15 个定义中 `lang` 为 `dsl`（14）或合成（1），**实测 0 个 python 因子**。分支仍必须写死——第一只 python 因子进线时，闸门不能靠「今天没有」决定走哪条路。

```bash
cd /c/work/sourcecode/tick-stock-panel
python -c "
import json,glob
for p in sorted(glob.glob('D:/TSP/data/user_data/custom_factors/*.json')):
    d=json.load(open(p,encoding='utf-8')); print(d.get('id'), d.get('kind'), d.get('status'), d.get('lang'))
"
```

**未知（未确证）**：`composite` 的 `components` 权重与环检测**当前无任何代码执行**（闸门未落地），`F-A14`–`F-A17` 均为待实现判据，不是已通过项。

---

### R3-3 §8.1 预热拆两套语义 + 写死 `al=0`

**原句（v0.3 §8.1）**

> 「裁定：`warmup_bars = 373`（`(13/14)^n < 1e-12` → n ≥ 373）。」

问题（派单第③点）：373 是**引擎侧**解析门槛，与策略经理「warmup 从首根 `ret1` 起、`warmup_bars=1` 不用 null 掩码」是**两套语义**，一个数字装不下。

**新句（v0.4 §8.1）**：拆为 `W-A` / `W-B` / `W-C` / `W-D` 四段，给出两条独立条款：

**条款一（引擎 / 矩阵侧预热 `warmup_bars`）**：取 **600**。理由：Wilder 无限记忆，`(13/14)^n` 只算 seed 权重，没算 RSI 的导数放大（`dRSI/dRS = 100/(1+RS)^2`，RS≈1 处放大 25 倍、上界 100 倍）。实测（300 symbol 子集、`2024-01-02` 起比对「窗口内重启」与「自首根起算」）：

| k | `max_abs_diff` | 判定 |
| ---: | ---: | --- |
| 28（`py_expr` 的 `span=2/α-1`） | **12.819** | 灾难性 |
| 100 | 5.40e-02 | 不可用 |
| 311 | 4.20e-08 | 不达 `1e-10` |
| 373 | **1.445e-10** | 超门槛 1.4 倍 |
| 450 | 2.56e-13 | 达标 |
| 500 | 2.84e-14 | 达标 |
| **600** | **0.0（逐位一致）** | **契约取值** |

**失效边界**：k ≥ 450 才稳定进 `1e-10`；k=373 差 1.4 倍；k ≤ 100 到 `1e-2`；k=28 到 12.8 个 RSI 点。**代价**：矩阵/增量路径须比首个使用点早 600 根起算（≈2.4 年）；首个使用点早于数据首部时按 symbol 首根起算（无代价）。

**条款二（研究 / 策略侧可用区，不是 `warmup_bars`）**：数值上**自 symbol 首根 bar 起算**，与 `research/strategy-search-20261107/scripts/common.py:139-151` 的 `ewm_mean(adjust=False).over("symbol")` 逐位一致；**不得截断、不得用 null 掩码**（截断或掩码直接破坏逐位一致）。首个可用值实测在 `i=1`（`ret1` 首次有定义；`i=0` 是 `0/0` 转 null）——这就是台账 `warmup_bars=1` 的表述。前 14 根数值未稳定 → `min_history_bars = 15`，由策略准入层按 `observed_bars` 判，**不得**用 `warmup_bars` 代判。

**硬规则**：`warmup_bars` **只能**用于「重算种子点 / 缓存预热」，**禁止**用于 null 掩码或「前 N 根不可交易」。只肯落一个数字时：落 **600**，且不做掩码。

**W-C `al=0` / `ag=0` 判定式（禁止兜底）**：判定式固定 `100 - 100/(1 + ag/al)`，**不得**加 `1e-12` 护栏（现网 `pipeline.py:580-583` 的 `rsi_6/14/24` 有护栏，`rsi_14_pct` 不得沿用）：

| 情形 | 结果 | 依据 |
| --- | --- | --- |
| `al==0 ∧ ag>0` | **100.0**（IEEE `x/0=+inf`）；**禁止兜成 null** | 实测 9,356 行 |
| `al==0 ∧ ag==0` | **null**（`0/0=NaN` → 必须显式 `fill_nan(None)`；NaN≠null，`null_count()` 抓不到） | 实测 6,033 行 |
| `ag==0 ∧ al>0` | 0.0 | 实测 5,702 行 |

护栏代价（实测）：沿用 `1e-12` 会把 9,356 行变成 `99.9999865614…99.9999999995`，`max|Δ| = 1.344e-05`，是 `F-A10` 门槛 `1e-10` 的 **约 13 万倍**。

**W-D 两个必须报数的项**：① `al==0` 行数（拆 `ag>0` / `ag==0`）：**15,389 = 9,356 + 6,033**（域 `2019-01-02`–`2026-11-06`，`9,025,084` 行 / `5,813` 只）；② **仅一侧为空的行数必须 = 0**：`(ag.is_null() XOR al.is_null()).sum()` 实测 **0**。附带：`rsi` NaN 行数 = **6,033**（`i=0` 5,813 / `i=1` 218 / `i=2` 2），转 null 后 null 行数须等于同值。

```bash
cd /c/work/sourcecode/tick-stock-panel
grep -n "def compile_formula" backend/app/factors/dsl.py                      # :563
cd backend && ./.venv/Scripts/python.exe -c "
from app.factors.dsl import OPERATORS, TS_OPERATORS, CROSS_OPERATORS
print(len(OPERATORS), len(TS_OPERATORS), len(CROSS_OPERATORS), 'ewm' in OPERATORS)
"                                                                             # 期望 25 13 3 False
grep -n "ewm_mean" app/indicators/pipeline.py | head -5                       # :576-577, :503, :417-429
```

---

## 3. R3 自纠 4 处（v0.4 未冻结，同版内更正）

这四处是**我写 v0.4 初稿时自己写错**，改前先核了盘上，逐条给原句/新句：

### C1 双 id 组数：4 组 → **8 组**

- **原句（v0.4 初稿 §7.8.1 #6）**：「同口径双 id 已是事实，**4 组**：`vol60`/`ma120`/`ma200`/`prior_amount_20` 在 pack 与 store 各一份」
- **新句**：「**8 组**（自纠…）：`ma120`/`ma200`/`vol60`/`prior_high_20`/`prior_high_250`/`prior_high_55`/`prior_low_10`/`prior_vol_20`；**`prior_amount_20` 没有 `uf_` 对应件**，`uf_dist_prior_high_250` 没有 pack 对应件」
- **依据**：目录 15 个 json 逐个读 `id`；`prior_amount_20` 的 `uf_` 文件不存在，而 `uf_prior_high_20`/`uf_prior_high_250`/`uf_prior_high_55`/`uf_prior_low_10`/`uf_prior_vol_20` 都存在
- **连带**：§7.5-3「现状 4 组」→「8 组」；§9 同句 →「8 组」

### C2 `registry.py#FACTOR_SPECS` → `#_CATALOG`

- **原句**：`registry.py#FACTOR_SPECS` 新增 `_base("rsi_14_pct", …)`（§8 表格行 + §8.1 落点 1，2 处）
- **新句**：`registry.py#_CATALOG`（`:83`）
- **依据**：`from app.factors.registry import FACTOR_SPECS` → `ImportError: cannot import name 'FACTOR_SPECS'`；模块内常量为 `_CATALOG`（`:83`），`len(_CATALOG)==77`
- **命令**：`cd backend && ./.venv/Scripts/python.exe -c "from app.factors.registry import _CATALOG; print(len(_CATALOG))"` → 77

### C3 `factor_columns_view()` 行号 `:59-61` → `:408`

- **原句**：「`factor_columns_view()` 对所有 spec 一视同仁（`registry.py:59-61` 只看 `id/label/group/formula_text`）」
- **新句**：「`factor_columns_view()` 在 `registry.py:408`，行内只看 `id/label/group/formula_text`，`column_view()` 在 `:61`」
- **依据**：`:59-61` 是 `FactorSpec.column_view()` 方法体；`def factor_columns_view()` 在第 408 行
- **命令**：`grep -n "def factor_columns_view\|def column_view" backend/app/factors/registry.py`

### C4（附带）#7 行补 5 组 `prior_*` 的写法差异

- **原句**：「两份的公式原文**不同 1 ULP**：pack 用 `(close - ts_delay(close,1)) / ts_delay(close,1)`，store 用 `close / ts_delay(close,1) - 1`」（只说了 `vol60` 一组）
- **新句**：「8 组里**只有 2 组表达式完全相同**（`ma120`/`ma200`）…另 5 组 `prior_*` 是**同窗口不同写法**」
- **依据**：逐文件读 `formula`；`ts_delay(ts_max(high,N),1)` 与 `ts_max(ts_delay(high,1),N)` 窗口同为 `[t-N,t-1]`

---

## 4. 未确证 / 未覆盖（不用「大概」圆过去）

| # | 项 | 状态 |
| --- | --- | --- |
| 1 | 8 组里第 4–8 组（5 个 `prior_*`）的逐值 `max_abs_diff` | **未跑**；只有表达式对照，无非零行占比 |
| 2 | `rsi_14` 与研究 `rsi14` 的逐值差 | 沿用 D2 的 0.892 点基线，本轮**未复算** |
| 3 | 闸门性能（`assert_factors_usable` 在 200+ 因子 × 每 bar 调用的开销） | **未测**；`gate.py` 尚不存在 |
| 4 | 活配置引用面（§7.8.1 #12 的 2 个文件） | 沿用上一轮枚举，**本轮未重跑** |
| 5 | `repo data/` 与 `ext_*` 85 个里是否有 python 因子 | **未查**；只查了 `D:/TSP/data` 的 15 个 |
| 6 | `store.py` 那 1 行删除（`+91/−1` 的 −1） | **未逐行审**，留给独立审核按 §7.4 禁止面判 |
| 7 | 15:51:09 写盘的动作主体 | **无法从盘上判定**（见 §0） |
| 8 | 存量 `draft` 因子清单（批二启用闸门的前置） | 仍未盘点；`D:/TSP/data` 侧 15 个定义里 14 个 `status=draft`、1 个 composite `draft` |

---

## 5. 未改动清单（边界证明）

```bash
cd /c/work/sourcecode/tick-stock-panel
git status --porcelain
```

- `docs/factors/**`、`docs/research/**`、`backend/**` 本轮**未改一字**；`docs/architecture/` 为未跟踪目录，本轮只动其中 2 个文件：契约正文、本修订记录。`archive/` 归档件**未动**。
- `git status` 里的 `M backend/app/api/factors.py`、`M backend/app/factors/store.py` 是 15:35:28 的批一b 工作区改动，**先于我本轮**，我未 touch；`M research/strategy-search-20261107/**` 4 个文件同理，非本轮。
- **未 add、未 commit、未部署、未重启**。

## 6. 给下游的两条执行提示（不是验收结论）

1. **批二闸门上线前必须做两件事**（否则上线即停产）：盘点存量 `draft`／Provider 无 `status` 的活配置引用；把台账 `canonical_id`/`aliases[]`/`superseded_by` 逐行填满（8 组双 id 一组不落）。
2. **§7.8 的 `FS03`–`FS06` 与 §7.7 的 `FS01/FS02` 是同一实现的两个半边**：`gate.py#assert_factors_usable()` 一次性实现，禁止各入口各写一遍；`mode` 三值（`production`/`research`/`diagnostic`）与 `verifiable`/`alias` 两个布尔维度叠加，不新增状态机。

---

本文件正文 sha256：`782b5f89f05586577b4f1e326c7bd4a6aa0872c787a0cdc192879e99c94fe18b`（校验：`head -c 22152 "docs/architecture/CONTRACT_REVISION_R3_20261107.md" | sha256sum`）· 行数 288 · 生成 2026-11-07 · 配套契约 v0.4（110,944 B / 1,050 行 / 正文 `11bfe51f…27f9c3`）
