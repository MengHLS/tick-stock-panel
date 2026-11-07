# -*- coding: utf-8 -*-
"""第三轮修补：(1) 补回被隐式拼接吃掉的两个逗号（§11.2 两行被并成一行）；
(2) footer 与 §11.2 不再列举「几次几时修订」——v0.8 正被并行流程反复原位改写，
    改为「只认哈希不认时刻」。
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
src = p.read_text(encoding="utf-8")

# 1) §11.2 两行：改成以逗号分隔的独立列表元素
a_old = (
    '    "（`DELIVERY_SCHEDULE` 与 R8 说明）。该文件自 20:39 落盘后于本日 20:52、20:58、21:02 '
    '**三次原位修订**（`xs_rank_market` 两层澄清 / footer 簿记 / §10 一行），每次字节都变而版本号不变；"\n'
    '    "本版底本 = **`BASE_SHA` = `__B8FS16__…`**（即下面四元组那一组字节）：构建脚本内断言构建期间该哈希不变，'
    '故底本可按哈希复现。**本版不覆盖 v0.8**：同一路径同一版本号本日已出现多组字节，再改会让已流通的哈希失效。"'
)
a_new = (
    '    "（`DELIVERY_SCHEDULE` 与 R8 说明）。该文件自 20:39 落盘后于本日被并行流程**多次原位改写**"\n'
    '    "（`xs_rank_market` 两层澄清、footer 簿记、§10 行等，至少四组不同字节），而版本号不变；",\n'
    '    "本版底本 = `__B8FS16__…`（即下面四元组那一组字节；构建脚本在构建期间断言该哈希不变，故底本可按哈希复现）。"\n'
    '    "**本版不覆盖 v0.8**：同一路径同一版本号本日已出现多组字节，再改会让已流通的哈希失效。",'
)
assert src.count(a_old) == 1, "anchor A not found"
src = src.replace(a_old, a_new)

# 2) footer：去掉时刻枚举
f_old = "为 2026-11-07 20:39 落盘后经 20:52 / 20:58 / 21:02 三次原位修订的字节，**本版以其为冻结参照**（多线程并行改写同一路径，故只认哈希不认时刻）"
f_new = "为 2026-11-07 20:39 落盘后经并行流程多次原位改写后的字节（版本号未变），**本版以其为冻结参照 —— 只认哈希不认时刻**"
assert src.count(f_old) == 1, "anchor B not found"
src = src.replace(f_old, f_new)

p.write_text(src, encoding="utf-8")
print("ok", p.stat().st_size, "B")
import py_compile
py_compile.compile(str(p), doraise=True)
print("compiles")
