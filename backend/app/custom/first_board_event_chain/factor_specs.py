"""Factor metadata owned by the first-board event-chain extension."""
from __future__ import annotations

from app.custom.first_board_event_chain.compute import (
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_MIN_PULLBACK_PCT,
    EVENT_CHAIN_DEPENDENCIES,
)
from app.factors.registry import FactorSpec

_STOCK_ONLY = frozenset({"stock"})
_TAGS = ("首板", "事件链", "实验")
_WARMUP = DEFAULT_LOOKBACK_BARS + 1


def _spec(
    factor_id: str,
    label: str,
    description: str,
    **overrides,
) -> FactorSpec:
    return FactorSpec(
        id=factor_id,
        label=label,
        group="首板事件链",
        formula_text=description,
        kind="virtual",
        dependencies=EVENT_CHAIN_DEPENDENCIES,
        warmup_bars=_WARMUP,
        asset_types=_STOCK_ONLY,
        incremental_safe=False,
        intraday_monitor_safe=False,
        stability="experimental",
        tags=_TAGS,
        **overrides,
    )


EVENT_CHAIN_FACTOR_SPECS = (
    _spec(
        "first_board_chain_stage",
        "首板事件链阶段",
        (
            f"目标首板向前回看{DEFAULT_LOOKBACK_BARS}个交易日, "
            "按最近首板优先递归; 0无锚/1结构不完整/2回调太浅/"
            "3回攻未过前高/4目标前已突破/5首次收盘突破; "
            f"最小回调{DEFAULT_MIN_PULLBACK_PCT:.0%}"
        ),
        unit="score",
    ),
    _spec(
        "first_board_chain_anchor_distance",
        "事件链锚点距离",
        "递归选中的前次首板与目标首板之间的交易日数; 未选中锚点为空",
        unit="days",
    ),
    _spec(
        "first_board_chain_pullback_pct",
        "事件链回调幅度",
        "前高 P 到回调低点 L 的跌幅 1-L/P; 无完整峰谷时为空",
        unit="ratio",
    ),
    _spec(
        "first_board_chain_target_above_reference_pct",
        "目标收盘距前高",
        "目标首板收盘 / 前高 P - 1; 无完整前高时为空",
        unit="ratio",
    ),
    _spec(
        "first_board_chain_strict_rebreak",
        "事件链首次收盘突破",
        "目标首板收盘首次突破前高 P, 且此前无收盘突破",
    ),
    _spec(
        "first_board_chain_early_breakout",
        "事件链目标前已突破",
        "回调后、目标首板前已有收盘价突破前高 P",
    ),
    _spec(
        "first_board_chain_recovered_not_breakout",
        "事件链回攻未过前高",
        "结构有效且目标首板收盘未突破前高 P",
    ),
    _spec(
        "first_board_chain_seed_close_preserved",
        "事件链锚点收盘守住",
        "回调低点 L 不低于锚点首板收盘价",
    ),
    _spec(
        "first_board_chain_seed_low_preserved",
        "事件链锚点低点守住",
        "回调低点 L 不低于锚点首板最低价",
    ),
)
