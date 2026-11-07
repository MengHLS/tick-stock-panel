from pathlib import Path
p=Path(r"C:/work/sourcecode/tick-stock-panel/docs/architecture/CONTRACT_REVISION_R10_20261107.md")
t=p.read_bytes().decode("utf-8")
lines=t.split("\r\n")
for i,ln in enumerate(lines,1):
    if "6d3db013" in ln or "a8e88134" in ln or "7.1 八" in ln:
        print(f"{i:4}| {ln[:400]}")
