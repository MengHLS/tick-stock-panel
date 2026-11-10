"""双均线 20/60 金叉 (S01)：ma20 上穿 ma60 买入，ma20 下穿 ma60 卖出，最长持有 60 个交易日。"""
import numpy as np

from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
    matrix_feature,
    valid_shift,
)

META = {
    "id": "custom_mw7fvp17",
    "name": "双均线 20/60 金叉",
    "description": "20 日均线上穿 60 日均线买入，下穿卖出，最长持有 60 个交易日。",
    "tags": ["趋势", "双均线", "S01"],
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "basic_filter": {
        "price_min": 2.0,
        "price_max": None,
        "market_cap_min": None,
        "float_cap_min": None,
        "float_cap_max": None,
        "amount_min": None,
        "amount_max": None,
        "turnover_min": None,
        "turnover_max": None,
        "exclude_st": True,
        "exclude_new_days": 30,
        "boards": ["沪主板", "深主板", "创业板", "科创板", "北交所"],
    },
    "params": [
        {
            "id": "fast_period",
            "label": "快线周期",
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 60,
            "step": 1,
        },
        {
            "id": "slow_period",
            "label": "慢线周期",
            "type": "int",
            "default": 60,
            "min": 20,
            "max": 250,
            "step": 1,
        },
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 100,
    "backtest_defaults": {
        "trailing_peak_price": "close",
        "entry_price_basis": "raw",
        "block_limit_open": True,
        "finalize_open_at_end": True,
        "exit_signal_requires_profit": False,
        "execution_costs": {"min_commission": 5.0, "transfer_fee_pct": 2e-06},
    },
}
EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = None
MAX_HOLD_DAYS = 60
REQUIRED_FEATURES = ["close", "ma20", "ma60"]


def _bounded_int(value, default, low, high):
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


class MaCross2060MatrixStrategy:
    """20 日与 60 日均线的金叉/死叉策略，按 20 日动量排序择优建仓。"""

    def required_fields(self) -> frozenset:
        return frozenset({"close", "ma20", "ma60"})

    def required_warmup_bars(self, params: dict) -> int:
        slow = _bounded_int(params.get("slow_period"), 60, 20, 250)
        return slow + 2

    def compute_signals(self, market: MarketDataMatrix, params: dict) -> SignalMatrix:
        fast_n = _bounded_int(params.get("fast_period"), 20, 5, 60)
        slow_n = _bounded_int(params.get("slow_period"), 60, 20, 250)
        if fast_n >= slow_n:
            fast_n, slow_n = 20, 60
        fast = np.asarray(matrix_feature(market, "ma%d" % fast_n), dtype=np.float64)
        slow = np.asarray(matrix_feature(market, "ma%d" % slow_n), dtype=np.float64)
        prev_fast = np.asarray(valid_shift(fast, 1), dtype=np.float64)
        prev_slow = np.asarray(valid_shift(slow, 1), dtype=np.float64)
        cross_up = (fast > slow) & (prev_fast <= prev_slow)
        cross_down = (fast < slow) & (prev_fast >= prev_slow)
        momentum = np.asarray(matrix_feature(market, "momentum_20d"), dtype=np.float64)
        momentum = np.where(np.isfinite(momentum), momentum, 0.0)
        return make_signal_matrix(
            market.shape,
            entry=cross_up.astype(np.uint8),
            exit=cross_down.astype(np.uint8),
            ranking_score=momentum,
        )


MATRIX_STRATEGY = MaCross2060MatrixStrategy()
