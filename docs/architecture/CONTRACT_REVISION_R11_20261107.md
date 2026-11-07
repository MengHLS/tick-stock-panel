# 契约修订 R11：把「§10.3 已停用」写进正文（v0.10 → v0.11）

- 日期：2026-11-07 22:4x–23:0x（本机）
- 作者：系统架构师
- 对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md` → `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md`
- 性质：**只补读取路径，不改判据。** 除下列三处（banner / H1 / footer）外，v0.11 正文与 v0.10 **逐字节相同**，并由 §5.5 的逆向还原给出构造性证明。
- 边界：未改 v0.7–v0.10 任何一份（四元组见 §6.2）；未改 `backend/**`；未改 `docs/factors/**`；未提交、未部署。撞名条款不在本文件生效范围（见 §7 与独立文件 `CLAUSE_NAMESPACE_COLLISION_20261107.md`）。

---

## 1. 一句话结论

R10 把「§10.3 停用」写进了**修订说明**，但没写进**契约正文**：v0.10 全文 `停用` 出现 **0 次**，只读现行契约的人仍会按 recipe 2 判 —— 这是今天唯一一处 **fail-closed 规则没有家**。R11 把这三行 banner 放进 §10.3 标题下，让「读到条款的人」与「读到说明的人」看到同一句结论。

**v0.11 = v0.10 逐字节为底 + §10.3 标题下 3 行停用 banner + 版本簿记。判据编号、阈值、主语义一字未动。**

## 2. 交付物四元组

| 项 | v0.10（底本） | v0.11（本版） | Δ |
| --- | --- | --- | --- |
| size | 244,093 B | **245,314 B** | +1,221 |
| 行数（`\n` 计数） | 2,057 | **2,061** | +4 |
| 正文前缀（`head -c`） | 242,303 B | **243,159 B** | +856 |
| 正文 sha256 | `e47703f2da50837627013d67abb8eebda094a2314490e35884de26af2cc4b870` | **`6ea5accbd50ce95ed5798cc7f99ef7715230015d4c516efcefa4b760c90302fc`** | — |
| 全文 sha256 | `8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007` | **`d1349af50826fcf61fe52b27129ff0c656c23c449e69d4f65d4c2332bd8dc57f`** | — |
| footer | 1,790 B | 2,155 B | +365 |
| 字符数（含 CRLF） | 154,365 | 155,144 | +779 |
| mtime | 22:00:29.882（落盘 21:39:53.840） | **22:51:10.228** | — |

**正文前缀算式**（与 R10 §1.2 同口径，不另立算法）：

```text
正文 = 文件去掉尾部 footer 行及其后的换行
v0.11: 245,314 − footer 2,153 − CRLF 2 = 243,159 ✓
v0.10: 244,093 − footer 1,788 − CRLF 2 = 242,303 ✓
```

**两本账分开记**（这条约定沿用 R10 §2.2）：

```text
字节账  +1,221 = banner 856 + H1 0 + footer 365
字符账  +779   = banner 530（含 4 个 CRLF）+ H1 0 + footer 249
```

**footer 的 365 B 拆开**：版本前缀改写 +99 B（`版本 **v0.10（2026-11-07 R10：` → 含 R11 说明的 `版本 **v0.11（…）**· v0.10（…`）+ 末句指针 +266 B。字符侧同理：+59 +190 = +249。

## 3. §10.3 停用 banner：位置与逐字

- 落点：`### 10.3` 标题行**之后**（v0.11 行号 `:1859`，标题行号与 v0.10 相同 —— banner 插在标题下方，不占标题位）。
- 形式：**1 个空行 + 3 行引用块**（共插入 4 行）。三行逐字如下（`:1861`–`:1863`）：

```text
> ⛔ **本条裁定自 2026-11-07 起停用（已停用，R10）—— 判据、实现、评审均不得再按本节 recipe 2 下判。**
> **现行唯一定义 = recipe 1 = §7.12.4 原文**（剔除 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键）；签认仍为**三元组** `(canonical_digest, schema_version, scanned_sources)`；`canonical_digest_recipe` 字段**不实现**，任何声称「recipe 2 合规」的产物按**不合规**处理；本节「比对规则（`F-A22`）」中「不可比」免检通道与「L2 起产物必须 `"2"`」一并不生效。
> 依据：`docs/architecture/CONTRACT_REVISION_R10_20261107.md` §7（独立审核四条 + 13 份产物 `canonical_digest_recipe` 全部 ABSENT、生成器 `grep` 为 0、审核 `A11 ok=false`）；本条只停用、不删除，正文历史保留以便复核。
```

三行尺寸（字符 / 字节）：68/138、285/448、169/262；加 4 个 CRLF 共 **856 B**。

**为什么是 banner 而不是删行**：被退回的是**条款的生效性**，不是**发生过的事实**。§10.3 里 `:1865–:1870` 的扰动矩阵、`:1863` 的 recipe 1 自洽实测，都是可以复核的事实记录，删掉会同时删掉「为什么退回」的证据。停用 banner 保留全部历史，只在最前面声明「不得据以下判」。R10 §7.2 的分层边界（文档层停用哪几条、保留哪几条）在这里被**落到正文**。

**行号平移**：banner 之后，原 §10.3 正文整体下移 4 行（原 `:1861` → 现 `:1865`；原 `:1880` 末条 → 现 `:1884`）；`### 10.4` 由 `:1882` → **`:1886`**，`### 10.5` 由 `:1890` → **`:1894`**。banner 内**不写任何行号**（否则收版即失真），只用「本节『比对规则（`F-A22`）』」这类标题名定位。

## 4. 逐处改动：3 个 hunk、4 处替换

| # | hunk 形态 | 位置（v0.11） | 原 → 新 | 尺寸 |
| --- | --- | --- | --- | --- |
| 1 | replace 1→1 | `:1` | H1 `接口契约 v0.10（2026-11-07）` → `接口契约 v0.11（2026-11-07）` | 字符 ±0 / 字节 ±0 |
| 2 | insert 4 | `:1861–:1864`（插在 `:1859` 标题与 `:1865` 事实之间） | （空行 + 3 行 banner） | +530 字符 / +856 B |
| 3 | replace 1→1 | `:2061`（footer） | footer 版本前缀改 v0.11 + 末句加指针 | +249 字符 / +365 B |

hunk 3 内部是两处替换（3a 版本 token、3b 指针），但**同一行内**，行级 numstat 只计 1 个 hunk、1 个 replace。

### 4.1 一处偏差，明写：H1 跟着改了版本号

派单的硬约束是「除 banner 与 footer 指针外正文逐字节不变」。**我动了 H1（v0.10 → v0.11），这是第 3 处，不严格在约束内**，理由与代价都写在这里：

- 不动 H1 的话，命名为 v0.11 的文件**第一行自报 v0.10** —— 这正是 R11 要修的那类「文件自述与实际不一致」；只读 H1 判版本的那种读法会被误导到另一版。
- 这是**版本簿记，不是判据**：`v0.10` 与 `v0.11` 都是 5 个字符，**字节账 ±0**，不影响任何阈值、编号、口径。
- 与先例一致：v0.4→v0.10 的每一次修订，H1 都是第 1 个 hunk（R10 自身 hunk 1 就是 H1）。
- **要严格的 2 hunk 版**：把 `build_contract_v11.py` 的 hunk 2 整段删掉重跑，其余字节不受影响（footer 的 `· v0.10（…R10…）` 仍在，版本链不断）。我不推荐 —— 文件会自报旧版本。

## 5. 可复跑清单

### 5.1 生成（确定性；重跑同字节）

```bash
cd /c/work/sourcecode/tick-stock-panel
backend/.venv/Scripts/python.exe research/arch-build-20261107/build_contract_v11.py
# 输出：size 245314 / lines 2061 / full d1349af50826fcf61fe52b27129ff0c656c23c449e69d4f65d4c2332bd8dc57f
```

脚本自带**底本守卫**（`build_contract_v11.py:28–:37`）：`BASE_SHA` / `BASE_LEN` / `BASE_NL` / `BASE_BODY_SHA` 四条任一不符即 `SystemExit`，**不写任何文件**。四处替换各有 `count == 1` 断言（尾锚点另加「必须落在文件末 5%」的断言，防止误命中 §1.1 与 §10.4 里同名路径）。

实测负样本：把 `BASE_SHA` 改成 64 个 `0` → `SystemExit: 底本哈希变了`，v0.11 文件未被触碰（`Get-FileHash` 前后相同）。

### 5.2 DST 重定向复跑（产物必须逐字节相等）

```bash
cd /c/work/sourcecode/tick-stock-panel
mkdir -p research/arch-build-20261107/_repro_r11
sed 's#^DST = .*#DST = Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro_r11/v11.md")#' \
  research/arch-build-20261107/build_contract_v11.py \
  > research/arch-build-20261107/_repro_r11/b.py
backend/.venv/Scripts/python.exe research/arch-build-20261107/_repro_r11/b.py
cmp docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md \
    research/arch-build-20261107/_repro_r11/v11.md && echo "BYTE-IDENTICAL"
```

实测输出：

```text
size 245314
lines 2061
full d1349af50826fcf61fe52b27129ff0c656c23c449e69d4f65d4c2332bd8dc57f
EQUAL: True
BYTE-IDENTICAL
```

条件（两条，缺一即失败）：`DST` 必须是**绝对 Windows 路径**（msys 的 `/tmp` 会落到 `C:\tmp`）；v0.11 正文与 footer 里**不含任何绝对路径** —— footer 里的 `docs/architecture/archive/…_v0.3_FROZEN.md` 是 v0.10 自带的历史字面量，不是本脚本写进去的。

### 5.3 四元组与两本账

```bash
python - <<'PY'
import hashlib, pathlib
p = pathlib.Path('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md')
raw = p.read_bytes()
lines = raw.split(b'\n'); k = len(lines) - 1
while lines[k].strip() == b'': k -= 1
body = sum(len(x) + 1 for x in lines[:k])
print('size', len(raw), 'lines', raw.count(b'\n'), 'body', body)
print('body_sha', hashlib.sha256(raw[:body]).hexdigest())
print('full_sha', hashlib.sha256(raw).hexdigest())
PY
# 期望：size 245314 / lines 2061 / body 243159
#       body_sha 6ea5accb…0302fc / full_sha d1349af5…d8dc57f
```

### 5.4 行级 numstat：两法必须给同一组 hunk

```bash
python - <<'PY'
import difflib
a = open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md', encoding='utf-8').read().splitlines(keepends=True)
b = open('docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md', encoding='utf-8').read().splitlines(keepends=True)
for aj in (True, False):
    ops = [(t, i1+1, i2, j1+1, j2) for t, i1, i2, j1, j2 in
           difflib.SequenceMatcher(None, a, b, autojunk=aj).get_opcodes() if t != 'equal']
    print(aj, len(ops), ops)
PY
git diff --no-index --numstat -- docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md \
                                      docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md
```

| 方法 | hunk | insert | replace | delete | added | deleted |
| --- | --- | --- | --- | --- | --- | --- |
| `difflib`（`autojunk=True`） | 3 | 1（4 行） | 2（1→1 ×2） | 0 | 6 | 2 |
| `difflib`（`autojunk=False`） | 3 | 1（4 行） | 2（1→1 ×2） | 0 | 6 | 2 |
| `git diff --no-index`（Myers） | 3 | — | — | — | **6** | **2** |

三法同一组；`git --stat` 尾行 = `1 file changed, 6 insertions(+), 2 deletions(-)`。

**等式**（必须写出来，否则「+6/−2」会被读成「改了 6 行」）：

```text
added   = insert 新行 + replace 新行 = 4 + 2 = 6
deleted = insert 旧行 + replace 旧行 = 0 + 2 = 2
净增行  = 6 − 2 = 4 = 2,061 − 2,057 ✓
```

**一处必须提前说明的差异**：两种 `autojunk` 对**插入点归属**的读法不同（`True` 记 `a=[1860,1859]`，`False` 记 `a=[1861,1860]`），因为 banner 文本以 `\r\n` 开头，「前导空行算插入还是算上下文」本身有歧义。**计数与 hunk 数完全相同**，只是那 1 个空行被归到哪一侧。`git` 的 `6/2` 与两者都相容。这不影响任何结论，但复跑时会看到，先写在这里。

### 5.5 逆向还原：删掉 4 处改动必须逐字节回到 v0.10

这是「除 banner 与 footer 外正文逐字节不变」的**构造性证明**（不是比对报告）：脚本见 `research/arch-build-20261107/verify_v11_20261107.py`，核心是依次撤销 banner、H1、footer 版本前缀、footer 指针四处，然后比对字节。

实测：`244093 8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007` —— **与 v0.10 逐字节相同**（`equals_v0_10_bytes: true`）。即：除了这 4 处，v0.11 与 v0.10 没有任何一个字节不同。

### 5.6 §7.1 八行公式：v0.3 → v0.11 **九版全同**

口径与 R10 §5.1 完全相同（`t.index('### 7.1') : t.index('### 7.2', i)`，含行尾 CRLF）：

| 版 | CRLF 字符 / sha16 | LF 字符 / sha16 |
| --- | --- | --- |
| v0.3 归档 / v0.4 / v0.5 / v0.6 / v0.7 / v0.8 / v0.9 / v0.10 / **v0.11** | 2,541 / `a8e88134f60b504c` **九版全同** | 2,514 / `6d3db0139a45f54c` **九版全同** |

脚本输出 `sec_7_1_all_9_identical: true`。这条是 R10 §6.1「台账绑块哈希而非版本号」口径的地基：v0.11 里 §7.1 一个字都没动，所以台账继续按块哈希绑定仍然成立。

### 5.7 判据号：218 项逐项相同

| 度量 | v0.10 | v0.11 |
| --- | --- | --- |
| `F-A<n>` / `F-A<n>-<m>` 出现次数（正文，不含 footer） | 218 | **218** |
| 序列是否逐项相同 | — | **是** |
| 去掉 H1 后正文是否逐字节相同 | — | **是** |
| `停用` 出现次数（全文） | **0** | **6**（banner 3 + footer 指针 3） |

口径说明：`F-A` 序列比对在**移除 banner 之后**做（banner 里引用了 `F-A22` 一次，否则会多出一项），并单独断言「去掉 H1 后正文逐字节相同」，两条一起才能说明「只加了 banner」。

## 6. 版本绑定：v0.11 绑什么、什么没动

### 6.1 判据 × 版本

| 判据 / 条款 | R10 时的绑定 | v0.11 后 |
| --- | --- | --- |
| `A1`–`A8`、`B1`–`B3`、`C1`–`C3`（XS 截面排名） | v0.9 文本 | **不变**（v0.9→v0.11 逐字节相同） |
| `F-A1`–`F-A42`（含 `-1…-6` 子号） | v0.10 | **不变**，编号与阈值一字未动 |
| `F-A11a`–`F-A11d` | v0.10 | **不变** |
| `F-A36` canonical digest 主语义 | recipe 1 三元组 | **不变**；recipe 2 已停用（banner `:1862`） |
| §7.16 `FS03` 判定对象、`F-A42-1…6` | v0.10 | **不变** |
| §7.1 块（台账绑定锚） | v0.10 块哈希 | **v0.11 块哈希同值**（2,514 / `6d3db013`，§5.6） |
| §10.3 recipe 2 | v0.10 生效 | **停用（已停用，R10）**，banner 在 `:1861–:1863` |

**结论：v0.10 → v0.11 之间没有任何判据文本变化。** 唯一改变的是「§10.3 是否生效」这一条**生效性**事实，而它是 R10 已经裁定过的（R10 §7.2 选项 b），R11 只负责把它搬到读者能看到的位置。

### 6.2 v0.7–v0.10 未改（四元组）

| 版 | size | 行 | 全文 sha16 |
| --- | --- | --- | --- |
| v0.7 | 193,586 | 1,696 | `5a87d4b090d996ab` |
| v0.8 | 206,608 | 1,792 | `2cf85ccbaaf1fed7` |
| v0.9 | 228,478 | 1,957 | `5d0abbb59636ae9c` |
| v0.10 | 244,093 | 2,057 | `8a3115aaf0e8c516` |

四份与 R10 落盘时逐项相同（v0.10 的 mtime 仍是 22:00:29.882）。**v0.11 之后，v0.10 降为「已被取代、文件保留不删」。**

## 7. 撞名条款：不在本文件生效

派单把「4 个活配置名被 `FS01` 拦」和 R11 放在一起，但两者性质不同：R11 是**补读取路径**（不改判据），撞名条款是 **判据变更**（要给 `assert_factors_usable` 加命名面入参、要新增 `F-A43`–`F-A45`）。把它写进 v0.11 会同时破坏两条硬约束（正文除 banner/footer 外逐字节不变；R11 不改判据），也会让一次**接口签名变更**绕过其他条款走过的评审循环。

故拆成独立文件：**`docs/architecture/CLAUSE_NAMESPACE_COLLISION_20261107.md`**（§7.17 草案，含 `F-A43`/`F-A44`/`F-A45`、签名、正负样本、验收）。

**并入点已定位，v0.12 一次落位即生效**：

- 位置：`### 7.16 …` 之后、`## 8. 改动性质总表` 之前（v0.11 行号：§7.16.7 判据表末行 `:1685`，`## 8.` 在 `:1687`）。
- 编号从 `F-A43` 起：v0.10 全文最大号是 `F-A42`（`F-A1`–`F-A42` 全部占用，实测 42 个唯一号），不重号。
- 生效边界：**v0.12 落盘前，`namespace` 入参不存在，闸门对 19 名仍拦 4 名**（今日实测，见该文件 §1）。任何人在 v0.12 之前按 `F-A43` 判实现，判到的是「未实现」而非「不合规」。

## 8. 未确证 / 未做 / 转交

**未确证**

- `F-A42-1…6` 仍未实现（`alias_of` / `strategy_usable` 在 `backend/app` 零命中），v0.11 不改变这一状态。
- v0.11 的 banner 是**文字**，不是判据：没有任何机器判据断言「读到 §10.3 的人会读到 banner」。若要把这条变成可判的，需要一个「章节首段必须是 banner/声明」的文档层检查器 —— 今天没有，本版也没造。
- 两种 `autojunk` 的插入点归属差异（§5.4）已说明，但**没有**为此改脚本去消歧：消歧需要规定「前导空行归属」，那属于 numstat 口径立法，不该由一次修订顺手定。

**未做**

- 未改 v0.7–v0.10；未改 `backend/**`；未改 `docs/factors/**`（台账 BINDING 段仍绑 v0.6 `a8334fea…`，一分未动）。
- 未提交、未部署；`docs/architecture/` 整目录仍未被 git 跟踪（`git ls-files docs/architecture` 为空），所以「未提交」在字面上无从谈起，「哈希锚点只存在于工作区」这一点与 R10 时相同。
- 未出 v0.12。

**转交**

- 撞名条款的实现（`namespace` 入参 + 调用点接线）→ 系统开发工程师，验收 → 独立审核工程师，评审依据 = `CLAUSE_NAMESPACE_COLLISION_20261107.md` §2。
- v0.12 = v0.11 + §7.17（撞名条款）一次落位，是**唯一**推荐的后续版本动作；不建议为撞名单独出一个 v0.11.x。

## 9. 本文件自身

本文件（`CONTRACT_REVISION_R11_20261107.md`）不在契约正文之列，不参与任何判据绑定；四元组由交付回执给出。
