"""Matrix-native reproduction of the first-board 3F T74 runner strategy."""
from __future__ import annotations

import numpy as np

from _legacy_t74_order import LEGACY_SECURITY_ORDER
from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
)

META = {
    "id": "first_limit_pullback_3f_runner_t74",
    "name": "首板3F回踩 · T74 Runner",
    "description": (
        "首板后观察T+1至T+5：出现收盘回踩、最大振幅<14%，"
        "仅沪深主板，按三个原子因子分档等权评分；T+5收盘取Top3，"
        "每天最多计划2笔，次日开盘买入。"
        "止损6%，盈利3%后启用峰值收盘回撤8%，MA5/MA10双破退出，"
        "第5持仓日按NEW_HIGH_3延长至74日，或强势续持至10日。"
    ),
    "tags": ["首板", "回踩", "3F", "T74", "实验"],
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "params": [
        {
            "id": "daily_candidates",
            "label": "每日排名候选数",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 3,
            "step": 1,
        },
        {
            "id": "min_score_pct",
            "label": "评分下限",
            "type": "float",
            "default": 55.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
        },
        {
            "id": "max_amplitude_pct",
            "label": "观察期最大振幅%",
            "type": "float",
            "default": 14.0,
            "min": 1.0,
            "max": 30.0,
            "step": 0.5,
        },
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 100,
    "stability": "experimental",
    "backtest_defaults": {
        "schema_version": 1,
        "initial_capital": 100000,
        "max_positions": 5,
        "max_exposure_pct": 1.0,
        "commission_pct": 0.00025,
        "stamp_tax_pct": 0.0005,
        "slippage_bps": 5.0,
        "mode": "position",
        "entry_fill": "open_t+1",
        "exit_fill": "open_t+1",
        "holding_days": 74,
        "position_sizing": "score_tier",
        "score_tiers": [
            [0.0, 0.0],
            [0.55, 0.20],
            [0.7166666666666667, 0.25],
        ],
        "entry_open_gap_range": [-0.04, 0.04],
        "entry_prev_day_change_range": [-0.05, 0.05],
        "trailing_peak_price": "close",
        "exit_signal_requires_profit": True,
        "plan_at_signal_close": True,
        "max_daily_entries": 2,
        "entry_price_basis": "raw",
        "block_limit_open": True,
        "allow_same_asset_positions": True,
        "finalize_open_at_end": True,
        "execution_costs": {
            "min_commission": 5.0,
            "transfer_fee_pct": 0.00001,
            "buy_slippage_tiers": [
                [100000000.0, 20.0],
                [500000000.0, 10.0],
                [2000000000.0, 5.0],
            ],
        },
        "hold_extension": {
            "decision_days": 5,
            "strong_hold_days": 10,
            "strong_hold_min_return": 0.03,
            "runner_new_high_days": 3,
            "runner_extend_days": 74,
        },
    },
}

BASIC_FILTER = {
    "price_min": None,
    "price_max": None,
    "market_cap_min": None,
    "float_cap_min": None,
    "float_cap_max": None,
    "amount_min": None,
    "amount_max": None,
    "turnover_min": None,
    "turnover_max": None,
    "exclude_st": True,
    "exclude_new_days": 0,
    "boards": ["沪主板", "深主板"],
}

EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = ["signal_first_limit_pullback_3f"]
EXIT_SIGNALS = ["signal_t74_ma5_ma10_breakdown"]
STOP_LOSS = -0.06
TRAILING_TAKE_PROFIT_ACTIVATE = 0.03
TRAILING_TAKE_PROFIT_DRAWDOWN = 0.08
# Full-mode loading needs data through the longest runner horizon. The
# engine's hold-extension policy still controls the actual exit day.
MAX_HOLD_DAYS = 74
RAW_PRICE_DECIMALS = 2
_LEGACY_SECURITY_ORDER = {
    symbol: rank for rank, symbol in enumerate(LEGACY_SECURITY_ORDER)
}


class FirstLimitPullback3FRunnerT74MatrixStrategy:
    def required_fields(self) -> frozenset[str]:
        return frozenset({
            "open",
            "high",
            "low",
            "close",
            "volume",
            "raw_high",
            "raw_low",
            "raw_close",
        })

    def required_warmup_bars(self, params: dict) -> int:
        del params
        return 10

    def daily_candidate_limit(self, params: dict) -> int:
        return _bounded_int(params.get("daily_candidates", 3), "daily_candidates", 1, 3)

    def daily_candidate_sort_key(
        self,
        symbols: tuple[str, ...],
        params: dict,
    ) -> tuple[str, ...]:
        legacy = params.get("legacy_security_ids")
        if legacy is not None:
            if not isinstance(legacy, dict):
                raise ValueError("legacy_security_ids must be a mapping")
            return tuple(str(legacy.get(symbol, symbol)) for symbol in symbols)
        unknown = len(_LEGACY_SECURITY_ORDER)
        return tuple(
            f"{_LEGACY_SECURITY_ORDER.get(symbol, unknown):06d}\x00{symbol}"
            for symbol in symbols
        )

    def exit_signal_for_selected_entries(
        self,
        market: MarketDataMatrix,
        selected_entry: np.ndarray,
        params: dict,
    ) -> np.ndarray:
        return _event_relative_ma_breakdown(
            market,
            entry=selected_entry,
            event_start=params.get("_event_start"),
        )

    def event_exit_times_for_selected_entries(
        self,
        market: MarketDataMatrix,
        selected_entry: np.ndarray,
        params: dict,
    ) -> dict[tuple[int, int], frozenset[int]]:
        """Return every MA exit signal on each selected event's own chain."""
        raw_close = _raw_price_field(market, "close")
        adjusted_close = market.close.astype(np.float64, copy=False)
        event_start = params.get("_event_start")
        out: dict[tuple[int, int], frozenset[int]] = {}
        for time_id, asset_id in np.argwhere(selected_entry):
            entry_time = int(time_id)
            asset = int(asset_id)
            seed_id = entry_time - 5
            if seed_id < 0:
                continue
            if (
                event_start is not None
                and market.timestamp_labels[seed_id][:10] < event_start
            ):
                continue
            exit_times = _event_exit_signal_times(
                market,
                raw_close,
                adjusted_close,
                asset_id=asset,
                seed_id=seed_id,
                entry_time=entry_time,
            )
            out[(entry_time, asset)] = exit_times
        return out

    def compute_signals(self, market: MarketDataMatrix, params: dict) -> SignalMatrix:
        ready, pullback, max_amplitude, mean_amplitude, volume_ratio = (
            _first_board_t5_observations(
                market,
                event_start=params.get("_event_start"),
                excluded_event_keys=_excluded_event_keys(
                    params.get("legacy_excluded_events")
                ),
                allowlist=_event_allowlist_mask(
                    market,
                    params.get("_event_allowlist"),
                ),
            )
        )
        ready_mask = np.nan_to_num(ready, nan=0.0) > 0.5
        pullback_ok = pullback < -1e-9
        max_amplitude_limit = _bounded_float(
            params.get("max_amplitude_pct", 14.0),
            "max_amplitude_pct",
            1.0,
            30.0,
        ) / 100.0
        score64 = np.where(
            ready_mask,
            (
                _max_amplitude_bucket_score(max_amplitude)
                + _amplitude_bucket_score(mean_amplitude)
                + _volume_bucket_score(volume_ratio)
            )
            / np.float64(3.0),
            np.float64(0.0),
        ).astype(np.float64, copy=False)
        eligible = (
            ready_mask
            & pullback_ok
            & np.isfinite(max_amplitude)
            & (max_amplitude < max_amplitude_limit)
            & np.isfinite(mean_amplitude)
            & np.isfinite(volume_ratio)
        )
        entry = eligible.astype(np.uint8)

        score64 = np.where(
            entry.astype(bool), score64, np.float64(0.0)
        ).astype(np.float64, copy=False)
        score = score64.astype(
            np.float32,
            copy=False,
        )
        exit_ = _event_relative_ma_breakdown(
            market,
            entry=entry.astype(bool, copy=False),
            event_start=params.get("_event_start"),
        )
        preclose_unavailable = _preclose_unavailable_for_entries(
            market,
            entry=entry.astype(bool, copy=False),
            gaps=params.get("_legacy_preclose_gaps"),
        )
        return make_signal_matrix(
            market.shape,
            entry=entry,
            exit=exit_.astype(np.uint8),
            score=score,
            entry_signal_code=np.where(entry != 0, 0, -1).astype(np.int16),
            exit_signal_code=np.where(exit_, 0, -1).astype(np.int16),
            entry_signal_ids=("signal_first_limit_pullback_3f",),
            exit_signal_ids=("signal_t74_ma5_ma10_breakdown",),
            ranking_score=score64,
            preclose_unavailable=preclose_unavailable,
        )


def _preclose_unavailable_for_entries(
    market: MarketDataMatrix,
    *,
    entry: np.ndarray,
    gaps: object,
) -> dict[tuple[int, int], frozenset[int]] | None:
    """Map the legacy execution-data preClose gap to (signal time, asset).

    The original forward execution projection kept the frozen baseline row's
    null ``preClose`` for relative days before its rd17 extension window
    started. Its simulator therefore rejected a sell quote with ``OTHER`` even
    though the OHLC fields were filled. This helper reproduces that availability
    mask only when the caller explicitly supplies the archived gap ledger.
    """
    if gaps is None:
        return None
    if not isinstance(gaps, dict):
        raise ValueError("_legacy_preclose_gaps must be a mapping")
    time_by_date = {
        label[:10]: time_id for time_id, label in enumerate(market.timestamp_labels)
    }
    by_entry: dict[tuple[int, int], frozenset[int]] = {}
    for time_id, asset_id in np.argwhere(entry):
        signal_time = int(time_id)
        seed_id = signal_time - 5
        if seed_id < 0:
            continue
        asset = int(asset_id)
        event_id = (
            f"{market.symbols[asset]}@{market.timestamp_labels[seed_id][:10]}"
        )
        dates = gaps.get(event_id)
        if not dates:
            continue
        if not isinstance(dates, (list, tuple, set, frozenset)):
            raise ValueError(
                f"_legacy_preclose_gaps[{event_id!r}] must be a date sequence"
            )
        blocked = {
            time_by_date[date]
            for date in dates
            if isinstance(date, str) and date in time_by_date
        }
        if blocked:
            by_entry[(signal_time, asset)] = frozenset(blocked)
    return by_entry or None


def _first_board_t5_observations(
    market: MarketDataMatrix,
    *,
    event_start: str | None = None,
    excluded_event_keys: frozenset[str] = frozenset(),
    allowlist: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Observe a first board five trading bars ago using source-raw prices."""
    shape = market.shape
    high = _raw_price_field(market, "high")
    low = _raw_price_field(market, "low")
    close = _raw_price_field(market, "close")
    ready = np.full(shape, np.nan, dtype=np.float64)
    pullback = np.full(shape, np.nan, dtype=np.float64)
    max_amplitude = np.full(shape, np.nan, dtype=np.float64)
    mean_amplitude = np.full(shape, np.nan, dtype=np.float64)
    volume_ratio = np.full(shape, np.nan, dtype=np.float64)
    valid = (
        np.isfinite(market.open)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(close)
        & np.isfinite(market.volume)
        & (market.open > 0)
        & (high > 0)
        & (low > 0)
        & (close > 0)
        & (market.volume > 0)
        & (high >= low)
    )
    first_board = _first_board_mask(market)
    for asset_id in range(shape[1]):
        for signal_id in range(5, shape[0]):
            seed_id = signal_id - 5
            if event_start is not None and market.timestamp_labels[seed_id][:10] < event_start:
                continue
            if (
                f"{market.symbols[asset_id]}@{market.timestamp_labels[seed_id][:10]}"
                in excluded_event_keys
            ):
                continue
            if allowlist is not None and not bool(allowlist[seed_id, asset_id]):
                continue
            if not bool(valid[seed_id : signal_id + 1, asset_id].all()):
                continue
            if not first_board[seed_id, asset_id]:
                ready[signal_id, asset_id] = 0.0
                continue
            if not market.open[seed_id, asset_id] < market.high[seed_id, asset_id] - 1e-9:
                ready[signal_id, asset_id] = 0.0
                continue

            observation = slice(signal_id - 4, signal_id + 1)
            previous_close = close[signal_id - 5 : signal_id, asset_id]
            amplitudes = (
                high[observation, asset_id] - low[observation, asset_id]
            ) / previous_close
            ready[signal_id, asset_id] = 1.0
            pullback[signal_id, asset_id] = (
                float(close[observation, asset_id].min())
                / float(close[seed_id, asset_id])
                - 1.0
            )
            max_amplitude[signal_id, asset_id] = float(amplitudes.max())
            mean_amplitude[signal_id, asset_id] = (
                sum(float(value) for value in amplitudes) / 5.0
            )
            volume_ratio[signal_id, asset_id] = (
                float(market.volume[signal_id - 4, asset_id])
                / float(market.volume[seed_id, asset_id])
            )
    return ready, pullback, max_amplitude, mean_amplitude, volume_ratio


def _event_relative_ma_breakdown(
    market: MarketDataMatrix,
    *,
    entry: np.ndarray,
    event_start: str | None = None,
) -> np.ndarray:
    """Evaluate MA5/MA10 on each selected event's own close history.

    The source simulator keys price history by event security id. Its rows start
    at the first-board event (relative day 0). An unrelated later first board
    must neither reset nor borrow rows from the selected event's history.
    """
    out = np.zeros(market.shape, dtype=bool)
    raw_close = _raw_price_field(market, "close")
    adjusted_close = market.close.astype(np.float64, copy=False)
    for asset_id in range(market.shape[1]):
        history_start: int | None = None
        prior_scale: float | None = None
        closes: list[float] = []
        for time_id in range(market.shape[0]):
            append_start: int | None = None
            if entry[time_id, asset_id]:
                seed_id = time_id - 5
                if seed_id < 0:
                    history_start = None
                    prior_scale = None
                    closes = []
                    continue
                if (
                    event_start is not None
                    and market.timestamp_labels[seed_id][:10] < event_start
                ):
                    history_start = None
                    prior_scale = None
                    closes = []
                    continue
                history_start = seed_id
                prior_scale = None
                closes = []
                append_start = seed_id
            elif history_start is not None:
                append_start = time_id
            if history_start is None:
                continue
            assert append_start is not None
            for cursor in range(append_start, time_id + 1):
                raw = float(raw_close[cursor, asset_id])
                adjusted = float(adjusted_close[cursor, asset_id])
                if (
                    not np.isfinite(raw)
                    or raw <= 0
                    or not np.isfinite(adjusted)
                    or adjusted <= 0
                ):
                    continue
                scale = adjusted / raw
                if (
                    prior_scale is not None
                    and abs(scale / prior_scale - 1.0) > 1e-4
                    and cursor > (history_start + 5) + 1
                ):
                    factor = prior_scale / scale
                    closes = [value * factor for value in closes]
                closes.append(raw)
                prior_scale = scale
            if len(closes) < 10:
                continue
            current_close = closes[-1]
            ma5 = sum(closes[-5:]) / 5.0
            ma10 = sum(closes[-10:]) / 10.0
            if current_close < ma5 and current_close < ma10:
                out[time_id, asset_id] = True
    return out


def _event_exit_signal_times(
    market: MarketDataMatrix,
    raw_close: np.ndarray,
    adjusted_close: np.ndarray,
    *,
    asset_id: int,
    seed_id: int,
    entry_time: int,
) -> frozenset[int]:
    closes: list[float] = []
    prior_scale: float | None = None
    exit_times: set[int] = set()
    for time_id in range(seed_id, market.shape[0]):
        raw = float(raw_close[time_id, asset_id])
        adjusted = float(adjusted_close[time_id, asset_id])
        if (
            not np.isfinite(raw)
            or raw <= 0
            or not np.isfinite(adjusted)
            or adjusted <= 0
        ):
            continue
        scale = adjusted / raw
        if (
            prior_scale is not None
            and abs(scale / prior_scale - 1.0) > 1e-4
            and time_id > entry_time + 1
        ):
            factor = prior_scale / scale
            closes = [value * factor for value in closes]
        closes.append(raw)
        prior_scale = scale
        if time_id < entry_time or len(closes) < 10:
            continue
        current_close = closes[-1]
        ma5 = sum(closes[-5:]) / 5.0
        ma10 = sum(closes[-10:]) / 10.0
        if current_close < ma5 and current_close < ma10:
            exit_times.add(time_id)
    return frozenset(exit_times)


def _raw_price_field(market: MarketDataMatrix, name: str) -> np.ndarray:
    """Prefer unadjusted OHLC and fall back for lightweight test matrices."""
    try:
        values = market.field(f"raw_{name}")
    except ValueError:
        values = market.field(name)
    return np.round(values.astype(np.float64), RAW_PRICE_DECIMALS)


def _excluded_event_keys(raw: object) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if not isinstance(raw, (list, tuple, set)):
        raise ValueError("legacy_excluded_events must be a list")
    keys: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or "@" not in item:
            raise ValueError(
                "legacy_excluded_events entries must be SYMBOL@YYYY-MM-DD"
            )
        keys.add(item)
    return frozenset(keys)


def _event_allowlist_mask(
    market: MarketDataMatrix,
    raw: object,
) -> np.ndarray | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple, set, frozenset)):
        raise ValueError("_event_allowlist must be a list of SYMBOL@YYYY-MM-DD")
    time_by_date = {
        label[:10]: time_id
        for time_id, label in enumerate(market.timestamp_labels)
    }
    asset_by_symbol = {
        symbol: asset_id
        for asset_id, symbol in enumerate(market.symbols)
    }
    mask = np.zeros(market.shape, dtype=bool)
    for item in raw:
        if not isinstance(item, str) or "@" not in item:
            raise ValueError("_event_allowlist entries must be SYMBOL@YYYY-MM-DD")
        symbol, _, event_date = item.partition("@")
        time_id = time_by_date.get(event_date)
        asset_id = asset_by_symbol.get(symbol)
        if time_id is not None and asset_id is not None:
            mask[time_id, asset_id] = True
    return mask


def _first_board_mask(market: MarketDataMatrix) -> np.ndarray:
    """Derive first-board events from the matcher's exchange-limit judgment."""
    locked = market.limit_up_locked.astype(bool, copy=False)
    first_board = np.zeros(market.shape, dtype=bool)
    first_board[0] = locked[0]
    # A suspension day has no bar. The source dataset treats that day as
    # "not limit-up yesterday" and keeps the next available first board.
    first_board[1:] = locked[1:] & ~locked[:-1]
    return first_board


def _max_amplitude_bucket_score(values: np.ndarray) -> np.ndarray:
    """LOW-direction two-bucket score for observation max amplitude."""
    out = np.full(values.shape, np.nan, dtype=np.float64)
    finite = np.isfinite(values)
    out[finite & (values < 0.08)] = 0.75
    out[finite & (values >= 0.08)] = 0.25
    return out


def _amplitude_bucket_score(values: np.ndarray) -> np.ndarray:
    """LOW-direction bucket scores used by the frozen 3F definition."""
    out = np.full(values.shape, np.nan, dtype=np.float64)
    finite = np.isfinite(values)
    out[finite & (values < 0.02)] = 0.90
    out[finite & (values >= 0.02) & (values < 0.04)] = 0.70
    out[finite & (values >= 0.04) & (values < 0.06)] = 0.50
    out[finite & (values >= 0.06) & (values < 0.08)] = 0.30
    out[finite & (values >= 0.08)] = 0.10
    return out


def _volume_bucket_score(values: np.ndarray) -> np.ndarray:
    """HIGH-direction bucket scores for T+1 volume / T volume."""
    out = np.full(values.shape, np.nan, dtype=np.float64)
    finite = np.isfinite(values)
    out[finite & (values < 0.5)] = 0.10
    out[finite & (values >= 0.5) & (values < 0.8)] = 0.30
    out[finite & (values >= 0.8) & (values < 1.2)] = 0.50
    out[finite & (values >= 1.2) & (values < 2.0)] = 0.70
    out[finite & (values >= 2.0)] = 0.90
    return out


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


MATRIX_STRATEGY = FirstLimitPullback3FRunnerT74MatrixStrategy()
