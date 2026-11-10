# -*- coding: utf-8 -*-
"""v0.17 生成器：v0.16 逐字节为底（CRLF 保持），只改 E4-A6 一处口径。锚点先断言唯一。"""
import hashlib
import pathlib

ROOT = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel")
A = ROOT / "docs/architecture"
S16 = A / "FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md"
S17 = A / "FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
W = ROOT / "research/arch-build-20261108"

raw = S16.read_bytes()
assert len(raw) == 316155, len(raw)
assert raw.count(b"\r\n") == raw.count(b"\n"), "行尾不齐"
text = raw.decode("utf-8")
assert text.endswith("\r\n")
lines = [l[:-1] if l.endswith("\r") else l for l in text.split("\n")[:-1]]
assert len(lines) == 2476, len(lines)
assert not any(l.endswith("\r") for l in lines)


def one(pred, name):
    hits = [i for i, l in enumerate(lines) if pred(l)]
    assert len(hits) == 1, "%s -> %d" % (name, len(hits))
    return hits[0]


i_h1 = one(lambda l: l == "# 因子化引擎与生产侧执行器 —— 接口契约 v0.16（2026-11-08）", "H1")
i_log = one(lambda l: l.startswith("| v0.16（裁定） | 2026-11-08 |"), "log16")
i_a6 = one(lambda l: l.startswith("| E4-A6 | 周号规则 |"), "E4-A6")
assert lines[i_a6 + 1] == "" and lines[i_a6 + 2].startswith("### 5.7 "), "5.7 结构"
i_foot = len(lines) - 1
assert lines[i_foot].startswith("本文件正文 sha256："), "footer"

lines[i_h1] = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.17（2026-11-08）"

LOG17 = ("| v0.17（裁定） | 2026-11-08 | **R17（v0.16 逐字节为底，只改 `E4-A6` 一处口径；`E4-A4` 五条、§7.16.4、"
         "`F-A1`–`F-A49` 的号与字面、全部判据阈值一字不动）**：`E4-A6` 的「错法」由散文「跨年周」**写死为 `dt_week` = "
         "(`calendar_year`, `iso_week`)**，(`calendar_year`, `%W`) 变体**单列一行、禁止混用**；断言由「差异被显式记录」改为"
         "**只比集合**（`ISO \\ 错法` 与 `错法 \\ ISO` 两个字面集合），**全轴与窗内两套同时给**；新增**取证表**写死 "
         "`week_end` 口径（下一根 bar 换键、末根 `null`、先整轴算再按窗口过滤），给全轴 **451 / 453**、窗内 **376 / 378**、"
         "差集 **∅ 与 {2019-12-31, 2024-12-31}**；写明 `2019-01-04` / `2024-01-05` / `2025-01-03` 在三种周键下**都是** "
         "`week_end`、故**不可能**是差集元素，`2026-11-06` 是末根 `null`、也不是差集元素；派单台账 v10 §6 的 "
         "452 / 451 / 454 与 `3+2` **降为对账备案**（出自「按周键 groupby 取组内最后一日」口径，不得作判据）；登记 "
         "`E4-K1`（§5.2 `week_rule` 默认值与实现相反）、`E4-K2`（§5.2 末根恒真与 §5.3/实现相反）、"
         "`E4-K3`（实现引「判据 `E4-A7`」但全文无此条）三处待裁定。 | "
         "开发经理 v0.17 派单（排期 v10 §6 `P0-Z`）+ 架构师本机复跑 "
         "`research/arch-build-20261108/probe_v017_e4a6.py`（四个集合逐日相等）+ 实现自述 "
         "`calendar_axis.py:20`「整轴 451 vs 453」 |")
lines.insert(i_log + 1, LOG17)
i_a6 += 1
i_foot += 1

A6 = ("| E4-A6 | 周号规则（**两种周键写死；断言只比集合**） | **正确** `iso_year_week` = (`iso_year`, `iso_week`)；"
      "**错法（本契约所称「错法」只有这一个）** `dt_week` = (`calendar_year`, `iso_week`)；另一种错误写法 "
      "(`calendar_year`, `%W`) 在取证表单列一行、**不得与上一行混用**。判据：对同一 `axis` 分别以两种 `week_rule` "
      "**显式传参**调用（不得依赖默认值），`week_end` 集合**按集合比**（禁止按个数比），字面日期见本节「E4-A6 取证表」。"
      "依据：实现自述 `calendar_axis.py:20`「整轴 451 vs 453」+ 本架构师 2026-11-08 13:2x 独立复跑 "
      "`research/arch-build-20261108/probe_v017_e4a6.py`（四个集合逐日相等） |")
lines[i_a6] = A6

block = (W / "_block_e4a6.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n").split("\n")
assert all("\r" not in l and "\n" not in l for l in block), "block 内有裸换行"
lines[i_a6 + 1:i_a6 + 2] = [""] + block + [""]
i_foot += len(block) + 2

sec16 = (W / "_sec16.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n").split("\n")
lines[i_foot:i_foot] = sec16 + [""]

def crlf(ls):
    return ("\r\n".join(ls) + "\r\n").encode("utf-8")

body = crlf(lines)
bhash = hashlib.sha256(body).hexdigest()
tl = len(lines) + 1
foot = (W / "_footer_tpl.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
foot = (foot.replace("@@BHASH@@", bhash).replace("@@BB@@", str(len(body)))
            .replace("@@TL@@", str(tl)).replace("@@BL@@", str(len(lines))))
assert "@@" not in foot, "footer 占位残留"
assert "\n" not in foot and "\r" not in foot, "footer 必须是单行"
out = body + foot.encode("utf-8") + b"\r\n"
assert out.count(b"\r\n") == out.count(b"\n"), "行尾不齐: %d CRLF / %d LF" % (out.count(b"\r\n"), out.count(b"\n"))
S17.write_bytes(out)
print("WROTE %s %d B / %d lines(CRLF)" % (S17.name, len(out), out.count(b"\r\n")))
print("BODY %d B / %d lines / sha256 %s" % (len(body), len(lines), bhash))
