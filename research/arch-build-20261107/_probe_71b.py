import hashlib
from pathlib import Path
t=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md").read_bytes().decode("utf-8")
lines=t.split("\r\n")
target_lf=("6d3db013", 2514)
target_crlf=("a8e88134", 2541)
hits=[]
N=len(lines)
for i in range(760, 800):
    for j in range(i+1, min(i+20, N)):
        seg_crlf="\r\n".join(lines[i:j])
        seg_lf=seg_crlf.replace("\r\n","\n")
        for seg, tag in ((seg_lf,"LF"),(seg_crlf,"CRLF")):
            h=hashlib.sha256(seg.encode("utf-8")).hexdigest()[:8]
            if h==(target_lf[0] if tag=="LF" else target_crlf[0]):
                hits.append((tag,i+1,j,len(seg),h))
for x in hits: print(x)
print("---- try with trailing newline ----")
hits2=[]
for i in range(760, 800):
    for j in range(i+1, min(i+25, N)):
        for trail in ("","\r\n","\n"):
            seg_crlf="\r\n".join(lines[i:j])+trail
            seg_lf=seg_crlf.replace("\r\n","\n")
            for seg, tag in ((seg_lf,"LF"),(seg_crlf,"CRLF")):
                h=hashlib.sha256(seg.encode("utf-8")).hexdigest()[:8]
                tgt = target_lf[0] if tag=="LF" else target_crlf[0]
                if h==tgt:
                    hits2.append((tag,i+1,j,repr(trail),len(seg),h))
for x in hits2: print(x)
