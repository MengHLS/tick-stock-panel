# 契约 v0.8 → v0.9 修订对照（R9：四处一次收齐）

生成时间：2026-11-07 21:35（Asia/Shanghai）· 系统架构师

底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md`（**一字未改**，206,608 B / 1,792 行 / 正文 `head -c 204939` → `18b769a44c4a2c5fdfdcffdaf61787311cec1b400432da245a3a300050be0689` / 全文 `2cf85ccbaaf1fed7e5316bf2c83c73b5193fc02f3aadf3b3e453600aabaedd2f`，mtime 2026-11-07 21:04:09；钉副本 `research/arch-build-20261107/_base/v0.8_base_2cf85ccbaaf1.md` 与之逐字节相同）
产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md`（228,478 B / 1,957 行 / 正文 `head -c 226428` → `d967d463ff1e10c00294cb47e622d245d55b9a7c49ace0410cb6bc53929c3955` / 全文 `5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c`，mtime 2026-11-07 21:14:03）

**性质：四处内容改动 + 版本簿记，判据语义只动 `F-A11b` 一处，方向是收窄。** 本版不改 v0.3–v0.8 任何文件，不新建第三份说明文件。§7.1 八行公式、`ewm` 否决、v0.3–v0.8 全部判据编号一字未动。**本周期不再追加版本，v0.9 为最后一版，此后进入冻结评审。**

## 1. 行级 numstat（两种算法各跑一遍，结论相同）

| 项 | 值 |
| --- | --- |
| 底本 | 206,608 B / 1,792 行 |
| 产物 | **228,478 B / 1,957 行** |
| 行级 opcodes（`difflib.SequenceMatcher`） | insert **165 行** / replace **3 段**（1→1 ×3）/ delete **0 行** |
| numstat（added / deleted） | **+168 / −3** |
| 净变化 | **+165 行**（1,792 → 1,957）；168 − 3 = 165 |
| 字符账 | Δ**13,874 字符** = 插入 13,516 + 替换净增 358（逐块见 1.2） |
| 字节账 | Δ**21,870 B**（中文占 3 字节） |

方法：`difflib.SequenceMatcher(None, A, B)`，`splitlines(keepends=True)`，`autojunk` 开/关各跑一次，两次输出**完全相同**；第二套用 `git diff --no-index`（Myers）独立跑，给出同一组 9 个位置、同一 `+168/−3`。

### 1.1 九个 hunk（新行号 = v0.9 行号）

| # | 类型 | 旧行（v0.8） | 新行（v0.9） | 行数 | 内容 | 归属 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | replace | 1 | **1** | 1 | 标题版本号 v0.8 → v0.9 | 簿记 |
| 2 | insert | — | **26** | 1 | §0 修订记录加 v0.9 一行 | 簿记 |
| 3 | insert | — | **230–248** | 19 | §2.7 两 bullet（第 4 处）+ §2.8 全节（第 3 处） | 内容 |
| 4 | replace | 1501 | **1521** | 1 | `F-A11b` 判据行（第 1 处） | 内容 |
| 5 | insert | — | **1526–1527** | 2 | `F-A11b` 为什么只写列级（第 1 处） | 内容 |
| 6 | insert | — | **1593–1685** | 93 | §7.16 全节（第 2 处） | 内容 |
| 7 | insert | — | **1805** | 1 | §9「未覆盖与依赖」加 R9 一行 | 簿记 |
| 8 | insert | — | **1906–1954** | 49 | §11 本版改动说明（含 11.1 / 11.2） | 簿记 |
| 9 | replace | 1792 | **1957** | 1 | footer（正文 sha / 行数 / 版本句） | 簿记 |

**hunk 数不等于改动处数**：9 个 hunk = 4 处内容 + 5 处簿记；内容改动落在 4 个 hunk（3、4、5、6），其中第 3 处（§2.8）与第 4 处（§2.7 两 bullet）在 v0.9 里是连续的 19 行、中间只隔空行，行级 diff 无法切开，故同属 hunk 3；第 1 处占 2 个 hunk（判据行替换 + 理由段新增）。

**与派单 hunk 表的一致性**：派单给的 `1 / 26 / 230–248 / 1521 / 1526–1527 / 1593–1685 / 1805 / 1906–1954 / 1957` 与我复算**逐项相同**。唯一可讲的差别是纯插入块两端空行的归属——`git diff` 记 `+231,19` / `+1527,2` / `+1594,93`（各后移 1 行，因为它把块首空行算作前一条上下文）；两种记法覆盖的字符和相同（2,119 / 458 / 7,366），不影响任何结论。

### 1.2 字符账逐块（可加总校验）

| 块 | 行 | 字符（含 CRLF） | 块 sha8 |
| --- | --- | --- | --- |
| §0 修订行 `:26` | 1 | 563 | `ed036b09` |
| §2.7 bullet + §2.8 `:230–248` | 19 | 2,119 | `031a3e36` |
| 理由段 `:1526–1527` | 2 | 458 | `1febd3aa` |
| §7.16 `:1593–1685` | 93 | 7,366 | `5b1bbb3a` |
| §9 一行 `:1805` | 1 | 451 | `a3ad5191` |
| §11 `:1906–1954` | 49 | 2,559 | `e265648c` |
| 插入小计 | 165 | **13,516** | — |
| 替换净增（标题 0 + `F-A11b` 行 +137 + footer +221） | — | **358** | — |
| 合计 | — | **13,874** = Δchars | — |

## 2. 四处逐处：原句 → 新句 → 依据

### 2.1 第 1 处（内容）：`F-A11b` 由「列级或逐元素混写」收窄为「只列级」——`:1521` + 理由段 `:1526–1527`

原句（v0.8 `:1501`）：

```text
| F-A11b | 数值一致（相对容差） | 逐列 `rel = max\|p−m\| / max(\|p\|, 1e-12) ≤ 2^-23 = 1.192e-07`；且逐列 `max\|p−m\| ≤ 2^-23 × max\|p\|`。样本必须同时覆盖 NaN 与非 NaN 行 |
```

新句（v0.9 `:1521`）：

```text
| F-A11b | 数值一致（**列级**相对容差；**不设**逐元素判据） | 逐列独立判：记 `d_col = max\|p − m\|`、`s_col = max\|p\|`（该列有限值绝对值的最大值），断言 `d_col / max(s_col, 1e-12) ≤ 2^-23 = 1.192e-07`；一个因子通过 = 它参与的**每一列**都通过。形状与轴标签须已由 `F-A11a` 对齐；样本必须同时覆盖 NaN 与非 NaN 行。`1e-12` 只是列级分母的退化下限（整列全零时避免除零），**没有**逐元素含义、也不对任何单个元素设容差 |
```

新增理由段（v0.9 `:1527`，前一行 `:1526` 为空行）：

```text
**为什么 `F-A11b` 只写列级、不写逐元素（v0.9 收窄；写在这里是为了下次不被「修」回去）**：逐元素读法（对**每个元素**要求 `|p−m| / max(|p|, 1e-12) ≤ 2^-23`）在 `float32` 存储下不可达，实测打穿。独立审核 2026-11-07 同一组真实数据：`boll_lower` **逐元素 1.416e-07（超 `2^-23` → FAIL）／列级 8.635e-08（PASS）**；越线点 `|p| = 9.27` 远离近零退化，属正确核的**多次 `float32` 运算累积**（单次存储量化上界 `2^-24 = 5.96e-08`，见 7.14.2），不是口径错。逐元素判据的实质是「用最坏一个元素的累加顺序代表整列」，会把正确实现判死；而它并不增加判别力——语义错在两种读法下都抓得住（7.14.5：语义错相对误差 0.6682，与 `2^-23` 差约 7 个数量级）。**结论：只判列级；`1e-12` 仅作列级分母的退化下限。**
```

**依据**：独立审核 2026-11-07 用同一组真实数据的实测表在 `docs/architecture/B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md:215`（`boll_lower` 逐元素 `1.416e-07` FAIL / 列级 `8.635e-08` PASS），越线点明细在同文件 `:218`（`|p| = 9.273`、`absdiff = 1.313e-06`、`rel = 1.416e-07`，明确「不是近零值退化」）；第三处呈现（倍率 `1.19×`）在 `research/independent-review-20261107/B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md:229`，且 1.416 ÷ 1.192 = 1.19，三处自洽。

原文的病在**一句话里混了两种读法**：`1e-12` 只有逐元素读法才需要（近零元素防除零），而后半句 `max|p−m| ≤ 2^-23 × max|p|` 是列级。按逐元素实现，正确核会把 `boll_lower` 判死。**这是本版唯一的判据语义变更**，方向是把不可达的读法删掉；`F-A11a`/`c`/`d`、`F-A10` 未动。

### 2.2 第 2 处（内容）：新增 §7.16 `FS03` 可判定条款——`:1593–1685`（93 行）

原句：**无**。v0.8 在 §7.15 之后直接进 §10，没有 §7.16。

新句（标题、首段）：

```text
### 7.16 canonical/alias 闸门：可判定条款（v0.9 新增；B0b-1 的交付依据）

本节把 `FS03` 从「一句话裁定」（§7.8.4 的模式矩阵、决策文件 `ID-CANON-1`）写成**可判定条款**：触发条件、生效入口、HTTP 形状、与 §7.15 canonical 表的接续、以及拒 alias 时 `vol60` 与 `uf_vol60` 各自的期望行为。**本节不新增裁定**，只把 §7.8.2 A-2/A-3、§7.8.4、§7.15.1 已有裁定落到可测的输入输出上；判据编号续 `F-A41` 取 `F-A42`。
```

子节与行号：

| 子节 | 行 | 内容 |
| --- | --- | --- |
| `7.16.1` | `:1598` | 前提事实（5 条，每条给可复跑依据） |
| `7.16.2` | `:1608` | `FS03` 触发条件 C1–C4（四条同时成立） |
| `7.16.3` | `:1625` | 生效入口穷举 4 个（查表 / 目录 / 策略提交 / 回测准入），并写明「为什么不在别处拒」 |
| `7.16.4` | `:1636` | HTTP 响应形状（唯一形状，与 `FS04`/`FS06` 共用，400 + `detail` 对象） |
| `7.16.5` | `:1657` | 与 §7.15 canonical 表接续（唯一权威，禁止二次登记） |
| `7.16.6` | `:1664` | 拒 alias 时 `vol60` / `uf_vol60` 逐模式期望行为 |
| `7.16.7` | `:1676` | 验收判据 `F-A42-1`–`6` |

判据六条（`:1680–1685`）：

| 行 | 编号 | 判据 |
| --- | --- | --- |
| `:1680` | `F-A42-1` | 字段落地：`FactorSpec` 增 `alias_of` / `strategy_usable`（第 22/23 字段），既有 21 字段一个不改 |
| `:1681` | `F-A42-2` | alias 拒得掉（两例负样本：`vol60` → `table_row=1`，`ma120` → `table_row=2`） |
| `:1682` | `F-A42-3` | canonical 放得行（`uf_vol60` 不被 `FS03` 拦；`research` 下 `vol60` 通过并标 `deprecated_alias_used`） |
| `:1683` | `F-A42-4` | 入口穷举：4 个入口逐个造负样本全部 400 `FS03` |
| `:1684` | `F-A42-5` | 表与定义一致：8 alias 与 §7.15.1 逐行相等，6 单侧件 `alias_of is None`，不一致 → `FS06` |
| `:1685` | `F-A42-6` | 不误伤：只在 `mode="production"` 触发；`get_factor` / `factor_columns_view()` 对 alias 仍返回 spec |

**依据**（三条，都可复跑）：

1. **缺口是实测的**：`grep -rn "strategy_usable\|alias_of\|FS03\|assert_factors_usable" backend/app/` → **0 行**（我 2026-11-07 21:2x 复跑）。字段与入口都不存在，B0b-1 无从开工。
2. **裁定早已存在、只缺可测形状**：8 组同口径双 id + 6 个单侧件的权威表在 v0.8 的 §7.15.1（v0.9 `:1548–1565`，我核过表体 = 表头 + 分隔 + **14 行**：8 个 alias 行 + 6 个单侧件行），决策文件 `docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md`（`ID-CANON-1`）。本节**不新增裁定**。
3. **判据编号续 `F-A41` 取 `F-A42`**，不占用任何既有号（`F-A11a`/`c`/`d`、`F-A10` 未动）。

**当前必红的部分（待实现，不是缺陷）**：我实测 `get_factor("vol60")` 存在、`get_factor("uf_vol60")` 为 `None`，故 `F-A42-2`（`production` 提交 `vol60` → 400 `FS03`）与 `F-A42-3`（canonical 放行）在实现落地前一定失败。

### 2.3 第 3 处（内容）：新增 §2.8 `observed_bars` 口径差异——`:234–248`（15 行）

原句：**无**。

新句（标题）：

```text
### 2.8 `observed_bars` 的口径差异（**信息项**，不改判据；口径归属交研究侧）
```

其下的表（`:240–243`）给四个值：判定不同的标的日 **40,717** 行；落在评估窗内（`2019-07-01`…`2026-10-30`，1,779 个交易日）**17,499** 行；差异方向**全部**为「`listing` 口径 ≥ 120 而 `bar` 口径 < 120」；与研究的对账 `A1` 逐日池内家数 **0 差**（可比 1,770 个交易日，`max_abs_diff = 0`，另 9 日一侧为 `null` 不计）。

**依据**：`research/b2-engine-20261107/logs/observed_bars_calibers.json`，我直接读取该文件（不是转述）：

| 键 | 值 |
| --- | --- |
| `rows` | 6,438,822 |
| `rows_diff_ge120` | **40,717** |
| `rows_b_ge120_only` | 40,717 |
| `rows_a_ge120_only` | **0** |
| `diff_in_eval_window` | **17,499** |

与我写进 §2.8 的两个数逐位相同；`rows_a_ge120_only = 0` 正是「方向全部是 listing 更宽」的来源。**本节不改任何判据**：`A1`–`A8` 的度量与靶值不变，`observed_bars` 取研究口径是 §2.1 注 1 早已写明的取法。口径归属交研究侧，我不裁。

### 2.4 第 4 处（内容）：§2.7 追加两 bullet（catalog 93 → 107 → 108）——`:231–232`

原句：**无**（v0.8 该处为空行 + 分隔线）。

新句：

```text
- **进入 `/api/factors` 对外目录（catalog 93 → 107 → 108）**：`in_universe` 由 `app/custom/research_universe_pack/factor_provider.py` 的 Provider 注册，按扩展点既定行为「注册即进目录」（B0 的 14 个 pack 因子同理）出现在 `GET /api/factors` 的 `factors[]` 里；目录条数 `93`（B0 前）→ `107`（B0 的 14 个）→ `108`（本批 `in_universe`）。实测 2026-11-07 20:5x：`len(all_factors()) == 193`（含 `ext_*` 85 条与其它 Provider 16 条），非 `ext_*` 口径 = **108**；该条目现状字段 `kind="custom"`、`group="研究补充"`、`unit="none"`、`scale_free=true`、`stability="stable"`、`warmup_bars=120`、`tags=("mask","研究基线","E3")`、`asset_types={"stock","etf"}`。
- **5 处「目录条数」断言已由实现侧同步到 108，不是本批回归**：`tests/test_factor_registry.py` 4 处 + `tests/test_factor_store.py:88` 原把条数硬编码为 `93`（B0 起即红：93 → 107）；实现侧 2026-11-07 20:48:59 统一改为 `108`（`git diff --numstat` 两文件 `+25/−9`，**未提交**；本轮实测 5 处，B2 报告记「6 条 factor 红灯」为测试用例级计数，差 1 处未追，不影响结论）。口径：改的是**过期断言值**，原有覆盖必须保留，不得以「重定基线」把红灯合法化；是否全绿由独立审核复跑，本契约不下结论。
```

**依据**：`git diff -U0 backend/tests/test_factor_registry.py backend/tests/test_factor_store.py` 里 `93 → 108` 的改动我逐行核过——**4 条 assert（registry `:286/:287/:326/:374`）+ 1 条 assert（store `:88`）+ 1 个 `builtin_count` 常量（store `:79`）+ 1 行注释（store `:86`）= 7 行字面量**。这同时把 `:232` 自记的「差 1 处未追」追平，见 §5.1。`len(all_factors()) == 193` / 非 `ext_*` = 108 这两个口径我独立复算一致，见 §5.2。

## 3. 版本簿记（4 处，非内容）

| # | 位置 | 行 | 改了什么 | 字符 |
| --- | --- | --- | --- | --- |
| 1 | 标题 | 1 | `v0.8` → `v0.9`（同行同长） | 41 → 41（Δ0） |
| 2 | §0 修订记录 | 26 | 加 v0.9 一行（四处 + 依据出处） | +563 |
| 3 | §9 | 1805 | 加 R9 一行（四处 + 判据） | +451 |
| 4 | §11 + footer | 1906–1954 / 1957 | 新增 §11（49 行）+ footer 重写 | +2,559 / +221 |

footer 是**自指闭环**：它内嵌本文件正文 sha256、正文字节数与本文件行数，所以只能在正文定稿后生成；这决定了它必须落在最后一处替换里，也解释了 footer 为何净增 221 字符（新增 v0.9 四处说明与「最后一版」声明）。

## 4. 四元组与逐字节复跑（DST 重定向）

```bash
cd /c/work/sourcecode/tick-stock-panel
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md
wc -c -l "$F"                       # 1957 228478
head -c 226428 "$F" | sha256sum     # d967d463ff1e10c00294cb47e622d245d55b9a7c49ace0410cb6bc53929c3955
sha256sum "$F"                      # 5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c
stat -c '%y' "$F"                   # 2026-11-07 21:14:03
```

| 项 | 值 |
| --- | --- |
| size | **228,478 B** |
| 行数 | **1,957** |
| 正文前缀 | `head -c 226428` → **`d967d463ff1e10c00294cb47e622d245d55b9a7c49ace0410cb6bc53929c3955`** |
| 全文 | **`5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c`** |
| 落盘时刻 | **2026-11-07 21:14:03**（Asia/Shanghai） |

**逐字节复跑（不覆盖盘上文件）**：把 `research/arch-build-20261107/build_contract_v09.py` 的 `DST` 指向临时路径即可。前提是 footer 里内嵌的是**字面量路径** `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md`（脚本 `:402`），不是 `DST.name` —— 换 `DST` 不会改变产物一个字节（我核过这一点，见下）。

```bash
TMP=/c/Users/A/AppData/Local/Temp/r9repro && mkdir -p "$TMP"
python - "$TMP" <<'PY'
import sys, pathlib
tmp = pathlib.Path(sys.argv[1])
src = pathlib.Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
t = src.read_text(encoding="utf-8")
old = 'DST = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md"'
new = 'DST = Path(r"%s") / "R9_repro.md"' % tmp
assert t.count(old) == 1
(tmp / "build_contract_v09_repro.py").write_text(t.replace(old, new), encoding="utf-8")
PY
cd "$TMP" && /c/work/sourcecode/tick-stock-panel/backend/.venv/Scripts/python.exe build_contract_v09_repro.py
cmp "$TMP/R9_repro.md" /c/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md && echo EQUAL
```

我这一轮的实跑输出（原文）：

```text
BASE 206608 1792 204939 18b769a44c4a2c5f 2cf85ccbaaf1fed7
DST_BYTES 228478
LINES 1957
BODY_BYTES 226428
BODY_SHA12 d967d463ff1e
FULL_SHA12 5d0abbb59636
BASE_STABLE 2cf85ccbaaf1fed7
cmp 无差异 → CMP_EQUAL True
```

脚本末尾自带断言 `hashlib.sha256(SRC.read_bytes()).hexdigest() == BASE_SHA`（"v0.8 changed during build"），所以「底本按哈希复现」不是承诺，是每次跑都会重验的断言。**v0.9 是当日唯一「脚本单跑即逐字节复现」的版本**，见 §6。

## 5. 两处口径差（登记，不改契约、不改判据）

### 5.1 「5 处」与「6 处」：`差 1 处未追` 已追平

契约 `:232` 自记「本轮实测 5 处，B2 报告记『6 条 factor 红灯』为测试用例级计数，差 1 处未追」。这 1 处就是 `test_factor_store.py:79` 的 `builtin_count = 108`（`git diff` 里它由 `93` 改为 `108`，但不是 assert）。完整数法：

| 数法 | 数 | 明细 |
| --- | --- | --- |
| 严格 assert 行 | **5** | `test_factor_registry.py:286/:287/:326/:374`（4）+ `test_factor_store.py:88`（1） |
| 计数点（含常量） | **6** | + `test_factor_store.py:79` `builtin_count = 108` |
| 字面量行（含注释） | **7** | + `test_factor_store.py:86` 注释里的 `93 → 108` |

结论：§2.7 `:232` 的「5 处断言」准确；§0 `:26` 与 §9 `:1805` 的「6 处」实为「6 个计数点」（5 条 assert + 1 个 `builtin_count` 常量）；「差 1 处」不是漏改，是两处用了不同计数单位。**建议下一版统一写「6 个计数点（其中 5 条 assert）」**。本轮不改契约。

### 5.2 「108」是密闭口径，不是任意导入路径的读数

契约 `:231` 已把两个口径并列（`len(all_factors()) == 193` 含 `ext_*` 85 条；非 `ext_*` = 108）。我独立复核：

| 口径 | `len(all_factors())` | 拆分（按 `kind`） |
| --- | --- | --- |
| 非 `ext_*`（= 契约的「目录 108」） | **108** | `base` 32 + `virtual` 61 + `custom` 15（= 93 内置 + 14 B0 pack + 1 `in_universe`） |
| 含 `ext_*`（本机运行时） | **193** | `base` 117（32 + **85** `ext_limit_board_events_*`）+ `virtual` 61 + `custom` 15 |

我另补一条**测试侧证据**，说明为什么同一个仓库里两个数都「对」：`tests/test_factor_registry.py:237` 有 autouse fixture `_isolate_runtime_ext_factors`，它把 `settings.data_dir` 指向 `tmp_path` 并剔除 `ext_` 条目，所以 harness 里恒为 108。我在同一进程里用两个钩子实测：`pytest_sessionstart` 读到 **193**，`pytest_runtest_call`（fixture 生效后）读到 **108**，测试本体 passed。

**引用纪律**：写「目录 108」必须注明「密闭口径（无运行时扩展表）」；本机运行时目录是 193，拿本机 `GET /api/factors` 去对 108 一定对不上。契约里的 108 不需要改。

## 6. 可引用性：为什么只有 v0.9 能按哈希复现到字节

| 版本 | 字节身份 | 复现性 | 引用方式 |
| --- | --- | --- | --- |
| v0.7 | 193,586 B / 1,696 行 / `5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8` / mtime 18:03:23 | 与 R7 说明 `:421` 记录值**逐字节相同**；本轮**未发现**改写证据 | 可引用；历史版本，`F-A30`–`F-A41` 判定对象不变 |
| v0.8 | 206,608 B / 1,792 行 / `2cf85ccb…` / mtime 21:04:09 | 同一路径同一版本号当天先后出现 **205,966 B（20:06）/ 206,152 B（20:05、20:38）/ 206,608 B（21:04）** 三组字节 | **只认哈希**，不认「路径 @ v0.8」；钉副本 `_base/v0.8_base_2cf85ccbaaf1.md`（206,608 B，逐字节相同） |
| v0.9 | 228,478 B / 1,957 行 / 正文 `d967d463…` / 全文 `5d0abbb5…` / mtime 21:14:03 | **脚本单跑即逐字节复现**（§4 `CMP_EQUAL True`，且脚本断言底本哈希不变） | **按四元组引用即可**，四元组就是身份 |

**一处更正（不圆）**：派单提到「v0.7 与 v0.8 都被并行流程原地改写过」。v0.7 这一半我**证不出**——盘上哈希等于 R7 自己记录的值、mtime 仍是 18:03:23，任何后续写入都会同时改变这两项。故本条只按 v0.8 写（v0.8 有三组字节的直接证据），v0.7 记为「可核验、未见改写」。若确有 v0.7 的改写，请给出改前字节或时刻，我据此补登。

## 7. 未动面（机器比对，不是目测）

| 项 | v0.8 | v0.9 | 结论 |
| --- | --- | --- | --- |
| §7.1 八行公式（CRLF 保留） | 2,541 / `a8e88134f60b504c` | 2,541 / `a8e88134f60b504c` | **逐字节相等** |
| §7.1 八行公式（LF 归一） | 2,514 / `6d3db0139a45f54c` | 2,514 / `6d3db0139a45f54c` | **逐字节相等** |
| 二至四级小节 | 122 个 | 131 个 | 改动 **4** / 新增 **9** / 删除 **0** / 逐字节相等 **118** |

改动的 4 个小节：

| 小节 | 原因 | 块长变化 |
| --- | --- | --- |
| `### 2.7 与现有模块的兼容性` | 第 4 处两 bullet | +874 |
| `### 7.14 F-A11 裁定：分层判据…` | 第 1 处（判据行 + 理由段） | +595 |
| `## 9. 未覆盖与依赖` | 加 R9 一行 | +451 |
| `### 10.6 对清单 v2 的影响与未确证` | **边界效应，非内容改动** | −1,204 |

`§10.6` 是第二个「R8 踩过的坑」：v0.9 的 §10.6 块是 v0.8 的**前缀**，差的 1,206 字符全是被新出现的 `## 11` 顶出块外的 `\r\n---\r\n` + 空行 + 旧 footer（1,195 + 2 = 1,197）。**不要拿小节块长度表相减**：块边界含空行归属（§2.7 的 +874 与插入 881 差 7，正是块内 `\r\n---\r\n` 的归属变化），加减一律用 §1.2 的行级字符数——那里能加总到 13,874。

## 8. 未确证（不圆）

- `F-A11b` 的列级阈值我**没有**在真实数据上重算：只核了报告里三处数互为 1.19× 关系（1.416 / 1.192），没有独立重跑 `boll_lower` 的 `max|p−m|` 与 `max|p|`。归独立审核。
- §7.16 的 `F-A42-1`…`6` **全部未实现、未跑**；`get_factor("uf_vol60")` 现为 `None`（实测），`F-A42-2`/`F-A42-3` 当前必红。
- 「108 / 193」只在两条调用路径（harness、裸导入）上实测，未穷举其他入口（直接读 `_REGISTRY`、API 层、其他 `data_dir`）。
- 派单提到的「v0.7 被原地改写」**未证实**（§6）。
- 本轮只写了 `docs/architecture/` 下的说明文件；**未改** `backend/**`、`docs/factors/**`、`research/**`，未动 v0.7 / v0.8 / v0.9 三份契约本体；未 add、未提交、未部署。

## 9. 复跑命令汇总

```bash
cd /c/work/sourcecode/tick-stock-panel
# 四元组
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md
wc -c -l "$F"; head -c 226428 "$F" | sha256sum; sha256sum "$F"; stat -c '%y' "$F"
# 行级 numstat（两套算法）
python -c "import difflib;a=open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md',encoding='utf-8',newline='').read().split('\r\n');b=open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md',encoding='utf-8',newline='').read().split('\r\n');sm=difflib.SequenceMatcher(None,a,b);[print(o) for o in sm.get_opcodes() if o[0]!='equal']"
git diff --no-index --numstat docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md
# 目录条数两口径
backend/.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');from app.factors import registry as r;fs=r.all_factors();print(len(fs), len([f for f in fs if not f.id.startswith('ext_')]))"
# 逐字节复跑（DST 重定向，见 §4）
```
