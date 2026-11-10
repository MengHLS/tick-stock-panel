# -*- coding: utf-8 -*-
"""v0.17 收口③：恢复 CRLF 行尾（v0.16 为纯 CRLF；收口②误把文件降为 LF），并重算 footer。

步骤：断言当前无 CR → 全部 \n 换 \r\n → 以 \r\n 切分重算正文/footer → 回写。
"""
import hashlib
import re

P = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
raw = open(P, "rb").read()
assert b"\r" not in raw, "当前文件已含 CR，勿重复执行"
raw = raw.replace(b"\n", b"\r\n")

lines = raw.split(b"\r\n")
idx = [i for i, l in enumerate(lines) if l.strip()]
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
print("正文", nbody, "B  sha", bsha)
print("全文", len(out), "B  行", out.count(b'\r\n'), "  lone-LF", out.count(b'\n') - out.count(b'\r\n'))
