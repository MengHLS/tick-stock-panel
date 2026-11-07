import pathlib
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/verify_v11_20261107.py")
t = p.read_text(encoding="utf-8")
start = t.index('BANNER = (')
end = t.index('POINTER = (')
new = '''# banner 从 v0.11 本体定位（不复制文字，避免两处漂移）：§10.3 标题后第一段引用块
_h = tb.index("### 10.3 ")
_blk_start = tb.index("\\r\\n\\r\\n", _h) + 4
_blk_end = tb.index("\\r\\n\\r\\n", _blk_start)
_banner_lines = tb[_blk_start:_blk_end].split("\\r\\n")
assert len(_banner_lines) == 3, f"banner 行数 {len(_banner_lines)}"
assert all(x.startswith("> ") for x in _banner_lines), "banner 不是引用块"
assert "（已停用，R10）" in _banner_lines[0], "banner 第 1 行缺「（已停用，R10）」"
assert "recipe 1 = §7.12.4 原文" in _banner_lines[1], "banner 第 2 行缺「recipe 1」"
BANNER = "\\r\\n" + "\\r\\n".join(_banner_lines) + "\\r\\n"
out["banner_shape"] = {"n_lines": len(_banner_lines),
                       "chars": [len(x) for x in _banner_lines],
                       "bytes": [len(x.encode()) for x in _banner_lines],
                       "block_bytes": len(BANNER.encode())}

'''
t = t[:start] + new + t[end:]
p.write_text(t, encoding="utf-8", newline="\n")
print("verify patched")
