# -*- coding: utf-8 -*-
from pathlib import Path

raw = Path("C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md").read_bytes()
print("size", len(raw), "CR", raw.count(b"\r"), "LF", raw.count(b"\n"))
t = raw.decode("utf-8")
lines = t.split("\n")
print("lf_lines", len(lines) - 1)
idx = [i + 1 for i, l in enumerate(lines) if l.endswith("\r")]
print("lines_ending_cr", len(idx), idx[:12])
