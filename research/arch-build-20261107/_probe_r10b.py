from pathlib import Path
t=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/CONTRACT_REVISION_R10_20261107.md").read_bytes().decode("utf-8")
lines=t.split("\r\n")
for i in range(462, 500):
    print(f"{i+1:4}| {lines[i]}")
