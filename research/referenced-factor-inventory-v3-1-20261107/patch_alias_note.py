"""A 项：把 summary 别名位置登记写进生成器 docstring（不碰产物、不碰 payload）。

锚点唯一性断言失败即退出，不写盘。
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil

PROJECT = pathlib.Path(r"C:\work\sourcecode\tick-stock-panel")
TARGET = PROJECT / "backend" / "scripts" / "build_referenced_factor_inventory.py"
BACKUP = pathlib.Path(__file__).parent / "build_referenced_factor_inventory.v3_1.bak.py"

ANCHOR = """  \u53d6\u5168\u6587\u54c8\u5e0c\uff08\u542b `generated_at`\uff09\uff0c\u53ea\u8bc1\u6587\u4ef6\u5b8c\u6574\u6027\uff1b\u4e0d\u662f\u7b7e\u8ba4\u5bf9\u8c61\u3001\u4e0d\u505a\u6bd4\u5bf9\u57fa\u51c6\u3002
"""

ADDITION = """
summary \u522b\u540d\u4f4d\u7f6e\u767b\u8bb0\uff08F-A35\uff1b\u5f85\u67b6\u6784\u5e08\u88c1\u5b9a\u8868\u5934\u63aa\u8f9e\uff09
  \u5951\u7ea6 v0.6 \u00a77.12.5 \u8868\u7b2c\u4e09\u884c\u5199\u4e3a\u300c`summary.by_verdict` / `by_code` / `by_namespace`\uff08\u9876\u5c42\uff09\u300d\uff0c
  \u800c F-A35 \u5224\u636e\u539f\u6587\u5199\u300c`summary.by_verdict == all_records.by_verdict`\u300d\u3002\u672c\u5b9e\u73b0\u53d6\u540e\u8005\uff1a
  \u4e09\u4e2a\u522b\u540d\u4f4d\u4e8e **`summary` \u5185\u7684\u9876\u5c42**\uff08\u8def\u5f84 `summary.by_verdict` \u7b49\uff09\uff0c\u4e0e
  `summary.all_records` \u7684\u540c\u540d\u952e**\u9010\u503c\u76f8\u7b49**\uff1b**\u4ea7\u7269 JSON \u7684\u6839\u5c42\u6ca1\u6709**
  `by_verdict` / `by_code` / `by_namespace` \u952e\uff08\u6839\u5c42\u53ea\u6709 `schema_version` / `generated_at` /
  `canonical_digest` / `repo_head` / `data_root` / `scanned_sources` / `records` / `summary` /
  `stale_count` / `notes`\uff09\u3002F-A35 \u6309 `summary.by_verdict` \u8def\u5f84\u65ad\u8a00\uff0c\u4e0d\u6309\u6839\u5c42\u53d6\u952e\u3002
  \u672c\u6761\u53ea\u662f\u4f4d\u7f6e\u767b\u8bb0\uff1a\u4e0d\u6539\u8ba1\u7b97\u3001\u4e0d\u6539\u4ea7\u7269\uff08\u56e0\u6b64\u4e0d\u6539 `canonical_digest`\uff09\uff0c
  \u88c1\u5b9a\u5f52\u67b6\u6784\u5e08\uff1b\u82e5\u88c1\u5b9a\u8981\u642c\u5230\u6839\u5c42\uff0c\u9700\u540c\u6b65\u6539 \u00a77.12.4 \u6458\u8981\u53e3\u5f84\u5e76\u91cd\u7b7e\u3002
"""


def main() -> None:
    raw = TARGET.read_bytes()
    before_sha = hashlib.sha256(raw).hexdigest()
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"backup -> {BACKUP.name}")
    text = raw.decode("utf-8")
    if ADDITION.strip() in text:
        print("already present, no-op")
        return
    count = text.count(ANCHOR)
    if count != 1:
        raise SystemExit(f"anchor count={count} (expected 1), abort")
    text = text.replace(ANCHOR, ANCHOR + ADDITION, 1)
    TARGET.write_bytes(text.encode("utf-8"))
    new_raw = TARGET.read_bytes()
    print(f"before sha={before_sha} bytes={len(raw)}")
    print(f"after  sha={hashlib.sha256(new_raw).hexdigest()} bytes={len(new_raw)}")
    print(f"lines {raw.count(10)} -> {new_raw.count(10)}")


if __name__ == "__main__":
    main()
