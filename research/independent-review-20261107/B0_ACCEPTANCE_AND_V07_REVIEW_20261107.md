# B0 验收与 v0.7 复审 — 独立审核报告

独立审核工程师 · 2026-11-07 18:0x · 项目 `C:\work\sourcecode\tick-stock-panel`

## 0. 绑定（评审开始时算，评审结束时复算，未变）

| 对象 | 字节 | 行 | sha256 |
| --- | ---: | ---: | --- |
| 唯一验收锚 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` | 89,833 | 914 | `5eb97724…565903` |
| 同上 `head -c 89350` | — | — | `b082d902…f9bfef` |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` | 193,073 | 1,696 | `f7b6adb2…3002908` |
| `research_factor_pack`（3 文件，mtime 14:33/14:34/14:42） | — | — | 未改动 |
| HEAD | — | — | `65c6e42f1fcd6362e72699afb118bdbcb247b3d3` |

v0.3 四值四项全中（本机 17:5x + 18:0x 各算一次）。活文件 `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B）与 `_v0.5.md`（138,729 B）未作锚。

**评审方法：** 所有数值我自己写脚本复算（`research/independent-review-20261107/b0r2/`），未使用作者 `research/factor-registration-20261107/verify_b0.py`。测试环境 `PYTHONUTF8=1`。中途我发现并修正了自己两个方法错误（见 §A.7 自纠），修正后的结果才是下面的结论。

---

## A 块：B0 的 14 个因子注册验收

### A 块总判定：**PASS-with-conditions（按你今日收窄的「研究名对齐 + 6 个 pack-only canonical」口径，可结项；条件见 A7）**

按收窄口径，B0 的交付物 = ①14 个研究名可编译可引用 ②6 个 pack-only canonical（`ma20`/`ma60`/`sd20`/`boll_lower`/`boll_upper`/`prior_amount_20`）在注册表里是唯一载体 ③数值保真与预热正确。这三条我实测全部成立。**但 A5 的 alias 闸门与 A7 的两处表述必须在结项记录里处理，不能当作已清零。**

### A1 编译与保真 —— PASS

```
$ python -c "compile_formula(f'{i} > 0') for 14 ids"
ok 14 / 14 bad []
```

保真我自己抽 25 只、评估窗 2019-07-01…2026-10-30（`indep_b0_wide.json`，17:48:38）：

| 项 | 实测 |
| --- | --- |
| 抽样标的 | 25 只（自 3,384 只等间距取） |
| 评估行 | 41,489 |
| 参与比较行（14 因子合计） | **577,179**（＞3 万要求） |
| `max_abs_diff` | **14/14 = 0.0**，`nonzero_rows` 全 0 |
| `ref_notnull_platform_null` / `ref_null_platform_notnull` | 14/14 全 0（空值位置逐位一致） |
| 参考值来源 | 我自己写的 polars 表达式（`rolling_mean/std/max/min`、`shift(1)`），非作者脚本 |

另有 3 只 / 3,660 行小样本（`indep_b0.json`，17:42）同结论。**保真成立。**

### A2 `n` 判据 —— PASS（作者判据修订复核成立，上界数字全中）

作者请求「`n > 5.4e6` 对 `ma200`/`prior_high_250` 算术不可达，改判 `n` = 该 warmup 下可达上界且 `diff=0`」。**我独立复算了上界**（`indep_bound_v2.py`，算法：全历史滚动 → 取评估窗；每股 `upper_i = b_i - max(0, w - p_i)`，`b_i`=窗内 bar 数、`p_i`=窗前 bar 数、`w`=首个非空 0-based 位置）：

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

**14/14 上界与实测严格相等，差额 0。** 作者报的 5,371,122 / 5,332,523 **复算成立**，不是自述。另加一项作者没做的检查：`no_spurious_null_when_history_sufficient` —— 历史充足的标的中「窗内出现 null」的标的数 = **0**。判据修订**核准**。

### A3 warmup —— PASS

每只标的首个非空位置（0-based）与「前一根必须 null」逐项核对（`indep_b0.json#warmup`，`000001.SZ`，2,136 根）：

| id | 期望 | 实测 | 前根 null | 参考实现一致 |
| --- | ---: | ---: | --- | --- |
| `ma20`/`boll_lower`/`boll_upper`/`sd20` | 19 | 19 | 是 | 是 |
| `ma60` | 59 | 59 | 是 | 是 |
| `prior_high_20`/`prior_vol_20`/`prior_amount_20` | 20 | 20 | 是 | 是 |
| `prior_low_10` | 10 | 10 | 是 | 是 |
| `prior_high_55` | 55 | 55 | 是 | 是 |
| `vol60` | 60 | 60 | 是 | 是 |
| `ma120` | 119 | 119 | 是 | 是 |
| `ma200` | 199 | 199 | 是 | 是 |
| `prior_high_250` | 250 | 250 | 是 | 是 |

`prior_*` 的 `N`（而非 `N-1`）口径正确 —— 与 `ts_delay(ts_max(high,N),1)` 定义一致。

### A4 幂等 —— PASS（分阶段实测；我上一轮口头说「幂等通过」不够准确，这里修正）

`indep_b0_final.py` 五阶段，每阶段取 `len(all_factors())` / 14 个 pack id 计数 / 版本：

| 阶段 | 动作 | total | Δ | pack id 计数 | 版本 |
| --- | --- | ---: | ---: | --- | --- |
| S0 | 冷启动 | 192 | — | 14×1 | 全 1 |
| S1 | `ensure_factor_providers()` ×1 | 192 | 0 | 14×1 | 全 1 |
| S2 | 再 ×3 | 192 | 0 | 14×1 | 全 1 |
| S3 | `register_factor_provider(同一实例)` ×2 | 192 | 0 | 14×1 | 全 1 |
| S4 | `load_into_registry(store)` ×2 | **207** | **+15** | **仍 14×1** | **仍全 1** |

**判定：pack 注册严格幂等（192→192，无重复 id，版本不递增）。** S4 的 192→207 是**首次装载 store 里 15 个盘上定义**（`cf_auction_resonance` + 14 个 `uf_*`），不是重复注册 —— 每条只出现 1 次（`no_dup_pack_ids=true`、`dup_ids=[]`）。上一轮我把 +15 笼统说成「幂等通过」，修正为：**生产启动序列（`ensure_factor_providers` → `load_into_registry`）跑两次不会重复；207 是生产态基线，192 只是未装 store 的诊断态。**

### A5 dual-id 事实核对 —— 事实成立；`strategy_usable` 的「已确认」只在文档层，代码零落地（阻塞结项表述）

**① 同一口径两套实现是否都进生产路径 —— 是。** 按生产启动序列（`main.py:217-221`、`worker.py:234-236`）后探测（`indep_alias_prod.py`）：

```
[startup] loaded_count=15 total=207 n_uf_cf=15
[alias_registry_prod] all_pairs_present=True  all_pairs_compile=True
```

8 对双 id **全部同时在册、全部可编译进策略表达式**，且经同一生产物化函数 `materialize_scoring_columns` 同时取值得：

| 口径 | 同时非空行 | `max_abs_diff` | 不等行数 |
| --- | ---: | ---: | ---: |
| `vol60` vs `uf_vol60` | 1,623 | 2.43e-17 | 1,471 |
| `ma120` vs `uf_ma120` | 1,446 | 0.0 | 0 |
| `ma200` vs `uf_ma200` | 1,206 | 0.0 | 0 |
| `prior_high_20` / `_55` / `_250` / `prior_low_10` / `prior_vol_20` | 1,053…1,773 | 0.0 | 0 |

**「同一口径两套实现都进生产路径」是实测，不是推测。**

**② alias 的 `strategy_usable=false` 是读代码确认还是只写在文档里 —— 只写在文档里。这是本轮最硬的一条缺陷。**

```
$ grep -rn "strategy_usable" --include=*.py backend/
(无输出)
$ grep -rn "alias_of\|replaced_by\|canonical_id" --include=*.py backend/   (排除 .venv)
(无输出)
```

`strategy_usable` / `alias_of` / `replaced_by` 在 `backend/` 全部 `.py` 中**零出现**；只存在于 `docs/architecture/*.md`、`docs/factors/evidence/*.json` 与 v0.7 §7.15 表。v0.7 §7.15.1 读表规则 1 要求「研究原名是 alias，标 `alias_of` + `strategy_usable=false`，生产入口 `FS03` 拒」，而 `FS03`/`FS10`/`MATRIX_KERNELS`/`matrix_supported` 同样在代码中**零出现**。

后果（事实）：`vol60` 与 `uf_vol60` 都能被策略引用，生产入口**没有任何拦截**，两条差 1 ULP 的路径可被不同策略分别选中。B0 收窄口径的前提是「8 个 pack id 只是 alias，策略侧须用 `uf_*`」，而这条前提**当前不可机械保证**：它依赖写入者自觉，不依赖闸门。

**③ `prior_amount_20` 确实只有 pack 一侧 —— 成立。** `get_factor("uf_prior_amount_20") is None`，盘上 `custom_factors/` 无该文件，与 v0.7 §7.15.1 第 14 行一致。

**④ `vol60` 两式差是否落在 `F-A3` 的 `<1e-12` 内、有没有被写成「逐位相同」 —— 落内；但作者文档写错了，且 v0.7 §7.15.2 正是禁止这种写法。**

我全样本复算（5,510,001 行，`vol60` 比较 5,307,478 行）：

```
pct_change 式 vs 文字式 x/shift-1 : n=5307478 nonzero=4088299 share=77.029% max=1.1102230246251565e-16 over_1e-12=0
pct_change 式 vs 减法式           : n=5307478 nonzero=0      share=0.000%  max=0.0                    over_1e-12=0
```

- 差值 `1.11e-16` **远小于 `1e-12`**；B0 的包用减法式（`(close-ts_delay(close,1))/ts_delay(close,1)`）后与 `pct_change` **逐位相等（0.0）**，`F-A3` 通过。这一条 B0 **可以算结项**。
- 但 `docs/factors/REGISTRATION_B0_20261107.md:12` 写「14/14 注册完成…数值保真 `max_abs_diff = 0`（**逐位相等**）」，`:219` 写「4.6% 的行不等」。两句都可证伪：**（i）** 该「逐位相等」只在 pack 侧成立，store 侧 `uf_vol60` 与 pack 差 1 ULP、77.029% 行不等 —— 用「14/14 逐位相等」概括全口径即违反 v0.7 §7.15.2「不得写逐位相同」；**（ii）** 「4.6%」与我复算的 77.029% 不符，是错的数字。

**A5 判定：dual-id 事实 PASS；alias 闸门 FAIL（阻塞结项表述）。**

### A6 矩阵路径 —— canonical `uf_*` 覆盖 **0/9**（实测），并修正「按前缀认因子」的说法

我上一轮只看静态表 `_MATRIX_COMPUTED_FEATURES` 就报 2/14，那是方法错误：`matrix_feature`（`matrix.py:4207-4227`）有三条通路 —— provider 分支、静态白名单、**6 条前缀启发式（`ma*`/`ema*`/`rsi_*`/`momentum_*`）**。用真实 `MarketDataMatrix` 逐名实调（`indep_matrix_probe.py`，5 只 × 601 日，`close.dtype=float32`）：

| 分组 | 因子 | 结果 |
| --- | --- | --- |
| 可算 6 | `ma20` `ma60` `ma120` `ma200` `boll_lower` `boll_upper` | 返回 float32，`shape=(601,5)` |
| 不可算 8 | `sd20` `vol60` `prior_high_20` `prior_high_55` `prior_high_250` `prior_low_10` `prior_vol_20` `prior_amount_20` | `ValueError: unsupported matrix feature: <id>`（`matrix.py:4557`） |

**canonical 侧 9 个 `uf_*` 全部 0/9：**

```
[matrix_uf_coverage] covered=[] n_covered=0
  uf_vol60 / uf_ma120 / uf_ma200 / uf_prior_high_20 / uf_prior_high_55 /
  uf_prior_high_250 / uf_prior_low_10 / uf_prior_vol_20 / uf_prior_amount_20
  → in_MATRIX_COMPUTED_FEATURES=False, provider=None, matrix_value='None'
```

**反例调用（最小复现）：**

```python
from app.backtest.matrix import build_market_data_matrix, matrix_feature
m = build_market_data_matrix(panel_df)      # close.dtype = float32
matrix_feature(m, "uf_ma120")               # → ValueError: unsupported matrix feature: uf_ma120
matrix_feature(m, "ma120")                  # → float32 array (601,5)   ← 同名口径的两套 id 命运相反
```

机制：`uf_*` 是 store 注册的 `kind=custom` 公式因子，`factor_provider_for("uf_ma120")` 返回 `None`（无 provider），名字既不进白名单也不匹配前缀 → 走到 `:4557` 抛错。**这与 v0.7 §7.13.1「6/14」不冲突**（那是研究名口径），但 **B0b 的「`uf_*` 覆盖 0/9」独立实测成立。**

**阻塞判定：不阻塞 B0 本批结项（B0b 是独立批次），但阻塞任何「canonical id 可在矩阵路径使用」的声明。**

### A7 结论：B0 能否按「研究名对齐 + 6 个 pack-only canonical」结项

**能结项，但必须带两条书面遗留：**

1. **A1/A2/A3/A4 四项实测 PASS**（保真 577,179 行 0 差、上界 14/14 全中、warmup 14/14 全中、pack 注册幂等 192→192）。
2. **A5② 的 alias 闸门不存在，代码零落地** —— 收窄口径的「策略侧须用 `uf_*`」目前无机械保证。若结项记录写成「alias 已隔离」，即为不实。要求结项记录原文写：**「8 个 pack id 目前仍是与 `uf_*` 并存的可引用实现；隔离依赖 `FS03`，`FS03` 未实现。」**
3. **A5④ 的 `REGISTRATION_B0_20261107.md:12`「逐位相等」与 `:219`「4.6%」必须订正**为「pack 侧 0.0；`uf_vol60` 与 pack 差 1 ULP（1.11e-16）、77.029% 行不等、`F-A3` 通过」。

### A.7 我自己的两处方法错误（留档，避免被当成作者的问题）

1. 首版 `reachable_bound()` 在**评估窗内**重新滚动，人为制造 warmup 缺失，上界低约 53 万行 → 已改为全历史滚动后取窗。
2. 上界式用 `pl.lit(0)`（Int32）与 UInt64 相减发生**整数环绕**，上界虚高到 635 万 → 已改 `Int64` 显式比较。

两次都是我脚本的错，与 `research_factor_pack` 实现无关；修正后 14/14 严格相等。

---

## B 块：v0.7 复审

### B 块判定：**v0.7 已在盘并按 sha 审（`f7b6adb2…3002908`，193,073 B / 1,696 行）。F-A40 条款可判定但实现为零；F-A41 与 §7.13 与我实测一致；F-A11b 有一处容差缺陷（对 `boll_*` 正确核不可达）；§4.6 B1 与 A7 已改且与证据一致。**

### B1 `F-A40`（D5 fail-closed）—— 条款 **PASS**（可判定），实现 **未落地**

条款链完整、可机械判定：sentinel `_UNSET` → `G2CaliberError` → HTTP 400 `detail={"code":"FS08","missing":[...]}`，5 条判据（`v0.7:82-86`）全部一义。三处默认值与 G2 相反的**事实描述我已核对为真**：`engine.py:228` `matching="close_t"`、`:258` `entry_price_basis="adjusted"`、`__post_init__` 的 `entry_fill/exit_fill → matching` 回退（`engine.py:280-283`）确实存在。

但 **`F-A40` 现在一条也跑不了**：

```
$ grep -rn "G2CaliberError\|FS08\|_UNSET" --include=*.py backend/app backend/tests
(无输出)
```

三者在代码中零出现。**判定：条款准予作为 G-A2 的开门条件；本条不阻塞冻结（它是规格），但「D5 已修」只能说「条款已写」，不能说「已可验收」。**

§7.15.3 自述「14 只全无 `status`」我抽查成立：`FactorSpec` 无 `status` 字段，盘上 15 个 JSON 均 `"status":"draft"`。P2 定性我同意（不阻塞 B2）。

### B2 `F-A41` / `§7.13`（`MATRIX_KERNELS`、`FS10` 准入拒绝）—— 条款与实测 **一致**，实现 **零**

- §7.13.1 的 14 行表（6 可算 / 8 不可算，逐行给出机制）**与我 A6 实测逐项相同**，包括「`ma20` 靠 `name[2:].isdigit()` 通过、`vol60` 因不匹配被拒」这条「拼写决定支持性」的判断。
- §7.13.2 三处缺陷定位准确：`factors.py:86-88` 基类 `return None`（我读到 `:86 def materialize_matrix_field` / `:87 del` / `:88 return None`）、fail-closed 抛错点在 `matrix.py:4557`、白名单 60 名 + 6 条前缀。
- 但 `MATRIX_KERNELS` / `matrix_supported` / `FS10` 在代码中**零出现**，`F-A41-1…5` 一条都不可执行。§7.13.3 硬要求 5 条写得很实（尤其 `F-A41-5` 要求基类改 `NotImplementedError`、全仓禁止「返回 None 表示未实现」），**建议保留**。

### B3 `F-A11a`–`d` 分层容差 —— **F-A11b 有一处实质缺陷：正确核也过不了**

用真实 `matrix_feature` 输出（8 只 × 843 日 = 6,592 行，`fa11b_reach.py`）算相对误差：

| 因子 | `max_abs` | `max_rel` | `/2^-23` | `F-A11b` |
| --- | ---: | ---: | ---: | --- |
| `ma20` | 7.46e-05 | 6.87e-08 | 0.58× | PASS |
| `ma60` | 6.99e-05 | 6.22e-08 | 0.52× | PASS |
| `ma120` | 6.48e-05 | 6.17e-08 | 0.52× | PASS |
| `ma200` | 6.37e-05 | 6.01e-08 | 0.50× | PASS |
| **`boll_lower`** | 1.39e-04 | **1.416e-07** | **1.19×** | **FAIL** |
| **`boll_upper`** | 1.54e-04 | **1.429e-07** | **1.20×** | **FAIL** |

**这不是语义错，是正确的 float32 核。** 原因：`boll_*` = `ma20 ± 2·sd20`，两次 float32 舍入沿复合运算累积，`max_rel` 突破单次舍入界 `2^-24 = 5.96e-08`，也突破 v0.7 给的 `2^-23 = 1.192e-07`。v0.7 §7.14.2 的实测表只算了「同一 float64 值存成 float32」的单次舍入（每列恰 `5.96e-08`），**没有算矩阵核内部的累加/复合误差**；§7.14.4 说「留一倍余量」正是为此设 `2^-23`，但复合因子需要**超过**一倍余量。

另有一个判据口径问题：§7.14.4 把 `F-A11b` 写成「逐列 `rel = max|p−m| / max(|p|, 1e-12)`」—— 这是**逐元素**相对误差（每元素除以自己的值），而同句后半段「`max|p−m| ≤ 2^-23 × max|p|`」是**列级**。两者对同一数据给出不同判决：按元素算 `boll_*` 1.19× FAIL；按列级算（`a11b_ok_abs`）6/6 全 PASS。**同一条判据里两个不同定义，实测得出相反验收结论。**

**修法建议（二选一，建议第 1 条）：**

1. **保留 `2^-23` 不动，把 `F-A11b` 明确为列级**：`max|p−m| ≤ 2^-23 × max(|p|)`，逐列一个数、不用逐元素。实测列级 6/6 通过（最差 `boll_upper`：1.429e-07 × 1.764e+03 量级 → 绝对差 1.54e-04，远在界内），代价最小，不放松语义错判别力。文字改法：把 `rel = max|p−m| / max(|p|, 1e-12)` 改为 `rel_col = max|p−m| / max(|p|)`，并删掉逐元素那句。
2. 若坚持逐元素，容差需提到 `3·2^-23 ≈ 3.6e-07`，并在 §7.14.2 表里补「复合因子」一行实测。

**判别力（你点名要的「漏 `shift(1)` 能被抓出」）—— 成立。** 我独立构造正确核 / 错误核（`fa11_power.py`，`sd20`/`prior_high_20`/`vol60` 各 6 只）：

| 因子 | 正确核 `max_rel` | 错误核 `max_rel` | 正确核 jaccard / 翻转 | 错误核 jaccard / 翻转 |
| --- | ---: | ---: | --- | --- |
| `sd20` | 2.18e-06 | **0.947** | 1.000000 / 0 | 0.959579 / **146** |
| `prior_high_20`（漏 `shift(1)`） | 5.82e-08 | **0.166** | 1.000000 / 0 | 0.991597 / **30** |
| `vol60` | 1.19e-06 | **672** | 0.999707 / 1 | 0.499635 / **3,423** |

语义错与量化噪声差 3–9 个数量级，`F-A11c`（jaccard ≥ 0.9999 且翻转 0）**确实抓得住**。但注意 `vol60` 正确核本身 jaccard 0.999707 / 翻转 1 —— 恰好越线（0.999707 < 0.9999），说明 0.9999 对低量级因子也偏紧。用真实 `ma20` 的对照（`fa11b_reach.py#discrimination`）：正确核翻转 0、19 日窗冒充 20 日翻转 9 → 抓住。

**另注 `F-A11d` 的 `tolerance="eps32"` 是自指字符串**，不可机械判定；建议写具体值（如 `"2^-23_col"`）。

### B4 `§4.6 B1` 的 null 日表述 —— **已改，且改得更严**

v0.7 `:497`：`n_days` 1,770、`max_abs_diff < 1e-12`、该子集研究侧均值 **0.542252**、生产 `null` 日单列 9 天，并明写「原『1,779 日 / 0.540742』是**含 `null` 日**的旧记录，**不作判据**」。这是你要的「null 日表述已改」，方向是**收窄**（排除 null 日），符合「收窄不算放宽」。§4.6.1 新增。**判定：已改，文本自洽。**

（`n_month_end` 88→87、通过率 53.4%→0.540230 同样收窄。这些数值我不重算 —— 需月末日历与 `xs_rank_pool` 实现，见未验证项。）

### B5 `A7` 的 ST 窗口 14 日 —— **已按实测改，与证据一致**

v0.7 `§2.6 A7` 改为「窗口终点 = 数据末端，不是固定 8 天」，当前 14 天 = 8 + 6，且**明令禁止硬编码 8 或 14**（两条规则现算），并要求 `coverageEnd` 前移时自动收缩。证据指向 `docs/factors/E3_DATA_AVAILABILITY_20261107.md`，我核了该文件 `:18`、`:112`、`:116`、`:118`：ST 表 `2026-10-20` 一次性写入 198 行 `st_flag=False`、此后 0 条 `True`，ST=True 由 218 家降到 20 家并持续至 `2026-11-06`（14 个交易日）。**契约与证据一致，判定 PASS。**

### B6 一条契约自洽问题（非阻塞，建议 P2）

§7.14.2 说「`float32` 的相对表示误差上界是 `2^-24`」，§7.14.4 把容差设成 `2^-23` 并注「留一倍余量」；但 §7.14.2 表里每列 `max rel` 恰是 `5.96e-08`，说明该表**只测了存储舍入**。我的 `boll_*` 1.19×–1.20× 实测证明「一倍余量」对复合因子不够。建议在 §7.14.2 表下补一句：「本表为存储舍入下界；复合因子（`boll_*` = `ma ± 2·sd`）实测 `max_rel` 可达 `1.43e-07`，故 `F-A11b` 按列级判（见 §7.14.4 修法）。」

---

## C 未验证项（单列，不得视为通过）

1. **端到端 API**：`GET /api/factors`、`POST /api/backtest/*` 上 14 个因子的可见性与错误码未测（作者也列为未做）。
2. **`FS03`/`FS08`/`FS10`/`MATRIX_KERNELS`**：全未实现 → 相关判据（`F-A40-1…5`、`F-A41-1…5`）**一条都未实跑**，本报告只判「条款可判定」。
3. **`strategy_usable` 的运行时效果**：代码零落地，因此「alias 被拒」**无法验证**（不是「验证失败」，是「无对象可验」）。
4. **`§4.6 B1/B2` 的 1,770 日 / 87 月末 / 0.542252 / 0.540230**：未重算（需 `xs_rank_pool` 实现与月末日历）。
5. **`XS-A7` 双路径 `≤1e-12`**：与 `F-A11` 同源问题（矩阵 float32），未单独验。
6. **`A7` 的 2,772 标的日偏差**：核了证据文件与契约一致，但未在行情库上独立重算 `198×14`。
7. **矩阵路径是否被生产回测实际使用**：`engine.py:23-29` 从 `matrix` 导入 `build_market_matrix` 等，属生产路径；但「某条具体策略回测是否走到 `matrix_feature`」未逐策略验证。
8. **B0 的部署面**：`data/user_data/extensions` 是否存在、Provider 是否在部署环境被 `ensure_factor_providers` 发现 —— 本机未查（pack 在 `backend/app/custom/`，按 `app/custom/*/factor_provider.py` 自动发现，逻辑上应生效，但未在部署态验）。
9. **`F-A11b` 修法后的复算**：列级判据基于 8 只 × 843 日样本，未覆盖全市场约 1.7M 行。

## D 缺陷清单

| # | 文件:行 | 问题 | 阻塞 | 改法 |
| --- | --- | --- | --- | --- |
| B0-1 | `docs/factors/REGISTRATION_B0_20261107.md:12` | 「14/14…`max_abs_diff = 0`（逐位相等）」把 pack 侧结果概括为全口径；store 侧 `uf_vol60` 与 pack 差 1 ULP、77.029% 行不等。违反 v0.7 §7.15.2「不得写逐位相同」 | **是**（结项记录不可带此句） | 改为「pack 侧 0.0；`uf_vol60` 与 pack 差 1.11e-16（`F-A3` 内），77.029% 行不等」 |
| B0-2 | `docs/factors/REGISTRATION_B0_20261107.md:219` | 「4.6% 的行不等」与复算的 77.029% 不符（5,307,478 行中 4,088,299 行不等） | 是（数字错误） | 改为 77.029%，注明探针窗口与分母 |
| B0-3 | `backend/app/extensions/factors.py:231-241`（`provider_factor_ids`/`sidecar_factor_ids` 所属注册面）+ 全仓 | `strategy_usable` / `alias_of` / `FS03` 代码零落地，8 个 pack alias 与 `uf_*` 并存且都可被策略引用；B0 收窄口径的前提无机械保证 | **是**（阻塞「alias 已隔离」的结项表述） | 结项记录写明闸门未实现；或实现 `FactorSpec.alias_of` + `FS03` 后再声明隔离 |
| B0-4 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md:1502`（`F-A11b`） | 同一条判据混用逐元素（`rel = max|p−m| / max(|p|,1e-12)`）与列级（`≤ 2^-23 × max|p|`）；按元素算 `boll_lower` 1.19×、`boll_upper` 1.20× **FAIL**（正确核），按列级 6/6 PASS | **是**（会误判正确实现，阻塞 B0b 验收） | 明确为列级：`max|p−m| ≤ 2^-23 × max(|p|)`；删逐元素句；§7.14.2 表下补复合因子上界 1.43e-07 |
| B0-5 | `v0.7:1503`（`F-A11c`） | 0.9999 对低量级因子偏紧：`vol60` 正确核 jaccard 0.999707 / 翻转 1，越线 | 否（P2） | 按量级分档，或改「翻转 0 且 jaccard ≥ 0.999」 |
| B0-6 | `v0.7:1504`（`F-A11d`） | `tolerance="eps32"` 是自指字符串，不可机械判定 | 否 | 写具体值 `"2^-23_col"` |
| B0-7 | `v0.7:1490`（§7.14.2 表） | 表只测存储舍入下界（每列恰 `5.96e-08`），未含核内累加/复合误差，与 §7.14.4「一倍余量」的立论不闭合 | 否（应与 B0-4 同批改） | 表下补下界说明 + 复合因子实测 |
| B0-8 | `backend/app/custom/research_factor_pack/factor_provider.py:20-23`（注释） | 注释写「矩阵侧实现是缺能力项…本包不在此处补一套」，与实测一致；但未点名 `ma20/ma60/ma120/ma200` 在矩阵侧**已可算**（靠前缀启发式），易被读成「6 个全不可用」 | 否 | 注释补「4 个 `ma*` 经前缀启发式可算，2 个 `boll_*` 经白名单可算」 |

**阻塞的只有 4 条：B0-1、B0-2（B0 结项表述）、B0-3（alias 闸门陈述）、B0-4（`F-A11b` 判据歧义）。** 前两条是文档订正（分钟级），B0-3 是结项措辞（不写代码就能不撒谎），B0-4 是一条判据的文字收窄（不放松语义错判别力）。

## E 一句话回答你两个问题

- **A 块（B0）**：按「研究名对齐 + 6 个 pack-only canonical」**可以结项** —— 四项实测 PASS（577,179 行 0 差 / 上界 14/14 / warmup 14/14 / pack 注册 192→192）；但结项记录必须原文写明「8 个 pack id 仍与 `uf_*` 并存可引用，`FS03` 未实现」，并订正「逐位相等」与「4.6%」两处。
- **B 块（v0.7）**：已审 `f7b6adb2…3002908`。`F-A40`/`F-A41` 条款可判定、实现为零（不阻塞冻结，阻塞验收）；`§4.6 B1` 与 `A7` 14 日已按实测改且收窄；**`F-A11b` 必须按列级重写，否则正确的 `boll_*` 矩阵核会被判失败。**

**本轮我不给 v0.7 整体 PASS**，理由是 B0-4 会让 B0b 的验收判据在正确实现上失败 —— 这不是风格问题，是判据会判错。

## F 复现命令（节选）

```bash
cd /c/work/sourcecode/tick-stock-panel
# A1/A4 保真+幂等（两次）
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_b0_wide.py
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_b0_final.py
# A2 可达上界 + A6 矩阵（研究名）+ A5 alias（冷启动态）
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_bound_v2.py
# A5 生产启动态 alias + 矩阵 uf_* 覆盖
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_alias_prod.py
# A6 真实 MarketDataMatrix 逐名探测 + 矩阵 vs 面板
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/indep_matrix_probe.py
# B3 F-A11b 可达性 + F-A11c 判别力
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/fa11b_reach.py
PYTHONUTF8=1 backend/.venv-codex/Scripts/python.exe research/independent-review-20261107/b0r2/fa11_power.py
# 绑定四值
wc -c docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md
sha256sum docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md
head -c 89350 docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md | sha256sum
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md
# 零落地断言
grep -rn "strategy_usable\|alias_of\|replaced_by" --include=*.py backend/ | grep -v .venv   # 期望空
grep -rn "G2CaliberError\|FS08\|_UNSET\|MATRIX_KERNELS\|FS10\|FS03" --include=*.py backend/app backend/tests  # 期望空
```
