# -*- coding: utf-8 -*-
"""把 build_contract_v09.py 里对 v0.8 的陈旧四元组/时刻引用，改为当前盘面事实。

事实（原生工具复算，2026-11-07 21:00 后）：
  v0.8 = 206,608 B / 1,792 行 / 正文 head -c 204,939 -> e6b10f9a... / 全文 651e30fa...
R8 说明 §7 已于 21:00:33 以这组值复核；v0.9 脚本原先写的是 20:52 时点的 206,592 / 998d5345 / 89816d00。
"""
from pathlib import Path

p = Path(r"C:\work\sourcecode\tick-stock-panel\research\arch-build-20261107\build_contract_v09.py")
lines = p.read_text(encoding="utf-8").split("\n")

# --- 1) §11.2 第 329/330 行（0-based 328/329）：改写 20:52 与「以修补后为底」的表述
assert "20:52:02" in lines[328], lines[328][:60]
lines[328] = (
    '    "（`DELIVERY_SCHEDULE` 与 R8 说明）；20:52 原位修补 4 行 + footer'
    '（`xs_rank_market` 的两层澄清：算子键层独立计数、因子台账层仍与 `rank` 合计 1 个），'
    '20:58:45 又修订 footer 的版本簿记（正文未动），R8 说明 §7 于 21:00:33 复核四元组；"'
)
assert "修补后" in lines[329], lines[329][:60]
lines[329] = (
    '    "本版以其**当前字节**为底 —— **正文逐字节相同**，本版只在旧 footer 处替换'
    '（下面的四元组即当前值）。**本版不覆盖它**：同一路径同一版本号出现两种字节，'
    '会让已流通的哈希失效。"'
)

# --- 2) footer 行（0-based 409）：20:52:02 快照 -> 20:58:45 快照
assert "20:52:02 快照" in lines[409], lines[409][:80]
lines[409] = lines[409].replace(
    "冻结为 2026-11-07 20:52:02 快照（20:39 落盘 + 20:52 原位修补）",
    "冻结为 2026-11-07 20:58:45 快照（20:39 落盘 + 20:52 修补 + 20:58 footer 修订，R8 说明 21:00:33 复核）",
)

p.write_text("\n".join(lines), encoding="utf-8")
print("patched", p.stat().st_size, "B")
print("residual 20:52:02 =", "\n".join(lines).count("20:52:02"))
print("residual 206,592 =", "\n".join(lines).count("206,592"))
