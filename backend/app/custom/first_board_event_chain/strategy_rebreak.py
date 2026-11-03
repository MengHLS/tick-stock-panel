"""Experimental matrix-native strategy for finite-lookback first-board rechains."""
from __future__ import annotations

import numpy as np

from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
    materialize_matrix_factors,
    matrix_feature,
    valid_shift,
)

_EVENT_CHAIN_FIELDS = frozenset({
    "first_board_chain_strict_rebreak",
    "first_board_chain_seed_close_preserved",
    "first_board_chain_target_above_reference_pct",
    "first_board_chain_pullback_pct",
})

FIRST_BOARD_CHAIN_LOOKBACK_BARS = 250

META = {
    "id": "first_board_chain_rebreak",
    "name": "首板结构回攻（实验）",
    "description": (
        "有限回看的前次首板→冲高→回调→再回攻结构。"
        "仅当目标首板收盘首次突破前高时产生T日信号，按项目成交设置执行。"
    ),
    "tags": ["首板", "事件链", "回攻", "研究"],
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "research_only": True,
    "stability": "experimental",
    "params": [
        {
            "id": "lookback_days",
            "label": "向前回看交易日",
            "type": "int",
            "default": FIRST_BOARD_CHAIN_LOOKBACK_BARS,
            "min": 5,
            "max": 512,
            "step": 10,
        },
        {
            "id": "min_pullback_pct",
            "label": "最小回调幅度%",
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "max": 30.0,
            "step": 0.5,
        },
        {
            "id": "require_new_high_after_anchor",
            "label": "首板后须再创新高",
            "type": "bool",
            "default": True,
        },
        {
            "id": "require_seed_close_preserved",
            "label": "回调须守住锚点收盘",
            "type": "bool",
            "default": False,
        },
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = ["signal_first_board_chain_rebreak"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 10


class FirstBoardChainRebreakMatrixStrategy:
    def required_fields(self) -> frozenset[str]:
        return frozenset({
            "open",
            "high",
            "low",
            "close",
            "consecutive_limit_ups",
        })

    def required_warmup_bars(self, params: dict) -> int:
        return _lookback_from_params(params) + 1

    def compute_signals(self, market: MarketDataMatrix, params: dict) -> SignalMatrix:
        materialized = materialize_matrix_factors(
            market,
            _EVENT_CHAIN_FIELDS,
            params={
                "lookback_bars": _lookback_from_params(params),
                "min_pullback_pct": _min_pullback_from_params(params),
                "require_new_high_after_anchor": bool(
                    params.get("require_new_high_after_anchor", True)
                ),
            },
        )
        entry = materialized.field("first_board_chain_strict_rebreak") > 0.5
        entry &= np.isfinite(market.close)
        if bool(params.get("require_seed_close_preserved", False)):
            entry &= (
                materialized.field("first_board_chain_seed_close_preserved") > 0.5
            )

        ma20 = matrix_feature(market, "ma20")
        previous_close = valid_shift(market.close, 1, np.isfinite(market.close))
        previous_ma20 = valid_shift(ma20, 1, np.isfinite(ma20))
        exit_ = (
            np.isfinite(ma20)
            & (market.close < ma20)
            & (previous_close >= previous_ma20)
        )

        target_above = materialized.field(
            "first_board_chain_target_above_reference_pct"
        )
        pullback = materialized.field("first_board_chain_pullback_pct")
        raw_score = (
            np.nan_to_num(target_above, nan=0.0, posinf=0.0, neginf=0.0)
            * np.float32(100.0)
            + np.nan_to_num(pullback, nan=0.0, posinf=0.0, neginf=0.0)
            * np.float32(20.0)
        )
        score = np.where(entry, raw_score, np.float32(0.0)).astype(
            np.float32,
            copy=False,
        )
        return make_signal_matrix(
            market.shape,
            entry=entry.astype(np.uint8),
            exit=exit_.astype(np.uint8),
            score=score,
            entry_signal_code=np.where(entry, 0, -1).astype(np.int16),
            exit_signal_code=np.where(exit_, 0, -1).astype(np.int16),
            entry_signal_ids=("signal_first_board_chain_rebreak",),
            exit_signal_ids=("signal_ma20_breakdown",),
        )


def _lookback_from_params(params: dict) -> int:
    return _bounded_int(
        params.get("lookback_days", FIRST_BOARD_CHAIN_LOOKBACK_BARS),
        "lookback_days",
        5,
        512,
    )


def _min_pullback_from_params(params: dict) -> float:
    return _bounded_float(
        params.get("min_pullback_pct", 5.0),
        "min_pullback_pct",
        0.0,
        30.0,
    ) / 100.0


def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _bounded_float(
    value: object,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


MATRIX_STRATEGY = FirstBoardChainRebreakMatrixStrategy()
