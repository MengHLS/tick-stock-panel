# -*- coding: utf-8 -*-
"""v0.14 自检（只读）。python research/arch-build-20261108/verify_v014.py"""
import hashlib
import pathlib
import re
import sys

V13 = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md")
V14 = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md")
ok = True


def chk(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (" — " + str(detail) if detail else ""), flush=True)


b13 = V13.read_bytes()
b14 = V14.read_bytes()
t14 = b14.decode("utf-8")
L14 = t14.split("\r\n")[:-1]

# A 底本未动
chk("A1 v0.13 未被改动", len(b13) == 277296 and hashlib.sha256(b13).hexdigest()[:16] == "a1374eb5cc526e11",
    "%d B / %s" % (len(b13), hashlib.sha256(b13).hexdigest()[:16]))

# B 换行与 footer 自洽
chk("B1 全 CRLF、无裸 CR", b14.count(b"\r\n") == b14.count(b"\n") and b14.count(b"\r") == b14.count(b"\r\n"),
    "crlf=%d" % b14.count(b"\r\n"))
i = b14.rfind("本文件正文 sha256".encode())
body = b14[:i]
footer = b14[i:].decode("utf-8")
h = hashlib.sha256(body).hexdigest()
chk("B2 footer 自述 sha == 正文字节复算", h in footer, h[:16])
m = re.search(r"head -c ([0-9]+) ", footer)
chk("B3 footer 自述 head -c == 正文字节", bool(m) and int(m.group(1)) == len(body), "%s / %s" % (m.group(1) if m else "?", len(body)))
m2 = re.search(r"全文 `([0-9]+)` 行", footer)
chk("B4 footer 自述行数 == 复算", bool(m2) and int(m2.group(1)) == len(b14.splitlines()), "%s / %d" % (m2.group(1) if m2 else "?", len(b14.splitlines())))
chk("B5 正文以 CRLF 结尾（footer 前）", body.endswith(b"\r\n"))

# C §7.1 块十二份全同
def blk(t):
    s = t.index("### 7.1")
    e = t.index("### 7.2", s)
    return t[s:e]

k13 = blk(b13.decode("utf-8"))
k14 = blk(t14)
chk("C1 §7.1 块 v0.13 == v0.14 逐字节", k13 == k14, "%d chars" % len(k14))
chk("C2 CRLF 口径 2,541 / a8e88134f60b504c",
    len(k14) == 2541 and hashlib.sha256(k14.encode()).hexdigest()[:16] == "a8e88134f60b504c",
    "%d / %s" % (len(k14), hashlib.sha256(k14.encode()).hexdigest()[:16]))
lf = k14.replace("\r\n", "\n")
chk("C3 LF 口径 2,514 / 6d3db0139a45f54c",
    len(lf) == 2514 and hashlib.sha256(lf.encode()).hexdigest()[:16] == "6d3db0139a45f54c",
    "%d / %s" % (len(lf), hashlib.sha256(lf.encode()).hexdigest()[:16]))

# D P0-X
dedup = [l for l in L14 if l.startswith("- **同一 `submitted_id` 命中多码时只报一码")]
chk("D1 去重条唯一存在", len(dedup) == 1, "%d 行" % len(dedup))
if dedup:
    d = dedup[0]
    chk("D2 去重条写明优先级 FS04>FS03>FS06>FS01", "`FS04` > `FS03` > `FS06` > `FS01`" in d)
    chk("D3 去重条写明「去重先于 detail 生成」", "去重发生在生成 `detail` 之前" in d)
    chk("D4 去重条写明 status 只跟最终 code 走", "只跟最终 `code` 走" in d)
    chk("D5 去重条写明 violations 仅 ≥2 不同 id", "≥2 个不同 `submitted_id`" in d)
    chk("D6 去重条不改 F-A42-2", "本条不改 `F-A42-2`" in d)
row = [l for l in L14 if l.startswith("| 批量入口（`/run-all`、`/factor/batch`），**或**")]
chk("D7 追加键表行已改", len(row) == 1, "%d 行" % len(row))

# E P0-Y 五条
e4 = [l for l in L14 if l.startswith("| E4-A4 |")]
chk("E1 E4-A4 行唯一", len(e4) == 1, "%d 行" % len(e4))
if e4:
    x = e4[0]
    for key, label in [
        ("**15** 个交易日", "①15 天"),
        ("`2024-02-29` 在轴上", "②02-29 在轴上"),
        ("`2024-02-29`", "②month_end==02-29"),
        ("`2024-02-09`（除夕）**不在**轴上", "③02-09 不在轴上"),
        ("is_rebalance(2024-02-23) == False", "④is_rebalance(02-23)==False"),
        ("week_end(2024-02-05) == 2024-02-08", "⑤week_end(02-05)==02-08"),
        ("实际 `month_end` 是 **`2024-02-29`**", "反例警戒 a"),
        ("不得", "反例警戒 b"),
    ]:
        chk("E2-%s" % label, key in x)

# F P2-1
chk("F1 §12.2 标题已改 D10", any(l.startswith("### 12.2 编号登记：D5 = G2 成交口径，D10 =") for l in L14))
chk("F2 §12.2 表行 D10", any(l.startswith("| **D10** | **`observed_bars` 口径偏差**") for l in L14))
chk("F3 §12.2 表行 D5 完好", any(l.startswith("| **D5** | **G2 成交口径**") for l in L14))
body14 = t14[:t14.rfind("本文件正文 sha256")]
chk("F4 正文删「本契约不自行另立号」", "本契约不自行另立号" not in body14)
chk("F5 研究侧「立 D5」列为待同步项", "待同步项" in t14 and "立 D5" in t14)
chk("F6 :126 登记号改 D10", "登记号 **D10**" in t14)

# G D6 不再指 observed_bars（排除否定句与变更记录）
bad = []
for n, l in enumerate(L14, 1):
    if "D6" in l and "observed_bars" in l:
        if ("不再使用" in l) or ("D6 → D10" in l) or ("D6`→`D10" in l) or ("`D6` 仅保留" in l):
            continue
        bad.append(n)
chk("G1 无「D6 = observed_bars」式断言", not bad, "可疑行 %s" % bad)

# H 判据号零改动
f13 = [l for l in b13.decode("utf-8").split("\r\n") if re.match(r"\| ?`?F-A\d", l)]
f14 = [l for l in L14 if re.match(r"\| ?`?F-A\d", l)]
chk("H1 判据行数与内容逐行相等", f13 == f14, "%d 行" % len(f14))
nums13 = set(re.findall(r"F-A\d+", b13.decode("utf-8")))
nums14 = set(re.findall(r"F-A\d+", t14))
chk("H2 未新增判据号", nums14 == nums13, "新增 %s" % (nums14 - nums13))

# I 其余版本未被改动（显式路径：v0.3 在 archive/、v0.4 为无后缀文件）
VERSIONS = [
    ("v0.3", "docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md", 89833, "5eb97724"),
    ("v0.4", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md", 128007, "5bd81a74"),
    ("v0.5", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md", 138729, "c7740508"),
    ("v0.6", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md", 162361, "946a1d86"),
    ("v0.7", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md", 193586, "5a87d4b0"),
    ("v0.8", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md", 206608, "2cf85ccb"),
    ("v0.9", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md", 228478, "5d0abbb5"),
    ("v0.10", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md", 244093, "8a3115aa"),
    ("v0.11", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md", 245364, "c2eec518"),
    ("v0.12", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md", 269092, "d7df40ff"),
    ("v0.13", "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md", 277296, "a1374eb5"),
]
for _name, _path, _size, _pre in VERSIONS:
    _pp = pathlib.Path(_path)
    if not _pp.exists():
        chk("I-%s 存在" % _name, False, _path)
        continue
    _bb = _pp.read_bytes()
    _hh = hashlib.sha256(_bb).hexdigest()[:8]
    chk("I-%s 未改动" % _name, _hh == _pre and len(_bb) == _size, "%d B / %s" % (len(_bb), _hh))


print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL", flush=True)
sys.exit(0 if ok else 1)
