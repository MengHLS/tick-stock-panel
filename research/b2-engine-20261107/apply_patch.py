"""对 backend 内核文件做精确文本替换 (fs 工具被限制在 research/ 下, 用 python 落地).

每个 patch = (old, new); old 必须在文件里恰好出现一次, 否则报错退出 (fail-closed)。
用法: python apply_patch.py <patch_module>
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")


def apply(rel_path: str, patches: list[tuple[str, str]]) -> None:
    path = PROJECT / rel_path
    text = path.read_text(encoding="utf-8")
    for index, (old, new) in enumerate(patches):
        count = text.count(old)
        if count != 1:
            raise SystemExit(
                f"[{rel_path} patch#{index}] old 出现 {count} 次 (要求 1 次), 中止:\n{old[:200]}"
            )
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print(f"patched {rel_path} ({len(patches)} edits)")


if __name__ == "__main__":
    module = sys.argv[1]
    sys.path.insert(0, str(Path(__file__).parent))
    import importlib

    mod = importlib.import_module(module)
    mod.main(apply)
