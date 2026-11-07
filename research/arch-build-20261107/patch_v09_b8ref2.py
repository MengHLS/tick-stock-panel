# -*- coding: utf-8 -*-
"""第二轮修补：v0.8 在本日被并行流程三次原位改写（20:52 / 20:58 / 21:02），
四元组随之变化。把 §11.2 与 footer 里「按时刻叙述」的写法改成「按底本哈希钉死」，
并用 __B8FS16__ 占位符（构建时由 BASE_SHA 回填），避免再次追字。
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
lines = p.read_text(encoding="utf-8").split("\n")

# §11.2 第 329 行：20:52/20:58 叙述 -> 三次原位修订 + 底本按哈希钉死
assert "20:58:45 又修订 footer" in lines[328], lines[328][:60]
lines[328] = (
    '    "（`DELIVERY_SCHEDULE` 与 R8 说明）。该文件自 20:39 落盘后于本日 20:52、20:58、21:02 '
    '**三次原位修订**（`xs_rank_market` 两层澄清 / footer 簿记 / §10 一行），每次字节都变而版本号不变；"'
)
assert "当前字节" in lines[329], lines[329][:60]
lines[329] = (
    '    "本版底本 = **`BASE_SHA` = `__B8FS16__…`**（即下面四元组那一组字节）：构建脚本内断言构建期间该哈希不变，'
    '故底本可按哈希复现。**本版不覆盖 v0.8**：同一路径同一版本号本日已出现多组字节，再改会让已流通的哈希失效。"'
)

# footer 第 410 行
assert "20:58:45 快照" in lines[409], lines[409][:80]
lines[409] = lines[409].replace(
    "冻结为 2026-11-07 20:58:45 快照（20:39 落盘 + 20:52 修补 + 20:58 footer 修订，R8 说明 21:00:33 复核）",
    "为 2026-11-07 20:39 落盘后经 20:52 / 20:58 / 21:02 三次原位修订的字节，**本版以其为冻结参照**（多线程并行改写同一路径，故只认哈希不认时刻）",
)

p.write_text("\n".join(lines), encoding="utf-8")
print("patched", p.stat().st_size, "B")
s = "\n".join(lines)
for k in ("20:58:45", "21:00:33", "当前字节", "修补后"):
    print("residual", k, s.count(k))
