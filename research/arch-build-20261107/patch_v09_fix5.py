# -*- coding: utf-8 -*-
"""第五轮：清掉 §2.7 第 3 条 bullet 的两行残余（该 bullet 原文跨 2 个字符串元素）。"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
lines = p.read_text(encoding="utf-8").split("\n")

drop = []
for i, ln in enumerate(lines):
    if ln.startswith('    "一律 `null`（= 只定义于 stock 域）'):
        drop.append(i)
    if ln.startswith('    "建议实现侧收窄为 `{\\"stock\\"}`。本条不改判据。"'):
        drop.append(i)
assert len(drop) == 2, drop
for i in sorted(drop, reverse=True):
    del lines[i]

p.write_text("\n".join(lines), encoding="utf-8")
import py_compile
py_compile.compile(str(p), doraise=True)
print("ok", p.stat().st_size, "B; residual:", "\n".join(lines).count("只定义于 stock 域"))
