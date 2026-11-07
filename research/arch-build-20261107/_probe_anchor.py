from pathlib import Path
raw = Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md").read_bytes()
cands = [
 "v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`",
 "逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`",
 "`docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`",
]
for c in cands:
    print(raw.count(c.encode("utf-8")), len(c), c[:40])
# where do they occur (line numbers)
lines = raw.split(b"\r\n")
for idx, ln in enumerate(lines, 1):
    if b"v0.3_FROZEN.md" in ln:
        print("line", idx, "len", len(ln))
