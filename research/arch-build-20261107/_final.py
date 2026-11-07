from pathlib import Path
A=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md")
B=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md")
ta=A.read_bytes().decode("utf-8"); tb=B.read_bytes().decode("utf-8")
print("chars", len(ta), len(tb), len(tb)-len(ta))
print("bytes", len(ta.encode()), len(tb.encode()), len(tb.encode())-len(ta.encode()))
fa=len(ta[:ta.index("本文件正文 sha256")]); fb=len(tb[:tb.index("本文件正文 sha256")])
print("body chars", fa, fb, fb-fa)
print("footer chars", len(ta)-fa, len(tb)-fb, (len(tb)-fb)-(len(ta)-fa))
lines=tb.split("\r\n")
b=lines[1860:1863]
print("banner chars", [len(x) for x in b], "sum", sum(len(x) for x in b))
p_start=tb.index("· **§10.3 已停用（R10）**"); p_end=tb.index("\r\n", p_start)
ptr=tb[p_start:p_end]
print("pointer chars", len(ptr), "bytes", len(ptr.encode()))
foot=tb[tb.index("本文件正文 sha256"):]
print("footer chars", len(foot), "bytes", len(foot.encode()))
print("footer old chars", len(ta[ta.index("本文件正文 sha256"):]))
# 定位 10.3 段内各行
for i in range(1858,1876):
    print(i+1, repr(lines[i][:50]))
