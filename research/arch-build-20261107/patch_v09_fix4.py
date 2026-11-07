# -*- coding: utf-8 -*-
"""第四轮（重做）：删掉 §2.7 第 3 条 bullet（asset_types 偏差登记）。

派单只要「把 catalog 规模变化写进既有行为描述」；第 3 条是我自己加的登记项，
既不在四处之内、也不改判据。按「只改这四处」纪律移除。同步改：
  - §11 的改动表：三 bullet -> 两 bullet，去掉 `L27_B3`
  - nums 占位表：删 L27_B3
  - footer 与 §0：「§2.7 3 bullet」->「§2.7 2 bullet」
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
src = p.read_text(encoding="utf-8")

# 1) 删 bullet：整行以该 bullet 的列表元素形式存在
before = src.count("一处现状偏差")
assert before >= 1, before
out = []
removed = 0
for ln in src.split("\n"):
    if "一处现状偏差（登记，不阻塞，归实现侧）" in ln and ln.strip().startswith('"'):
        removed += 1
        continue
    out.append(ln)
assert removed == 2, removed   # bullet 行 + nums 里的 L27_B3 行（含同一串）一起被删
src = "\n".join(out)

# 2) nums 占位：L27_B3 已在第 1 步与 bullet 一起删掉，此处只做零残留校验
assert '"L27_B3":' not in src

# 3) §11 改动表：三 bullet -> 两 bullet
a = "| 4 | §2.7 追加三 bullet | `L27_B1` / `L27_B2` / `L27_B3` | **现状描述** | catalog 93→107→108 |"
b = "| 4 | §2.7 追加两 bullet | `L27_B1` / `L27_B2` | **现状描述** | catalog 93→107→108 |"
assert src.count(a) == 1
src = src.replace(a, b)

# 4) 其余「3 bullet / 三 bullet」表述
for old, new in (("§2.7 3 bullet", "§2.7 2 bullet"), ("§2.7 三 bullet", "§2.7 两 bullet")):
    src = src.replace(old, new)

p.write_text(src, encoding="utf-8")
import py_compile
py_compile.compile(str(p), doraise=True)
print("ok", p.stat().st_size, "B")
print("residual 一处现状偏差:", src.count("一处现状偏差"), "L27_B3:", src.count("L27_B3"))
