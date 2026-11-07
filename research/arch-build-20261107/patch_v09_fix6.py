# -*- coding: utf-8 -*-
"""第六轮：删掉 §11.1「第 4 处」段落末尾我自加的 `asset_types` 偏差登记句。

派单第 4 处只要「catalog 规模变化（107/108）写进既有行为描述」。
`asset_types={"stock","etf"}` 与 §2.3「只定义于 stock 域」的差别是我自己加的登记，
既不在四处之内、也不改判据 —— 按「只改这四处」纪律移除。
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
lines = p.read_text(encoding="utf-8").split("\n")

key = '另登记一处偏差：该条目 `asset_types='
hits = [i for i, ln in enumerate(lines) if key in ln]
assert len(hits) == 1, hits
i = hits[0]
print("DROP:", lines[i][:120])
del lines[i]
p.write_text("\n".join(lines), encoding="utf-8")

import py_compile
py_compile.compile(str(p), doraise=True)
src = "\n".join(lines)
print("ok", p.stat().st_size, "B; residual asset_types-in-S11:", src.count("另登记一处偏差"))
print("residual 一处现状偏差:", src.count("一处现状偏差"))
