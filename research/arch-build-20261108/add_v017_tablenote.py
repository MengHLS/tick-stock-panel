# -*- coding: utf-8 -*-
"""v0.17 收口⑤：加表注，说明「%W 行与 dt_week 行在本轴逐日相同」是实测、不是抄重。"""
import hashlib
import re

P = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
raw = open(P, "rb").read()
lines = raw.split(b"\r\n")

key = "| (`calendar_year`, `%W`) —— **另一种错误写法，不得与上一行混用**".encode("utf-8")
hits = [i for i, l in enumerate(lines) if l.startswith(key)]
assert len(hits) == 1, f"定位失败 {len(hits)}"
i = hits[0]
note = (
    "（表注，勿删）上一行与 `%W` 行在本轴上的集合**逐日相同**（都是 453 / 378，"
    "`错法 \\ ISO` 与 `ISO \\ 错法` 也相同）——**这不是抄写重复，是本口径下的实测**："
    "`%W` 与「自然年 + ISO 周号」的差集中在跨年那几天（`%W` 有第 00 周、ISO 有第 52/53 周），"
    "而 `week_end` 只看「相邻两根是否换键」，编号本身的差在多数位置被抵掉。"
    "这是实测结论、不是恒等式，换一条轴可能不同。"
    "**键的定义仍必须写死为 `dt_week`**：`%W` 不在实现的两个合法取值内"
    "（`WEEK_RULES` 只有 `iso_year_week` / `dt_week`），按 §5.6 仍判红；"
    "判据判的是「显式传入的键」，不是「碰巧同集合」。"
)
assert lines[i + 1].strip() == b"", "上一行应为空行"
lines[i + 2:i + 2] = [b"", note.encode("utf-8")]

idx = [k for k, l in enumerate(lines) if l.strip()]
last = idx[-1]
body = b"\r\n".join(lines[:last]) + b"\r\n"
bsha = hashlib.sha256(body).hexdigest()
nbody = len(body)
nfull = len(lines) - 1

f = lines[last].decode("utf-8")
f = re.sub(r"(本文件正文 sha256：`)[0-9a-f]{64}", lambda x: x.group(1) + bsha, f)
f = re.sub(r"(head -c )\d+", lambda x: x.group(1) + str(nbody), f)
f = re.sub(
    r"· 正文 `\d+ B` · 全文 `\d+` 行（正文 `\d+` \+ footer 1）",
    f"· 正文 `{nbody} B` · 全文 `{nfull}` 行（正文 `{nfull - 1}` + footer 1）",
    f,
)
lines[last] = f.encode("utf-8")
out = b"\r\n".join(lines)
open(P, "wb").write(out)
print("正文", nbody, "B sha", bsha)
print("全文", len(out), "B 行", out.count(b"\r\n"), "loneLF", out.count(b"\n") - out.count(b"\r\n"))
