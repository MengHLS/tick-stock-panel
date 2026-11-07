from pathlib import Path
import hashlib
B=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md")
t=B.read_bytes().decode("utf-8")
lines=t.split("\r\n")
banner=lines[1860:1863]
for i,l in enumerate(banner,1):
    print("banner",i,"chars",len(l),"bytes",len(l.encode()))
print("banner total bytes(with CRLF)", sum(len(l.encode())+2 for l in banner)+2)
foot=lines[2060]
print("footer chars", len(foot), "bytes", len(foot.encode()))
ptr=t[t.index("· **§10.3 已停用（R10）**"):]
ptr=ptr.split("· v0.3 冻结态")[0] if False else None
# pointer exact
p_start=t.index("· **§10.3 已停用（R10）**")
p_end=t.index("\r\n", p_start)
p=t[p_start:p_end]
print("pointer chars", len(p), "bytes", len(p.encode()))
print("pointer:", p)
# 10.4 heading new line no
for i,l in enumerate(lines,1):
    if l.startswith("### 10.4") or l.startswith("### 10.3") or l.startswith("### 10.5"):
        print(i, l[:60])
print("v0.11 footer sha16", hashlib.sha256(t[t.index("本文件正文 sha256"):].encode()).hexdigest()[:16])
