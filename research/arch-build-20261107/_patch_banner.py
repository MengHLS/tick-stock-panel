import pathlib, re
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/build_contract_v11.py")
t = p.read_text(encoding="utf-8")
lines = t.split("\n")
idx = [i for i, ln in enumerate(lines) if "现行唯一定义" in ln]
print("hits", idx)
for i in idx:
    print(repr(lines[i][:80]))
new_line = ('    "> **现行唯一定义 = recipe 1 = §7.12.4 原文**（剔除 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键）；'
            '签认仍为**三元组** `(canonical_digest, schema_version, scanned_sources)`，`canonical_digest_recipe` 字段**不实现**；'
            '本节「本版起新产物必须用它」/「签认由三元组升为四元组」/「不可比不得判失败」/「L2 起产物必须 `\\"2\\"`」四句一并不生效；'
            '任何声称「recipe 2 合规」的产物按**不合规**处理。",')
assert len(idx) == 1, idx
lines[idx[0]] = new_line
p.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print("patched ->", new_line[:60])
print("check:", [ln for ln in p.read_text(encoding='utf-8').split('\n') if '现行唯一定义' in ln][0][-120:])
