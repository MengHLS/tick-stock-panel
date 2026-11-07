"""E3 `in_universe` 股票池掩码因子 (契约 v0.7 §2)。

与 `research_factor_pack` 分开成一个包: Provider 的 factor id 集合在版本间必须稳定
(app/extensions/factors.py#register_factor_provider), 且 `in_universe` 是有状态的
(as-of ST 合并 + 覆盖期末端判定), 与纯 DSL 因子包不是一类。
"""
from __future__ import annotations
