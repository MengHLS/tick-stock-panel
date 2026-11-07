# -*- coding: utf-8 -*-
"""v5.13 收尾：①§17 小节编号撞号（旧「### 17.6 本节没做的事」）改 17.5.1；②§17.4 就地加 §17.6.1 指针。只改 md。"""
import io
from pathlib import Path
MD = Path(__file__).resolve().parents[2] / "docs/factors/F_CLASS_REGISTRATION_20261107.md"
def sub(t, old, new, tag):
    n = t.count(old)
    if n != 1:
        raise SystemExit("[FAIL] %s: %d hits" % (tag, n))
    return t.replace(old, new)
t = io.open(MD, encoding="utf-8", newline="").read()
t = sub(t, "### 17.6 本节没做的事",
        "### 17.5.1 本节没做的事（§17 全节）", "A6 renumber")
t = sub(t, "（`field:ma20` / `field:ma60` / `field:boll_lower` / `field:boll_upper`），走 column 面 → **今天不会被打成 400**。400 只在「被当因子引用」时出现。",
        "（`field:ma20` / `field:ma60` / `field:boll_lower` / `field:boll_upper`；**写法订正见 §17.6.1**：7 条信号 14 处引用里 12 处带 `field:`、2 处是裸名 `ma20`），走 column 面 → **今天不会被打成 400**。400 只在「被当因子引用」时出现。",
        "A7 17.4 pointer")
io.open(MD, "w", encoding="utf-8", newline="").write(t)
print("[ok] md patched, %d chars" % len(t))
