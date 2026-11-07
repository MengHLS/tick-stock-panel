import pathlib
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/R11_draft.md")
t = p.read_text(encoding="utf-8")
for a,b in [("245314","245364"),("243159","243209"),("| 242,303 B | **243,209 B** | +856 |","| 242,303 B | **243,209 B** | +906 |")]:
    print(a, "->", t.count(a)); t = t.replace(a,b)
p.write_text(t, encoding="utf-8", newline="\n")
for token in ("245314","243159","+856","+1,221","856"):
    print("residual", token, t.count(token))
