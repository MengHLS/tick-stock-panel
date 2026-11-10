# -*- coding: utf-8 -*-
"""v0.17 收口④：修正判读 3 的结构性论证（原写「错法是 ISO 的加密划分」方向错了）。

错法与正确键只差年份位，周号位相同；错法在跨年处把**同一 ISO 周切成两段**（2024-12-30/31
记 (2024,1)、2025-01-02 起记 (2025,1)），于是**多出**末日、不会漏掉末日。
保留 CRLF，并按本版正文字节重算 footer。
"""
import hashlib
import re

P = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
raw = open(P, "rb").read()
lines = raw.split(b"\r\n")

key = "3. **`ISO \\ 错法` 恒为空集是结构性的".encode("utf-8")
hits = [i for i, l in enumerate(lines) if l.startswith(key)]
assert len(hits) == 1, f"定位失败：{len(hits)}"
i = hits[0]
old = lines[i].decode("utf-8")
assert "加密" in old

new = (
    "3. **`ISO \\ 错法` 恒为空集是结构性的，不是巧合**：两个键**只差年份位**"
    "（`iso_year` ↔ `calendar_year`），**周号位相同**。对连续两根 bar：若 `iso_week` 不同，"
    "则错法键的第二位必不同；若 `iso_week` 相同，则两根同属一个 ISO 周、`iso_year` 必相同"
    "（一个周号只属于一个 ISO 年），ISO 键也不变。故 **ISO 键变化 ⇒ 周号位变化 ⇒ 错法键变化**："
    "正确口径认可的每个 `week_end`，错法也认可，`ISO \\ 错法` **只能为空**。"
    "反过来不成立——错法在跨年处把**同一 ISO 周按自然年切成两段**"
    "（2024-12-30 / 12-31 记作 `(2024,1)`，2025-01-02 起记作 `(2025,1)`），"
    "于是**多出**一个末日：差集恰为「**自然年最后一个交易日，且下一根 bar 仍在同一 ISO 周内**」的那两天。"
    "任何实现报出非空 `ISO \\ 错法`，**只有**两种可能：周键取错"
    "（如误并入 `week` 一位，把 2018/2019、2024/2025 两个 W01 并成一周），"
    "或换用了另一种 `week_end` 口径（见 ⑤）。这一条让判据自诊断，不靠对数字的记忆。"
)
lines[i] = new.encode("utf-8")

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
print("旧行", len(old.encode()), "B → 新行", len(new.encode()), "B")
print("正文", nbody, "B sha", bsha)
print("全文", len(out), "B 行", out.count(b"\r\n"), "loneLF", out.count(b"\n") - out.count(b"\r\n"))
