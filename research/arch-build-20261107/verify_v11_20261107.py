"""v0.11 取证：四元组 + 两法 numstat + §7.1 块哈希 + 逆向还原证明 + 判据号不变。

只读 v0.10 / v0.11 与 archive，不写任何契约文件。
§7.1 块口径与 R10 §5.1 完全相同（`t.index('### 7.1') : t.index('### 7.2', i)`）。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

REPO = Path(r"C:/work/sourcecode/tick-stock-panel")
ARCH = REPO / "docs" / "architecture"
A = ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md"
B = ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md"

ra, rb = A.read_bytes(), B.read_bytes()
ta, tb = ra.decode("utf-8"), rb.decode("utf-8")

out: dict = {}


def quad(raw: bytes) -> dict:
    return {"size": len(raw), "lines": raw.count(b"\n"), "full": hashlib.sha256(raw).hexdigest()}


def body_prefix_len(raw: bytes) -> int:
    lines = raw.split(b"\n")
    k = len(lines) - 1
    while k >= 0 and lines[k].strip() == b"":
        k -= 1
    return sum(len(x) + 1 for x in lines[:k])


out["quad_v0_10"] = quad(ra)
out["quad_v0_11"] = quad(rb)
for tag, raw in (("quad_v0_10", ra), ("quad_v0_11", rb)):
    n = body_prefix_len(raw)
    out[tag].update(
        {
            "body_len": n,
            "body_sha": hashlib.sha256(raw[:n]).hexdigest(),
            "footer_len": len(raw) - n,
            "footer_sha": hashlib.sha256(raw[n:]).hexdigest(),
        }
    )

# ── numstat
def numstat(la, lb, autojunk):
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=autojunk)
    ins = rep = dele_h = add = rem = 0
    detail = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        detail.append([tag, i1 + 1, i2, j1 + 1, j2])
        if tag == "insert":
            ins += 1
            add += j2 - j1
        elif tag == "delete":
            dele_h += 1
            rem += i2 - i1
        else:
            rep += 1
            add += j2 - j1
            rem += i2 - i1
    return {"hunks": len(detail), "insert": ins, "replace": rep, "delete": dele_h,
            "added": add, "deleted": rem, "detail": detail}


la = ta.splitlines(keepends=True)
lb = tb.splitlines(keepends=True)
out["numstat_autojunk_true"] = numstat(la, lb, True)
out["numstat_autojunk_false"] = numstat(la, lb, False)

gp = subprocess.run(["git", "diff", "--no-index", "--numstat", str(A), str(B)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
out["git_numstat"] = gp.stdout.split("\t")[:2]
gp2 = subprocess.run(["git", "diff", "--no-index", "--stat", str(A), str(B)],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
out["git_stat_tail"] = gp2.stdout.strip().splitlines()[-1]

# ── §7.1 块（与 R10 §5.1 同口径）
def sec71(text: str) -> dict:
    i = text.index("### 7.1")
    j = text.index("### 7.2", i)
    blk = text[i:j]
    lf = blk.replace("\r\n", "\n")
    return {"crlf_len": len(blk), "crlf": hashlib.sha256(blk.encode()).hexdigest()[:16],
            "lf_len": len(lf), "lf": hashlib.sha256(lf.encode()).hexdigest()[:16]}


out["sec_7_1_v0_10"] = sec71(ta)
out["sec_7_1_v0_11"] = sec71(tb)

# 七版全同（v0.4–v0.11）
versions = {
    "v0.3": ARCH / "archive" / "FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md",
    "v0.4": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107.md",
    "v0.5": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md",
    "v0.6": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md",
    "v0.7": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md",
    "v0.8": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md",
    "v0.9": ARCH / "FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md",
    "v0.10": A,
    "v0.11": B,
}
blocks = {}
for k, p in versions.items():
    blocks[k] = sec71(p.read_bytes().decode("utf-8"))
out["sec_7_1_all_9_identical"] = len({json.dumps(v, sort_keys=True) for v in blocks.values()}) == 1
out["sec_7_1_per_version"] = blocks

# ── 逆向还原：撤销 4 处改动后必须逐字节等于 v0.10
# banner 从 v0.11 本体定位（不复制文字，避免两处漂移）：§10.3 标题后第一段引用块
_h = tb.index("### 10.3 ")
_blk_start = tb.index("\r\n\r\n", _h) + 4
_blk_end = tb.index("\r\n\r\n", _blk_start)
_banner_lines = tb[_blk_start:_blk_end].split("\r\n")
assert len(_banner_lines) == 3, f"banner 行数 {len(_banner_lines)}"
assert all(x.startswith("> ") for x in _banner_lines), "banner 不是引用块"
assert "（已停用，R10）" in _banner_lines[0], "banner 第 1 行缺「（已停用，R10）」"
assert "recipe 1 = §7.12.4 原文" in _banner_lines[1], "banner 第 2 行缺「recipe 1」"
BANNER = "\r\n" + "\r\n".join(_banner_lines) + "\r\n"
out["banner_shape"] = {"n_lines": len(_banner_lines),
                       "chars": [len(x) for x in _banner_lines],
                       "bytes": [len(x.encode()) for x in _banner_lines],
                       "block_bytes": len(BANNER.encode())}

POINTER = (
    "· **§10.3 已停用（R10）**：停用 banner 在 §10.3 标题下三行；"
    "recipe 1 = §7.12.4 原文为唯一定义，签认三元组，`canonical_digest_recipe` 不实现；"
    "依据 `CONTRACT_REVISION_R10_20261107.md` §7 / `CONTRACT_REVISION_R11_20261107.md` §2"
)
rev = tb
assert rev.count(BANNER) == 1, "banner 不唯一"
rev = rev.replace(BANNER, "", 1)
rev = rev.replace("# 因子化引擎与生产侧执行器 —— 接口契约 v0.11（2026-11-07）",
                  "# 因子化引擎与生产侧执行器 —— 接口契约 v0.10（2026-11-07）", 1)
rev = rev.replace(
    "版本 **v0.11（2026-11-07 R11：§10.3 停用 banner 写入正文 + 版本簿记，判据零改动）**· v0.10（2026-11-07 R10：",
    "版本 **v0.10（2026-11-07 R10：", 1)
rev = rev.replace(POINTER, "", 1)
out["reverse_restore"] = {
    "len": len(rev.encode("utf-8")),
    "sha": hashlib.sha256(rev.encode("utf-8")).hexdigest(),
    "equals_v0_10_bytes": rev.encode("utf-8") == ra,
}

# ── 判据号：banner 与 footer 指针之外必须逐项相同
tail_a = ta[ta.index("本文件正文 sha256"):]
tail_b = tb[tb.index("本文件正文 sha256"):]
body_a = ta[: ta.index("本文件正文 sha256")]
body_b_raw = tb[: tb.index("本文件正文 sha256")]
body_b = body_b_raw.replace(BANNER, "")
pat = re.compile(r"F-A\d+(?:-\d)?")
out["fa_seq"] = {
    "body_equal_after_banner_removal": body_a == body_b,
    "fa_seq_equal": pat.findall(body_a) == pat.findall(body_b),
    "n_a": len(pat.findall(body_a)),
    "n_b": len(pat.findall(body_b)),
}
# 除 banner 外，正文逐字节相同（即：删掉 banner 后，H1 之外的正文与 v0.10 相同 → 用 difflib 结构证明）
body_b_no_h1 = body_b.split("\r\n", 1)[1]
body_a_no_h1 = body_a.split("\r\n", 1)[1]
out["fa_seq"]["body_no_h1_equal"] = body_a_no_h1 == body_b_no_h1

# ── 停用计数
out["stopword"] = {
    "v0_10_full": ta.count("停用"),
    "v0_11_full": tb.count("停用"),
    "v0_11_in_banner": BANNER.count("停用"),
}

# ── 其它契约 v0.7–v0.10 未变
out["untouched"] = {p.name: quad(p.read_bytes()) for p in sorted(ARCH.glob("FACTOR_ENGINE_CONTRACTS_20261107_v0.[789].md"))}
out["untouched"]["FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md"] = quad(ra)

blob = json.dumps(out, ensure_ascii=False, indent=2)
(REPO / "research" / "arch-build-20261107" / "EVIDENCE_v11.json").write_text(blob, encoding="utf-8")
print("wrote EVIDENCE_v11.json")
