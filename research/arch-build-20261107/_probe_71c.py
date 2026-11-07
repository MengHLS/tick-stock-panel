import hashlib
from pathlib import Path
t=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md").read_bytes().decode("utf-8")
lines=t.split("\r\n")
N=len(lines)
# find any contiguous range 760..800 whose CRLF join length is 2514 or 2541
for i in range(700, 800):
    for j in range(i+1, min(i+45, N)):
        seg_crlf="\r\n".join(lines[i:j])
        if len(seg_crlf) in (2514, 2541, 2523):
            print("CRLF", i+1, j, len(seg_crlf), hashlib.sha256(seg_crlf.encode()).hexdigest()[:8])
        seg_lf=seg_crlf.replace("\r\n","\n")
        if len(seg_lf) in (2514, 2541, 2523):
            print("LF  ", i+1, j, len(seg_lf), hashlib.sha256(seg_lf.encode()).hexdigest()[:8])
print("total chars", len(t), "lines", N)
print("765-791 LF len", len("\n".join(lines[764:791])))
print("765-791 CRLF len", len("\r\n".join(lines[764:791])))
