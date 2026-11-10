# -*- coding: utf-8 -*-
import glob, hashlib, os, re
files = sorted(glob.glob(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_*.md"))
print(f"files={len(files)}")
for f in files:
    t = open(f, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    i = t.find("### 7.1 ")
    j = t.find("### 7.2 ", i + 1)
    if i < 0 or j < 0:
        print(f"{os.path.basename(f):58} NO-BLOCK"); continue
    core = t[i:j]
    lf = core
    crlf = core.replace("\n", "\r\n")
    print(f"{os.path.basename(f):58} LF {len(lf):5d}/{hashlib.sha256(lf.encode()).hexdigest()[:16]}"
          f"  CRLF {len(crlf):5d}/{hashlib.sha256(crlf.encode()).hexdigest()[:16]}")
