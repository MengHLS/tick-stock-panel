import pathlib
p = pathlib.Path(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/R11_draft.md")
t = p.read_text(encoding="utf-8")
reps = [
 ("245,314", "245,364"),
 ("+1,221", "+1,271"),
 ("243,159", "243,209"),
 ("6ea5accbd50ce95ed5798cc7f99ef7715230015d4c516efcefa4b760c90302fc",
  "aa6e06c306eb250d96b7f37af12e672733483b598507b50331f909dbed8525b2"),
 ("d1349af50826fcf61fe52b27129ff0c656c23c449e69d4f65d4c2332bd8dc57f",
  "c2eec518d6bae2c2ac483a8a6524d7c28ec6048f339c723c1e68c9ebc0c3c58d"),
 ("155,144", "155,158"),
 ("+779", "+793"),
 ("banner 856", "banner 906"),
 ("banner 530", "banner 544"),
 ("68/138、285/448、169/262", "68/138、299/498、169/262"),
 ("加 4 个 CRLF 共 **856 B**", "共 **906 B**"),
 ("`:1865–:1870`", "`:1867–:1872`"),
 ("`:1863` 的 recipe 1 自洽实测", "`:1865` 的 recipe 1 自洽实测"),
 ("22:51:10.228", "22:58:22.275"),
 ("+530 字符 / +856 B", "+544 字符 / +906 B"),
]
for a, b in reps:
    n = t.count(a)
    if n == 0:
        print("MISS:", a[:50])
    t = t.replace(a, b)
# banner 第 2 行逐字更新
old_l2_start = t.index("> **现行唯一定义 = recipe 1")
old_l2_end = t.index("\n", old_l2_start)
new_l2 = ("> **现行唯一定义 = recipe 1 = §7.12.4 原文**（剔除 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键）；"
          "签认仍为**三元组** `(canonical_digest, schema_version, scanned_sources)`，`canonical_digest_recipe` 字段**不实现**；"
          "本节「本版起新产物必须用它」/「签认由三元组升为四元组」/「不可比不得判失败」/「L2 起产物必须 `\"2\"`」四句一并不生效；"
          "任何声称「recipe 2 合规」的产物按**不合规**处理。")
t = t[:old_l2_start] + new_l2 + t[old_l2_end:]
p.write_text(t, encoding="utf-8", newline="\n")

# 残留检查
for token in ("245,314","+1,221","243,159","6ea5accb","d1349af5","155,144","+779","856 B","22:51:10"):
    print("residual", token, t.count(token))
print("len", len(t))
