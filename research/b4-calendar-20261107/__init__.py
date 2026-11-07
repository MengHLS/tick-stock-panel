"""E4 调仓日轴 (`month_end` / `week_end`) 的因子包 (契约 v0.7 §4.7)。

与 `research_factor_pack` / `research_universe_pack` 分开成一个包: Provider 的 factor id
集合在版本间必须稳定 (`app/extensions/factors.py#register_factor_provider`), 且这两个是
**日级日历列** (帧外信息: 市场交易日集合), 与纯 DSL 因子包、有状态的 `in_universe` 都不是
一类。日历口径见 `calendar_axis.py` 的 docstring。
"""
from __future__ import annotations
