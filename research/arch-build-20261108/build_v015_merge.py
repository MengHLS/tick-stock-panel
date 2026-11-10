# -*- coding: utf-8 -*-
"""把派单三项（P0-X / P0-Y / P2-1）并入盘上现行 v0.14（另一线程的 R14 另一批），产出 v0.15。

做法与教训：
* **按内容锚点定位，不用行号**；每处先断言全文唯一命中。
* **先做全部替换、最后才插入**；插入后绝不回车再索引。
* 底本哈希在读取时立刻钉住；footer 由本版正文字节重算。
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

CRLF = b"\r\n"
BASE = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md")
OUT = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md")

BASE_BYTES = 292537
BASE_SHA = "5a26d4825219507a"
BASE_BODY_N = 290672
BASE_BODY_SHA = "6d9f3b506b226fdf"


def die(m: str) -> None:
    print("ABORT:", m, flush=True)
    sys.exit(2)


raw = BASE.read_bytes()
if len(raw) != BASE_BYTES:
    die("base bytes %d != %d" % (len(raw), BASE_BYTES))
if hashlib.sha256(raw).hexdigest()[:16] != BASE_SHA:
    die("base full sha %s" % hashlib.sha256(raw).hexdigest()[:16])
if hashlib.sha256(raw[:BASE_BODY_N]).hexdigest()[:16] != BASE_BODY_SHA:
    die("base body sha mismatch")
if raw.count(CRLF) != raw.count(b"\n"):
    die("base not pure CRLF")
print("BASE OK %d B / %s / %s" % (len(raw), BASE_SHA, BASE_BODY_SHA), flush=True)

text = raw.decode("utf-8")
lines = text.split("\r\n")[:-1]
if "\r\n".join(lines) + "\r\n" != text:
    die("split/join not byte exact")
print("lines", len(lines), flush=True)


def find1(needle: str, label: str) -> int:
    """返回 needle 所属行的下标（0-based），要求全文唯一命中且只落在一行内。"""
    n = text.count(needle)
    if n != 1:
        die("%s: 唯一性失败 命中 %d" % (label, n))
    idx = text[: text.index(needle)].count("\r\n")
    # 确认 needle 不跨行
    if "\r\n" in needle:
        die("%s: needle 跨行" % label)
    return idx


def line_of(needle: str, label: str) -> str:
    i = find1(needle, label)
    if needle not in lines[i]:
        die("%s: 行内不匹配" % label)
    return lines[i]


# ------------------------------ 读取原句
L_H1 = lines[0]
if not L_H1.startswith("# 因子化引擎与生产侧执行器 —— 接口契约 v0.14（2026-11-08）"):
    die("H1 不是 v0.14")

L126 = line_of("登记号 **D6**", "126")
i126 = find1("登记号 **D6**", "126")

L605 = line_of("| E4-A4 | 节假日月 |", "E4-A4")
i605 = find1("| E4-A4 | 节假日月 |", "E4-A4")

L_TBL = line_of("| 批量入口（`/run-all`、`/factor/batch`） | `violations`（数组） |", "追加键表行")
i_TBL = find1("| 批量入口（`/run-all`、`/factor/batch`） | `violations`（数组） |", "追加键表行")

L_BAT = line_of("- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id` 取被扫描顺序的**第一条**违规", "批量条")
i_BAT = find1("- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id` 取被扫描顺序的**第一条**违规", "批量条")

L_122_T = line_of("### 12.2 编号登记：D5 = G2 成交口径，D6 = `observed_bars`", "12.2 标题")
i_122_T = find1("### 12.2 编号登记：D5 = G2 成交口径，D6 = `observed_bars`", "12.2 标题")

L_D6ROW = line_of("| **D6** | **`observed_bars` 口径偏差**", "12.2 表行")
i_D6ROW = find1("| **D6** | **`observed_bars` 口径偏差**", "12.2 表行")

L_D5OK = line_of("- **核准：全文 `D5` 只有 2 处**", "核准 bullet")
i_D5OK = find1("- **核准：全文 `D5` 只有 2 处**", "核准 bullet")

L_RESEARCH = line_of("- **研究侧文档的号与本契约不一致**", "研究侧 bullet")
i_RESEARCH = find1("- **研究侧文档的号与本契约不一致**", "研究侧 bullet")

L_CONFLICT = line_of("- **冲突备案（需裁定；本契约不自行另立号）**", "冲突备案 bullet")
i_CONFLICT = find1("- **冲突备案（需裁定；本契约不自行另立号）**", "冲突备案 bullet")

L_CITE = line_of("- **引用纪律（D6 的差异行数不要单引 17,499）**", "引用纪律 bullet")
i_CITE = find1("- **引用纪律（D6 的差异行数不要单引 17,499）**", "引用纪律 bullet")

print("anchors: H1,126=%d,E4A4=%d,TBL=%d,BAT=%d,12.2T=%d,D6row=%d,D5ok=%d,research=%d,conflict=%d,cite=%d"
      % (i126, i605, i_TBL, i_BAT, i_122_T, i_D6ROW, i_D5OK, i_RESEARCH, i_CONFLICT, i_CITE), flush=True)

# ------------------------------ 新内容
NEW_H1 = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.15（2026-11-08）"

if L126.count("登记号 **D6**") != 1:
    die("126 marker count")
NEW126 = L126.replace("登记号 **D6**", "登记号 **D10**")

NEW605 = (
    "| E4-A4 | 节假日月（2024-02 春节月，**可判定五条**） | "
    "① 2024-02 轴上 **15** 个交易日；"
    "② **`2024-02-29` 在轴上**，且它就是 `2024-02` 的 `month_end`；"
    "③ `2024-02-09`（除夕）**不在**轴上，复市首日 `2024-02-19`；"
    "④ `is_rebalance(2024-02-23) == False`（该日在轴上，次交易日 `2024-02-26` 仍属同月）；"
    "⑤ `week_end(2024-02-05) == 2024-02-08`（该周轴上 `02-05`/`02-06`/`02-07`/`02-08`，`02-09` 无 bar）。"
    "**两条反例警戒**：（a）**不得**写「`month_end` == 节前最后一个交易日」——节前最后交易日是 **`2024-02-08`**，"
    "实际 `month_end` 是 **`2024-02-29`**；（b）**不得**假设 `2/29` 不在轴上——2024 为闰年，`2024-02-29` 是正常交易日。"
    "依据：`D:/TSP/data/kline_daily_enriched` **2,141** 个 `date=` 分区去重复算"
    "（本架构师 2026-11-08 02:1x 独立复跑 `research/arch-build-20261108/probe_v014_p0y.py`，五点全 PASS） |"
)

NEW_TBL = (
    "| 批量入口（`/run-all`、`/factor/batch`），**或** `blocked` 含 ≥2 个**不同** `submitted_id` "
    "| `violations`（数组；每项只列该 id 去重后的一码） | 8 | 本节下一条 + 本节「去重先于 `detail`」条（v0.15 落定） |"
)

DEDUP = (
    "- **同一 `submitted_id` 命中多码时只报一码、不写 `violations`（去重先于 `detail` 生成；v0.15 落定，P0-X）**："
    "`blocked` 里同一个 `submitted_id` 可同时命中多码——8 个 alias 的**常规路径**就是 `FS03` + `FS01`"
    "（其 `FactorSpec` 来自 pack、无 `status` 载体，必带一条 `FS01`），**不是边界情形**。"
    "**去重发生在生成 `detail` 之前**：按优先级 **`FS04` > `FS03` > `FS06` > `FS01`** 取一码作 `detail.code`，"
    "同 id 的其余码**丢弃、不写入 `violations`**；`violations` **仅当 `blocked` 含 ≥2 个不同 `submitted_id`** 时出现，"
    "且每项只列该 id **去重后**的一码。`status` 追加键**只跟最终 `code` 走**：最终码为 `FS01` 才追加 `status`，"
    "被 `FS03` / `FS06` 压掉时**不追加**。故**单 id 请求恒为 7 键**（多 id 批量见下一条）。"
    "**实测（2026-11-08 02:1x，`RegistryFacts(D:/TSP/data)`、`mode=\"production\"`、单 id；本架构师独立复跑 "
    "`research/arch-build-20261108/probe_v014_p0x.py`）**：`vol60` → `code=FS03`、`blocked` **2 项但同属一个 id**"
    "（`FS03` + `FS01`）→ 按本条应为 **7 键**；`uf_vol60` → 通过（`blocked=()`）；`ma20` → `code=FS01` → **8 键**（7 + `status`）。"
    "**本条不改 `F-A42-2`**：`vol60` / `ma120` 两例负样本仍判「`detail` 逐键等于本节示例、`table_row` 分别 = **1** / **2**」。"
    "**现盘 `backend/app/factors/gate.py:660` 仍按 `if len(report.blocked) > 1:` 追加 `violations`（实测 8 键），按本条判为红，待实现侧改；本条不新增判据号、不改任何阈值。**"
)

NEW_BAT = (
    "- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id` 取被扫描顺序的**第一条**违规（已按上一条去重），"
    "`detail.violations = [{\"submitted_id\": …, \"code\": …}, …]` **只列不同 `submitted_id` 各一条**；"
    "`blocked` 里所有违规同属一个 `submitted_id` 时**不出现** `violations`（此时恰 7 键）。"
)

NEW_122_T = "### 12.2 编号登记：D5 = G2 成交口径，D10 = `observed_bars`"
NEW_D6ROW = L_D6ROW.replace("| **D6** |", "| **D10** |", 1)
if NEW_D6ROW == L_D6ROW:
    die("D6 row unchanged")

NEW_D5OK = L_D5OK.replace("**核准：全文 `D5` 只有 2 处**", "**核准：全文 `D5` 只有 3 处**")
if NEW_D5OK == L_D5OK:
    die("D5OK unchanged")

NEW_RESEARCH = (
    "- **研究侧文档的号与本契约不一致（列为待同步项）**：`caliber-decisions-20261107.md` §11.1 标题现写「**立 D5**」，"
    "其**内容** = 本契约的 **D10**。该文件是研究侧产物、不在本契约改动范围，**编号以本契约与冻结评审裁定为准**；"
    "其「立 D5」列为**待同步项**（研究侧下一版改）。跨文档引用一律走证据 id `D-B2-1`，两种叫法落到同一对象。"
)

NEW_CONFLICT = (
    "- **冲突已裁定（v0.15 落定，不再是待裁项）**：独立审核 `CONTRACT_REVIEW_20261107.md` `:140` 的 **D6** 已用于"
    "「`_plan_buys`（`3487` 行排序）指错」，`:195` 记该条**已关闭**——该号**保留不改**，只作历史引用。"
    "`observed_bars` 口径偏差改判为 **D10**（稳定 id 仍是 **`D-B2-1`**），**一号两用自此消除**；"
    "D6 → D10 的改齐由**冻结评审一次性完成**，本契约**不再使用「D6 = `observed_bars`」的旧写法**。"
)

NEW_CITE = L_CITE.replace("**引用纪律（D6 的差异行数不要单引 17,499）**",
                          "**引用纪律（D10 的差异行数不要单引 17,499）**")
if NEW_CITE == L_CITE:
    die("CITE unchanged")

# ------------------------------ 先替换（全部原位）
out = list(lines)
out[0] = NEW_H1
out[i126] = NEW126
out[i605] = NEW605
out[i_TBL] = NEW_TBL
out[i_BAT] = DEDUP
out[i_122_T] = NEW_122_T
out[i_D6ROW] = NEW_D6ROW
out[i_D5OK] = NEW_D5OK
out[i_RESEARCH] = NEW_RESEARCH
out[i_CONFLICT] = NEW_CONFLICT
out[i_CITE] = NEW_CITE

# ------------------------------ 最后插入（批量条重写版，紧跟去重条）
out.insert(i_BAT + 1, NEW_BAT)

body_lines = out[:-1]
body = "\r\n".join(body_lines) + "\r\n"
body_bytes = body.encode("utf-8")
body_n = len(body_bytes)
body_sha = hashlib.sha256(body_bytes).hexdigest()

CRLF_S = chr(13) + chr(10)
PIN = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md"
parts = [
    "本文件正文 sha256：`" + body_sha + "`（校验：`head -c " + str(body_n) + " \"" + PIN
    + "\" | sha256sum`；正文 = 全文去掉最后一行 footer，以换行结尾）",
    "· 正文 `" + str(body_n) + " B` · 全文 `" + str(len(body_lines) + 1) + "` 行（正文 `"
    + str(len(body_lines)) + "` + footer 1）",
    "· 版本 **v0.15（2026-11-08 R15：派单三项一次并入 v0.14 现状；判据阈值与判据号零改动）** —— ",
    "① **§7.16.4（P0-X）**：`violations` 追加键的触发条件收窄为「`blocked` 含 **≥2 个不同** `submitted_id`」；"
    "同一 `submitted_id` 命中多码时按 **`FS04` > `FS03` > `FS06` > `FS01`** 只报一码、**去重先于 `detail` 生成**、"
    "`status` 只跟最终 `code` 走（8 个 alias 的 `FS03`+`FS01` 属常规路径，单 id 恒 7 键）；",
    "② **§5.6 `E4-A4`（P0-Y）**：由「春节月 `month_end` == 节前最后一个交易日、`2/29` 不在轴上」"
    "重写为**可判定五条**（2024-02 轴上 15 天 / `2024-02-29` 在轴上且为 `month_end` / `2024-02-09` 不在轴上 / "
    "`is_rebalance(2024-02-23)==False` / `week_end(2024-02-05)==2024-02-08`）；",
    "③ **§12.2（P2-1）**：`observed_bars` 编号 **D6 → D10**（稳定 id `D-B2-1`），删「本契约不自行另立号」句，"
    "`D6` 仅保留为已关闭 `_plan_buys` 条的历史引用，研究侧「立 D5」列为**待同步项** ",
    "· 生成：**v0.14 逐字节为底**（292,537 B / 2,370 行 / 全文 `5a26d4825219507a` / 正文 `6d9f3b506b226fdf`）"
    " + **10 行正文替换 + 1 行新增**（H1 / §2.1 注 1 `D6`→`D10` / §5.6 `E4-A4` / §7.16.4 表格行 / "
    "§7.16.4 去重条 + 批量条 / §12.2 标题 / §12.2 表行 / §12.2 核准句 / §12.2 研究侧 / §12.2 冲突备案 / §12.2 引用纪律）"
    " + 本 footer 由**本版正文字节**重算",
    "· **v0.15 为现行版**；v0.14（R14 另一批：`F-A45-2` 收窄 / `FS04` 载体 / 接线前效力）、"
    "v0.13 及更早逐字节保留不删",
    "· `§7.1` 八行公式**十三份全同（v0.3–v0.15，含本版）**：LF `2,514` / `6d3db0139a45f54c`、"
    "CRLF `2,541` / `a8e88134f60b504c`（台账 v5.11 `[4]` 绑块哈希，版本号不参与判定）",
    "· `F-A1`–`F-A47` 判据号与阈值一字未动；本版**不新增任何判据号**；错误码集不变（`FS01`–`FS10`，`FS09` 为已占空位）",
]
CRLF2 = chr(13) + chr(10)
CH = chr(13)
NL = chr(10)
FOOTER = "".join(parts)

final = body + FOOTER + CRLF2
OUT.write_bytes(final.encode("utf-8"))

b = OUT.read_bytes()
i = b.rfind("本文件正文 sha256".encode())
print("=== WROTE ===", flush=True)
print("path        :", OUT, flush=True)
print("bytes       :", len(b), flush=True)
print("lines       :", len(b.splitlines()), flush=True)
print("full sha256 :", hashlib.sha256(b).hexdigest(), flush=True)
print("body bytes  :", i, flush=True)
print("body sha256 :", hashlib.sha256(b[:i]).hexdigest(), flush=True)
print("footer ok   :", hashlib.sha256(b[:i]).hexdigest().encode() in b[i:], flush=True)
