"""E5 `market_breadth` (全市场站上 ma60 的宽度) 独立包。

为什么单独一个包, 不并入 `research_universe_pack` 或 `research_factor_pack`:
`register_factor_provider` 要求同一 provider 的 `factor_ids` 跨版本稳定
(`app/extensions/factors.py:168-172`)。把 `market_breadth` 塞进 `in_universe` 所在的
包会改动该包的 id 集合, 而那个集合已被 E3 的验收锚定; 塞进 B0 包同理。

计算与登记在 `breadth.py` (只有一条公式原文, 求值走 dsl 同一条路径)。
"""
