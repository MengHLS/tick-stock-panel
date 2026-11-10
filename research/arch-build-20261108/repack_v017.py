# -*- coding: utf-8 -*-
"""v0.17 收口②：把「十五份」改成实测的 14 份，并指向真实校验脚本；随后重算 footer 四个量。"""
import hashlib
import re

P = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
OLD = "**十五份全同（v0.3–v0.17，含本版）**"
NEW = "**十四份全同（v0.3 冻结归档 + v0.5–v0.17，含本版）**"

txt = open(P, encoding="utf-8").read()
n = txt.count(OLD)
assert n == 2, f"期望 2 处，实得 {n}"
txt = txt.replace(OLD, NEW)
m = txt.count("`verify_v017.py` B1–B3")
assert m == 1, f"脚本名引用实得 {m}"
txt = txt.replace("`verify_v017.py` B1–B3", "`verify_v017_final.py` F1（逐份列 LF/CRLF 哈希）")

lines = txt.encode("utf-8").split(b"\n")
idx = [i for i, l in enumerate(lines) if l.strip()]
last = idx[-1]
body = b"\n".join(lines[:last]) + b"\n"
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
out = b"\n".join(lines)
open(P, "wb").write(out)
print("正文", nbody, "B sha", bsha)
print("全文", len(out), "B 行", len(out.split(b'\n')) - 1)
