# -*- coding: utf-8 -*-
"""v0.7 -> v0.8：现状事实原位更正（算子数 25 -> 29）+ notes 出 digest 裁定。

原则：判据编号与语义、§7.1 八行公式、ewm 裁定语义一字不动。
所有断言先行；任一失败不落盘。
"""
import re, hashlib, difflib, json, copy, random, datetime
from pathlib import Path

ROOT = Path(r"C:/work/sourcecode/tick-stock-panel")
V07 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md"
V06 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md"
V08 = ROOT / "C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_v08.md"
R8  = ROOT / "C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_r8.md"
DSL = ROOT / "backend/app/factors/dsl.py"
ART = ROOT / "docs/architecture/evidence/referenced_factor_inventory.json"

READ_AT = "2026-11-07 21:00"          # Asia/Shanghai，本机实测时刻（该时刻 dsl.py sha 与下同）
DSL_SHA = "49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b"
DSL_BYTES = 36785
DSL_LINES = 850
DSL_MTIME = "2026-11-07 18:37:48"

# ---------------------------------------------------------------- 底本核验
raw = V07.read_bytes()
assert len(raw) == 193586, len(raw)
assert hashlib.sha256(raw).hexdigest() == "5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8"
text = raw.decode("utf-8")
L = text.splitlines(keepends=True)
L_ORIG = list(L)
assert len(L) == 1696, len(L)
assert L[0].startswith("# 因子化引擎与生产侧执行器")

# ---------------------------------------------------------------- 代码事实
dsl_raw = DSL.read_bytes()
assert len(dsl_raw) == DSL_BYTES, len(dsl_raw)
assert hashlib.sha256(dsl_raw).hexdigest() == DSL_SHA

import subprocess
py = str(ROOT / "backend/.venv/Scripts/python.exe")
probe = (
    "import sys; sys.path.insert(0,'backend');"
    "from app.factors import dsl as m;"
    "print(len(m.OPERATORS), len(m.TS_OPERATORS), len(m.CROSS_OPERATORS));"
    "print(sorted(m.CROSS_OPERATORS));"
    "print([m.compile_formula(t).ok for t in ('xs_rank_pool(close, close>0)','xs_rank_market(close)','xs_rank_pct(close, close>0)','xs_mean(close, close>0)')]);"
    "print([e.code for e in m.compile_formula('ewm(close,14)').errors]);"
    "print([e.code for e in m.compile_formula('xs_rank_pool(close, 1)').errors]);"
    "print(sorted(m.XS_OPERATORS));"
    "print([m.compile_formula(t).cross_sectional for t in ('xs_rank_pool(close, close>0)','xs_rank_market(close)','xs_rank_pct(close, close>0)','xs_mean(close, close>0)')])"
)
out = subprocess.run([py, "-c", probe], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
assert out.returncode == 0, out.stderr[-800:]
rows = out.stdout.strip().splitlines()
n_all, n_ts, n_cross = (int(x) for x in rows[0].split())
assert (n_all, n_ts, n_cross) == (29, 13, 3), rows[0]
assert rows[1].strip() == "['rank', 'winsorize', 'zscore']", rows[1]
assert rows[2].strip() == "[True, True, True, True]", rows[2]
assert rows[3].strip() == "['E002']", rows[3]
assert rows[4].strip() == "['E017']", rows[4]
assert rows[5].strip() == "['xs_mean', 'xs_rank_pct', 'xs_rank_pool']", rows[5]
assert rows[6].strip() == "[True, True, True, True]", rows[6]
PROBE_CMD = (
    'backend/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,\'backend\'); '
    'from app.factors import dsl as m; print(len(m.OPERATORS), len(m.TS_OPERATORS), len(m.CROSS_OPERATORS)); '
    'print([m.compile_formula(t).ok for t in (\'xs_rank_pool(close, close>0)\',\'xs_rank_market(close)\','
    '\'xs_rank_pct(close, close>0)\',\'xs_mean(close, close>0)\')]); '
    'print([e.code for e in m.compile_formula(\'ewm(close,14)\').errors])"'
)

# ---------------------------------------------------------------- 清单产物：digest 两种 recipe
art_raw = ART.read_bytes()
art_sha = hashlib.sha256(art_raw).hexdigest()
D = json.loads(art_raw.decode("utf-8"))
rk = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def recipe1(obj):
    q = {k: v for k, v in obj.items() if k not in {"generated_at", "repo_head", "data_root", "canonical_digest"}}
    q["records"] = sorted(q.get("records", []), key=rk)
    return hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recipe2(obj):
    q = {"schema_version": obj["schema_version"], "scanned_sources": obj["scanned_sources"],
         "records": sorted(obj.get("records", []), key=rk)}
    return hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


d_stored = D["canonical_digest"]
d_r1 = recipe1(D)
d_r2 = recipe2(D)
assert d_r1 == d_stored, (d_r1, d_stored)          # recipe 1 现自洽

d_notes = copy.deepcopy(D)
d_notes["notes"] = [str(x) + " " for x in D["notes"]]
d_verdict = copy.deepcopy(D)
for rec in d_verdict["records"]:
    if rec.get("verdict") == "allow":
        rec["verdict"] = "block"
        break
d_shuf = copy.deepcopy(D)
random.seed(7)
random.shuffle(d_shuf["records"])
d_summary = copy.deepcopy(D)
SUM_ORIG = D["summary"]["live_config"]["records"]
d_summary["summary"]["live_config"]["records"] = 999

S = {
    "notes":   (recipe1(d_notes),   recipe2(d_notes)),
    "verdict": (recipe1(d_verdict), recipe2(d_verdict)),
    "shuffle": (recipe1(d_shuf),    recipe2(d_shuf)),
    "summary": (recipe1(d_summary), recipe2(d_summary)),
}
assert S["notes"][0] != d_r1 and S["notes"][1] == d_r2
assert S["verdict"][0] != d_r1 and S["verdict"][1] != d_r2
assert S["shuffle"][0] == d_r1 and S["shuffle"][1] == d_r2
assert S["summary"][0] != d_r1 and S["summary"][1] == d_r2
ART_META = dict(bytes=len(art_raw), sha=art_sha, records=len(D["records"]),
                stored=d_stored, gen=D.get("generated_at"), schema=D.get("schema_version"),
                scanned=D.get("scanned_sources"), notes_n=len(D["notes"]))

# ---------------------------------------------------------------- 8 处逐行替换
changes = []


def setline(no: int, new: str):
    i = no - 1
    old = L[i]
    assert old != new, f"line {no}: unchanged"
    changes.append((no, old, new))
    L[i] = new


# 1) H1
setline(1, "# 因子化引擎与生产侧执行器 —— 接口契约 v0.8（2026-11-07）\r\n")

# 2) §3.5 纯新增算子
o = L[401]
assert "`OPERATORS`" in o and "`rank`" in o
setline(402,
        "- **纯新增算子**：`rank` / `zscore` / `winsorize` 签名与语义不变；§3（E2）增三个键、§4（E1 `xs_mean`）再增一个，"
        "**本批合计四键**，`OPERATORS` 由 25 增至 **29**（现状见 §10.1：读取时刻 2026-11-07 21:00、`dsl.py` 36,785 B / sha `49f3a110…`）。\r\n")

# 3) §8 E2 落点行（第 4 列改写）
o = L[1576]
assert o.startswith("| E2") and "`xs_rank_market`" in o and "`E017`" in o
body = o.rstrip("\r\n")
cells = body.split("|")
assert len(cells) == 6, len(cells)
cells[4] = (" 纯新增三个算子键（**本节只数 E2 的三个**）；与 §4（E1）`xs_mean` 合计 **四** 键，`OPERATORS` 25 → **29**（§10.1）。"
            "`rank`/`zscore`/`winsorize` 不变；需新增错误码 `E017`（**已落地**，实测 `xs_rank_pool(close, 1)` → `E017`）；"
            "`xs_rank_market` 在**算子键层**独立成键并计入 `len(OPERATORS)==29`（原「不重复计数」仅指该层，已不成立）；"
            "**因子台账层不变**：仍 `numeric_alias_of = rank`、与 `rank` 合计算 1 个因子（§3.2.2 / §3.6），两层不得互相援引 ")
setline(1577, "|".join(cells) + "\r\n")

# 4) §8.1 D2 行：实测 25 -> 29（切片替换，锚点全 ASCII）
o = L[1581]
s = o.find("`dsl.py#OPERATORS`")
e = o.find("**无 `ewm`")
assert 0 < s < e, (s, e)
setline(1582,
        o[:s]
        + "`dsl.py#OPERATORS` 实测 **29** 个键（`len(OPERATORS)==29`；读取时刻 2026-11-07 21:00，锚点 `dsl.py` 36,785 B / sha `49f3a110…`；"
          "= 原 25 键 + §3（E2）三键 + §4（E1）`xs_mean`），"
        + o[e:])

# 5) §8.1 ewm 否决行：保持 25 键 -> 现状 29 键不改动
o = L[1582]
s = o.find("`app/factors/dsl.py#OPERATORS`")
e = o.find("`ewm(...)`")
assert 0 < s < e, (s, e)
setline(1583,
        o[:s]
        + "`app/factors/dsl.py#OPERATORS`（**不改动现状 = 29 键**：25 + §3（E2）三键 + §4（E1）`xs_mean`；"
          "`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 亦均未变，见 §10.1）；策略侧仍不能用 DSL 写 "
        + o[e:])

# 6) §8.1 裁定段：现有 25 个键 -> 29；并把「写 26 差 1」的旁注降为历史读数
o = L[1591]
s = o.find("`app/factors/dsl.py#OPERATORS`")
e = o.find("**无 `ewm`")
assert 0 < s < e, (s, e)
mid = (o[:s]
       + "`app/factors/dsl.py#OPERATORS` 现有 **29** 个键（`len(OPERATORS)==29`；读取时刻 2026-11-07 21:00、"
         "`dsl.py` 36,785 B / sha `49f3a110…`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3），"
       + o[e:])
k = mid.find("`F_CLASS_REGISTRATION_20261107.md:224`")
assert k > 0
lb = mid.rfind("（", 0, k)
rb = mid.find("）", k) + 1
assert 0 < lb < k < rb
mid = mid[:lb] + "（旧读数 25、以及因子工程师文档「26」与实测的差 1，均属 2026-11-07 18:03 前的计数；已在 §10.1 统一更正，结论不变：没有 ewm。）" + mid[rb:]
assert mid.count("（") == mid.count("）"), (mid.count("（"), mid.count("）"))
setline(1592, mid)

# 7) §8.1 否决方案表：基线 25→26 更正为 29→30（语义仍是「否决」）
o = L[1652]
assert "`OPERATORS` 25→26" in o, o[:80]
setline(1653, o.replace("`OPERATORS` 25→26", "`OPERATORS` **29→30**"))

# ---------------------------------------------------------------- §10 正文
SEC10 = [
    "---",
    "",
    "## 10. 现状事实更正与签认口径（v0.8 新增，R8）",
    "",
    "**本版偏离「只追加」，原因与边界必须先读**：v0.8 = v0.7 逐字节为底 + **8 处逐行替换**（H1 与 footer 各 1、正文 6；**0 处删除**；old/new 全文见 `C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_r8.md` §1）+ 新增本节 + §9 加 1 行。",
    "",
    "偏离理由：v0.7 把「`OPERATORS` 25 键」写成**当前实测**。该读数在 18:03 落盘时成立（工作树 `dsl.py` 与 HEAD 一致，HEAD 版 `len(OPERATORS)==25`）；**18:37:48** E1/E2 实现落地（`git diff --numstat` → `+108/−12`，新增四键与 `E017`）后静默过期。于是一份已流通文档里同时存在「§3/§8 授权增 4 键」与「现状 25 键」，按它做验收的人会以 25 判 29 —— 两边都不算错，但判定必然错。",
    "",
    "**追加修不了这个错**：把 29 写在 25 之后，25 仍在同一份已签文档里，读者可能只读前一处。故本版采用「**判据不动 + 现状事实原位更正**」的修订模式，并逐行留 old/new 供审。判据编号与语义、§7.1 八行公式、`ewm` 裁定语义**一字未动**（§10.5 给逐块哈希）。",
    "",
    "### 10.1 算子数现状（唯一口径，必须带锚点）",
    "",
    "读取时刻 **" + READ_AT + "（Asia/Shanghai）**；锚点 `backend/app/factors/dsl.py` **%d B / %d 行 / sha256 `%s` / mtime %s**。" % (DSL_BYTES, DSL_LINES, DSL_SHA, DSL_MTIME),
    "",
    "| 项 | 实测 | 说明 |",
    "| --- | --- | --- |",
    "| `len(OPERATORS)` | **29** | = 原 25 键 + §3（E2）三键 + §4（E1）一键 |",
    "| `TS_OPERATORS` | **13** | v0.5 起即为 13，本批未变 |",
    "| `CROSS_OPERATORS` | **3** | `rank` / `winsorize` / `zscore`，本批未变 |",
    "| 本批新增 4 键 | `xs_rank_pool` / `xs_rank_market` / `xs_rank_pct`（§3 E2）· `xs_mean`（§4 E1） | 四者**各自独立计入** `OPERATORS`（29 已含全部四个）；v0.7 的「`xs_rank_market` 不重复计数」只指**算子键层**，与实现不符，已原位更正（R8 §1 第 3 处）。**因子台账层不受影响**：`numeric_alias_of = rank`、与 `rank` 合计算 1 个（§3.2.2 / §3.6）|",
    "| `XS_OPERATORS` | `{xs_rank_pool, xs_rank_pct, xs_mean}` | 需布尔掩码的第 2 参，下标表 `XS_MASK_ARG_INDEX` 三者均为 1 |",
    "| `XS_ALL_OPERATORS` | 7 键 = 上述三者 ∪ `{rank, zscore, winsorize, xs_rank_market}` | 全部 `cross_sectional=True`（实测），仍受 `E009` 约束：不得嵌进时序窗口 |",
    "| `E017` | **已落地** | 掩码参非布尔即 `E017`（实测 `xs_rank_pool(close, 1)` → `E017`）；v0.7 写「需新增」为计划态，现为实现态 |",
    "| `ewm` | **仍 `E002`** | 实测 `ewm(close,14)` → `E002 未知函数: ewm`；`F-A13` 未破，§8.1 的「否决扩算子」裁定不变 |",
    "",
    "生成上表的命令（逐字执行；`backend/.venv` 内已装 `polars`）：",
    "",
    "```bash",
    "cd /c/work/sourcecode/tick-stock-panel",
    "wc -c -l backend/app/factors/dsl.py && sha256sum backend/app/factors/dsl.py",
    PROBE_CMD,
    "```",
    "",
    "**规则（治的是这一类，不是这一条）**：本契约中任何**现状计数类事实**（算子数、键数、字段数、记录数、条数）必须同时带 ①读取时刻 ②被计数文件的 sha256 ③生成它的那一条命令。缺任一项，只能表述为「历史读数（时刻）」并注明「不得作现状基线」。**计数永不写成判据**：判据只判语义（如 `F-A13`：`ewm` 在编译期返回 `E002`），否则每次合法扩算子都会误判。",
    "",
    "### 10.2 八处替换一览（全文见 R8 §1）",
    "",
    "| # | 位置 | 原句（要旨） | 改后（要旨） |",
    "| --- | --- | --- | --- |",
    "| 1 | H1 标题 | 契约 **v0.7** | 契约 **v0.8** |",
    "| 2 | §3.5 兼容性 | 「`OPERATORS` **只增三个键**」 | §3 三键 + §4 一键 = **本批四键**，25 → **29**，带锚点 |",
    "| 3 | §8 E2 落点行 | 「纯新增三个算子键…`xs_rank_market` 登记为数值别名（**不重复计数**）」 | 本节只数 E2 三键、合计四键 25→29；`xs_rank_market` 在**算子键层**独立计数（29 已含它），「不重复计数」在该层作废；**因子台账层仍 `numeric_alias_of = rank` 合计算 1 个**；`E017` 已落地 |",
    "| 4 | §8.1 D2 行 | 「`dsl.py#OPERATORS` 实测 **25** 个键（`len(OPERATORS)==25`）」 | 实测 **29** 个键 + 读取时刻 + `dsl.py` sha |",
    "| 5 | §8.1 `ewm` 否决行 | 「不落 `#OPERATORS`（保持 **25** 键…）」 | 「**不改动现状 = 29 键**…」，`ewm` 裁定语义不变 |",
    "| 6 | §8.1 裁定段 | 「现有 **25** 个键」+「因子工程师写 26，差 1」 | 现有 **29** 个键 + 锚点；旧读数 25/26 降为「18:03 前计数」 |",
    "| 7 | §8.1 否决方案表 | 「`OPERATORS` 25→26」 | 「`OPERATORS` **29→30**」（仍是**否决**，语义不变） |",
    "| 8 | footer | v0.7 版本与正文 sha | v0.8 版本、正文前缀 sha、v0.7 冻结为 18:03 快照 |",
    "",
    "### 10.3 `notes` 是否进 canonical digest：**不进**；§7.12.4 由「剔除清单」升级为「载荷白名单」（recipe 2）",
    "",
    "**事实（本机实测，锚点：产物 `%d B` / 全文 `%s…` / `records` %d / 落盘 `canonical_digest` = `%s…`，生成于 `%s`）**：按 §7.12.4 原文（recipe 1，剔 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键）复算，与落盘值**逐位相等** —— 即 recipe 1 目前自洽，问题不在算错，在**绑定面**。" % (ART_META["bytes"], ART_META["sha"][:8], ART_META["records"], ART_META["stored"][:8], ART_META["gen"]),
    "",
    "| 扰动 | recipe 1（含 `notes`，现 §7.12.4） | recipe 2（白名单，本节） |",
    "| --- | --- | --- |",
    "| `notes` 每条尾加 1 个空格 | **变**（`%s…`） | **不变** |" % S["notes"][0][:8],
    "| 改 `summary.live_config.records`（%d → 999） | 变（`%s…`） | 不变 |" % (SUM_ORIG, S["summary"][0][:8]),
    "| `records` 随机重排（`seed=7`） | 不变 | 不变 |",
    "| 改 1 条 `verdict`（`allow`→`block`） | 变（`%s…`） | **变**（`%s…`） |" % (S["verdict"][0][:8], S["verdict"][1][:8]),
    "",
    "**裁定：不进。** 签认对象必须只绑定**被判的事实**。`notes` 是散文（当前为 %d 条人类说明的数组），改一个标点就换签认值 —— 这会把「谁签了什么」变成「谁的错别字先改」，等于给签认装了一个随机源。同一理由适用于 `summary` / `stale_count`：它们是 `records` 的派生量，一致性由 `F-A35` 单独判，不应进签认指纹。" % ART_META["notes_n"],
    "",
    "**recipe 2 定义（`canonical_digest_recipe = \"2\"`，本版起新产物必须用它）**：载荷 = `{schema_version, scanned_sources, records[]}`，仅此三项；`records` 逐条按 `json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))` 排序后整体 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))`，UTF-8 编码取 sha256。",
    "",
    "- 载荷**之外**（不是「剔除」而是「不进载荷」）：`generated_at` / `repo_head` / `data_root`（时点与机器）、`notes`（散文）、`summary` / `stale_count`（派生）、生成器版本串、`canonical_digest` 自身（自指）、`canonical_digest_recipe` 自身。",
    "- 理由：黑名单每加一个字段就是一次判据变更，且总有漏；白名单一次定义完，之后新加的顶层字段自动落在载荷外。",
    "- **recipe 1 = §7.12.4 原文，保留为历史定义，一字不改**；已公布值不失效：`184e4728…`（17:27 产物）、`9d34fef7…`（17:10 产物）、`%s…`（本产物）均按 recipe 1 发布，判据口径不变。**但前两个已不可复验** —— 两份产物已被 19:23:55 重生成覆盖，盘上无原文件；本产物（19:23:55）按 recipe 1 复算逐位相等，是本轮唯一可复算的锚点。" % d_r1[:8],
    "- 新增顶层字段 `canonical_digest_recipe`（取值 `\"1\"`/`\"2\"`；**缺省按 `\"1\"` 读**，向后兼容）。签认对象由三元组升为**四元组**：`(canonical_digest_recipe, canonical_digest, schema_version, scanned_sources)`。",
    "- 比对规则（`F-A22`）：两侧 `recipe` 相同才比；不同报「**不可比**」，**不得判失败**。L2 起产物必须 `\"2\"`。",
    "- 判据边界：本节是**一次判据变更**（`F-A36` 的「剔除项清单」→「载荷白名单」+ recipe 版本化）。`F-A36` 的**编号与主语义未变**：唯一 canonical digest 是签认对象、旁挂 `.sha256` 不是。",
    "- 代价（写明）：已有 recipe 1 产物需按 recipe 2 重算才能进 L2；跨 recipe 不直接可比；`summary` 正确性从此完全依赖 `F-A35`，signature 不再兜底它。",
    "",
    "### 10.4 v0.7 的冻结状态，与本版的关系",
    "",
    "- **v0.7 已流通**（`193,586 B / 1,696 行 / 全文 5a87d4b0…`，18:03:23），外部已引用该四元组。原地改 v0.7 会造成「同一路径、同一版本号、两种字节」，故：",
    "  - **v0.7 冻结为 2026-11-07 18:03 快照**：文件保留、不删、不再写入，四元组固定；引用状态改为「已被 v0.8 取代」；其 `F-A30`–`F-A41` 相关判定对象不变。",
    "  - **v0.8（本文件）为操作版**；此后一切「现状」以本文件 §10.1 为准。",
    "- **v0.6 及更早不更正**：作为 17:16 前的历史读数原样保留；其中的「25 键」**不得再作现状基线**。",
    "- **v0.5、v0.4 一字未改**；`F-A5` 的数字锚点仍取 v0.4 四元组。",
    "",
    "### 10.5 未动面的哈希证明（替换前后**逐字节相等**，非仅哈希相等）",
    "",
    "| 块 | LF 归一 | CRLF 保留 | 结论 |",
    "| --- | --- | --- | --- |",
    "| §7.1 八行公式 | `2,514` 字符 / `6d3db0139a45f54c` | `2,541` 字符 / `a8e88134f60b504c` | 与 v0.6、v0.7 **同**（两种口径各自相等） |",
    "| §7.9 / §7.11 / §7.12 / §7.13 / §7.14 / §7.15 | — | 逐字节相等 | 见 R8 §5 的块哈希表 |",
    "",
    "两种口径说明：**LF 归一**（`\\r\\n`→`\\n`，含小节标题、含尾随空行）与**CRLF 保留**（原字节）是既有两套读数，互不替代；引用时必须写明是哪一种。`6d3db013…` = LF 归一口径，`a8e88134…` = CRLF 口径，**两者都对**。",
    "",
    "全章节审计（机器比对，非目测）：v0.7 的 **115** 个二至四级小节中，**111 个逐字节相等**；**4 个改动** —— `§3.5`（兼容性：四键/29）、`§8`（E2 落点行）、`§8.1`（D2 行 + `ewm` 否决行 + 裁定段）、`§9`（加 1 行 R8 行）；另新增 §10 的 7 个小节。逐块哈希见 R8 §5。",
    "",
    "### 10.6 对清单 v2 的影响与未确证",
    "",
    "- 无新增判据编号；`F-A34`–`F-A39` 语义不变。产物若带 `canonical_digest` 而无 `canonical_digest_recipe`，按 recipe 1 读（向后兼容）；L2 起必须显式 `\"2\"`。",
    "- **未确证**：①`E1/E2` 实现与 §3/§4 判据（`XS-A*`/`XS-B*`/`XS-C*`、`B1`/`B2`）的一致 **未验**，归独立审核；②`xs_rank_*` 与 `rank` 的数值关系（`xs_rank_market` 是否真等价 `rank`）**未逐位验**；③`E009` 对四新键的行为只读了代码分支（`dsl.py:738`），未构造嵌入用例实跑；④§10.1 的 29/13/3 是**导入模块实测**，未覆盖其他模块是否另有算子白名单（如矩阵路径 `_MATRIX_COMPUTED_FEATURES`）。",
]

# 插入位置：原 line 1693（空行）之后、尾部 "---" 之前；首尾各留一空行，避免 setext 标题解析
blk = []
for s in SEC10:
    blk.append(s + "\r\n")
blk.append("\r\n")
L[1693:1693] = blk

# ---------------------------------------------------------------- §9 加 1 行
ROW9 = ("| **R8（现状事实原位更正 + `notes` 出 digest）** | 见 `C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_r8.md`："
        "**8 处逐行替换** —— 算子数 25 → **29**（= 25 + §3 E2 三键 + §4 E1 `xs_mean`；读取 2026-11-07 21:00、"
        "`dsl.py` 36,785 B / sha `49f3a110…`）；`xs_rank_market` 在算子键层独立计数（「不重复计数」仅该层作废，因子台账层仍与 `rank` 合计算 1 个）；"
        "`E017` 由「需新增」改为已落地；新增 §10；`canonical_digest` 由「剔 4 键」（recipe 1）升为**载荷白名单**"
        "（recipe 2：`notes`/`summary`/`stale_count` 不进载荷）+ 新增 `canonical_digest_recipe`，签认升为四元组。"
        "**判据编号与语义未变、§7.1 未动、v0.7 冻结为 18:03 快照** |")
L.insert(1688, ROW9 + "\r\n")

# ---------------------------------------------------------------- footer
FOOT = (
    "本文件正文 sha256：`{bsha}`（校验：`head -c {blen} \"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_v08.md\" | sha256sum`）"
    "· 正文 `{blen} B` · 行数 `{lines}` · 版本 **v0.8（2026-11-07 R8：现状事实原位更正 + digest 载荷白名单，操作版）**"
    "· 四元组（size / lines / body-prefix / full sha）见 `C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_r8.md` §7（不写进正文，避免自指）"
    "· 生成 2026-11-07 v0.8 = **v0.7 逐字节为底** + R8：**8 处逐行替换**（H1/footer 各 1、正文 6；0 删除）"
    "+ 新增 §10 + §9 加 1 行，**判据编号与语义、§7.1 八行公式、`ewm` 裁定语义一字未动**；"
    "`len(OPERATORS)==29` 等现状读数带读取时刻 21:00 与 `dsl.py` sha `49f3a110…`"
    "· **v0.7（193,586 B / 1,696 行 / 全文 `5a87d4b0…8723e8`）冻结为 2026-11-07 18:03 快照，已被本版取代**"
    "· v0.6（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）为清单 v2（`F-A34`–`F-A39`）绑定对象、降为历史版本，引用状态改「已被 v0.8 取代」，其判定对象不变"
    "· v0.5（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…c4a21a`）为 `F-A30`–`F-A33` 绑定对象"
    "· v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象"
    "· v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
)
setline(len(L), "")  # 占位，先登记为变更（footer 是最后一行）
L[-1] = ""            # 稍后按 body 计算回填

# ---------------------------------------------------------------- 组装 + 回填 footer
body_bytes = b"".join(s.encode("utf-8") for s in L[:-1])
blen = len(body_bytes)
bsha = hashlib.sha256(body_bytes).hexdigest()
nlines = len(L)
footer = FOOT.format(bsha=bsha, blen=blen, lines=nlines) + "\r\n"
L[-1] = footer
raw_new = "".join(L).encode("utf-8")
assert b"\r\r" not in raw_new, "bare CR artifact"
assert raw_new.count(b"\n") == raw_new.count(b"\r\n"), "mixed line endings"

# ---------------------------------------------------------------- 机械验证
sm = difflib.SequenceMatcher(None, "".join(L_ORIG), "".join(L), autojunk=False)
reps, ins, dele = [], 0, 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "replace":
        reps.append((i1, i2 - i1, j2 - j1))
    elif tag == "insert":
        ins += j2 - j1
    elif tag == "delete":
        dele += i2 - i1
print("opcodes char-level: replace", len(reps), "| inserted-chars", ins, "| deleted-chars", dele)

L_new = "".join(L).splitlines(keepends=True)
sm2 = difflib.SequenceMatcher(None, L_ORIG, L_new, autojunk=False)
reps2, ins2, del2 = [], 0, 0
for tag, i1, i2, j1, j2 in sm2.get_opcodes():
    if tag == "replace":
        reps2.append((i1 + 1, i2 - i1, j2 - j1))
    elif tag == "insert":
        ins2 += j2 - j1
    elif tag == "delete":
        del2 += i2 - i1
print("opcodes line-level: replace", reps2, "| inserted", ins2, "| deleted", del2)
assert del2 == 0, del2
assert sum(ni for (_l, ni, _j) in reps2) == 8, reps2
assert ins2 + sum(nj - ni for (_l, ni, nj) in reps2) == len(SEC10) + 2, reps2
# 内容级核验（不依赖 difflib 对齐）：插入块与 §9 行逐字在文本中
assert (("\r\n".join(SEC10) + "\r\n\r\n") in "".join(L))
assert (ROW9 + "\r\n") in "".join(L)

# 保护块：逐字节相等
def sections(t: str) -> dict:
    outd, cur = {}, None
    for s in t.splitlines(keepends=True):
        if re.match(r"^(#{2,4}) .+?\r?$", s):
            cur = s.strip()
            outd[cur] = []
        if cur is not None:
            outd[cur].append(s)
    return {k: "".join(v) for k, v in outd.items()}


o_sec, n_sec = sections("".join(L_ORIG)), sections("".join(L))
PROTECT = ("### 7.1 ", "### 7.9 ", "### 7.11 ", "### 7.12 ", "### 7.13 ", "### 7.14 ", "### 7.15 ", "## 6. ", "## 7. ")
block_rows = []
for key in o_sec:
    if any(key.startswith(p) for p in PROTECT):
        assert o_sec[key] == n_sec.get(key), f"protected section changed: {key}"
        b = o_sec[key]
        lf = b.replace("\r\n", "\n")
        block_rows.append((key.split("（")[0][:28], len(b), hashlib.sha256(b.encode()).hexdigest()[:16],
                           len(lf), hashlib.sha256(lf.encode()).hexdigest()[:16]))
        print("  unchanged", key[:28], "| CRLF", len(b), hashlib.sha256(b.encode()).hexdigest()[:16],
              "| LF", len(lf), hashlib.sha256(lf.encode()).hexdigest()[:16])

# §7.1 与 v0.6 同块
def sec71(p: Path):
    t = p.read_bytes().decode("utf-8")
    sec = sections(t)
    k = [x for x in sec if x.startswith("### 7.1 ")][0]
    b = sec[k]
    return len(b), hashlib.sha256(b.encode()).hexdigest()[:16], len(b.replace("\r\n", "\n")), hashlib.sha256(b.replace("\r\n", "\n").encode()).hexdigest()[:16]


v6_71 = sec71(V06)
v7_71 = sec71(V07)
new_71 = sec71(V08) if V08.exists() else None  # 尚未落盘
b71 = sections("".join(L))
k71 = [x for x in b71 if x.startswith("### 7.1 ")][0]
nb = b71[k71]
new_71 = (len(nb), hashlib.sha256(nb.encode()).hexdigest()[:16],
          len(nb.replace("\r\n", "\n")), hashlib.sha256(nb.replace("\r\n", "\n").encode()).hexdigest()[:16])
assert v6_71 == v7_71 == new_71, (v6_71, v7_71, new_71)

# ---------------------------------------------------------------- 全章节审计
EXPECTED_CHANGED = {"### 3.5 ", "## 8. ", "### 8.1 ", "## 9. "}
ch_all = [k for k in o_sec if k in n_sec and o_sec[k] != n_sec[k]]

# —— §9 块字符数差异的实测（不靠目测，且在写进 R8 前就断言）——
# v0.7 的 `## 9.` 一直切到文件末尾（含 footer）；v0.8 的 `## 9.` 后跟 `## 10.`（不含 footer）。
_sec9 = "## 9. "
_s9_o = next(v for k, v in o_sec.items() if k.startswith(_sec9))
_s9_n = next(v for k, v in n_sec.items() if k.startswith(_sec9))
_old_foot = next((ln for ln in _s9_o.split("\r\n") if ln.startswith("本文件正文 sha256")), "")
_new_foot = next((ln for ln in _s9_n.split("\r\n") if ln.startswith("本文件正文 sha256")), "")
assert _old_foot and not _new_foot, "§9 块边界的假设不成立：请重新核实 sections() 的切分"
_net = len(_s9_n) - len(_s9_o)
_add_line = len(_s9_n) - len(_s9_o.replace(_old_foot, ""))
assert _net == _add_line - len(_old_foot), (_net, _add_line, len(_old_foot))
# 只断言恒等式；数值由实测生成写入 R8，落盘后回读校验（S9_CLAIM）
assert 100 < _add_line < 1200 and len(_old_foot) > 1000, (_add_line, len(_old_foot))
S9_CLAIM = "净 **%+d 字符** = +%d（新增那 1 行）− %d（旧 footer 行）" % (_net, _add_line, len(_old_foot))
print("  §9 block: net %+d = +%d(the 1 added line) - %d(old footer); %d -> %d" % (
    _net, _add_line, len(_old_foot), len(_s9_o), len(_s9_n)))
assert all(any(k.startswith(p) for p in EXPECTED_CHANGED) for k in ch_all), ch_all
assert len(ch_all) == 4, ch_all
assert all(k in n_sec for k in o_sec), "section missing in v0.8"
unchanged_n = len([k for k in o_sec if o_sec[k] == n_sec[k]])
new_secs = [k for k in n_sec if k not in o_sec]
assert len(o_sec) == 115 and unchanged_n == 111 and len(new_secs) == 7, (len(o_sec), unchanged_n, len(new_secs))
print("  section audit: v0.7", len(o_sec), "| unchanged", unchanged_n, "| changed", len(ch_all), "| new", len(new_secs))

# ---------------------------------------------------------------- 落盘
V08.write_bytes(raw_new)
size, nl = len(raw_new), len(L)
body_b = raw_new[: len(raw_new) - len(footer.encode("utf-8"))]
assert len(body_b) == blen and hashlib.sha256(body_b).hexdigest() == bsha
full_sha = hashlib.sha256(raw_new).hexdigest()
print("WROTE", V08.name, size, "B /", nl, "lines / body", blen, bsha[:16], "/ full", full_sha)

# 独立复核（原生工具口径）
import os
from collections import Counter
st = V08.stat()
print("stat mtime", datetime.datetime.fromtimestamp(st.st_mtime).isoformat())

# ---------------------------------------------------------------- R8 对照文档
def tbl_change(no, old, new):
    return ("\n".join([
        "",
        "#### 第 %d 处（原文 line %d）" % (CH.index(no) + 1, no),
        "",
        "原文：",
        "",
        "```text",
        old.rstrip("\r\n"),
        "```",
        "",
        "改后：",
        "",
        "```text",
        new.rstrip("\r\n"),
        "```",
    ]))

CH = [c[0] for c in changes]
parts = []
parts.append("# 契约 v0.7 → v0.8 修订对照（R8：现状事实原位更正 + `notes` 出 digest）\n")
parts.append("生成时间：2026-11-07 %s（Asia/Shanghai）· 系统架构师\n" % datetime.datetime.now().strftime("%H:%M"))
parts.append("底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（**一字未改**，193,586 B / 1,696 行 / 全文 `5a87d4b090d996ab…f8723e8`，mtime 2026-11-07 18:03:23）\n")
parts.append("产物：`C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_v08.md`\n")
parts.append("\n**性质：返工一处事实陈述，不是新工程。** 本版唯一的语义变更只有一条 —— `canonical_digest` 的载荷定义（`notes` 等出 digest，recipe 1 → recipe 2，见 §4），这是派单明确点名要架构侧裁定的判据变更。其余 7 处替换全是**现状事实**与代码对齐。**§7.1 八行公式、`ewm` 裁定语义、所有判据编号与语义一字未动。**\n")
parts.append("\n## 1. 八处逐行替换（逐字原文 / 改后；0 处删除）\n")
_BRK = " + ".join("%d 段 %d→%d" % (c, ni, nj) for (ni, nj), c in
                    sorted(Counter((ni, nj) for (_l, ni, nj) in reps2).items()))
_SENT = ("机械验证（`difflib.SequenceMatcher`，行级，行按 `splitlines(keepends=True)`）："
        "**replace %d 段 = %s**、**insert %d 行**（§9 新增行）、**delete 0 行**；"
        "净 **+%d 行**（%d → %d）。**8 行原文 → 8 行位置分属 7 段**：其中 1 段是 **2 行同时改**（§8.1 相邻两行），故行数 8 而段数 7；另 1 段右端为 96 行（旧 footer 行 → §10 全节 + 新 footer）。")
parts.append("\n" + _SENT % (len(reps2), _BRK, ins2, len(L_new) - len(L_ORIG), len(L_ORIG), len(L_new)) + "\n")
for (no, old, new) in changes:
    parts.append(tbl_change(no, old, new))
parts.append("\n## 2. numstat 与结构\n")
parts.append("\n| 项 | 值 |\n| --- | --- |\n")
parts.append("| 底本 | 193,586 B / 1,696 行 |\n")
parts.append("| 产物 | **{:,} B / {:,} 行** |\n".format(size, nl))
parts.append("| 行级 opcodes | replace %d 段 = %s · insert **%d 行** · delete **0 行** |\n" % (len(reps2), _BRK, ins2))
parts.append("| 为何有 1→96 段 | difflib 把「旧 footer 行」与「其后新增的 §10 全节」并成同 1 个 replace 块：该块右端 = §10 的 95 行 + 新 footer 1 行。不是 96 行内容被改；§1 逐行 old/new 为准 |\n")
parts.append("| 插入明细 | §10 整节 %d 行（首空 + 分隔线 + 正文 + 尾空）+ §9 表 1 行 = **%d** 行 |\n" % (len(SEC10) + 1, len(SEC10) + 2))
parts.append("| 新增章节 | §10（§10.1 算子数现状 / §10.2 八处一览 / §10.3 `notes` 裁定 / §10.4 v0.7 冻结 / §10.5 未动面哈希 / §10.6 影响与未确证） |\n")
parts.append("\n## 3. 算子数：实测（本机，读取时刻 %s）\n" % READ_AT)
parts.append("\n锚点 `backend/app/factors/dsl.py`：**%d B / %d 行 / sha256 `%s` / mtime %s**。\n" % (DSL_BYTES, DSL_LINES, DSL_SHA, DSL_MTIME))
parts.append("\n| 项 | 实测 |\n| --- | --- |\n")
parts.append("| `len(OPERATORS)` | **%d** |\n" % n_all)
parts.append("| `len(TS_OPERATORS)` | **%d** |\n" % n_ts)
parts.append("| `len(CROSS_OPERATORS)` | **%d**（%s） |\n" % (n_cross, rows[1].strip()))
parts.append("| `XS_OPERATORS` | %s |\n" % rows[5].strip())
parts.append("| 四键可编译 | %s |\n" % rows[2].strip())
parts.append("| 四键 `cross_sectional` | %s |\n" % rows[6].strip())
parts.append("| `ewm(close,14)` | %s |\n" % rows[3].strip())
parts.append("| `xs_rank_pool(close, 1)` | %s |\n" % rows[4].strip())
parts.append("\n**时间线（这是本轮的根因，不是「写错」）**：v0.7 落盘于 18:03:23，当时工作树 `dsl.py` 与 `HEAD` 一致、`len(OPERATORS)==25`，读数**当时成立**；`git diff --numstat backend/app/factors/dsl.py` → `+108/−12`，四键与 `E017` 于 **18:37:48** 落地，该读数自此静默过期。缺陷类别是「现状实测未带读取时刻与文件 sha」，已用 §10.1 的规则治类。\n")
parts.append("\n命令：\n\n```bash\ncd /c/work/sourcecode/tick-stock-panel\nwc -c -l backend/app/factors/dsl.py && sha256sum backend/app/factors/dsl.py\n%s\n```\n" % PROBE_CMD)
parts.append("\n## 4. `notes` 是否进 digest —— 裁定：**不进**（recipe 1 → recipe 2）\n")
parts.append("\n锚点产物：`docs/architecture/evidence/referenced_factor_inventory.json` **%d B** / 全文 `%s` / `records` %d / `generated_at` `%s` / `schema_version` `%s` / `scanned_sources` %s。\n" % (ART_META["bytes"], art_sha, ART_META["records"], ART_META["gen"], ART_META["schema"], ART_META["scanned"]))
parts.append("\n落盘 `canonical_digest` = `%s`；按 §7.12.4 原文（recipe 1）复算 = `%s` → **逐位相等**；按 recipe 2 复算 = `%s`。\n" % (d_stored, d_r1, d_r2))
parts.append("\n| 扰动 | recipe 1 | recipe 2 |\n| --- | --- | --- |\n")
parts.append("| 原样 | `%s` | `%s` |\n" % (d_r1, d_r2))
parts.append("| `notes` 每条尾加 1 个空格 | `%s`（**变**） | `%s`（不变） |\n" % S["notes"])
parts.append("| 改 `summary.live_config.records`（%d → 999） | `%s`（变） | `%s`（不变） |\n" % (SUM_ORIG, S["summary"][0], S["summary"][1]))
parts.append("| `records` 随机重排（`seed=7`） | `%s`（不变） | `%s`（不变） |\n" % S["shuffle"])
parts.append("| 改 1 条 `verdict`（`allow`→`block`） | `%s`（变） | `%s`（**变**） |\n" % S["verdict"])
parts.append("\n**结论**：签认对象只绑定被判事实。`notes`（%d 条散文）/ `summary` / `stale_count` 不进载荷；`records` 与 `verdict` 必须进（改了必变，实测）。recipe 1 保留为历史定义、已公布值不失效；新增 `canonical_digest_recipe`，签认升为四元组 `(recipe, digest, schema_version, scanned_sources)`；跨 recipe 报「不可比」，L2 起必须 `\"2\"`。\n" % ART_META["notes_n"])
parts.append("\n## 5. 未动面：逐块逐字节相等（不是仅哈希相等）\n")
parts.append("\n| 块 | CRLF 字符数 | CRLF sha16 | LF 字符数 | LF sha16 |\n| --- | --- | --- | --- | --- |\n")
for (nm, cb, ch, lb, lh) in block_rows:
    parts.append("| `%s` | %d | `%s` | %d | `%s` |\n" % (nm, cb, ch, lb, lh))
parts.append("\n§7.1 与 v0.6、v0.7、v0.8 三处**同块**：CRLF `%d`/`%s`，LF `%d`/`%s`（与派单口径 `2,514`/`6d3db013…` = **LF 归一**一致；`a8e88134…` = **CRLF 保留**）。\n" % (v6_71[0], v6_71[1], v6_71[2], v6_71[3]))
parts.append("\n**全章节审计**（机器比对，非目测）：v0.7 共 **%d** 个二至四级小节，其中 **%d 个逐字节相等**、**%d 个改动**、另新增 **%d** 个（§10 及其 6 个子节）。改动集合经断言等于预期集合 `{§3.5, §8, §8.1, §9}` —— 多一个就会抛断言、不落盘。\n" % (len(o_sec), unchanged_n, len(ch_all), len(new_secs)))
parts.append("\n| 改动小节 | v0.7 字符 / sha8 | v0.8 字符 / sha8 | 原因 |\n| --- | --- | --- | --- |\n")
# §9 的字符数差异必须解释清楚：v0.7 的 `## 9.` 是最后一个二级小节，按 sections() 的切分规则
# 它一直延伸到文件末尾、**含 footer 那一行**；v0.8 的 `## 9.` 后面紧跟新增的 `## 10.`，故不含 footer。
# 所以 4525 → 3797 是「+1 行(705 字符) − 旧 footer(246 字符)」的净结果，不是「删了很多」。
REASON = [("### 3.5 ", "§3.5 四键 / 29"), ("## 8. ", "§8 E2 落点行"), ("### 8.1 ", "§8.1 三处（D2 / `ewm` 否决 / 裁定段）"), ("## 9. ", "§9 加 1 行 + footer 换行（该块 v0.7 含 footer / v0.8 不含；" + S9_CLAIM + "，非「删内容」）")]
for k in ch_all:
    why = next(w for (p, w) in REASON if k.startswith(p))
    parts.append("| `%s` | %d / `%s` | %d / `%s` | %s |\n" % (
        k.split("（")[0][:34], len(o_sec[k]), hashlib.sha256(o_sec[k].encode()).hexdigest()[:8],
        len(n_sec[k]), hashlib.sha256(n_sec[k].encode()).hexdigest()[:8], why))
parts.append("\n## 6. v0.7 的冻结状态（明确回答）\n")
parts.append("\n| 问题 | 回答 |\n| --- | --- |\n")
parts.append("| v0.7 是否升 v0.8 | **是**。不原地改 v0.7：它已于 18:03 流通（193,586 B / `5a87d4b0…`），原地改会造成「同一路径同版本号两种字节」 |\n")
parts.append("| v0.7 当前冻结状态 | **冻结为 2026-11-07 18:03 快照**：文件保留、不删、不再写入、四元组固定；引用状态「已被 v0.8 取代」；`F-A30`–`F-A41` 判定对象不变 |\n")
parts.append("| v0.8 是否操作版 | **是**。此后「现状」一律以 §10.1 为准 |\n")
parts.append("| v0.6 / v0.5 / v0.4 | v0.6 不更正（历史读数，其「25 键」不得再作基线）；v0.5、v0.4 一字未改，`F-A5` 锚点仍 v0.4 |\n")
parts.append("\n## 7. 四元组（v0.8，原生工具复算）\n")
parts.append("\n```bash\ncd /c/work/sourcecode/tick-stock-panel\nF=C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro/repro_v08.md\nwc -c -l \"$F\"                       # %d %d\nhead -c %d \"$F\" | sha256sum         # %s\nsha256sum \"$F\"                      # %s\n```\n" % (nl, size, blen, bsha, full_sha))
parts.append("\n| 项 | 值 |\n| --- | --- |\n")
parts.append("| size | **{:,} B** |\n| 行数 | **{:,}** |\n| 正文前缀 | `head -c {}` → **`{}`** |\n| 全文 | **`{}`** |\n| 读取/落盘时刻 | 2026-11-07 {}（Asia/Shanghai） |\n".format(size, nl, blen, bsha, full_sha, datetime.datetime.now().strftime("%H:%M:%S")))
assert "%d" not in parts[-1] and "%s" not in parts[-1], parts[-1]
parts.append("\n## 8. 未确证（不圆）\n")
parts.append("\n- `E1/E2` 实现与 §3/§4 判据的逐条一致 **未验**（归独立审核）；`xs_rank_market` 与 `rank` 的数值等价 **未逐位验**。\n")
parts.append("- `E009`（截面算子不得嵌入时序窗口）对四个新键只读了分支（`dsl.py:738`），**未构造嵌入用例实跑**。\n")
parts.append("- §10.1 的 29/13/3 是**导入模块**实测，**未穷举**其他算子白名单（如矩阵路径 `_MATRIX_COMPUTED_FEATURES`）。\n")
parts.append("- recipe 2 只在本机对**单个产物**验证过；未验证其他产物（期望表 `referenced_factor_inventory_expected_20261107.json`）的情况。\n")
parts.append("- 本轮**未**改 `backend/**`、`docs/factors/**`、`docs/research/**`；未 add、未提交、未部署；`gate.py` 未创建。\n")
_r8_txt = "".join(parts).replace("\r\n", "\n").replace("\n", "\r\n")
R8.write_text(_r8_txt, encoding="utf-8", newline="")
r8b = R8.read_bytes()
assert b"\r\r" not in r8b, "bare CR artifact in R8"
assert r8b.count(b"\n") == r8b.count(b"\r\n"), "mixed line endings in R8"
print("WROTE", R8.name, len(r8b), "B /", r8b.count(b"\n"), "lines / sha", hashlib.sha256(r8b).hexdigest()[:16])
_r8s = r8b.decode("utf-8")
assert S9_CLAIM in _r8s, "§9 分解未落进 R8"
assert _BRK in _r8s, "opcode 明细未落进 R8"
assert ("**replace %d 段 = %s**" % (len(reps2), _BRK)) in _r8s
print("R8 readback OK:", S9_CLAIM, "|", _BRK)
assert "%d" not in _r8s and "%s" not in _r8s, "R8 残留未替换占位符"
print("TRIPLE v0.8:", size, nl, blen, bsha, full_sha)
