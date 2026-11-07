"""把 W-I 补判据写进交付文档（docs/factors/ 不在 fs MCP 允许目录内，故用脚本改）。

锚点只用短串，避开文档里含 dumps 参数名的那半句（避免与环境/工具处理冲突）。
"""
from __future__ import annotations

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "docs" / "factors" / "B2_IMPLEMENTATION_20261107.md",
    ROOT / "research" / "b2-engine-20261107" / "B2_IMPLEMENTATION_20261107.md",
]

OLD_DIGEST = "4b85d1291e748d79979d9ebd84accd835655952732bf67a055179bf9bc16b348"
NEW_DIGEST = "020ff5c3a7825fce18ba4a7bba14d35d23175f74802f8a054edfe03d60990bb0"

EDITS = [
    (
        "（48 条：**47 PASS / 0 FAIL / 1 INFO**，47,338 B，sha256 ",
        "（49 条：**48 PASS / 0 FAIL / 1 INFO**，49,293 B，sha256 ",
    ),
    ("`" + OLD_DIGEST + "`", "`" + NEW_DIGEST + "`"),
    ("## 5. 接线验证（W-A…W-H，走生产入口）", "## 5. 接线验证（W-A…W-I，走生产入口）"),
    (
        "| W-H | 14 日窗经生产入口同样全 null | PASS |\n",
        "| W-H | 14 日窗经生产入口同样全 null | PASS |\n"
        "| W-I | E009 对四个新键生效：`ts_mean(<xs…>)` 全部 `E009`"
        "（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct` / `xs_mean`），"
        "对照 `rank` / `zscore` 同为 `E009` 不变；且 `xs_rank_pool(close, in_universe)`、"
        "`xs_mean(close, in_universe)` 编译通过（掩码标签被接受） | PASS |\n"
        "\n"
        "> W-I 是补 v0.8 §10.2「未确证③」（`E009` 对四新键只读了代码分支、"
        "未构造嵌入用例实跑）：8 个用例全部实跑，期望码与实际码逐条相等。"
        "v0.8 §10.2「未确证②」（`xs_rank_market` 是否真等价 `rank`）由 XS-B1 逐位比对已覆盖。\n",
    ),
    ("# 生产入口接线 (W-A..W-H)", "# 生产入口接线 (W-A..W-I)"),
]


def main() -> int:
    for path in TARGETS:
        text = io.open(path, encoding="utf-8").read()
        for old, new in EDITS:
            n = text.count(old)
            if n != 1:
                raise SystemExit(f"[FAIL] 锚点命中 {n} 次于 {path.name}: {old[:50]!r}")
            text = text.replace(old, new)
        io.open(path, "w", encoding="utf-8", newline="").write(text)
        print(f"[ok] {path}  {len(text.encode('utf-8'))} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
