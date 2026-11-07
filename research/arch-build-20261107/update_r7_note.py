# -*- coding: utf-8 -*-
"""把 R7 说明文件从「候选未落盘」更新为「已落盘」，并补记四处并入。

只改 CONTRACT_REVISION_R7_20261107.md 自己；不碰任何契约文件。
footer 自指 sha / 字节 / 行数按改后正文重算。
"""
from __future__ import annotations
import hashlib, os, re, subprocess, sys

ROOT = r"C:\work\sourcecode\tick-stock-panel"
P = os.path.join(ROOT, "docs", "architecture", "CONTRACT_REVISION_R7_20261107.md")
MARK = "本文件正文 sha256："
NAME = "docs/architecture/CONTRACT_REVISION_R7_20261107.md"

V07_PATH = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md"
V07_BYTES = 193073
V07_LINES = 1696
V07_BODY = 191420
V07_BODY_SHA = "f824cfba15f3abba91928296780c1210779d6628d882fcff8167cf09590c3c01"
V07_FULL_SHA = "f7b6adb2bd8f35b3cf470e56c8092a309bbdd28229b25c30d39bc24ce3002908"
NUMSTAT = "+248 / −6"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def crlf(t):
    return t.replace("\r\n", "\n").replace("\n", "\r\n")


raw = open(P, "rb").read().decode("utf-8")
idx = raw.index(MARK)
body = raw[:idx]

REPL = [
    # 抬头：候选 → 已落盘
    ("- 候选产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（**未落盘**，理由见 §5；四元组见 §7.2，由 `build_contract_r7.py` 在临时副本上实测）",
     "- 产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（**已落盘 2026-11-07 17:5x**，四元组见 §7.2；并入了本批四处，见 §7.4）"),
    ("**契约文件状态：v0.3 / v0.4 / v0.5 / v0.6 一份未改；v0.7 未落盘。**",
     "**契约文件状态：v0.3 / v0.4 / v0.5 / v0.6 一份未改；v0.7 已落盘（未冻结）。**"),
    ("### 7.2 候选 v0.7（**未落盘**；数值由构建器在临时副本上实测，临时文件已删）",
     "### 7.2 v0.7（**已落盘**；下列四元组由本机原生 `wc` / `head -c` / `sha256sum` 独立复算，不取自构建器自报）"),
    ("| 总字节 | **180,002 B** |", "| 总字节 | **193,073 B** |"),
    ("| 行数 | **1,616** |", "| 行数 | **1,696** |"),
    ("| 正文前缀 | `head -c 178631` |", "| 正文前缀 | `head -c 191420` |"),
    ("| 正文 sha256 | **`071b52d6e04ccf9ea93fe04c7cb01921ae43a83e97b069d765e14b2778819425`** |",
     "| 正文 sha256 | **`f824cfba15f3abba91928296780c1210779d6628d882fcff8167cf09590c3c01`** |"),
    ("| 全文 sha256 | **`c58df54d300e6e7026ccdd8b3cb87941e72a578d810af7f7391bd5f081abbd98`** |",
     "| 全文 sha256 | **`f7b6adb2bd8f35b3cf470e56c8092a309bbdd28229b25c30d39bc24ce3002908`** |"),
    ("| `git diff --no-index --numstat`（v0.6 → 候选 v0.7） | **+165 / −3** |",
     "| `git diff --no-index --numstat`（v0.6 → v0.7） | **+248 / −6** |"),
    ("| 相对 v0.6 的净变化 | 行 1,616 − 1,454 = **+162**；字节 180,002 − 162,361 = **+17,641** |",
     "| 相对 v0.6 的净变化 | 行 1,696 − 1,454 = **+242**；字节 193,073 − 162,361 = **+30,712** |"),
    ("| **合计** | — | **+165 / −3** | 与 `numstat` 一致（162 净增 + 3 替换） |",
     "| **合计** | — | **+248 / −6** | 与 `numstat` 一致（242 净增 + 6 替换：H1 / `A7` / `B1` / `B2` / `F-A11` / footer 自指哈希） |"),
    ("| E 替换 3 行 | H1 / §8.1 `F-A11` / footer | 3 | 各自 1 进 1 出 |",
     "| E 替换 6 行 | H1 / §2.6 `A7` / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer | 6 | 各自 1 进 1 出 |"),
    ("**不改任何其它既有行**：`git diff --no-index --numstat` 应为 **+165 / −3**（3 = 三处替换行）。",
     "**不改任何其它既有行**：`git diff --no-index --numstat` 实际 **+248 / −6**（6 = 六处替换行，含本批并入的 `A7`/`B1`/`B2`）。"),
    ("| B §7.13 + §7.14 | §7.12 之后、§8 之前 | 129 | 能力清单 14 行 + 硬要求 5 条 + `F-A41` 5 条 + 否决表 + `F-A11a`–`d` |",
     "| B §7.13 + §7.14 + §7.15 | §7.12 之后、§8 之前 | 180 | 能力清单 14 行 + 硬要求 5 条 + `F-A41` 5 条 + 否决表 + `F-A11a`–`d` + §7.15 canonical 表 14 行 |"),
    ("3. `## 8. 改动性质总表` 前插 §7.13 + §7.14（锚点唯一）；",
     "3. `## 8. 改动性质总表` 前插 §7.13 + §7.14 + §7.15（锚点唯一）；"),
    ("### 6.5 合并只做 5 件事（构建器逐条断言锚点唯一）",
     "### 6.5 合并做的事（构建器逐条断言锚点唯一；落盘版含本批四处并入，共 9 件）"),
]

for a, b in REPL:
    if a not in body:
        sys.exit("替换锚点缺失: %r" % a[:70])
    body = body.replace(a, b, 1)

NEW_SECTION = crlf("""### 7.4 本批并入的四处（同一版 v0.7，不另开 R8；行号 = 落盘后 v0.7 实际行号）

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

""")

# 插到 §7.3 之后、## 8. 之前
anchor = "### 7.3 本文件（R7）四元组"
pos = body.index(anchor)
end = body.index("---", pos)
body = body[:end] + NEW_SECTION + body[end:]

# 未确证：去掉「v0.7 未落盘」相关，补两条
body = body.replace(
    "- **派单基线漂移**：派单按 v0.4 行号（`F-A11 :1198`）派发，实际现行是 v0.6（`:1421`）。我只按文本内容匹配锚点，未按行号定位，故锚点在 v0.6 上仍唯一——但排期若仍在用 v0.4 行号，需同步更新。",
    "- **派单基线漂移**：派单按 v0.4 行号（`F-A11 :1198`）派发，实际现行是 v0.6（`:1421`）。我只按文本内容匹配锚点，未按行号定位，故锚点在 v0.6 上仍唯一——但排期若仍在用 v0.4 行号，需同步更新。\n- **`B1`/`B2` 的新靶值（1,770 / 0.542252 / 87 / 0.540230）只有研究侧一只脚**：生产侧 `market_breadth` 尚未实现，我只复算了研究侧逐日值并做减法；「两侧均非 `null`」这句话在实现出来之前**无法端到端验证**。\n- **§7.15.3 的元数据实测依赖 `D:/TSP/data` 当前盘面**：`load_into_registry(Path(\"D:/TSP/data\"))` 装载 15 个定义；若盘上新增/删除定义，`192 → 207` 这两个数会变。`status`/`unit` 的结论只对今天这 15 个文件成立。",
    1,
)

# 边界：更新为「已落盘」
body = body.replace(
    "未新建契约文件；未 add、未提交、未部署；未创建 `gate.py`；",
    "未新建第三份契约文件（v0.7 是 v0.6 的追加版，不是新契约）；未 add、未提交、未部署；未创建 `gate.py`；",
    1,
)
body = body.replace(
    "新增文件只有本文与 `research/arch-build-20261107/build_contract_r7.py`（构建器，含锚点断言）。",
    "新增文件：`FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（落盘）、`research/arch-build-20261107/build_contract_r7.py`、`build_contract_r7b.py`（落盘构建器，含 8 条锚点唯一性断言 + H1 断言）。",
    1,
)

bb = body.encode("utf-8")
lines = body.count("\n") + 1
footer = crlf(
    "本文件正文 sha256：`%s`（校验：`head -c %d \"%s\" | sha256sum`）· "
    "正文 `%d B` · 行数 `%d` · 版本 **R7（2026-11-07，D5 / 矩阵路径点名 / `F-A11` 分层判据 / 并入四处）**· "
    "底本 v0.6 一字未改（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）· "
    "**v0.7 已落盘**（%d B / %d 行 / 正文 `head -c %d` → `%s…%s` / 全文 `%s…%s`，原生工具复算）· "
    "构建器 `research/arch-build-20261107/build_contract_r7b.py`（8 条锚点唯一性断言 + H1 断言；`--land` 才落盘）"
    % (
        sha(bb), len(bb), NAME, len(bb), lines,
        V07_BYTES, V07_LINES, V07_BODY,
        V07_BODY_SHA[:8], V07_BODY_SHA[-6:], V07_FULL_SHA[:8], V07_FULL_SHA[-6:],
    )
) + "\r\n"

open(P, "wb").write((body + footer).encode("utf-8"))
print("REF_BYTES", len((body + footer).encode("utf-8")))
print("REF_LINES", (body + footer).count("\n"))
print("REF_BODY_SHA", sha(bb))
print("REF_FULL_SHA", sha((body + footer).encode("utf-8")))
