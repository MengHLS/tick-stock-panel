# 契约修订说明 R10 —— v0.9 → v0.10（含两条口径裁定）

**文件性质**：交付说明，**不是契约本体**。契约本体是 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md`；本文件只记录「改了什么、为什么、怎么复算」，并承载两条本版必须落的口径裁定（§7 §10.3 停用、§8 FS02 面）。

**角色**：系统架构师（独立于研究侧与实现侧）。不下验收结论，不写业务实现。

**边界（本轮实际遵守）**：未改 v0.7–v0.10 任何契约本体；未改 `backend/**`；未改 `docs/factors/**`；未 `git add`、未提交、未部署。本轮新增只有本文件、`research/arch-build-20261107/_repro_r10/`（复现临时件）与 `research/arch-build-20261107/_base/v0.10_base_8a3115aa.md`（按哈希留证）。

**时点**：全部读数 2026-11-07 21:5x–22:0x（Asia/Shanghai），逐条给命令，能自己复跑。

---

## 0. 一页结论

| 项 | 值 |
| --- | --- |
| 内容 | 一处正文勘误（§2.1 注 1）+ 两类登记（§12.2 编号 / §12.3 等价性清单）+ 版本簿记（H1 / §12 / footer） |
| 判据 | 阈值与判据号**零改动**；唯一收紧的是实现纪律（「滚动口径等价」被判为**不等价**） |
| 行级 | **4 hunk** / insert **100** 行 / replace **3 段（1→1 ×3）** / delete **0**；numstat `+103 / −3`，净 **+100**（1,957 → 2,057） |
| 字符 | Δ **9,354** 字符 = +1 +237 +9,357 −241 |
| 字节 | Δ **15,615** B |
| 四元组 | **244,093 B / 2,057 行 / 正文 `head -c 242,303` → `e47703f2…` / 全文 `8a3115aa…`** |
| 可复现 | DST 重定向复跑**逐字节相同**（`cmp` 无差异）；脚本自带底本 `BASE_SHA` 断言，篡改后 abort（我实测过） |
| **裁定 1** | **v0.10 §10.3（recipe 2）自本说明落盘起停用**；签认仍为 recipe 1 **三元组**；`canonical_digest_recipe` 字段不实现（§7） |
| **裁定 2** | **FS02 面「照实现」**：只在因子命名空间判，列命名空间（68 名，base）不 gate（§8） |
| 台账指针 | 不追版本号，**改绑 §7.1 块哈希**；v0.3 归档继续作不可变权威（§6.2） |

---

## 1. 四元组与复算

### 1.1 四元组

| 项 | 值 |
| --- | --- |
| 路径 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md` |
| size | **244,093 B** |
| 行数 | **2,057** |
| 正文前缀 | `head -c 242303` → **`e47703f2da50837627013d67abb8eebda094a2314490e35884de26af2cc4b870`** |
| 全文 sha256 | **`8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007`** |
| mtime | **2026-11-07 21:39:53.840**（落盘）；22:00:29.882 被并行流程以**相同字节**重写一次，见 §1.5 |

上述五个值由原生 `wc -c` / `wc -l` / `head -c … | sha256sum` / `sha256sum` / `stat` 复算，**不取脚本自报**。

### 1.2 正文前缀算式（为什么是 `head -c 242,303`）

正文 = 全文去掉末尾 footer 行（含其行尾 CRLF）。

```
全文        244,093 B
footer 行    1,788 B   (= 1,175 字符，中文多字节；行尾 CRLF 另 2 B)
footer CRLF      2 B
正文 = 244,093 - 1,788 - 2 = 242,303 B
```

- 正文以 `---\r\n\r\n`（7 B）收尾，该 7 字节位于 **242,296–242,302**；故 `head -c 242,303` 恰好截到分隔行末、footer 之前。
- 反算校验：`242,303 + 1,790 = 244,093` ✓
- 对照 v0.9（R9 已用同一算式）：`228,478 - 2,048 - 2 = 226,428`，footer 1,416 字符 → 2,048 B（+2 B 行尾 CRLF）。两版算法完全一致，不是为凑数临时发明的口径。

### 1.3 DST 重定向复跑（可粘贴；我实跑过，产物逐字节相同）

```bash
cd C:/work/sourcecode/tick-stock-panel
mkdir -p research/arch-build-20261107/_repro_r10
python - <<'PY'
import pathlib
src = pathlib.Path("research/arch-build-20261107/build_contract_v10.py")
s = src.read_text(encoding="utf-8")
old = 'DST = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md"'
assert s.count(old) == 1, "DST 行不唯一，别盲目替换"
new = ('DST = __import__("pathlib").Path('
       '"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro_r10/out_v10.md")')
pathlib.Path("research/arch-build-20261107/_repro_r10/b.py").write_text(
    s.replace(old, new), encoding="utf-8")
PY
python research/arch-build-20261107/_repro_r10/b.py
cmp docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md \
    research/arch-build-20261107/_repro_r10/out_v10.md && echo "EQUAL True"
```

实跑输出（原样；末行 `counts` 属脚本自检，控制台中文显示为乱码，不影响判定）：

```
body_bytes 242303
body_sha    e47703f2da50837627013d67abb8eebda094a2314490e35884de26af2cc4b870
total_bytes 244093
total_lines 2057
full_sha    8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007
EQUAL True
```

**两个坑（我踩了，写在这里省下一次）**

1. `DST` 必须是**绝对 Windows 路径**（`C:/…`）。本机 python 是 Windows 版，msys 的 `/tmp/x/out.md` 会落到 `C:\tmp\x\out.md`：脚本照样打印 `total_bytes 244093`，但你在 `/tmp` 下 `cmp` 找不到文件，看上去像「复现失败」。
2. footer 里嵌的是**字面量路径** `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md`（脚本 `:245` 的字符串常量），**不是** `DST.name` —— 所以改 `DST` 不改产物一个字节。这也正是「可重定向复现」能成立的前提；若哪天有人把 footer 改成 `DST.name`，这条复现方法立刻失效。

### 1.4 底本哈希自校验是脚本内置的，不是口头承诺

`research/arch-build-20261107/build_contract_v10.py:25–36`（`SRC`:25 / `DST`:26 / `BASE_SHA`:28 / `BASE_LEN`:29 / `BASE_BODY_CUT`:30 / 三条 `assert`:33–34、36）：

```python
SRC = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md"
DST = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md"
BASE_SHA = "5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c"
BASE_LEN = 228478
BASE_BODY_CUT = 226428
raw = SRC.read_bytes()
assert len(raw) == BASE_LEN, ("底本长度变了", len(raw))
assert hashlib.sha256(raw).hexdigest() == BASE_SHA, "底本哈希变了"
body = raw[:BASE_BODY_CUT]
assert body.endswith(b"---\r\n\r\n"), "正文末尾不是 --- 分隔行"
```

**守卫是活的（我实测）**：把 `BASE_SHA` 改成 64 个 `0` 后运行 → `AssertionError: 底本哈希变了`，**未写任何文件**。即「v0.10 = v0.9 逐字节为底」在**每次复跑时都被重新校验**；底本被并行流程动过一个字节，就出不了货。

### 1.5 mtime 不能当锚（本说明写作期间就发生了一次）

- 落盘：**2026-11-07 21:39:53.840**
- 本说明写作期间：**22:00:29.882** 该路径被并行流程重写一次，**size 与 sha256 均未变**（244,093 B / `8a3115aa…`）。
- 结论：v0.10 与 v0.7 / v0.8 同类 —— **只认哈希不认时刻**。已按哈希留证 `research/arch-build-20261107/_base/v0.10_base_8a3115aa.md`（244,093 B / 同 sha），后续任何比对以它为准，不以 mtime 为准。
- 这不是孤例：v0.8 当天出现过 205,966 / 206,152 / 206,608 三组字节（版本号未变）；v0.10 这次是**同字节重写**（危害小，但足以让 mtime 失效）。

---

## 2. 逐处改动：原句 → 新句 → 依据

4 个 hunk，逐条给原句、新句、依据、账。

### 2.1 H1（`:1`，41 → 42 字符）

| 项 | 内容 |
| --- | --- |
| 原句 | `# 因子化引擎与生产侧执行器 —— 接口契约 v0.9（2026-11-07）` |
| 新句 | `# 因子化引擎与生产侧执行器 —— 接口契约 v0.10（2026-11-07）` |
| 依据 | 版本号簿记本身 |
| 账 | +1 字符 / +1 B |

### 2.2 `:126` §2.1 注 1 —— **本版唯一的一处正文勘误**（169 → 406 字符）

**原句（v0.9，整行 169 字符）**

> `observed_bars` 在研究中 = `date.cum_count().over("symbol")`，即**该标的在已加载面板内的 bar 行数**，不是「上市自然日」。系统侧**等价且更稳**的实现是「以当日为末端的滚动可交易日计数 ≥ 120」，前提是计算时**前置了 ≥120 根 bar 的 warmup 数据**。

**新句（v0.10，整行 406 字符）**

> `observed_bars` 在研究中 = `date.cum_count().over("symbol")`，即**该标的在已加载面板内的 bar 行数**，不是「上市自然日」。系统侧按 `cum_count` 实现（`docs/research/caliber-decisions-20261107.md` §11.1 决定七，登记号 **D6**，见 §2.8 / §12.2），**面板起点必须固定 `2018-01-08`**；若调用方只前置约 120 根 bar 的 `warmup`，「累计」会退化为「滚动」口径——实测池子 **−3.9%**（−99,713 标的日 / 1,001 只；未过其余三条时 −277,304 标的日 / 1,274 只），**且代码不改、验收全绿**。**「滚动可交易日计数」不是等价实现，已否决**（caliber §11.2：方向更严、逐年不衰减）。

**依据（五条，都可复跑）**

1. **自相矛盾**：§2.8（`:236`）已写「实现取 `date.cum_count().over("symbol")`」；注 1 却说等价实现是滚动计数。
2. **与口径裁定相反**：`docs/research/caliber-decisions-20261107.md` §11.1 决定七 —— 留 **A（`cum_count`）**、面板起点固定 `2018-01-08`；B 与滚动口径均不采用。
3. **实测不等价**：`research/b2-engine-20261107/logs/observed_bars_calibers.json` → `rows_diff_ge120 = 40,717`、`diff_in_eval_window = 17,499`、`rows_a_ge120_only = 0`；过其余三条后 **−99,713 标的日 / 1,001 只 = −3.9%**（基数 = A 口径下过其余三条的 2,560,060 标的日；与 `E3-A1` 的 `n = 2,527,847` 差 32,213 = 被 ST 条件滤掉的部分）。
4. **逐年不衰减**（所以不是「早期年份噪声」）：2019 `6,197` / 2020 `14,372` / 2021 `16,111` / 2022 `15,268` / 2023 `8,112` / 2024 `6,278` / 2025 `17,424` / 2026 `15,951`。
5. **机理**：A **单调**（入池后不因这一条退出）；滚动**不单调**（任一交易日停牌 → 该标的随后 120 个交易日连续被踢出，再进再踢）。

**判据影响：零。** `A1`–`A8`、`F-A11a`–`d`、`F-A40`–`F-A42` 的阈值与编号一字未动。本条把「看起来等价的实现」判为「不等价」，只**收紧实现纪律**，不放宽任何判据。

**账**：169 → 406 字符（**+237**）/ 321 → 720 B（**+399**）。

### 2.3 §12 插入（新行 `1955`–`2054`，100 行，0 删除）

| 子块 | 行（v0.10） | 内容 | 依据（可复跑） |
| --- | --- | --- | --- |
| §12.0 引言 | 1955–1958 | 本版 = v0.9 + 一处勘误 + 两类登记 + 版本簿记；§11 保持原样，故新章从 §12 起 | 避免与「§11 本版改动说明（R9）」标题打架 |
| §12.1 表 | 1959–1973 | §2.1 注 1 的九项：位置 / 原句 / 错在哪 / 原始变化 / 过其余三条 / 逐年 / 机理 / 出处 / 改后 / 判据影响 | `caliber-decisions-20261107.md` §11.2–§11.3；`observed_bars_calibers.json` |
| 面板起点两法 | 1974–1978 | 两条**系统改动**（不是口径改动）的落地方式 | `backend/app/custom/research_universe_pack/universe.py` 逐 symbol `cum_count` → 同一 `(date, symbol)` 的 `observed_bars` **取决于调用方加载起点**；`E3-A1` 的 0 差是在 frame 起 `2018-01-08` 下取得（`research/b2-engine-20261107/verify_e3.py:30`、`:42`） |
| §12.2 编号登记 | 1979–1990 | **D5** = G2 成交口径（`F-A40` + `FS08`）；**D6** = `observed_bars`（证据 id `D-B2-1`）+ 4 条纪律 bullet | `docs/architecture/CONTRACT_REVIEW_20261107.md:139`（D5 占号）/`:140`（D6 已被 `_plan_buys` 3487 行排序占用）/`:195`（该条已关闭）；排期 v5 `:73` |
| §12.3 清单 | 1991–2054 | 分布表（**9 实测 / 4 部分 / 7 待验 / 13 规格 / 9 n-a = 42**）+ 42 行逐条 + 3 条读表规则 | 口径 = 在 **v0.9** 上 `grep -c '等价\|同式\|逐位相同\|逐位一致'` = **42**（我复跑：42） |

**脚本内置断言**：`len(ROWS) == 42`、`sum(cnt.values()) == 42`。清单不可能悄悄变 41 或 43；分布表与逐行表不可能各说各话。

**为什么全表「位置」标 v0.9 行号（这是刻意选择，不是偷懒）**：§12 插在**文件末尾**（插入点 `1955` 之后只剩 footer），所以 `:1955` 之前的 v0.9 行号**完全不漂移**。逐行改写成 v0.10 行号只会制造一个新的复算面、多一处可错的地方。凡引用 §12.3 的「位置」，一律理解为 **v0.9 行号**。

**账**：0 → 9,357 字符（**+9,357**）/ 0 → 15,475 B（**+15,475**）。

### 2.4 footer（`:2057`，1,418 → 1,177 字符）

| 项 | 内容 |
| --- | --- |
| 原 footer | 正文 sha `d967d463…` / 正文 `226428 B` / 1,957 行 / v0.9 一句话 / v0.8 冻结参照 / v0.7 降历史 / v0.6–v0.3 簿记 = **1,418 字符** |
| 新 footer | 正文 sha `e47703f2…` / 正文 `242303 B` / 2,057 行 / v0.10 一句话 + 「本周期终版」/ v0.9 已被取代 / v0.8 只认哈希 / v0.7 降历史 / v0.6–v0.3 簿记 = **1,177 字符** |
| 依据 | 版本簿记 + 前序状态改写（v0.9 由「现行」→「已被取代」，v0.8 由「冻结参照」→「只认哈希不认时刻」） |
| **不自指全文 sha** | 全文 sha 依赖 footer 自身，写进去就是不定点方程。四元组里的全文 sha 一律由外部（`wc` / `sha256sum` / 脚本）给出 |
| 账 | **−241 字符** / 2,050 → 1,790 B（**−260**） |

---

## 3. 行级 numstat：两法必须同组，并给等式

### 3.1 两法结果（我实跑，逐项相等）

| 方法 | hunk | insert 新行 | replace | delete 旧行 | added | deleted |
| --- | --- | --- | --- | --- | --- | --- |
| `difflib.SequenceMatcher(autojunk=True)` | 4 | 100 | 3 段（1→1 ×3） | 0 | 103 | 3 |
| `difflib.SequenceMatcher(autojunk=False)` | 4 | 100 | 3 段（1→1 ×3） | 0 | 103 | 3 |
| `git diff --no-index`（Myers） | 4 | 100 | 3 段（1→1 ×3） | 0 | 103 | 3 |

`git diff --no-index --numstat` 原样输出：

```
103	3	docs/architecture/{FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md => FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md}
1 file changed, 103 insertions(+), 3 deletions(-)
```

`autojunk` 开与关给出**完全相同**的结果 —— 说明没有「重复行被当垃圾丢掉」的假象，这组 diff 是稳的。

### 3.2 逐 hunk（旧行 = v0.9，新行 = v0.10）

| # | 类型 | 旧行 | 新行 | 行数 | 内容 |
| --- | --- | --- | --- | --- | --- |
| 1 | replace | 1 | 1 | 1 → 1 | H1 版本号 |
| 2 | replace | 126 | 126 | 1 → 1 | §2.1 注 1 |
| 3 | insert | （插在 1954 之后，旧区间为空） | **1955–2054** | 0 → 100 | §12 全章 |
| 4 | replace | 1957 | 2057 | 1 → 1 | footer |

### 3.3 等式（add 与 insert、delete 与 replace 的关系）

```
added   = insert 的新行数 + replace 的新行数 = 100 + 3 = 103
deleted = insert 的旧行数 + replace 的旧行数 =   0 + 3 =   3
净增    = added - deleted = 行数差 = 103 - 3 = 100 = 2,057 - 1,957
```

**两个必须避开的读法错误**

- 「**4 hunk**」≠「改了 4 行」：4 个 hunk 里只有 1 个是块插入（100 行），另外 3 个各是 1 行替换。
- 「`+103/−3`」≠「净 +103」：净增是 **+100**。

---

## 4. 字符账与字节账（两本账要分开）

| 块 | 字符（旧 → 新） | 净字符 | 净字节 |
| --- | --- | --- | --- |
| H1 | 41 → 42 | **+1** | +1 |
| §2.1 注 1 | 169 → 406 | **+237** | +399 |
| §12 插入 | 0 → 9,357 | **+9,357** | +15,475 |
| footer | 1,418 → 1,177 | **−241** | −260 |
| **合计** | 145,011 → 154,365 | **+9,354** | **+15,615** |

复核等式：

```
字符：+1 + 237 + 9,357 - 241 = 9,354   = 154,365 - 145,011  OK
字节：+1 + 399 + 15,475 - 260 = 15,615 = 244,093 - 228,478  OK
```

**计数约定**：本文件所有「字符」一律**含行尾 CRLF**（单行 footer `1,418 → 1,177` 即含 CRLF；不含则 `1,416 → 1,175`，差值 −241 不变）。字节一律按 UTF-8 实长。

**字节 ≠ 字符**：中文一字 3 B，所以 Δ 字节（15,615）远大于 Δ 字符（9,354）。任何「按字符推字节」的估算都会错 —— R8 那轮我就在这儿错过一次，这次两本账分开列。

---

## 5. 未动面的证明

### 5.1 §7.1 八行公式：**v0.3 归档 → v0.10 逐字节相同**

取块方式 `### 7.1` → `### 7.2`（台账脚本自带同一个取块函数），8 个版本逐个复算：

| 版本 | CRLF 字符 / sha16 | LF 字符 / sha16 |
| --- | --- | --- |
| v0.3 归档（`archive/…_v0.3_FROZEN.md`） | 2,541 / `a8e88134f60b504c` | 2,514 / `6d3db0139a45f54c` |
| v0.4（未编号 `FACTOR_ENGINE_CONTRACTS_20261107.md`） | 同上 | 同上 |
| v0.5 | 同上 | 同上 |
| v0.6 | 同上 | 同上 |
| v0.7 | 同上 | 同上 |
| v0.8 | 同上 | 同上 |
| v0.9 | 同上 | 同上 |
| **v0.10** | **同上** | **同上** |

判定：`ALL IDENTICAL: True`。两套口径都对，**引用时必须写明是哪一套**（LF 归一口径 / CRLF 保留口径）。

### 5.2 小节审计：132 节 → **129 逐字节相同 / 2 改 / 5 增 / 1 删**（136 = 132 − 1 + 5）

- **改 2 节**：H1（标题行）、`### 2.1 注`（其块包含 `:126`）。
- **增 5 节**：新 H1、`## 12.`、`### 12.1`、`### 12.2`、`### 12.3`。
- **删 1 节**：旧 H1（`# … v0.9（2026-11-07）`）—— 改版本号后节名变了，按节名比对计为「删旧 + 增新」，实为同一行的 1→1 替换（§3 行级账里是 replace，不是 delete）。132 − 1 + 5 = **136** = v0.10 节数。
- **边界效应（不要当改动）**：`## 11.2 与 v0.8 的关系、以及为什么这次叫 v0.9` 报「changed」，是因为它是 **v0.9 的文件尾块**（块体一直延伸到 EOF，把旧 footer 包在里面）。它的正文一字未动，变的是它屁股后面的 footer + 新插入的 §12。
- **教训（R9 已写过一次，这里再说一次）**：**别拿小节块长度表相减**，加减一律用 §3 / §4 的行级账。

### 5.3 三份旧版一字未改（收到派单时 = 本说明落盘时，同值）

| 版本 | size | 行 | 全文 sha | mtime |
| --- | --- | --- | --- | --- |
| v0.7 | 193,586 | 1,696 | `5a87d4b090d996ab…` | 18:03:23.683 |
| v0.8 | 206,608 | 1,792 | `2cf85ccbaaf1fed7…` | 21:04:09.347 |
| v0.9 | 228,478 | 1,957 | `5d0abbb59636ae9c…` | 21:14:03.280 |

---

## 6. 版本绑定：v0.9 与 v0.10 各绑哪些判据

### 6.1 判据 / 条款 × 绑定版本

| 判据 / 条款 | 文本出处（v0.10 行） | 首次生效 | **现在绑谁** | 说明 |
| --- | --- | --- | --- | --- |
| `F-A11b`（**只判列级**：`d_col / max(s_col, 1e-12) ≤ 2^-23`） | `:1521`（理由段 `:1527`） | v0.9 | **v0.10** | 判据文本 v0.9 → v0.10 **逐字节相同** |
| §7.16 `FS03` 可判定条款（C1–C4 / 4 个入口 / HTTP 400 形状） | `:1593–1685` | v0.9 | **v0.10** | 同上 |
| `F-A42-1` … `F-A42-6` | `:1680–1685` | v0.9 | **v0.10** | 同上；**实现未落**（`alias_of` / `strategy_usable` 在 `backend/app` 零命中） |
| §2.8 `observed_bars` 信息项（40,717 / 窗内 17,499） | `:234–248` | v0.9 | **v0.10** | 信息项，不改判据 |
| §2.7 catalog 93 → 107 → **108** + 6 处断言同步 | `:231–232` | v0.9 | **v0.10** | 108 是**密闭口径**（193 = 108 + 85 个 `ext_*`） |
| §2.1 注 1（`cum_count` + 面板起点 `2018-01-08`） | `:126` | **v0.10** | v0.10 | 本版唯一正文勘误；是**实现纪律**，不是判据 |
| **D5 / D6 编号** | `:1979–1990`（§12.2） | **v0.10** | v0.10 | 只在 v0.10 里有 |
| **42 处等价性断言清单** | `:1991–2054`（§12.3） | **v0.10** | v0.10 | 只在 v0.10 里有 |
| `F-A5` | v0.4 | v0.4 | **v0.4** | §9 绑定声明未变 |
| `F-A30`–`F-A33` | v0.5 | v0.5 | **v0.5** | 同上 |
| `F-A34`–`F-A39`（清单 v2） | v0.6 | v0.6 | **v0.6** | 同上 |

**一句话**：`v0.9` 与 `v0.10` 之间**没有任何判据文本变化**（唯一被改的 `:126` 是**注**、不是判据），所以「判据一律以 v0.10 为准」**不引入任何新判据面**；v0.9 的角色降为「判据文本的同一性见证」。需要单独记的只有 §12 里那两件只在 v0.10 出现的东西（D5/D6 编号、42 处清单）。v0.4 / v0.5 / v0.6 的绑定关系**一个都没动**。

### 6.2 台账脚本的落后指针：一句话口径

**现状（我实跑）**：`docs/factors/evidence/scripts/check_f_class_ledger.py:49–61` 绑

- `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` → `4105c08da2de7ec4…`，89,833 B
- `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md` → `a8334fea9696c2ef…`，162,361 B

运行尾部 `BINDING` 段把这两个 sha 打出来（`contract` / `contract2`）。台账契约指针**落后四版**（v0.7 / v0.8 / v0.9 / v0.10 都没被绑）。

另有第三个指针 `:64–70` `CONTRACT_PREV` → **v0.5**，脚本注释明写「**non-binding**，只作为 `§7.1` 未漂移的证据」，`BINDING` 段只在文件存在时打印、不参与判定。这三个指针今天都指向**同一个块**（§5.1），所以「落后四版」不产生误判，只产生**漏拦**。

**口径（一句话）**：**不追版本号，改绑块哈希** —— 把「live numbered revision」从「v0.6 这个文件」换成「§7.1 块 `2,541` 字符 / `a8e88134…`（CRLF）或 `2,514` / `6d3db013…`（LF）」，**v0.3 归档继续作不可变权威**。

**为什么**：§7.1 在 v0.3 → v0.10 **八版逐字节相同**（§5.1），块哈希本身就是**版本无关的锚**。追版本号等于每升一版改一个不产生任何判定差异的常量；而**落后指针的真实代价不是误判，是漏拦** —— 它只保护 v0.6 与归档，对 v0.9 / v0.10 §7.1 的原地改写**静默放行**。这才是要修的东西。

**边界**：`docs/factors/**` 写权在因子工程师，本文件只给口径与证据，**我没有改那个脚本**。改之前当前绑定**不会误判**（块相同），只是拦不住新版的改动。

**顺带一条观察（同一脚本，非本次范围、非我裁定）**：该脚本当前 `RESULT: FAIL`，原因是 `RECORD MISMATCHES: 2` —— `freeze_declaration_version_agree`、`md_fingerprint_matches_registry` 两个 check 没有写进 JSON 的 `self_check` 块。**与 BINDING 无关**，也不影响 §7.1 的块比对结果；纯记录问题，交因子工程师。

---

## 7. §10.3（recipe 2）处置：**停用**（选项 b）

### 7.1 裁定

**单选 (b)**：`FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md §10.3`（:1859–:1880）**自本说明落盘起停用（void）**。

- 签认对象仍为 **recipe 1** = §7.12.4 原文（剔除 `generated_at` / `repo_head` / `data_root` / `canonical_digest` 四键）。
- 签认是**三元组**：`(canonical_digest, schema_version, scanned_sources)`。
- 顶层字段 `canonical_digest_recipe` **不实现**。
- 任何声称「recipe 2 / 载荷白名单」合规的产物，一律按**不合规**处理 —— 没有生成器、没有字段、没有产物，声称本身就是错误。

### 7.2 生效边界（四层，逐层写死）

| 层 | **停用范围** | **保持有效** |
| --- | --- | --- |
| **事实层** | — | 已公布 digest 全部仍按 recipe 1 判：`184e4728…`（17:26–17:27 三份）、`9d34fef7…`（17:10，无副本）、`aefdf528…`（19:23:55 十份）。`F-A22`「同输入两跑 `canonical_digest` 相等」不变 |
| **判据层** | ①「`F-A36` 剔除清单 → 载荷白名单」②「L2 起产物必须 `"2"`」③「跨 recipe 报不可比、**不得判失败**」 | `F-A36` 按 §7.12.4 原文复算 == 落盘值；扰动 `generated_at` / `repo_head` / `data_root` / 记录顺序**不变**；改任一 `verdict` **必变** |
| **文档层** | §10.3 的规范性条款：`:1872`（recipe 2 定义 +「本版起新产物必须用它」）、`:1876` 末句「前两个已不可复验」（**该句为假，见 §7.5**）、`:1877`（新增字段 + 四元组）、`:1878`（比对规则 + L2 必须 `"2"`）、`:1879–1880`（判据边界 + 代价） | `:1861` 事实段（recipe 1 自洽、问题在**绑定面**）与 `:1863–1868` 扰动矩阵**是实测事实，保留有效**；`:1876` 前半句「recipe 1 保留为历史定义、已公布值不失效」保留 |
| **实现层** | 不新增 `canonical_digest_recipe`；不改生成器 | `backend/scripts/build_referenced_factor_inventory.py`（64,975 B）继续只写 recipe 1（`CANONICAL_DROP` 四键，`:139`） |

**引用纪律**：引用 v0.10 §10.3 时**必须**带「（已停用，R10）」，不带即为**引用错误**。冻结评审清单请把「§10.3 停用条款」列为一条，位置 :1859–:1880。

**为什么不在契约里就地加一行标注**：那要改契约本体，本轮禁止。所以现行**有效文档集合 = {v0.10 本体 + 本说明}**，两者必须一起引；单独引 v0.10 §10.3 会读出一个「要求实现、但没实现」的合规态。

### 7.3 为什么是 (b) 而不是 (a)

1. **没有实现面**：13 份产物（3 份 `184e4728…` + 10 份 `aefdf528…`）的 `canonical_digest_recipe` **全部 ABSENT**；生成器 `grep -c canonical_digest_recipe` = **0**；独立审核 `A11_generator_implements_recipe2: ok=false`。**改写得再正确，也是在描述一个不存在的合规态。**
2. **终版边界**：本周期已宣布「只走冻结评审、不再追加版本」。出 R11 会再触发一轮字节追逐 —— 今天已实测到 v0.7 / v0.8 / v0.10 三次被并行流程原地重写（v0.10 就在本说明写作期间被**同字节**重写一次），每多一版就多一个可漂移面。
3. **方向**：停用是 **fail-closed**（没人能声称 recipe 2 合规）；而「重写后仍无实现」的条款只会招来这种声称 —— 那正是审核说的**免验通道**。

### 7.4 审核四条要求 → 落在哪里

| 审核要求 | 本裁定下的处置 |
| --- | --- |
| ① 声明与复现不一致 = **FAIL** | 停用后没有「声明」可言，该要求**休眠**；**重启时必须作为 `F-A36` 的 FAIL 条件写入**（声明的 recipe 与复算不一致 → FAIL，不是「不可比」） |
| ② 删「不可复验」，改副本路径 | 已在 §7.5 给出实测更正：`184e4728…` **有 3 份副本、全部按 recipe 1 复算通过**；`9d34fef7…` 确实 0 份 |
| ③ 取值域只 `{"1","2"}`，域外 fail-closed | 字段不实现，取值域问题不存在；**重启时必须照此写**（`"3"` / `""` / 其他值 → 直接 fail-closed，不得回退到默认） |
| ④ 「不可比」只用于同生产者 `F-A22` | 随条款失效（单 recipe，比对面只有一种口径）；**重启时必须照此写** |

### 7.5 实测更正：「前两个已不可复验」为假（就其中一份而言）

按 §7.12.4 原文（recipe 1）复算，四份产物：

| 产物 | 落盘 digest | 复算 | 记录数 | 结论 |
| --- | --- | --- | --- | --- |
| `research/referenced-factor-inventory-v3-20261107/run1.json` | `184e4728…` | `184e4728…` | 218 | **MATCH** |
| `research/referenced-factor-inventory-v3-20261107/final_run_a.json` | `184e4728…` | `184e4728…` | 218 | **MATCH** |
| `research/referenced-factor-inventory-v3-1-20261107/final_run_v3_prev.json` | `184e4728…` | `184e4728…` | 218 | **MATCH** |
| `docs/architecture/evidence/referenced_factor_inventory.json` | `aefdf528…` | `aefdf528…` | 218 | **MATCH** |

- `184e4728…` = **3 份副本在盘**（各 184,643 B，`generated_at` 分别 17:26:27 / 17:27:33 / 17:27:43）→ **「盘上无原文件、已不可复验」对它是假的**。
- `aefdf528…` = **10 份副本**（186,343 B，18:03–19:23），全 MATCH。
- `9d34fef7…` = **0 份副本**（在盘上 425 个 JSON 里只作为文档引用出现）→ 这一份**确实**不可复验。

**结论**：条款拿「不可复验」当换口径的理由，**前提不成立** —— 旧 digest 的可复验性与「该不该换口径」是两件事；而且「旧值不可复验」恰恰是**保留**而非替换它的理由（一换就再也验不了）。这也是审核退回它的第一刀。

---

## 8. 顺手裁定：`gate.py` 的 FS02 面 —— **照实现**

### 8.1 结论（一句话）

**照实现**：`FS02` 只在**因子命名空间**上判；列命名空间（管线列 / 指标列，`ref_namespace=column`）**不判 FS02**，按 `kind="base"` 不 gate。

### 8.2 依据（三条，都是我复跑的）

1. **清单自己就分两个命名空间**：`docs/architecture/evidence/referenced_factor_inventory.json` 的 `summary.all_records.by_namespace = {column: 97, factor: 107}`；`summary.live_config` 的 **79 条** primary **全部** `namespace=column` / `class=base` / `verdict=allow`。照字面判 FS02 = **把清单自己判成 79 条违例**。
2. **契约另一处已写「base / virtual 不 gate」**：§7.8.3 表第 1 行（`:1003`）；§7.7.2 矩阵末行（`:919`）；§7.8.5 标题「不做这一段，批二一上线就停产」本身就是在承认**存量引用的是列、不是因子**。
3. **实测零缺口**：活配置里 **23** 个不同列名 —— `close` / `open` / `high` / `low` / `raw_close` / `raw_high` / `raw_low` / `volume` / `amount` / `ma5` / `ma10` / `ma20` / `ma60` / `macd_dea` / `macd_dif` / `boll_lower` / `boll_upper` / `high_60d` / `low_60d` / `limit_up_price` / `limit_down_price` / `consecutive_limit_ups` / `vol_ratio_5d` —— **全部**落在 gate 的列面内（缺失 **0**）。

### 8.3 列面的定义（写死，防止面自己长大）

```
列面 = dsl.BASE_COLUMNS(9) ∪ pipeline 的 6 个列集合
     = INDICATOR_COLUMNS ∪ ENRICHED_COLUMNS ∪ ENRICHED_STORAGE_COLS
       ∪ LIMIT_SIGNAL_OUTPUTS ∪ _ALL_INDICATOR_COLS ∪ _LIMIT_PRICE_COLUMNS
     = 68 名
```

- 我实测 `len(_column_universe()) == 68`（9 + 59）。
- 68 里 **25 个**在 registry 有 spec、**43 个**无 spec 无定义（正是 CONTRACT-GAP 5 说的那批）。
- **必须把 `68` 做成断言**（`len == 68` 入 B2 验收）：列面靠 `getattr` 拼出来，哪天 pipeline 多一个常量，FS02 的面会**静默变大** —— 闸门被自己的 base 面架空，这比判严更危险。

### 8.4 建议收紧（不是本文件的改动，交 B2 验收）

43 个无 spec 里有 **12 个不是「数据列」**：

- **8 个 `_` 前缀引擎暂存列**：`_boll_std`、`_daily_pct`、`_ema12`、`_ema26`、`_kdj_hn`、`_kdj_ln`、`_tr`、`_vol_ma5`
- **4 个身份 / 元数据列**：`symbol`、`date`、`name`、`quote_ts`

建议**移出列面**（68 → **56**）：策略配置引用 `_tr` 这类内部暂存列属于配置错误，应当得 `FS02`，而不是被 base 面放行。**实测零风险**：活配置 23 个列名里 `_` 前缀 **0** 个、身份列 **0** 个。移出后 `ma55` 这种拼错仍 `FS02`（不在 56、不在 registry），fail-closed 方向不变。

### 8.5 我没有裁的部分

`gate.py` 顶部列的 CONTRACT-GAP **1–4**（`mode="none"` 的第 4 个取值、`shadow` 参数、`entry` 位置参数、`GateReport` 六字段承载 4 个 research/diagnostic 标记）**不在本次口径内，我没有裁定**。它们需要单独一轮；其中第 4 条（标记落点）可能要扩 `GateReport` 字段 —— 那是**判据面改动**，得走版本，不能顺手放行。

---

## 9. 未确证与不做的事

**未确证（我不下结论）**

- `F-A42-1` … `F-A42-6` 全未实现：`alias_of` / `strategy_usable` 在 `backend/app` 零命中，`get_factor("uf_vol60")` 现为 `None` → `F-A42-2` / `F-A42-3` **当前必红**。
- §12.3 清单里 7 条「待验」我没有提升为实测 —— 按读表规则 1，只有「实测」可当既有事实引用。
- 列面 68 只在一条调用路径（`RegistryFacts.facts`）实测；矩阵 / 回测路径是否另有算子白名单未覆盖。
- `F-A11b` 的列级阈值我没有在真实数据上重算（只核了报告三处数互为 **1.19×**：1.416e-07 ÷ 1.192e-07）。

**没做（边界）**

- 未改 v0.7–v0.10 任何契约本体；未改 `backend/**`；未改 `docs/factors/**`；未 `git add`、未提交、未部署。
- 未出 R11（本裁定为 (b)）。

**转交**

- 台账 BINDING 升级（§6.2 口径）→ **因子工程师**（`docs/factors/**` 写权）。
- 若将来真要做 recipe 2 → **系统开发工程师**先落生成器 + 字段 + 产物，再由架构师按 §7.4 四条出 R11。顺序不能倒。

---

## 10. 复算清单（一页，粘进 shell 就能跑）

```bash
cd C:/work/sourcecode/tick-stock-panel
S=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md
S9=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md

# 1) 四元组
wc -c "$S"; wc -l "$S"; sha256sum "$S"
head -c 242303 "$S" | sha256sum            # 期望 e47703f2…
stat -c '%s %y' "$S"
python -c "print(244093-1788-2)"           # 242303

# 2) 行级 numstat（两法）
python - <<'PY'
import difflib
a=open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md',encoding='utf-8').read().splitlines(keepends=True)
b=open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md',encoding='utf-8').read().splitlines(keepends=True)
for aj in (True,False):
    ops=[(t,i1+1,i2,j1+1,j2) for t,i1,i2,j1,j2 in difflib.SequenceMatcher(None,a,b,autojunk=aj).get_opcodes() if t!='equal']
    print(aj, len(ops), ops)
PY
git diff --no-index --numstat -- "$S9" "$S"   # 期望 103  3

# 3) §7.1 八版逐字节（取块 ### 7.1 -> ### 7.2）
python - <<'PY'
import hashlib, pathlib
files={'v0.3':'docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md',
 'v0.4':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md',
 'v0.5':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md',
 'v0.6':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md',
 'v0.7':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md',
 'v0.8':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md',
 'v0.9':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md',
 'v0.10':'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md'}
seen=set()
for k,p in files.items():
    t=pathlib.Path(p).read_bytes().decode('utf-8')
    i=t.index('### 7.1'); j=t.index('### 7.2',i); blk=t[i:j]
    lf=blk.replace('\r\n','\n')
    r=(len(blk),hashlib.sha256(blk.encode()).hexdigest(),len(lf),hashlib.sha256(lf.encode()).hexdigest())
    seen.add(r); print(k, r[0], r[1][:16], r[2], r[3][:16])
print('ALL IDENTICAL:', len(seen)==1)      # 期望 2541 a8e88134… / 2514 6d3db013…
PY

# 4) digest 复算（recipe 1）
python - <<'PY'
import json,hashlib
DROP={'generated_at','repo_head','data_root','canonical_digest'}
rk=lambda x: json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
for p in ['research/referenced-factor-inventory-v3-20261107/run1.json',
          'research/referenced-factor-inventory-v3-20261107/final_run_a.json',
          'research/referenced-factor-inventory-v3-1-20261107/final_run_v3_prev.json',
          'docs/architecture/evidence/referenced_factor_inventory.json']:
    d=json.load(open(p,encoding='utf-8'))
    q={k:v for k,v in d.items() if k not in DROP}
    q['records']=sorted(q.get('records',[]),key=rk)
    h=hashlib.sha256(json.dumps(q,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    print(p.split('/')[-1], d.get('canonical_digest')==h, h[:8])
PY

# 5) FS02 列面（需要 backend venv）
cd backend && .venv/Scripts/python.exe -c "from app.factors.gate import _column_universe as u; print(len(u()))"   # 68
```

---

*本说明是交付说明，不是契约本体；四元组一律以 §1.1 为准，mtime 不作锚（§1.5）。契约本体一字未改。*
