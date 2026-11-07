import hashlib, pathlib, re
repo = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel")
pairs = [
 ("research/arch-build-20261107/R11_draft.md", "docs/architecture/CONTRACT_REVISION_R11_20261107.md"),
 ("research/arch-build-20261107/CLAUSE_draft.md", "docs/architecture/CLAUSE_NAMESPACE_COLLISION_20261107.md"),
]
for src, dst in pairs:
    s = (repo/src).read_text(encoding="utf-8")
    # 统一 CRLF，去掉可能的 BOM/尾随空白差异
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "\r\n")
    if not s.endswith("\r\n"):
        s += "\r\n"
    data = s.encode("utf-8")
    p = repo/dst
    p.write_bytes(data)
    body = data[: data.rindex(b"\r\n", 0, data.rindex(b"\r\n"))+2]
    print(dst)
    print("  size", len(data), "lines", data.count(b"\n"), "chars", len(s))
    print("  full", hashlib.sha256(data).hexdigest())
    print("  has_BOM", data.startswith(b"\xef\xbb\xbf"), "bare_LF", len(re.findall(rb"(?<!\r)\n", data)))
