# -*- coding: utf-8 -*-
"""v0.9 表格列数自检：每张表内所有行的未转义竖线数应一致。"""
from collections import Counter

p = r"C:\work\sourcecode\tick-stock-panel\docs\architecture\FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md"
L = open(p, "rb").read().decode("utf-8").split("\r\n")


def cells(s: str) -> int:
    return s.count("|") - s.count("\\|")


ranges = [(230, 252, "§2.7/§2.8"), (1518, 1534, "§7.14.4"), (1594, 1692, "§7.16"), (1906, 1960, "§11")]
for a, b, name in ranges:
    rows = [(i + 1, cells(L[i])) for i in range(a, b) if L[i].startswith("|")]
    dist = Counter(c for _, c in rows)
    print(name, dict(dist), "rows", len(rows))
    if len(dist) > 1:
        for ln, c in rows:
            print("  MIXED", ln, c, L[ln - 1][:70])
