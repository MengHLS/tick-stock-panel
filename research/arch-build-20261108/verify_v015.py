# -*- coding: utf-8 -*-
"""v0.15 自检（只读）。"""
import hashlib, pathlib, re, sys
V14 = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md")
V15 = pathlib.Path("docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md")
ok = True
def chk(n, c, d=""):
    global ok
    ok = ok and bool(c)
    print(("PASS " if c else "FAIL ") + n + (" — " + str(d) if d else ""), flush=True)

b14, b15 = V14.read_bytes(), V15.read_bytes()
t15 = b15.decode("utf-8")
L15 = t15.split("\r\n")[:-1]

chk("A0 v0.14 未被改动", len(b14) == 292537 and hashlib.sha256(b14).hexdigest()[:16] == "5a26d4825219507a",
    "%d B / %s" % (len(b14), hashlib.sha256(b14).hexdigest()[:16]))
chk("A1 全 CRLF 无裸 CR", b15.count(b"\r\n") == b15.count(b"\n") and b15.count(b"\r") == b15.count(b"\r\n"),
    "crlf=%d" % b15.count(b"\r\n"))
i = b15.rfind("本文件正文 sha256".encode())
body, footer = b15[:i], b15[i:].decode("utf-8")
h = hashlib.sha256(body).hexdigest()
chk("A2 footer sha 自洽", h in footer, h[:16])
m = re.search(r"head -c ([0-9]+) ", footer)
chk("A3 footer head -c 自洽", bool(m) and int(m.group(1)) == len(body), "%s / %s" % (m.group(1) if m else "?", len(body)))
m2 = re.search(r"全文 `([0-9]+)` 行", footer)
chk("A4 footer 行数自洽", bool(m2) and int(m2.group(1)) == len(b15.splitlines()), "%s / %d" % (m2.group(1) if m2 else "?", len(b15.splitlines())))

def blk(t):
    s = t.index("### 7.1"); e = t.index("### 7.2", s); return t[s:e]
k14, k15 = blk(b14.decode("utf-8")), blk(t15)
chk("B1 §7.1 块逐字节相等 v0.14==v0.15", k14 == k15, "%d chars" % len(k15))
chk("B2 CRLF 2,541 / a8e88134f60b504c", len(k15) == 2541 and hashlib.sha256(k15.encode()).hexdigest()[:16] == "a8e88134f60b504c")
lf = k15.replace("\r\n", "\n")
chk("B3 LF 2,514 / 6d3db0139a45f54c", len(lf) == 2514 and hashlib.sha256(lf.encode()).hexdigest()[:16] == "6d3db0139a45f54c")

# P0-X
d = [l for l in L15 if l.startswith("- **同一 `submitted_id` 命中多码时只报一码")]
chk("C1 去重条唯一", len(d) == 1)
if d:
    x = d[0]
    for k, lab in [("`FS04` > `FS03` > `FS06` > `FS01`", "优先级"),
                   ("去重发生在生成 `detail` 之前", "去重先于 detail"),
                   ("只跟最终 `code` 走", "status 跟码"),
                   ("≥2 个不同 `submitted_id`", "violations 触发"),
                   ("本条不改 `F-A42-2`", "F-A42-2 不破"),
                   ("恒为 7 键", "单 id 7 键")]:
        chk("C2-%s" % lab, k in x)
chk("C3 追加键表行已改", len([l for l in L15 if l.startswith("| 批量入口（`/run-all`、`/factor/batch`），**或**")]) == 1)
chk("C4 F-A42-2 行仍在且未改", any(l.startswith("| F-A42-2 |") for l in L15))

# P0-Y
e = [l for l in L15 if l.startswith("| E4-A4 |")]
chk("D1 E4-A4 唯一", len(e) == 1)
if e:
    x = e[0]
    for k, lab in [("**15** 个交易日", "①15天"),
                   ("`2024-02-29` 在轴上", "②02-29在轴"),
                   ("实际 `month_end` 是 **`2024-02-29`**", "②month_end"),
                   ("`2024-02-09`（除夕）**不在**轴上", "③02-09不在"),
                   ("is_rebalance(2024-02-23) == False", "④02-23"),
                   ("week_end(2024-02-05) == 2024-02-08", "⑤week_end")]:
        chk("D2-%s" % lab, k in x)

# P2-1
chk("E1 12.2 标题 D10", any(l.startswith("### 12.2 编号登记：D5 = G2 成交口径，D10 =") for l in L15))
chk("E2 12.2 表行 D10", any(l.startswith("| **D10** | **`observed_bars` 口径偏差**") for l in L15))
chk("E3 12.2 表行 D5 完好", any(l.startswith("| **D5** | **G2 成交口径**") for l in L15))
body_only = t15[:t15.rfind("本文件正文 sha256")]
chk("E4 正文删「不自行另立号」", "本契约不自行另立号" not in body_only)
chk("E5 研究侧列待同步项", "待同步项" in t15)
chk("E6 :126 登记号 D10", "登记号 **D10**" in t15)
chk("E7 D5 核准句改 3 处", "全文 `D5` 只有 3 处" in t15)

bad = []
for n, l in enumerate(L15, 1):
    if "D6" in l and "observed_bars" in l:
        if any(k in l for k in ("不再使用", "D6 → D10", "D6`→`D10", "`D6` 仅保留")):
            continue
        bad.append(n)
chk("F1 无「D6 = observed_bars」断言", not bad, "可疑 %s" % bad)

f14 = [l for l in b14.decode("utf-8").split("\r\n") if re.match(r"\| ?`?F-A\d", l)]
f15 = [l for l in L15 if re.match(r"\| ?`?F-A\d", l)]
chk("G1 判据行逐行相等", f14 == f15, "%d 行" % len(f15))
n14 = set(re.findall(r"F-A\d+", b14.decode("utf-8")))
n15 = set(re.findall(r"F-A\d+", t15))
chk("G2 未新增/删除判据号", n14 == n15, "差 %s" % (n14 ^ n15))

VERS = [("v0.3","docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md",89833,"5eb97724"),
        ("v0.4","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md",128007,"5bd81a74"),
        ("v0.5","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md",138729,"c7740508"),
        ("v0.6","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md",162361,"946a1d86"),
        ("v0.7","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md",193586,"5a87d4b0"),
        ("v0.8","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md",206608,"2cf85ccb"),
        ("v0.9","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md",228478,"5d0abbb5"),
        ("v0.10","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md",244093,"8a3115aa"),
        ("v0.11","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md",245364,"c2eec518"),
        ("v0.12","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md",269092,"d7df40ff"),
        ("v0.13","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md",277296,"a1374eb5"),
        ("v0.14","docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md",292537,"5a26d482")]
for nm, pth, sz, pre in VERS:
    pp = pathlib.Path(pth)
    if not pp.exists():
        chk("H-%s 存在" % nm, False, pth); continue
    bb = pp.read_bytes(); hh = hashlib.sha256(bb).hexdigest()[:8]
    chk("H-%s 未改动" % nm, hh == pre and len(bb) == sz, "%d B / %s" % (len(bb), hh))

print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL", flush=True)
sys.exit(0 if ok else 1)

