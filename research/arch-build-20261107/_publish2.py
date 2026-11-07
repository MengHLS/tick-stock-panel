import hashlib, pathlib, re
repo = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel")
src = repo/"research/arch-build-20261107/R11_draft.md"
dst = repo/"docs/architecture/CONTRACT_REVISION_R11_20261107.md"
s = src.read_text(encoding="utf-8").replace("\r\n","\n").replace("\n","\r\n")
if not s.endswith("\r\n"): s += "\r\n"
data = s.encode("utf-8")
dst.write_bytes(data)
print("R11", len(data), "bytes /", data.count(b"\n"), "lines /", len(s), "chars")
print("full", hashlib.sha256(data).hexdigest())
print("bare_LF", len(re.findall(rb"(?<!\r)\n", data)), "BOM", data.startswith(b"\xef\xbb\xbf"))
