# -*- coding: utf-8 -*-
"""第七轮（修正 2）：修复 fix6 造成的空行丢失。

删掉 `asset_types` 那句后，上一行字符串与紧随的 `""` 变成 Python 隐式拼接，
空串元素被吞掉 -> §11.1 第 4 处段落与 `## 11.2` 之间少了空行。
给该行补逗号，让它成为独立元素，`""` 恢复为空行。
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
lines = p.read_text(encoding="utf-8").split("\n")

key = '5 处「条数 == 93」的断言'
hits = [i for i, ln in enumerate(lines) if key in ln]
assert len(hits) == 1, hits
i = hits[0]
s = lines[i].rstrip()
needle = '」。' + '"'          # 句号 + 右引号 + 字面量收尾引号
assert s.endswith(needle), repr(s[-30:])
assert not s.endswith(','), repr(s[-30:])
lines[i] = s + ","
print("FIXED tail:", lines[i][-24:])
p.write_text("\n".join(lines), encoding="utf-8")

import py_compile
py_compile.compile(str(p), doraise=True)
print("ok", p.stat().st_size, "B")
