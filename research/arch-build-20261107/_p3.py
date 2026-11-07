import pathlib
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/verify_v11_20261107.py")
t = p.read_text(encoding="utf-8")
t = t.replace('pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/EVIDENCE_v11.json").write_text(blob, encoding="utf-8")',
              '(REPO / "research" / "arch-build-20261107" / "EVIDENCE_v11.json").write_text(blob, encoding="utf-8")')
p.write_text(t, encoding="utf-8", newline="\n")
print("ok")
