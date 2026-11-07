import pathlib
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/R11_draft.md")
t = p.read_text(encoding="utf-8")
pairs = [("6ea5accb…0302fc", "aa6e06c3…d8525b2"), ("d1349af5…d8dc57f", "c2eec518…c0c3c58d")]
for a,b in pairs:
    print(a, t.count(a)); t = t.replace(a,b)
p.write_text(t, encoding="utf-8", newline="\n")
for token in ("6ea5accb","d1349af5","245,314","+1,221"):
    print("residual", token, t.count(token))
# 摘要打印关键行
for ln in t.split("\n"):
    if any(k in ln for k in ("| size","| 行数","正文前缀","正文 sha256","全文 sha256","| footer","字符数","mtime","字节账","字符账","三行尺寸","BANNER","期望：","输出：","size 2")):
        print(">>", ln[:220])
