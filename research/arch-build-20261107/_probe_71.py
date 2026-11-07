from pathlib import Path
t=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md").read_bytes().decode("utf-8")
lines=t.split("\r\n")
print("n lines", len(lines))
for i in range(764, 796):
    print(f"{i+1:5}| {lines[i][:220]}")
