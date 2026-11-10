# -*- coding: utf-8 -*-
"""v0.14 构建脚本：v0.13 逐字节为底，只做派单的三处（P0-X / P0-Y / P2-1）+ 版本簿记。

纪律：底本哈希断言；每处替换先断言全文唯一命中；新内容一律 r'''...''' 原样串；
footer 由本版正文字节重算。
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

CRLF = b"\r\n"
BASE = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md")
OUT = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md")

BASE_BYTES = 277296
BASE_SHA = "a1374eb5cc526e11"
BASE_BODY_N = 275854
BASE_BODY_SHA = "73901fd0faff9711"


def die(msg: str) -> None:
    print("ABORT:", msg, flush=True)
    sys.exit(2)


raw = BASE.read_bytes()
if len(raw) != BASE_BYTES:
    die("base bytes %d != %d" % (len(raw), BASE_BYTES))
if hashlib.sha256(raw).hexdigest()[:16] != BASE_SHA:
    die("base full sha mismatch")
if hashlib.sha256(raw[:BASE_BODY_N]).hexdigest()[:16] != BASE_BODY_SHA:
    die("base body sha mismatch")
if raw.count(CRLF) != raw.count(b"\n") or not raw.endswith(CRLF):
    die("base not pure CRLF")
print("BASE OK %d B / full %s / body %s" % (BASE_BYTES, BASE_SHA, BASE_BODY_SHA), flush=True)

text = raw.decode("utf-8")
lines = text.split("\r\n")[:-1]
if "\r\n".join(lines) + "\r\n" != text:
    die("split/join not byte-exact")
print("lines %d" % len(lines), flush=True)


def line_at(n: int) -> str:
    return lines[n - 1]


def expect(n: int, prefix: str) -> str:
    got = line_at(n)
    if not got.startswith(prefix):
        die("line %d unexpected: %r" % (n, got[:70]))
    return got


L1 = expect(1, "# 因子化引擎与生产侧执行器 —— 接口契约 v0.13（2026-11-08）")
L126 = expect(126, '1. `observed_bars` 在研究中 = `date.cum_count().over("symbol")`')
L605 = expect(605, "| E4-A4 | 节假日月 |")
L1660 = expect(1660, "| 批量入口（`/run-all`、`/factor/batch`） | `violations`（数组） | 8 |")
L1665 = expect(1665, "- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id`")
L2183 = expect(2183, "### 12.2 编号登记：D5 = G2 成交口径，D6 = `observed_bars`")
L2188 = expect(2188, "| **D6** | **`observed_bars` 口径偏差**")
L2191 = expect(2191, "- **研究侧文档的号与本契约不一致**")
L2192 = expect(2192, "- **冲突备案（需裁定；本契约不自行另立号）**")
L2193 = expect(2193, "- **引用纪律（D6 的差异行数不要单引 17,499）**")
print("ten target lines OK", flush=True)

# ---------------- A. H1
NEW1 = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.14（2026-11-08）"

# ---------------- B. :126  D6 -> D10
if L126.count("登记号 **D6**") != 1:
    die(":126 marker not unique")
NEW126 = L126.replace("登记号 **D6**", "登记号 **D10**")
if NEW126 == L126:
    die(":126 unchanged")

# ---------------- C. :605  E4-A4 (P0-Y)
NEW605 = (
    "| E4-A4 | 节假日月（2024-02 春节月，**可判定五条**） | "
    "① 2024-02 轴上 **15** 个交易日；"
    "② **`2024-02-29` 在轴上**，且它就是 `2024-02` 的 `month_end`；"
    "③ `2024-02-09`（除夕）**不在**轴上，复市首日 `2024-02-19`；"
    "④ `is_rebalance(2024-02-23) == False`（该日在轴上，次交易日 `2024-02-26` 仍属同月）；"
    "⑤ `week_end(2024-02-05) == 2024-02-08`（该周轴上 `02-05`/`02-06`/`02-07`/`02-08`，`02-09` 无 bar）。"
    "**两条反例警戒**：（a）**不得**写「`month_end` == 节前最后一个交易日」——节前最后交易日是 **`2024-02-08`**，实际 `month_end` 是 **`2024-02-29`**；"
    "（b）**不得**假设 `2/29` 不在轴上——2024 为闰年，`2024-02-29` 是正常交易日。"
    "依据：`D:/TSP/data/kline_daily_enriched` **2,141** 个 `date=` 分区去重复算"
    "（本架构师 2026-11-08 02:1x 独立复跑 `research/arch-build-20261108/probe_v014_p0y.py`，五点全 PASS） |"
)

# ---------------- D. :1660 追加键表行 (P0-X)
NEW1660 = (
    "| 批量入口（`/run-all`、`/factor/batch`），**或** `blocked` 含 ≥2 个**不同** `submitted_id` "
    "| `violations`（数组；每项只列该 id 去重后的一码） | 8 | 本节下一条 + 本节「去重先于 `detail`」条（v0.14 落定） |"
)

# ---------------- E. :1665 去重条（新增）+ 批量条（重写）
DEDUP = (
    "- **同一 `submitted_id` 命中多码时只报一码、不写 `violations`（去重先于 `detail` 生成；v0.14 落定，P0-X）**："
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

NEW1665 = (
    "- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id` 取被扫描顺序的**第一条**违规（已按上一条去重），"
    "`detail.violations = [{\"submitted_id\": …, \"code\": …}, …]` **只列不同 `submitted_id` 各一条**；"
    "`blocked` 里所有违规同属一个 `submitted_id` 时**不出现** `violations`（此时恰 7 键）。"
)

# ---------------- F/G/H. §12.2 (P2-1)
NEW2183 = "### 12.2 编号登记：D5 = G2 成交口径，D10 = `observed_bars`"

if L2188.count("| **D6** |") != 1:
    die(":2188 marker not unique")
NEW2188 = L2188.replace("| **D6** |", "| **D10** |", 1)

NEW2191 = (
    "- **研究侧文档的号与本契约不一致（列为待同步项）**：`caliber-decisions-20261107.md` §11.1 标题现写「**立 D5**」，"
    "其**内容** = 本契约的 **D10**。该文件是研究侧产物、不在本契约改动范围，**编号以本契约与冻结评审裁定为准**；"
    "其「立 D5」列为**待同步项**（研究侧下一版改）。跨文档引用一律走证据 id `D-B2-1`，两种叫法落到同一对象。"
)

NEW2192 = (
    "- **冲突已裁定（v0.14 落定，不再是待裁项）**：独立审核 `CONTRACT_REVIEW_20261107.md` `:140` 的 **D6** 已用于"
    "「`_plan_buys`（`3487` 行排序）指错」，`:195` 记该条**已关闭**——该号**保留不改**，只作历史引用。"
    "`observed_bars` 口径偏差改判为 **D10**（稳定 id 仍是 **`D-B2-1`**），**一号两用自此消除**；"
    "D6 → D10 的改齐由**冻结评审一次性完成**，本契约**不再使用「D6 = `observed_bars`」的旧写法**。"
)

NEW2193 = L2193.replace("**引用纪律（D6 的差异行数不要单引 17,499）**",
                        "**引用纪律（D10 的差异行数不要单引 17,499）**")
if NEW2193 == L2193:
    die(":2193 title unchanged")

# ---------------- assemble
# 先做全部原位替换（一律用 v0.13 的 1-based 行号，替换不影响后续索引），
# 最后再插入新增行；否则插入一行会让后面所有行号 +1，导致覆盖错行。
out = list(lines)
out[0] = NEW1            # :1
out[125] = NEW126        # :126
out[604] = NEW605        # :605
out[1659] = NEW1660      # :1660
out[1664] = DEDUP        # :1665 -> 改为去重条
out[2182] = NEW2183      # :2183 标题
out[2187] = NEW2188      # :2188 表行
out[2190] = NEW2191      # :2191 研究侧
out[2191] = NEW2192      # :2192 冲突备案
out[2192] = NEW2193      # :2193 引用纪律
# 最后一个动作才是插入：把重写后的批量条插到去重条之后（原 :1665 之后）
out.insert(1665, NEW1665)

body_lines = out[:-1]
body = "\r\n".join(body_lines) + "\r\n"
body_bytes = body.encode("utf-8")
body_n = len(body_bytes)
body_sha = hashlib.sha256(body_bytes).hexdigest()

PIN = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md"
FOOTER = (
    "本文件正文 sha256：`" + body_sha + "`（校验：`head -c " + str(body_n) + " \"" + PIN
    + "\" | sha256sum`；正文 = 全文去掉最后一行 footer，以换行结尾）"
    + "· 正文 `" + str(body_n) + " B` · 全文 `" + str(len(body_lines) + 1) + "` 行（正文 `"
    + str(len(body_lines)) + "` + footer 1）"
    + "· 版本 **v0.14（2026-11-08 R14：派单三项一次改齐；判据阈值与判据号零改动）** —— "
    + "① **§7.16.4（P0-X）**：`violations` 追加键的触发条件收窄为「`blocked` 含 **≥2 个不同** `submitted_id`」；"
    + "同一 `submitted_id` 命中多码时按 **`FS04` > `FS03` > `FS06` > `FS01`** 只报一码、**去重先于 `detail` 生成**、"
    + "`status` 只跟最终 `code` 走（8 个 alias 的 `FS03`+`FS01` 属常规路径，单 id 恒 7 键）；"
    + "② **§5.6 `E4-A4`（P0-Y）**：由「春节月 `month_end` == 节前最后一个交易日、`2/29` 不在轴上」重写为**可判定五条**"
    + "（2024-02 轴上 15 天 / `2024-02-29` 在轴上且为 `month_end` / `2024-02-09` 不在轴上 / `is_rebalance(2024-02-23)==False` / "
    + "`week_end(2024-02-05)==2024-02-08`）；"
    + "③ **§12.2（P2-1）**：`observed_bars` 编号 **D6 → D10**（稳定 id `D-B2-1`），删「本契约不自行另立号」句，"
    + "`D6` 仅保留为已关闭 `_plan_buys` 条的历史引用，研究侧「立 D5」列为**待同步项** "
    + "· 生成：**v0.13 逐字节为底**（277,296 B / 2,295 行 / 全文 `a1374eb5cc526e11` / 正文 `73901fd0faff9711`）"
    + "+ **10 行正文替换 + 1 行新增**（H1 / §2.1 注 1 `D6`→`D10` / §5.6 `E4-A4` / §7.16.4 表格行 / "
    + "§7.16.4 新增去重条 + 批量条 / §12.2 标题 / §12.2 表行 / §12.2 三条 bullet）+ 本 footer 由**本版正文字节**重算"
    + "· **v0.14 为现行版**；v0.13 及更早逐字节保留不删"
    + "· `§7.1` 八行公式**十二份全同（v0.3–v0.14，含本版）**：LF `2,514` / `6d3db0139a45f54c`、"
    + "CRLF `2,541` / `a8e88134f60b504c`（台账 v5.11 `[4]` 绑块哈希，版本号不参与判定）"
    + "· `F-A1`–`F-A47` 判据号与阈值一字未动；本版**不新增任何判据号**；错误码集不变（`FS01`–`FS10`，`FS09` 为已占空位）"
)

final = body + FOOTER + "\r\n"
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
ok = hashlib.sha256(b[:i]).hexdigest().encode() in b[i:]
print("footer self-consistent:", ok, flush=True)
