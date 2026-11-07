# B0 验收与 v0.7 复审 — 独立审核报告

独立审核工程师 · 2026-11-07 18:0x–18:4x · 项目 `C:\work\sourcecode\tick-stock-panel`
测试环境：`PYTHONUTF8=1`；所有数值由我自己写脚本复算（`research/independent-review-20261107/b0r2/`），未使用作者 `research/factor-registration-20261107/verify_b0.py`。

## 0. 绑定四值（本轮开头与收尾各复算一次，均命中）

| 对象 | 字节 | 行 | sha256 |
| --- | ---: | ---: | --- |
| 唯一验收锚 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` | 89,833 | 914 | `5eb97724…565903` |
| 同上 `head -c 89350` | — | — | `b082d902…f9bfef` |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` | **193,586** | **1,696** | **`5a87d4b0…f8723e8`** |
| 同上 `head -c 191933`（正文） | — | — | `73e15ddc…8efd6d0` |
| HEAD | — | — | `65c6e42f1fcd6362e72699afb118bdbcb247b3d3` |

**版本绑定说明（必须留档）**：本轮开工时盘上 v0.7 是 `f7b6adb2…`/193,073 B/1,696 行。评审中途（18:03:23）架构师追加了 513 B，现为 `5a87d4b0…`/193,586 B。我以 **当前 sha `5a87d4b0` 重新绑定了全部行号并逐条复核**，本报告所有 v0.7 行号均指该版。`CONTRACT_REVISION_R7_20261107.md §7.2` 声明的四元组（193,586 B / 正文 `73e15ddc` / 全文 `5a87d4b0`）与我实测**逐位一致**，因此 R7 与盘上 v0.7 是同一版；早先的 `f7b6adb2` 是未落地的中间稿，不作锚。

---

## A 块：B0 的 14 个因子注册验收

### A 块总判定：**PASS-with-conditions**（按收窄口径「研究名对齐 + 6 个 pack-only canonical」**可以结项**，但结项记录必须带 A7 的两条书面遗留）

### A1 编译与保真 —— PASS

14 个 pack id 全部 `compile_formula("<id> > 0")` 成功（14/14，bad=[]）。保真我自己抽 25 只、评估窗 2019-07-01…2026-10-30 复算：

| 项 | 实测 |
| --- | --- |
| 抽样标的 | 25 只（自 3,384 只等间距取） |
| 评估行 | 41,489 |
| **参与比较行（14 因子合计）** | **577,179**（要求 ≥3 万，达标 19.2 倍） |
| `max_abs_diff` | **14/14 = 0.0**，`nonzero_rows` 全 0 |
| 空值位置 | 14/14 双向 0（`ref_notnull_platform_null` = `ref_null_platform_notnull` = 0） |
| 参考值来源 | 我自己写的 polars 表达式（`rolling_mean/std/max/min` + `shift(1)`） |

复现：`indep_b0_wide.py` → `577179 rows compared`（本轮 18:29 重跑，与上一轮同结论）。

### A2 `n` 判据 —— PASS（作者改判成立，两个数字我独立复算命中）

作者主张「`n > 5.4e6` 对 `ma200`/`prior_high_250` 算术不可达，改判 `n` = 该 warmup 下可达上界且 `diff = 0`」。我独立实现上界：**全历史滚动后再取评估窗**（不是窗内重滚），每股 `upper_i = b_i − max(0, w − p_i)`，`b_i` = 窗内 bar 数、`p_i` = 窗前 bar 数、`w` = 首个非空 0-based 位置。

| 因子 | `w` | 我算的可达上界 | 平台实测非空 | 相等 |
| --- | ---: | ---: | ---: | --- |
| `ma20`/`boll_lower`/`boll_upper`/`sd20` | 19 | 5,497,082 | 5,497,082 | 是 |
| `ma60` | 59 | 5,470,011 | 5,470,011 | 是 |
| `prior_high_20`/`prior_vol_20`/`prior_amount_20` | 20 | 5,496,401 | 5,496,401 | 是 |
| `prior_low_10` | 10 | 5,503,218 | 5,503,218 | 是 |
| `prior_high_55` | 55 | 5,472,715 | 5,472,715 | 是 |
| `vol60` | 60 | 5,469,335 | 5,469,335 | 是 |
| `ma120` | 119 | 5,428,988 | 5,428,988 | 是 |
| **`ma200`** | 199 | **5,371,122** | 5,371,122 | 是 |
| **`prior_high_250`** | 250 | **5,332,523** | 5,332,523 | 是 |

**14/14 严格相等，差额全 0。** 作者报的 5,371,122 / 5,332,523 复算成立，非自述。另加一项作者未做的检查：历史充足的标的中「窗内出现 null」的标的数 = **0**（`no_spurious_null_when_history_sufficient`）。判据修订**核准**。
复现：`indep_bound_v2.py` → `all_eq=True`。

### A3 warmup —— PASS

逐标的首个非空位置（0-based `N−1`；`prior_*` 为 `N`）与「前一根必须 null」逐项核对（`000001.SZ`，2,136 根）：

| id | 期望 | 实测 | 前根 null |
| --- | ---: | ---: | --- |
| `ma20`/`boll_lower`/`boll_upper`/`sd20` | 19 | 19 | 是 |
| `ma60` | 59 | 59 | 是 |
| `prior_high_20`/`prior_vol_20`/`prior_amount_20` | 20 | 20 | 是 |
| `prior_low_10` | 10 | 10 | 是 |
| `prior_high_55` | 55 | 55 | 是 |
| `vol60` | 60 | 60 | 是 |
| `ma120` | 119 | 119 | 是 |
| `ma200` | 199 | 199 | 是 |
| `prior_high_250` | 250 | 250 | 是 |

`prior_*` 用 `N` 而非 `N−1` 正确 —— 与 `ts_delay(ts_max(high, N), 1)` 定义一致。14/14 与参考实现一致。

### A4 幂等 —— PASS（分阶段实测；订正我上一轮的口头表述）

| 阶段 | 动作 | total | Δ | 14 个 pack id 计数 | 版本 |
| --- | --- | ---: | ---: | --- | --- |
| S0 | 冷启动 | 192 | — | 14×1 | 全 1 |
| S1 | `ensure_factor_providers()` ×1 | 192 | 0 | 14×1 | 全 1 |
| S2 | 再 ×3 | 192 | 0 | 14×1 | 全 1 |
| S3 | `register_factor_provider(同一实例)` ×2 | 192 | 0 | 14×1 | 全 1 |
| S4 | `load_into_registry(store)` ×2 | **207** | **+15** | **仍 14×1** | **仍全 1** |

**判定：pack 注册严格幂等（192→192，无重复 id，版本不递增）。** S4 的 +15 是**首次装载 store 里 15 个盘上定义**（`cf_auction_resonance` + 14 个 `uf_*`），每条只出现 1 次（`dup_ids=[]`、`pack_id_unique=True`），不是重复注册。

**订正我自己上一轮的口头结论**：我曾笼统说「幂等通过」（把 S4 的 192→207 也一并算作通过），那是不准确的。准确说法：**pack 注册严格幂等；207 是装了 store 的生产态基线，192 只是未装 store 的诊断态。** 分阶段脚本 `indep_b0_final.py` 的汇总字段 `total_stable_all_phases=False` 正是这个意思，不是缺陷。

### A5 dual-id 事实核对 —— 事实成立；**alias 闸门代码零落地（阻塞结项表述）**

**① 同一口径是否真的两套实现都进生产路径 —— 是（实测）。** 按生产启动序列（`main.py:217-221`、`worker.py:234-236`）装载后探测（`indep_alias_prod.py`）：

```
[startup] loaded_count=15 total=207 n_uf_cf=15
[alias_registry_prod] all_pairs_present=True  all_pairs_compile=True
```

8 对双 id 全部同时在册、全部可编译进策略表达式。经同一生产物化函数 `materialize_scoring_columns` 同时取值：

| 口径 | 同时非空行 | `max_abs_diff` | 不等行数 |
| --- | ---: | ---: | ---: |
| `vol60` vs `uf_vol60` | 1,623 | 2.43e-17 | 1,471 |
| `ma120` / `ma200` | 1,446 / 1,206 | 0.0 | 0 |
| `prior_high_20`/`_55`/`_250`/`prior_low_10`/`prior_vol_20` | 1,053…1,773 | 0.0 | 0 |

**注意冷启动反例**：不跑生产启动序列时 `n_uf=0`，`uf_*` 全部不在册，`materialize_scoring_columns(("uf_vol60",))` 直接 `ColumnNotFoundError`。**所以「双 id 并存」是生产装载后的状态，不是注册表固有状态** —— 这一点必须写清，否则单测会把 0 个 `uf_*` 当成正常。

**② alias 的 `strategy_usable=false`：只写在文档里，代码零落地 —— 本轮最硬的一条缺陷。**

```
$ grep -rn "strategy_usable" --include=*.py backend/          → 无输出
$ grep -rn "alias_of|replaced_by|canonical_id" --include=*.py backend/ → 无输出
$ grep -rn "FS03|FS10|MATRIX_KERNELS|G2CaliberError|FS08" --include=*.py backend/app backend/tests → 无输出
```

`strategy_usable` / `alias_of` / `replaced_by` 在 `backend/` 全部 `.py` 中**零出现**，只存在于 `docs/architecture/*.md`、`docs/factors/evidence/*.json` 与 v0.7 §7.15 表。v0.7 `:1547`（§7.15.1 读表规则 1）要求「研究原名是 alias，标 `alias_of` + `strategy_usable=false`，生产入口 `FS03` 拒」；`FS03` 见 `:974`、`:999`、`:1006`；`:1081` 自述「`gate.py` 不存在，`alias_of`/`FS03`/`assert_factors_usable` 在 `backend/app/**` 中 0」。**契约自己承认零实现，与我实测一致。**

后果：`vol60` 与 `uf_vol60` 都能被策略引用，生产入口**没有任何拦截**，两条差 1 ULP 的路径可被不同策略分别选中。收窄口径的前提「8 个 pack id 只是 alias、策略侧须用 `uf_*`」**当前不可机械保证**，只依赖写入者自觉。

**③ `prior_amount_20` 确实只有 pack 一侧 —— 成立。** `get_factor("uf_prior_amount_20") is None`、`uf_prior_amount_20_exists=False`，与 v0.7 §7.15 表一致。

**④ `vol60` 两式差是否落在 `F-A3` 的 `<1e-12` 内、有没有被写成「逐位相同」。**

我按作者**同一口径**（60 只标的 / 116,287 行探针，即 `probe_vol60.py` 的取数方式）复算：

| 比较对象 | `n_both` | 不等行 | 占比 | `max` |
| --- | ---: | ---: | ---: | ---: |
| `vol60`（文字式 `x/shift−1`）vs `vol60`（减法式） | 112,741 | 87,841 | **77.914%** | 1.11e-16 |
| 同上，分母改 116,287 行 | — | 87,841 | 75.538% | — |
| 原始收益率 `pct_change` vs 文字式（同 60 只） | 116,227 | 108,887 | 93.685% | 1.11e-16 |
| 原始收益率，全样本 3,384 只 | 6,419,491 | 6,050,254 | 94.248% | 2.22e-16 |

- **差值 1.11e-16 远小于 `1e-12`，`F-A3` 通过**；B0 包采用减法式后与 `pct_change` **逐位相等（0.0）**。**这一条 B0 可以算结项。**
- **但 `docs/factors/REGISTRATION_B0_20261107.md` 两处可证伪：**
  - `:12`「14/14 … `max_abs_diff = 0`（**逐位相等**）」—— 该「逐位相等」只在 pack 侧成立；store 侧 `uf_vol60` 与 pack 差 1 ULP、77.9% 行不等。用「14/14 逐位相等」概括全口径违反 v0.7 `:1552`（§7.15.2 硬约束「`vol60` 两式差 1 ULP，禁止写逐位相同」）。
  - `:219`「**4.6% 的行不等**（60 只标的 116,287 行探针）」—— 按该句自己声明的口径复算是 **77.914%**（分母 112,741）或 75.538%（分母 116,287），**与 4.6% 差一个数量级以上**。4.6% 不可复现，是错的。

**A5 判定：dual-id 事实 PASS；alias 闸门 FAIL（阻塞「alias 已隔离」的结项表述）；`:12`/`:219` 两处数字/表述 FAIL。**

### A6 矩阵路径 —— **canonical `uf_*` 覆盖 0/9（实测）**；研究名侧 6/14

用真实的 `MarketDataMatrix`（5 只 × 601 日，`close.dtype=float32`）逐名实调 `matrix_feature`：

| 分组 | 因子 | 结果 |
| --- | --- | --- |
| 可算 6 | `ma20` `ma60` `ma120` `ma200` `boll_lower` `boll_upper` | 返回 `float32`，`shape=(601,5)` |
| 不可算 8 | `sd20` `vol60` `prior_high_20` `prior_high_55` `prior_high_250` `prior_low_10` `prior_vol_20` `prior_amount_20` | `ValueError: unsupported matrix feature: <id>` |

**canonical 侧 9 个 `uf_*` 全部 0/9**：`in_MATRIX_COMPUTED_FEATURES=False`、`provider=None`、`matrix_value=None`。

反例调用（最小复现，直接可跑）：

```python
from app.backtest.matrix import build_market_data_matrix, matrix_feature
m = build_market_data_matrix(panel_df)   # close.dtype = float32
matrix_feature(m, "ma120")               # → float32 array (601,5)
matrix_feature(m, "uf_ma120")            # → ValueError: unsupported matrix feature: uf_ma120
```

机制：`uf_*` 是 store 注册的 `kind=custom` 公式因子，`factor_provider_for("uf_ma120")` 返回 `None`，名字既不进白名单也不匹配 `ma*`/`ema*`/`rsi_*`/`momentum_*` 前缀启发式 → 走到 fail-closed 抛错。

**顺带订正我上一轮的方法错误**：我只看静态表 `_MATRIX_COMPUTED_FEATURES` 就报「2/14」，漏了前缀启发式，导致错判 `ma20`/`ma60`/`ma120`/`ma200` 不可算。真实覆盖是 **6/14（研究名）**，与 v0.7 §7.13.1 一致。

**阻塞判定：不阻塞 B0 本批结项（B0b 是独立批次），但阻塞任何「canonical id 可在矩阵路径使用」的声明。**

### A7 结论：B0 能否按「研究名对齐 + 6 个 pack-only canonical」结项

**能结项，但必须带两条书面遗留：**

1. **A1/A2/A3/A4 四项实测 PASS**：保真 577,179 行 14/14 零差、上界 14/14 严格相等、warmup 14/14 全中、pack 注册 192→192 严格幂等。
2. **A5② alias 闸门不存在** —— 收窄口径的「策略侧须用 `uf_*`」无机械保证。**结项记录须原文写：**「8 个 pack id 目前仍是与 `uf_*` 并存的可引用实现；隔离依赖 `FS03`，`FS03` 未实现。」**不得写「alias 已隔离」。**
3. **A5④ 两处必须订正**：`REGISTRATION_B0_20261107.md:12` 的「逐位相等」改为「pack 侧 0.0；`uf_vol60` 与 pack 差 1 ULP（1.11e-16，`F-A3` 内），77.9% 行不等」；`:219` 的「4.6%」改为「77.914%（60 只 / 112,741 可比行）」。

### A.7 我自己的三处方法错误（留档，避免被算到作者头上）

1. 首版 `reachable_bound()` 在**评估窗内**重新滚动，人为制造 warmup 缺失，上界偏低约 53 万行 → 已改为全历史滚动后取窗。
2. 上界式用 `pl.lit(0)`（Int32）与 UInt64 相减发生**整数环绕**，上界虚高到 635 万 → 已改 `Int64` 显式比较。
3. A6 只查静态白名单、漏前缀启发式，误报 2/14 → 已改为实调 `matrix_feature` 逐名探测，得 6/14。

---

## B 块：v0.7 复审

### B 块判定：**已按 sha 审 `5a87d4b0`（193,586 B / 1,696 行）。F-A40 条款可判定、实现为零；F-A41 与 §7.13 与我实测一致、实现为零；`F-A11b` 有一处判据歧义（同一句两个读法，对正确核判决相反）；§4.6 B1 与 A7 14 日已按实测改且方向收窄。**

### B1 `F-A40`（D5 fail-closed）—— 条款 **PASS（可判定）**，实现 **未落地**

条款链完整、可机械判定：sentinel `_UNSET` → `G2CaliberError` → HTTP 400 `detail={"code":"FS08","missing":[...]}`。5 条判据在 `v0.7:82-86`，全部一义（只缺一个字段 → 该字段进 `missing`；全字段齐给显式值 `close_t`+`adjusted` → 成功；`research` 需 `g2_override=true`，`production` 400 `FS08`）。

三处默认值与 G2 相反的**事实描述我核对为真**：`engine.py:228` `matching="close_t"`、`:258` `entry_price_basis="adjusted"`、`__post_init__` 的 `entry_fill/exit_fill → matching` 回退（`engine.py:280-283`）。

但 **`F-A40` 现在一条也跑不了**：`G2CaliberError` / `FS08` / `_UNSET` 在 `backend/app` 与 `backend/tests` 的 `.py` 中**零出现**。**判定：条款准予作为 G-A2 开门条件；本条不阻塞冻结（它是规格），但「D5 已修」只能说「条款已写」，不能说「已可验收」。**

`§7.15.3` 自述「14 只全无 `status`」我抽查成立：`FactorSpec` 无 `status` 字段，盘上 15 个 JSON 均 `"status":"draft"`。P2 定性我同意（不阻塞）。

### B2 `F-A41` / `§7.13`（`MATRIX_KERNELS`、`FS10` 准入拒绝）—— 条款与实测 **一致**，实现 **零**

- `§7.13.1`（`v0.7:1394`）的 14 行表（6 可算 / 8 不可算，逐行给机制）**与我 A6 实测逐项相同**，包括「`ma20` 靠 `name[2:].isdigit()` 通过、`vol60` 因不匹配被拒」这条「拼写决定支持性」的判断。
- `§7.13.2` 三处缺陷定位准确：`factors.py:86-88` 基类 `return None`、fail-closed 抛错点 `matrix.py:4557`、白名单 60 名 + 6 条前缀。
- `§7.13.3`（`:1425`）硬要求 5 条写得很实（尤其 `F-A41-5` 要求基类改 `NotImplementedError`、全仓禁止「返回 None 表示未实现」），**建议保留**。
- 但 `MATRIX_KERNELS`（`:1428`）/ `matrix_supported` / `FS10` 在代码中**零出现**，`F-A41-1…5`（`:1446-1450`）一条都不可执行。

### B3 `F-A11a`–`d` 分层容差 —— **F-A11b 有一处判据歧义：同一句两个读法，对正确核判决相反**

用真实 `matrix_feature` 输出（8 只 × 843 日）算误差，`v0.7:1501`（`F-A11b`）原文是：

> 逐列 `rel = max|p−m| / max(|p|, 1e-12) ≤ 2^-23 = 1.192e-07`；且逐列 `max|p−m| ≤ 2^-23 × max|p|`

这句含**两个不同定义**：前半段的 `1e-12` 只有当 `max(|p|,...)` 是**逐元素分母**（每元素除以自己的 |p|）时才有意义 —— 若按列级，分母恒为列最大值，「1e-12」永不触发，是死代码。而后半段 `max|p−m| ≤ 2^-23 × max|p|` 明确是**列级**。我按两种读法在同一组真实数据上分别算（`fa11b_read.py`）：

| 因子 | 读法1（逐元素 `rel`） | 判定 | 读法2（列级） | 判定 | 判决相反 |
| --- | ---: | --- | ---: | --- | --- |
| `ma20` | 6.874e-08 | PASS | 4.485e-08 | PASS | 否 |
| **`boll_lower`** | **1.416e-07** | **FAIL** | 8.635e-08 | PASS | **是** |
| **`boll_upper`** | **1.429e-07** | **FAIL** | 8.721e-08 | PASS | **是** |

**这不是语义错，是正确的 float32 核。** `boll_* = ma20 ± 2·sd20`，两次 float32 舍入沿复合运算累积，逐元素 `max_rel` 突破单次舍入界 `2^-24`，也突破 `2^-23`。我核了越线点：`boll_lower` 最坏元素 `|p| = 9.273`、`absdiff = 1.313e-06`、`rel = 1.416e-07` —— **不是近零值退化**，是正常量级上的舍入累积。

**为什么 v0.7 没测到**：`§7.14.2`（`v0.7:1468-1480`）那张表每列「相对误差 max」都恰是 `5.96e-08 = 2^-24`，证明它只算了「同一 float64 值存成 float32」的**单次存储舍入**，没算矩阵核内部的累加/复合误差。`§7.14.4` 末句自己也说「实测只覆盖单次舍入，不含 float32 累加」—— 所以 `2^-23` 这个「留一倍余量」对复合因子不够，实测差 **1.19×–1.20×**。

**修法建议（二选一，建议第 1 条，代价最小且不放松语义错判别力）：**

1. **保留 `2^-23` 不动，把 `F-A11b` 明确写成列级一条**：`max|p−m| ≤ 2^-23 × max|p|`，删掉「`/ max(|p|, 1e-12)`」那句（或标注它只是列级分母写法）。实测列级 6/6 PASS。
2. 若坚持逐元素，容差须提到 `3·2^-23 ≈ 3.6e-07`，并在 `§7.14.2` 表下补「复合因子」一行实测（`boll_*` 达 1.43e-07）。

**判别力（你点名要的「漏 `shift(1)` 能被抓出」）—— 成立。** 我独立构造正确核 / 错误核（`fa11_power.py`，`sd20`/`prior_high_20`/`vol60` 各 6 只）：

| 因子 | 正确核 `max_rel` | 错误核 `max_rel` | 正确核 jaccard / 翻转 | 错误核 jaccard / 翻转 |
| --- | ---: | ---: | --- | --- |
| `sd20` | 2.18e-06 | **0.947** | 1.000000 / 0 | 0.959579 / **146** |
| `prior_high_20`（漏 `shift(1)`） | 5.82e-08 | **0.166** | 1.000000 / 0 | 0.991597 / **30** |
| `vol60` | 1.19e-06 | **672** | 0.999707 / 1 | 0.499635 / **3,423** |

语义错与量化噪声差 3–9 个数量级，`F-A11c`（jaccard ≥ 0.9999 且翻转 0）**确实抓得住**。但 `vol60` 正确核本身 jaccard 0.999707 / 翻转 1 已越线（0.999707 < 0.9999），说明 0.9999 对低量级因子偏紧。用真实 `ma20` 对照（`fa11b_reach.py#discrimination`）：正确核翻转 0、19 日窗冒充 20 日翻转 9 → 抓住。

**另注 `F-A11d`（`v0.7:1503`）的 `tolerance="eps32"` 是自指字符串**，不可机械判定；建议写具体值（如 `"2^-23_col"`）。

### B4 `§4.6 B1` 的 null 日表述 —— **已改，且改得更严**

`v0.7:497`：`n_days = 1,770`、`max_abs_diff < 1e-12`、该子集研究侧均值 **0.542252**、生产 `null` 日单列 9 天，并明写「原『1,779 日 / 0.540742』是**含 `null` 日**的旧记录，**不作判据**」。方向是**收窄**（排除 null 日），符合「收窄不算放宽」。`§4.6.1` 新增。**判定：已改，文本自洽。**
（`n_month_end` 88→87、通过率 0.534091→0.540230 同样收窄，见 `:498`。这些数值我不重算 —— 需 `xs_rank_pool` 实现与月末日历，见未验证项。）

### B5 `A7` 的 ST 窗口 14 日 —— **已按实测改，与证据一致**

`v0.7 §2.6 A7` 改为「窗口终点 = 数据末端，不是固定 8 天」，当前 14 天 = 8 + 6，且**明令禁止硬编码 8 或 14**（两条规则现算），并要求 `coverageEnd` 前移时自动收缩。证据指向 `docs/factors/E3_DATA_AVAILABILITY_20261107.md`，我核了 `:18`、`:112`、`:116`、`:118`：ST 表 `2026-10-20` 一次性写入 198 行 `st_flag=False`、此后 0 条 `True`，ST=True 由 218 家降到 20 家并持续至 `2026-11-06`（14 个交易日）。**契约与证据一致，判定 PASS。**

### B6 一条契约自洽问题（非阻塞，建议与 B0-4 同批改）

`§7.14.2` 说 float32 相对表示误差上界 `2^-24`，`§7.14.4` 设容差 `2^-23` 并注「留一倍余量」；但 `§7.14.2` 表里每列 `max rel` 恰是 `5.96e-08`，说明该表**只测存储舍入**。我的 `boll_*` 1.19×–1.20× 实测证明「一倍余量」对复合因子不够。建议在 `:1480` 后补一句：「本表为存储舍入下界；复合因子（`boll_*` = `ma ± 2·sd`）实测 `max_rel` 可达 1.43e-07，故 `F-A11b` 按列级判（见 §7.14.4 修法）。」

---

## C 未验证项（单列，不得视为通过）

1. **端到端 API**：`GET /api/factors`、`POST /api/backtest/*` 上 14 个因子的可见性与错误码未测。
2. **`FS03`/`FS08`/`FS10`/`MATRIX_KERNELS`**：代码零实现 → `F-A40-1…5`、`F-A41-1…5` **一条都未实跑**，本报告只判「条款可判定」。
3. **`strategy_usable` 的运行时效果**：代码零落地，「alias 被拒」**无对象可验**（不是验证失败）。
4. **`§4.6 B1/B2` 的 1,770 日 / 87 月末 / 0.542252 / 0.540230**：未重算（需 `xs_rank_pool` 实现与月末日历）。
5. **`XS-A7` 双路径 `≤1e-12`**：与 `F-A11` 同源（矩阵 float32），未单独验。
6. **`A7` 的 2,772 标的日偏差**：核了证据文件与契约一致，未在行情库上独立重算 `198×14`。
7. **矩阵路径是否被生产回测实际使用**：`engine.py:23-29` 从 `matrix` 导入属生产路径，但「某条具体策略回测是否走到 `matrix_feature`」未逐策略验证。
8. **B0 的部署面**：pack 在 `backend/app/custom/`，按 `app/custom/*/factor_provider.py` 自动发现，逻辑上应生效，未在部署态验。
9. **`F-A11b` 列级判据的全市场复算**：列级结论基于 8 只 × 843 日 = 6,592 行样本，未覆盖全市场约 1.7M 行。

## D 缺陷清单

| # | 文件:行 | 问题 | 阻塞 | 改法 |
| --- | --- | --- | --- | --- |
| B0-1 | `docs/factors/REGISTRATION_B0_20261107.md:12` | 「14/14 … `max_abs_diff = 0`（逐位相等）」把 pack 侧结果概括为全口径；store 侧 `uf_vol60` 与 pack 差 1 ULP、77.9% 行不等。违反 v0.7 `:1552`（§7.15.2 禁止写逐位相同） | **是**（结项记录不可带此句） | 改为「pack 侧 0.0；`uf_vol60` 与 pack 差 1.11e-16（`F-A3` 内），77.9% 行不等」 |
| B0-2 | `docs/factors/REGISTRATION_B0_20261107.md:219` | 「4.6% 的行不等」按该句自己声明的口径复算是 **77.914%**（60 只 / 112,741 可比行），差一个数量级以上 | **是**（数字错误，不可复现） | 改为 77.914%，并注明分母 112,741（不是 116,287） |
| B0-3 | 全仓 + `backend/app/extensions/factors.py` | `strategy_usable`/`alias_of`/`FS03` 代码零落地；8 个 pack alias 与 `uf_*` 并存且都可被策略引用，收窄口径前提无机械保证 | **是**（阻塞「alias 已隔离」的结项表述） | 结项记录写明闸门未实现；或实现 `FactorSpec.alias_of` + `FS03` 后再声明隔离 |
| B0-4 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md:1501`（`F-A11b`） | 同一句混用逐元素（`/max(|p|,1e-12)`）与列级（`≤ 2^-23 × max|p|`）两个定义；按逐元素算正确核 `boll_lower` 1.19×、`boll_upper` 1.20× **FAIL**，按列级 6/6 PASS。判据不可机械判定 | **是**（会误判正确实现，阻塞 B0b 验收） | 明确为列级：`max|p−m| ≤ 2^-23 × max|p|`；删逐元素句；`§7.14.2` 表下补复合因子上界 1.43e-07 |
| B0-5 | `v0.7:1502`（`F-A11c`） | 0.9999 对低量级因子偏紧：`vol60` 正确核 jaccard 0.999707 / 翻转 1，越线 | 否（P2） | 按量级分档，或改「翻转 0 且 jaccard ≥ 0.999」 |
| B0-6 | `v0.7:1503`（`F-A11d`） | `tolerance="eps32"` 是自指字符串，不可机械判定 | 否 | 写具体值 `"2^-23_col"` |
| B0-7 | `v0.7:1468-1480`（§7.14.2 表） | 表只测存储舍入下界（每列恰 5.96e-08），未含核内累加/复合误差，与 §7.14.4「一倍余量」立论不闭合 | 否（与 B0-4 同批改） | 表下补下界说明 + 复合因子实测 |
| B0-8 | `backend/app/custom/research_factor_pack/factor_provider.py:20-23`（注释） | 注释说「矩阵侧实现是缺能力项…本包不在此处补一套」，未点名 `ma20/ma60/ma120/ma200` 在矩阵侧**已可算**（靠前缀启发式），易被读成 6 个全不可用 | 否 | 注释补「4 个 `ma*` 经前缀启发式可算，2 个 `boll_*` 经白名单可算」 |

**阻塞 4 条：B0-1、B0-2（B0 结项表述）、B0-3（alias 闸门陈述）、B0-4（`F-A11b` 判据歧义）。** 前两条是文档订正（分钟级），B0-3 是结项措辞（不写代码就能不撒谎），B0-4 是一条判据的文字收窄（不放松语义错判别力）。

## E 一句话回答你两个问题（两块分开，不合并总评）

- **A 块（B0）**：按「研究名对齐 + 6 个 pack-only canonical」**可以结项** —— 四项实测 PASS（577,179 行 14/14 零差 / 上界 14/14 严格相等 / warmup 14/14 / pack 注册 192→192 严格幂等）。但结项记录必须原文写明「8 个 pack id 仍与 `uf_*` 并存可引用，`FS03` 未实现」，并订正 `:12`「逐位相等」与 `:219`「4.6%」（实为 77.914%）两处。**矩阵侧 canonical `uf_*` 覆盖 0/9，不阻塞本批，但阻塞任何「canonical 可用于矩阵路径」的声明。**
- **B 块（v0.7）**：已按 **`5a87d4b0`（193,586 B / 1,696 行）**审。`F-A40`/`F-A41` 条款可判定、实现为零（不阻塞冻结，阻塞验收）；`§4.6 B1` 与 `A7` 14 日已按实测改且方向收窄，PASS；**`F-A11b` 必须明确成列级一条，否则正确的 `boll_*` 矩阵核会被判 FAIL。**

**本轮我不给 v0.7 整体 PASS**，唯一理由是 B0-4：判据会判错正确实现。这不是风格问题。

## F 复现命令

```bash
cd /c/work/sourcecode/tick-stock-panel
# A1 保真（577,179 行 14/14 零差）
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_b0_wide.py
# A2 可达上界（14/14 严格相等）+ A5 冷启动态
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_bound_v2.py
# A4 分阶段幂等（S0..S4）
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_b0_final.py
# A5 生产启动态 8 对双 id + A6 uf_* 覆盖 0/9
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_alias_prod.py
# A6 真实 MarketDataMatrix 逐名探测（6/14）
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_matrix_probe.py
# A5④ vol60 按作者口径复算 4.6% → 77.914%
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/vol60_4p6.py
# B3 F-A11b 两读法判决相反 + F-A11c 判别力
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/fa11b_read.py
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/fa11_power.py
# 绑定四值
wc -c docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md            # 89833
sha256sum docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md        # 5eb97724…565903
head -c 89350 docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md | sha256sum  # b082d902…f9bfef
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md                       # 5a87d4b0…f8723e8
head -c 191933 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md | sha256sum      # 73e15ddc…8efd6d0
# 零落地断言（两条都应无输出）
grep -rn "strategy_usable\|alias_of\|replaced_by" --include=*.py backend/app   # 期望空
grep -rn "G2CaliberError\|FS08\|_UNSET\|MATRIX_KERNELS\|FS10\|FS03" --include=*.py backend/app backend/tests  # 期望空
```
