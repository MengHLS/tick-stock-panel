# -*- coding: utf-8 -*-
"""v0.17 收口：删掉正文中残留的 v0.16 footer 行，并按本版正文字节重算 footer。

原因：v0.17 构建时把 §16 插在 v0.16 footer **之后**，导致正文里留着一行
"本文件正文 sha256：d58d90b5…"（那是 v0.16 的 footer），读者会读到两个正文 sha。
本脚本把该行删除（§15 以「版本关系」行结束，随后 `---` + §16），再重算 footer 四个量。
"""
import hashlib
import re
import sys

p = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
raw = open(p, "rb").read()
lines = raw.split(b"\n")

hits = [i for i, l in enumerate(lines) if l.startswith("本文件正文 sha256：".encode())]
assert len(hits) == 2, f"期望 2 个 footer 行，实得 {len(hits)}"
stale = lines[hits[0]].decode("utf-8")
assert "d58d90b577af07b4" in stale, "被删的不是 v0.16 footer"
del lines[hits[0]]

idx = [i for i, l in enumerate(lines) if l.strip()]
last = idx[-1]
body = b"\n".join(lines[:last]) + b"\n"
bsha = hashlib.sha256(body).hexdigest()
nbody = len(body)
nfull = len(lines) - 1          # wc -l of final file
nbody_lines = nfull - 1

footer = lines[last].decode("utf-8")
assert "cc697f44d67facd2" in footer, "末行不是 v0.17 footer"

f = re.sub(r"(本文件正文 sha256：`)[0-9a-f]{64}", lambda m: m.group(1) + bsha, footer)
f = re.sub(r"(head -c )\d+", lambda m: m.group(1) + str(nbody), f)
f = re.sub(
    r"· 正文 `\d+ B` · 全文 `\d+` 行（正文 `\d+` \+ footer 1）",
    f"· 正文 `{nbody} B` · 全文 `{nfull}` 行（正文 `{nbody_lines}` + footer 1）",
    f,
)
assert bsha in f and f"head -c {nbody}" in f and f"正文 `{nbody} B`" in f
assert f"全文 `{nfull}` 行（正文 `{nbody_lines}` + footer 1）" in f

out = b"\n".join(lines[:last] + [f.encode("utf-8")] + lines[last + 1:])
open(p, "wb").write(out)
print("stale removed, bytes:", len(stale))
print("body", nbody, "B  sha", bsha)
print("full", len(out), "B  lines", len(out.split(b'\n')) - 1)
