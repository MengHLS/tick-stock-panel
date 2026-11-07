from pathlib import Path
t=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md").read_bytes().decode("utf-8")
lines=t.split("\r\n")
out=[]
for i in range(1856, 1868):
    out.append(f"{i+1:5}| {lines[i]}")
Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_peek.txt").write_text("\n".join(out), encoding="utf-8")
print("ok")
