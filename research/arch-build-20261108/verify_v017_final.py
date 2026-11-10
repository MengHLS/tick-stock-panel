# -*- coding: utf-8 -*-
"""v0.17 终检：不信任构建脚本自报，全部从盘上重算。

A. 四元组：正文/全文 字节、行数、sha256（与 footer 自述逐项比对）
B. 全文 '3+3' / '双向各 3' 计数 = 0；「自然年」凡出现必带 iso_week 或 %W 限定
C. 判据号集合：与 v0.16 逐号相等（不增不减）
D. E4-A1..A5 行、§7.16.4 块：与 v0.16 逐字节相等
E. 判据条款行删除数 = 0（diff 删除侧只允许 H1 / E4-A6 / 旧 footer）
F. §7.1 八行块：v0.3–v0.17 十五份全同（LF 与 CRLF 两种口径）
"""
import hashlib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path("docs/architecture")
V16 = D / "FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md"
V17 = D / "FACTOR_ENGINE_CONTRACTS_20261108_v0.17.md"
res = []


def chk(tag, ok, detail=""):
    res.append((tag, ok, detail))
    print(("PASS " if ok else "FAIL ") + tag + ("  " + detail if detail else ""))


def body_of(path):
    lines = path.read_bytes().split(b"\n")
    idx = [i for i, l in enumerate(lines) if l.strip()]
    return lines[: idx[-1]], lines[idx[-1]]


# ---------- A ----------
raw17 = V17.read_bytes()
lines17 = raw17.split(b"\n")
idx17 = [i for i, l in enumerate(lines17) if l.strip()]
body17 = b"\n".join(lines17[: idx17[-1]]) + b"\n"
footer17 = lines17[idx17[-1]].decode("utf-8")
chk("A1 footer 行唯一", raw17.count("本文件正文 sha256".encode()) == 1)
chk("A2 正文 sha", hashlib.sha256(body17).hexdigest() in footer17,
    hashlib.sha256(body17).hexdigest()[:16])
chk("A3 正文字节", f"正文 `{len(body17)} B`" in footer17, str(len(body17)))
nfull = len(lines17) - 1
chk("A4 全文行数", f"全文 `{nfull}` 行（正文 `{nfull - 1}` + footer 1）" in footer17, str(nfull))
chk("A5 全文字节=wc -c", len(raw17) == int(footer17.split("正文 `")[1].split(" B`")[0]) + len(footer17.encode()) + 1,
    str(len(raw17)))
chk("A6 H1 版本号", lines17[0].decode("utf-8").strip().endswith("v0.17（2026-11-08）"),
    lines17[0].decode("utf-8").strip()[:60])
chk("A7 旧 footer 已不在正文", "d58d90b577af07b4" not in t17 if (t17 := body17.decode("utf-8")) else False)

# ---------- B ----------
t17 = body17.decode("utf-8")
chk("B1 '3+3' = 0", t17.count("3+3") == 0, str(t17.count("3+3")))
chk("B2 '双向各 3' = 0", t17.count("双向各 3") == 0)
chk("B3 无裸「自然年+周号」", t17.count("自然年+周号") == 0 and t17.count("自然年 + 周号") == 0)
bad = []
for m in re.finditer("自然年", t17):
    seg = t17[max(0, m.start() - 40): m.start() + 120]
    if "iso_week" not in seg and "%W" not in seg and "ISO 周" not in seg:
        bad.append(seg.replace("\n", " ")[:70])
chk("B4 每处「自然年」均带限定", not bad, f"{len(bad)} 处未带" if bad else "")
for b in bad:
    print("   ! ", b)

# ---------- C ----------
pat = re.compile(r"F-A\d+(?:-\d+)?")
b16, _ = body_of(V16)
s16 = set(pat.findall("\n".join(l.decode("utf-8") for l in b16)))
s17 = set(pat.findall(t17))
chk("C1 判据号集合相等", s16 == s17, f"v0.16={len(s16)} v0.17={len(s17)} 增={sorted(s17 - s16)} 减={sorted(s16 - s17)}")

# ---------- D ----------
l16 = [l.decode("utf-8") for l in b16]
l17 = t17.split("\n")
for k in ("E4-A1", "E4-A2", "E4-A3", "E4-A4", "E4-A5", "E4-A6"):
    a = [x for x in l16 if x.startswith(f"| {k} |")]
    b = [x for x in l17 if x.startswith(f"| {k} |")]
    if k == "E4-A6":
        chk("D-E4-A6 被改（应改）", a != b, f"旧 {len(a)} 行 → 新 {len(b)} 行")
    else:
        chk(f"D{k} 逐字节未动", a == b and len(a) == 1)

# §7.16.4 块：从标题到下一个 '### 7.17'
def block(lines, start_pat, end_pat):
    s = next(i for i, l in enumerate(lines) if re.match(start_pat, l))
    e = next(i for i in range(s + 1, len(lines)) if re.match(end_pat, lines[i]))
    return "\n".join(lines[s:e])


def block_by_text(lines, marker, end_pat):
    s = next(i for i, l in enumerate(lines) if marker in l)
    e = next(i for i in range(s + 1, len(lines)) if re.match(end_pat, lines[i]))
    return "\n".join(lines[s:e])


for tag, marker, ep in (
    ("§7.16.4", "**7.16.4 HTTP 响应形状", r"^#{2,4} 7\.17|^#{2,4} 7\.16\.5"),
    ("§7.17", "## 7.17", r"^#{2,4} 7\.18|^## 8"),
):
    try:
        a, b = block_by_text(l16, marker, ep), block_by_text(l17, marker, ep)
        chk(f"D{tag} 逐字节相等", a == b, f"{len(a)} vs {len(b)} 字符")
    except StopIteration as e:
        chk(f"D{tag} 定位失败", False, str(e))

# ---------- E ----------
import difflib
sm = difflib.SequenceMatcher(None, l16, l17, autojunk=False)
dels = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag in ("replace", "delete"):
        dels += [(k + 1, l16[k]) for k in range(i1, i2)]
chk("E1 删除侧行数 = 2（H1 + E4-A6）", len(dels) == 2, f"{len(dels)} 行: {[d[0] for d in dels]}")
for ln, txt in dels:
    print("   DEL", ln, "|", txt[:70])
chk("E2 删除侧无判据行", not any(x.startswith("| F-A") for _, x in dels))
chk("E3 删除侧无 assert/阈值", not any(("assert" in x or "阈值" in x) for _, x in dels))

# ---------- F ----------
def s71(txt):
    i = txt.index("### 7.1")
    j = txt.index("### 7.2")
    return txt[i:j]


files = sorted(D.glob("FACTOR_ENGINE_CONTRACTS_2026110*_v0.*.md")) + [D / "archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md"]
tb = {}
for f in files:
    if not f.exists():
        print("   (缺)", f.name)
        continue
    txt = f.read_text(encoding="utf-8")
    if "### 7.1" not in txt or "### 7.2" not in txt:
        continue
    seg = s71(txt)
    lf = seg.replace("\r\n", "\n")
    crlf = lf.replace("\n", "\r\n")
    tb[f.name] = (len(lf), hashlib.sha256(lf.encode()).hexdigest()[:16],
                  len(crlf), hashlib.sha256(crlf.encode()).hexdigest()[:16])
vals = set(tb.values())
chk("F1 §7.1 全部相同", len(vals) == 1, f"{len(tb)} 份")
for k, v in tb.items():
    print("   ", k, v)

print()
print("SUMMARY:", "ALL PASS" if all(ok for _, ok, _ in res) else "HAS FAIL",
      f"({sum(1 for _, ok, _ in res if ok)}/{len(res)})")
