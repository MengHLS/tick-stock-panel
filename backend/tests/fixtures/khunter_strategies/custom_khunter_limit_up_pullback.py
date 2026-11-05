"""KHunter 涨停回马枪的单文件矩阵策略移植。"""

import numpy as np

from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
    matrix_feature,
)
from app.backtest.matrix import (
    valid_shift as shift,
)

META = {
    "id": "custom_khunter_limit_up_pullback",
    "name": "涨停回马枪",
    "description": "放量涨停后缩量回调，回落不破支撑并再次放量启动。",
    "tags": ["涨停", "回调", "回马枪", "实验"],
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "basic_filter": {
        "price_min": 2.0,
        "price_max": 500.0,
        "exclude_st": True,
    },
    "params": [
        {
            "id": "limit_up_lookback_days",
            "label": "涨停回溯天数",
            "type": "int",
            "default": 6,
            "min": 3,
            "max": 15,
            "step": 1,
        },
        {
            "id": "limit_up_volume_ratio",
            "label": "涨停量比",
            "type": "float",
            "default": 2.2,
            "min": 1.0,
            "max": 5.0,
            "step": 0.1,
        },
        {
            "id": "pullback_range_max_pct",
            "label": "回调振幅上限",
            "type": "float",
            "default": 15.0,
            "min": 2.0,
            "max": 30.0,
            "step": 0.5,
        },
        {
            "id": "support_ratio",
            "label": "支撑比例",
            "type": "float",
            "default": 0.95,
            "min": 0.85,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "id": "resistance_ratio",
            "label": "阻力比例",
            "type": "float",
            "default": 1.05,
            "min": 1.0,
            "max": 1.2,
            "step": 0.01,
        },
        {
            "id": "volume_shrink_ratio",
            "label": "缩量比例",
            "type": "float",
            "default": 0.5,
            "min": 0.1,
            "max": 0.9,
            "step": 0.05,
        },
        {
            "id": "selection_rise_min_pct",
            "label": "启动涨幅",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 9.0,
            "step": 0.5,
        },
        {
            "id": "selection_volume_ratio",
            "label": "启动量比",
            "type": "float",
            "default": 1.5,
            "min": 1.0,
            "max": 4.0,
            "step": 0.1,
        },
        {
            "id": "ma_period",
            "label": "启动均线",
            "type": "int",
            "default": 5,
            "min": 3,
            "max": 20,
            "step": 1,
        },
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 50,
    "backtest_defaults": {
        "schema_version": 1,
        "entry_fill": "open_t+1",
        "exit_fill": "open_t+1",
        "plan_at_signal_close": True,
    },
}

BASIC_FILTER = {
    "price_min": 2.0,
    "price_max": 500.0,
    "market_cap_min": None,
    "float_cap_min": None,
    "float_cap_max": None,
    "amount_min": None,
    "amount_max": None,
    "turnover_min": None,
    "turnover_max": None,
    "exclude_st": True,
    "exclude_new_days": 0,
}

EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = ["signal_khunter_limit_up_pullback"]
EXIT_SIGNALS = ["signal_khunter_ma_breakdown"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10

RULES = """
1. 最近若干交易日内出现交易所判定涨停，且涨停日成交量达到前五日均量 2.2 倍。
2. 涨停后的回调振幅不超过 15%，至少一日缩量，且收盘不破涨停收盘价 95%。
3. 启动日涨幅超过 2%、成交量达到前一日 1.5 倍并站上 MA5。
"""


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _bounded_float(
    value,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not np.isfinite(parsed):
        parsed = default
    return min(max(parsed, minimum), maximum)


class KhunterLimitUpPullbackMatrixStrategy:
    def required_fields(self) -> frozenset[str]:
        return frozenset({"raw_close"})

    def required_warmup_bars(self, params: dict) -> int:
        lookback = _bounded_int(
            params.get("limit_up_lookback_days"),
            6,
            3,
            15,
        )
        ma_period = _bounded_int(params.get("ma_period"), 5, 3, 20)
        return max(20, lookback + ma_period)

    def compute_signals(
        self,
        market: MarketDataMatrix,
        params: dict,
    ) -> SignalMatrix:
        lookback = _bounded_int(
            params.get("limit_up_lookback_days"),
            6,
            3,
            15,
        )
        limit_volume_ratio = _bounded_float(
            params.get("limit_up_volume_ratio"),
            2.2,
            1.0,
            5.0,
        )
        pullback_range_max = _bounded_float(
            params.get("pullback_range_max_pct"),
            15.0,
            2.0,
            30.0,
        ) / 100.0
        support_ratio = _bounded_float(
            params.get("support_ratio"),
            0.95,
            0.85,
            1.0,
        )
        resistance_ratio = _bounded_float(
            params.get("resistance_ratio"),
            1.05,
            1.0,
            1.2,
        )
        shrink_ratio = _bounded_float(
            params.get("volume_shrink_ratio"),
            0.5,
            0.1,
            0.9,
        )
        rise_min = _bounded_float(
            params.get("selection_rise_min_pct"),
            2.0,
            0.0,
            9.0,
        ) / 100.0
        selection_volume_ratio = _bounded_float(
            params.get("selection_volume_ratio"),
            1.5,
            1.0,
            4.0,
        )
        ma_period = _bounded_int(params.get("ma_period"), 5, 3, 20)

        close = market.close.astype(np.float64, copy=False)
        high = market.high.astype(np.float64, copy=False)
        low = market.low.astype(np.float64, copy=False)
        volume = market.volume.astype(np.float64, copy=False)
        valid = (
            np.isfinite(close)
            & np.isfinite(high)
            & np.isfinite(low)
            & np.isfinite(volume)
            & market.tradable.astype(bool)
            & (volume > 0)
        )
        entry = np.zeros(market.shape, dtype=bool)
        scores = np.zeros(market.shape, dtype=np.float64)
        max_gap = lookback - 1

        for asset_id in range(market.shape[1]):
            bars = np.flatnonzero(valid[:, asset_id])
            for position in range(max(1, ma_period), len(bars)):
                current_time = int(bars[position])
                previous_time = int(bars[position - 1])
                previous_close = close[previous_time, asset_id]
                previous_volume = volume[previous_time, asset_id]
                if previous_close <= 0 or previous_volume <= 0:
                    continue
                current_rise = (
                    close[current_time, asset_id] / previous_close - 1.0
                )
                current_volume_ratio = (
                    volume[current_time, asset_id] / previous_volume
                )
                ma_start = position - ma_period + 1
                current_ma = float(
                    close[bars[ma_start:position + 1], asset_id].mean()
                )
                if (
                    current_rise <= rise_min
                    or current_volume_ratio < selection_volume_ratio
                    or close[current_time, asset_id] <= current_ma
                ):
                    continue

                for gap in range(1, min(max_gap, position) + 1):
                    limit_position = position - gap
                    limit_time = int(bars[limit_position])
                    if not market.limit_up_locked[limit_time, asset_id]:
                        continue
                    baseline_bars = bars[
                        max(0, limit_position - 5):limit_position
                    ]
                    if len(baseline_bars) < 5:
                        continue
                    baseline_volume = float(
                        volume[baseline_bars, asset_id].mean()
                    )
                    if baseline_volume <= 0:
                        continue
                    limit_volume = volume[limit_time, asset_id]
                    observed_limit_ratio = limit_volume / baseline_volume
                    if observed_limit_ratio < limit_volume_ratio:
                        continue

                    pullback_bars = bars[limit_position + 1:position + 1]
                    if pullback_bars.size == 0:
                        continue
                    pullback_highs = high[pullback_bars, asset_id]
                    pullback_lows = low[pullback_bars, asset_id]
                    pullback_closes = close[pullback_bars, asset_id]
                    pullback_volumes = volume[pullback_bars, asset_id]
                    if not (
                        np.isfinite(pullback_highs).all()
                        and np.isfinite(pullback_lows).all()
                        and np.isfinite(pullback_closes).all()
                        and np.isfinite(pullback_volumes).all()
                    ):
                        continue
                    highest = float(pullback_highs.max())
                    lowest = float(pullback_lows.min())
                    if highest <= 0:
                        continue
                    pullback_range = (highest - lowest) / highest
                    limit_close = close[limit_time, asset_id]
                    support = limit_close * support_ratio
                    resistance = limit_close * resistance_ratio
                    if pullback_range > pullback_range_max:
                        continue
                    if pullback_closes.min() < support:
                        continue
                    if pullback_closes.max() > resistance:
                        continue
                    if not (pullback_closes < limit_close).any():
                        continue
                    if not (
                        pullback_volumes <= limit_volume * shrink_ratio
                    ).any():
                        continue

                    entry[current_time, asset_id] = True
                    recency = 1.0 - (gap - 1) / max_gap
                    tightness = 1.0 - pullback_range / pullback_range_max
                    volume_strength = min(observed_limit_ratio / 3.0, 1.0)
                    scores[current_time, asset_id] = (
                        0.5 * volume_strength
                        + 0.25 * recency
                        + 0.25 * tightness
                    )
                    break

        ma = matrix_feature(market, f"ma{ma_period}")
        previous_ma = shift(ma, 1)
        previous_close_matrix = shift(close, 1)
        exit_ = (
            (close < ma)
            & (previous_close_matrix >= previous_ma)
            & valid
        )
        score = scores.astype(np.float32, copy=False)
        return make_signal_matrix(
            market.shape,
            entry=entry.astype(np.uint8),
            exit=exit_.astype(np.uint8),
            score=score,
            entry_signal_code=np.where(entry, 0, -1).astype(np.int16),
            exit_signal_code=np.where(exit_, 0, -1).astype(np.int16),
            entry_signal_ids=("signal_khunter_limit_up_pullback",),
            exit_signal_ids=("signal_khunter_ma_breakdown",),
            ranking_score=scores,
        )


MATRIX_STRATEGY = KhunterLimitUpPullbackMatrixStrategy()
