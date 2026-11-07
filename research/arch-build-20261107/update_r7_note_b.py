# -*- coding: utf-8 -*-
"""R7 说明文件定点同步：v0.7 四元组随注 2 两处修补更新，并重算本文件 footer 自指哈希。"""
import hashlib, os, sys

ROOT = r"C:\work\sourcecode\tick-stock-panel"
NOTE = os.path.join(ROOT, "docs", "architecture", "CONTRACT_REVISION_R7_20261107.md")

NEW_BYTES = 193586
NEW_LINES = 1696
NEW_BODY_LEN = 191933
NEW_BODY_SHA = "73e15ddc4d8e4a780d02f72cd4e06342834e28fbc77c284b34476e91f8efd6d0"
NEW_FULL_SHA = "5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8"

EDITS = [
    # §6.5 「不改任何其它既有行」的 numstat
    ("**不改任何其它既有行**：`git diff --no-index --numstat` 实际 **+248 / −6**（6 = 六处替换行，含本批并入的 `A7`/`B1`/`B2`）。",
     "**不改任何其它既有行**：`git diff --no-index --numstat` 实际 **+250 / −8**（8 = 八处替换行：H1 / §2.6 `A7` / §2.6 注 2 窗口行 / §2.6 注 2 代价行 / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer 自指哈希）。"),
    # §7.2 四元组
    ("| 总字节 | **193,073 B** |", "| 总字节 | **193,586 B** |"),
    ("| 正文前缀 | `head -c 191420` |", "| 正文前缀 | `head -c 191933` |"),
    ("| 正文 sha256 | **`f824cfba15f3abba91928296780c1210779d6628d882fcff8167cf09590c3c01`** |",
     "| 正文 sha256 | **`73e15ddc4d8e4a780d02f72cd4e06342834e28fbc77c284b34476e91f8efd6d0`** |"),
    ("| 全文 sha256 | **`f7b6adb2bd8f35b3cf470e56c8092a309bbdd28229b25c30d39bc24ce3002908`** |",
     "| 全文 sha256 | **`5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8`** |"),
    ("| `git diff --no-index --numstat`（v0.6 → v0.7） | **+248 / −6** |",
     "| `git diff --no-index --numstat`（v0.6 → v0.7） | **+250 / −8** |"),
    ("| 相对 v0.6 的净变化 | 行 1,696 − 1,454 = **+242**；字节 193,073 − 162,361 = **+30,712** |",
     "| 相对 v0.6 的净变化 | 行 1,696 − 1,454 = **+242**；字节 193,586 − 162,361 = **+31,225** |"),
    # 块表
    ("| E 替换 6 行 | H1 / §2.6 `A7` / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer | 6 | 各自 1 进 1 出 |",
     "| E 替换 8 行 | H1 / §2.6 `A7` / §2.6 注 2 窗口行 / §2.6 注 2 代价行 / §4.6 `B1` / §4.6 `B2` / §8.1 `F-A11` / footer | 8 | 各自 1 进 1 出；注 2 两行 = 落盘后自检发现「注 2 仍写死 8 天、与 `A7` 的 14 天冲突」，同版修补，未另开版本 |"),
    ("| **合计** | — | **+248 / −6** | 与 `numstat` 一致（242 净增 + 6 替换：H1 / `A7` / `B1` / `B2` / `F-A11` / footer 自指哈希） |",
     "| **合计** | — | **+250 / −8** | 与 `numstat` 一致（242 净增 + 8 替换：H1 / `A7` / 注 2 两行 / `B1` / `B2` / `F-A11` / footer 自指哈希） |"),
]


def main():
    raw = open(NOTE, "rb").read().decode("utf-8")
    # footer 单独处理（自指哈希要最后重算）
    idx = raw.rindex("本文件正文 sha256：")
    body, footer = raw[:idx], raw[idx:]

    for old, new in EDITS:
        n = body.count(old)
        if n != 1:
            sys.exit("替换命中 %d 次（应为 1）: %r" % (n, old[:60]))
        body = body.replace(old, new)

    # 在 §7.4 前追加一条修补登记（若尚无）
    marker = "### 7.4 本批并入的四处（同一版 v0.7，不另开 R8；行号 = 落盘后 v0.7 实际行号）"
    if "7.3b" not in body:
        add = (
            "### 7.3b 落盘后自检发现并同版修补的一处（未另开版本）\n\n"
            "- 现象：`§2.3` 注 2 的**代价行**仍写「窗口 8 个交易日内整池不可判定」，而 `§2.6 A7` 已改为「至数据末端、当前 14 天（8 + 6）」；两处并存会让实施者按 8 天排期，并漏掉 `10-30`…`11-06` 的 6 天。\n"
            "- 同源问题：注 2 上方的 `st_unknown_windows` 规范行只写默认区间 8 天，未说明它**不等于**窗口总数。\n"
            "- 处置：两行均按 `A7` 口径重写（合计 14 天 = 8 + 6，且明文**禁止硬编码 8 或 14**，必须按「`st_unknown_windows` ∩ 评估窗」＋「`date > coverageEnd` ∩ 评估窗」现算）。同一版 v0.7 内修补，`numstat` 由 +248/−6 变为 **+250/−8**。\n"
            "- 未改：§2.2 参数表 `st_unknown_windows` 默认值 `((\"2026-10-20\",\"2026-10-29\"),)` 本身正确，不动。\n\n"
        )
        if marker in body:
            body = body.replace(marker, add + marker, 1)
        else:
            sys.exit("找不到 §7.4 锚点")

    new_body = body.encode("utf-8")
    bs = hashlib.sha256(new_body).hexdigest()
    nb = len(new_body)
    lines = body.count("\n") + (0 if body.endswith("\n") else 0)

    # footer 重写：替换其中的 sha 与 head -c 上界、行数
    import re
    f2 = re.sub(r"`[0-9a-f]{64}`", "`%s`" % bs, footer, count=1)
    f2 = re.sub(r"head -c [0-9]+", "head -c %d" % nb, f2, count=1)
    f2 = re.sub(r"正文 `[0-9]+ B`", "正文 `%d B`" % nb, f2, count=1)
    f2 = re.sub(r"行数 `[0-9]+`", "行数 `%d`" % (body.count("\n")), f2, count=1)

    out = new_body + f2.encode("utf-8")
    open(NOTE, "wb").write(out)

    raw2 = out.decode("utf-8")
    total_lines = raw2.count("\n") + (0 if raw2.endswith("\n") else 1)
    print("NOTE_BYTES", len(out))
    print("NOTE_LINES", total_lines)
    print("NOTE_BODY_LEN", nb)
    print("NOTE_BODY_SHA", bs)
    print("NOTE_FULL_SHA", hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    main()
