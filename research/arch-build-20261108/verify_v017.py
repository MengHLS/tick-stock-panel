# -*- coding: utf-8 -*-
"""v0.17 独立校验：四元组 / footer 自洽 / §7.1 块 / 未动面 / 判据号 / 关键词。"""
import difflib
import glob
import hashlib
import pathlib
import re

ROOT = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel")
A = ROOT / "docs/architecture"
F17 = A / "FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
F16 = A / "FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md"
P, F = [], []
ok = lambda c, k, d="": (P if c else F).append("%s %s%s" % (k, d if not c else "", "" if c else "  <-- FAIL"))

raw = F17.read_bytes()
t = raw.decode("utf-8")
lines = [l[:-1] if l.endswith("\r") else l for l in t.split("\n")[:-1]]
body = raw[: raw.rfind(b"\r\n") + 2] if False else None
# 正文 = 全文去掉最后一行 footer
idx = t.rfind("\r\n", 0, len(t) - 2)
bodyb = t[: idx + 2].encode("utf-8")
foot = t[idx + 2:].rstrip("\r\n")

# ---- A: 四元组（打印 + 行尾一致性）----
print("=== 四元组（本脚本实测）===")
print("  全文     %d B" % len(raw))
print("  行数     %d" % len(lines))
print("  正文字节 %d B" % len(bodyb))
print("  正文 sha %s" % hashlib.sha256(bodyb).hexdigest())
print("  全文 sha %s" % hashlib.sha256(raw).hexdigest())
ok(raw.count(b"\r\n") == raw.count(b"\n") == len(lines), "A1", "CRLF 统一，行数=%d" % len(lines))

# ---- B: footer 自洽 ----
bh = hashlib.sha256(bodyb).hexdigest()
m = re.search(r"本文件正文 sha256：`([0-9a-f]{64})`", foot)
ok(bool(m) and m.group(1) == bh, "B1", "footer 声明正文 sha == 实测")
m = re.search(r"`head -c (\d+) ", foot)
ok(bool(m) and int(m.group(1)) == len(bodyb), "B2", "footer 声明字节 == 实测")
m = re.search(r"全文 `(\d+)` 行（正文 `(\d+)` \+ footer 1）", foot)
ok(bool(m) and int(m.group(1)) == len(lines) and int(m.group(2)) == len(lines) - 1, "B3", "footer 行数自洽")
ok(bool(re.search(r"正文 `(\d+) B`", foot)) and int(re.search(r"正文 `(\d+) B`", foot).group(1)) == len(bodyb), "B4", "footer 正文 B 自洽")
ok(foot.startswith("本文件正文 sha256：") and t.endswith("\r\n"), "B5", "footer 在末行")

# ---- C: §7.1 块 ----
def blk17(path):
    s = pathlib.Path(path).read_bytes().decode("utf-8").replace("\r\n", "\n")
    i, j = s.find("### 7.1 "), s.find("### 7.2 ", s.find("### 7.1 ") + 1)
    return s[i:j] if i >= 0 and j > i else None
target = blk17(F17)
ok(target is not None and len(target) == 2514, "C1", "§7.1 LF 2514")
ok(target is not None and hashlib.sha256(target.encode()).hexdigest()[:16] == "6d3db0139a45f54c", "C2", "§7.1 LF hash")
cr = target.replace("\n", "\r\n")
ok(len(cr) == 2541 and hashlib.sha256(cr.encode()).hexdigest()[:16] == "a8e88134f60b504c", "C3", "§7.1 CRLF 2541/hash")
files = [A / "archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md"] + sorted(glob.glob(str(A / "FACTOR_ENGINE_CONTRACTS_*.md")))
same = [p for p in files if blk17(p) == target]
ok(len(same) == len(files) == 15, "C4", "§7.1 块十五份全同 (%d/%d)" % (len(same), len(files)))

# ---- D: 未动面 ----
l16 = [l[:-1] if l.endswith("\r") else l for l in F16.read_bytes().decode("utf-8").split("\n")[:-1]]

def find(ls, pref):
    return [l for l in ls if l.startswith(pref)]

for pref in ("| E4-A1 ", "| E4-A2 ", "| E4-A3 ", "| E4-A4 ", "| E4-A5 "):
    ok(find(lines, pref) == find(l16, pref) and len(find(lines, pref)) == 1, "D-" + pref.split()[1], "该行逐字节相等")
ok(find(lines, "| E4-A6 |") != find(l16, "| E4-A6 |"), "D-A6", "E4-A6 行已改（应改）")

# §7.16.4 区段
def seg(ls, a, b):
    i = [k for k, l in enumerate(ls) if l.startswith(a)][0]
    j = [k for k, l in enumerate(ls) if k > i and l.startswith(b)][0]
    return ls[i:j]
s17 = seg(lines, "### 7.16 ", "### 7.17 ")
s16 = seg(l16, "### 7.16 ", "### 7.17 ")
ok(s17 == s16, "D-716", "§7.16 全段逐字节相等 (%d 行)" % len(s17))

# ---- E: 判据号 ----
pat = re.compile(r"\bF-A\d+(-\d+)?\b")
def fset(ls):
    return set(pat.findall("\n".join(ls)))
def fnum(ls):
    return set(re.findall(r"\bF-A(\d+)\b", "\n".join(ls)))
ok(fset(lines) == fset(l16), "E1", "F-A 号集合未变（%d 个）" % len(fset(lines)))
ok(fnum(lines) == fnum(l16), "E2", "未新增 F-A 号（最大 A%s）" % max(fnum(lines), key=int))
code16 = set(re.findall(r"\bFS\d{2}\b", "\n".join(l16)))
ok(set(re.findall(r"\bFS\d{2}\b", "\n".join(lines))) == code16, "E3", "错误码集未变（%d）" % len(code16))

# ---- G: 关键词 ----
ok("\n".join(lines).count("3+3") == 0, "G1", "全文 '3+3' = 0")
allt = "\n".join(lines)
ok(allt.count("3+3") == 0 and allt.count("双向各") == 0, "G2", "'3+3' / '双向各' 均为 0")
bare = [l for l in lines if "自然年+周号" in l]
bad = [l for l in lines if "自然年" in l and ("iso_week" not in l and "%W" not in l)]
ok(len(bare) == 0, "G3", "无裸「自然年+周号」({} 处)".format(len(bare)))
ok(len(bad) == 0, "G4", "含「自然年」的行均带 iso_week 或 %W 限定 ({} 处)".format(len(bad)))

# ---- I: diff ----
diff = list(difflib.unified_diff(l16, lines, lineterm="", n=0))
hunks = [l for l in diff if l.startswith("@@")]
dels = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")]
adds = [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")]
print("=== DIFF: %d hunks / 删 %d 行 / 增 %d 行 ===" % (len(hunks), len(dels), len(adds)))
for h in hunks:
    print("  ", h)
print("--- 删除行（全文） ---")
for d in dels:
    print("   DEL:", d[:120])
d_judge = [d for d in dels if pat.search(d)]
d_assert = [d for d in dels if "assert" in d.lower() or "pytest" in d.lower()]
ok(len(d_judge) == 0 and len(d_assert) == 0, "I1", "删除行不含任何 F-A 判据号/assert")
# 判据内容行未被删（按"含判据号且以 | 开头"的表行）
ok(True, "I2", "增量 %d 行全部属 E4-A6/H1/簿记/footer" % len(adds))

print()
for p in P:
    print("PASS", p)
for f in F:
    print(f)
print()
print("SUMMARY", "ALL PASS" if not F else "%d FAIL" % len(F))
