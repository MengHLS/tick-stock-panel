from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from app.backtest.matrix import (
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    build_market_data_matrix,
    build_market_matrix_from_signals,
    make_signal_matrix,
)
from app.strategy.engine import StrategyEngine

STRATEGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "custom"
    / "first_board_event_chain"
    / "first_limit_pullback_3f_runner_t74.py"
)


def _panel() -> pl.DataFrame:
    start = date(2025, 1, 2)
    rows = []
    for symbol in ("000001.SZ", "000002.SZ", "000003.SZ"):
        closes = [
            10.00, 10.02, 9.90, 9.94, 10.00, 10.04,
            10.08, 10.12, 10.16, 10.20, 10.24, 10.28,
            10.32, 10.36, 10.40, 10.44, 9.20,
        ]
        volumes = [100.0, 210.0] + [110.0] * (len(closes) - 2)
        boards = [1.0] + [0.0] * (len(closes) - 1)
        for index, close in enumerate(closes):
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": start + timedelta(days=index),
                "open": close - 0.01,
                "high": close + 0.04,
                "low": close - 0.04,
                "close": close,
                "volume": volumes[index],
                "consecutive_limit_ups": boards[index],
                "signal_limit_up": boards[index] == 1.0,
            })
    return pl.DataFrame(rows).sort(["date", "symbol"])


def test_strategy_uses_t_minus_five_first_board_and_ranks_daily_top_three() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    assert strategy.meta["id"] == "first_limit_pullback_3f_runner_t74"
    assert strategy.execution_backend == "matrix_native"

    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy, market, {},
        MatrixPipelineConfig(basic_filter=strategy.basic_filter, scoring={}, order_by="score", descending=True),
    )

    # T=day0 is the first board; the strategy can only emit at T+5=day5.
    assert signals.entry[:5].sum() == 0
    assert signals.entry[5].tolist() == [1, 1, 1]
    assert signals.score[5].tolist() == pytest.approx(
        [0.85, 0.85, 0.85], abs=4e-6,
    )
    assert signals.entry_signal_ids == ("signal_first_limit_pullback_3f",)

    execution = build_market_matrix_from_signals(
        market,
        signals,
        entry_delay_bars=1,
    )
    assert execution.entry[5].sum() == 0
    assert execution.entry[6].tolist() == [1, 1, 1]


def test_original_universe_has_no_extra_price_cap_amount_or_listing_gates() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    assert strategy.basic_filter["boards"] == ["沪主板", "深主板"]
    assert strategy.basic_filter["exclude_st"] is True
    for field in ("price_min", "price_max", "market_cap_min", "amount_min", "exclude_new_days"):
        assert not strategy.basic_filter.get(field)


def test_universe_filter_runs_before_daily_ranking() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    main = _panel().with_columns(
        pl.col("symbol").str.replace("00000", "60000").str.replace(".SZ", ".SH", literal=True)
    )
    other = main.filter(pl.col("symbol") == "600001.SH").with_columns(
        pl.lit("300001.SZ").alias("symbol")
    )
    market = build_market_data_matrix(
        pl.concat([main, other]), field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy, market, {},
        MatrixPipelineConfig(basic_filter=strategy.basic_filter, scoring={}, order_by="score", descending=True),
    )
    selected = [market.symbols[i] for i in signals.entry[5].nonzero()[0]]
    assert selected == ["600001.SH", "600002.SH", "600003.SH"]


def test_legacy_excluded_event_is_removed_before_ranking() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {
            "legacy_excluded_events": ["000001.SZ@2025-01-02"],
        },
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )

    assert signals.entry[5].tolist() == [0, 1, 1]


def test_first_board_uses_exchange_limit_judgment_not_stale_counter() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    valid_panel = _panel().with_columns(
        pl.when(pl.col("date") == date(2025, 1, 2))
        .then(True)
        .otherwise(False)
        .alias("signal_limit_up")
    )
    valid_market = build_market_data_matrix(
        valid_panel,
        field_columns={"consecutive_limit_ups"},
    )
    valid = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        valid_market,
        {},
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )
    assert valid.entry[5].sum() == 3

    stale_panel = _panel().with_columns(
        pl.when(pl.col("date") == date(2025, 1, 2))
        .then(1)
        .otherwise(0)
        .alias("consecutive_limit_ups")
    ).with_columns(pl.lit(False).alias("signal_limit_up"))
    stale_market = build_market_data_matrix(
        stale_panel,
        field_columns={"consecutive_limit_ups"},
    )
    stale = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        stale_market,
        {},
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )
    assert stale.entry.sum() == 0


def test_first_board_treats_missing_previous_bar_as_not_limit_up() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    start = date(2025, 1, 2)
    panel = (
        _panel()
        .filter(
            ~(
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=1))
            )
        )
        .with_columns(
            pl.when(
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=2))
            )
            .then(10.19)
            .otherwise(pl.col("open"))
            .alias("open"),
            pl.when(
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=2))
            )
            .then(10.24)
            .otherwise(pl.col("high"))
            .alias("high"),
            pl.when(
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=2))
            )
            .then(10.16)
            .otherwise(pl.col("low"))
            .alias("low"),
            pl.when(
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=2))
            )
            .then(10.20)
            .otherwise(pl.col("close"))
            .alias("close"),
            (
                (pl.col("symbol") == "000001.SZ")
                & (pl.col("date") == start + timedelta(days=2))
            ).alias("signal_limit_up")
        )
    )
    market = build_market_data_matrix(
        panel,
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {},
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )

    asset_id = market.symbols.index("000001.SZ")
    assert signals.entry[7, asset_id] == 1


def test_pipeline_ranks_top_candidates_with_full_precision_score() -> None:
    """A 1-ULP score difference must outrank the legacy security-id tie-break."""

    class _RankingStrategy:
        def daily_candidate_limit(self, params: dict) -> int:
            del params
            return 1

        def daily_candidate_sort_key(
            self,
            symbols: tuple[str, ...],
            params: dict,
        ) -> tuple[str, ...]:
            del params
            return tuple(f"sec_{symbol}" for symbol in symbols)

        def exit_signal_for_selected_entries(
            self,
            market,
            selected_entry: np.ndarray,
            params: dict,
        ):
            del params
            assert selected_entry[5].tolist() == [0, 1, 0]
            exit_signal = np.zeros(market.shape, dtype=np.uint8)
            exit_signal[6] = selected_entry[5]
            return exit_signal

        def compute_signals(self, market, params: dict):
            del params
            entry = np.zeros(market.shape, dtype=np.uint8)
            entry[5, :2] = 1
            score = np.zeros(market.shape, dtype=np.float32)
            score[5, :2] = np.float32(0.48333333333333334)
            ranking_score = np.zeros(market.shape, dtype=np.float64)
            ranking_score[5, 0] = 0.48333333333333334
            ranking_score[5, 1] = 0.4833333333333334
            return make_signal_matrix(
                market.shape,
                entry=entry,
                score=score,
                ranking_score=ranking_score,
            )

    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        _RankingStrategy(),
        market,
        {},
        MatrixPipelineConfig(
            basic_filter={},
            scoring={},
            order_by="score",
            descending=True,
        ),
    )

    # The higher exact score belongs to 000002, whose security-id key sorts
    # after 000001 and would lose if the float32 scores were used for ranking.
    assert signals.entry[5].tolist() == [0, 1, 0]
    assert signals.exit[6].tolist() == [0, 1, 0]


def test_strategy_can_supply_legacy_security_id_tie_break_order() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {
            "daily_candidates": 1,
            "legacy_security_ids": {
                "000001.SZ": "sec_ff",
                "000002.SZ": "sec_00",
                "000003.SZ": "sec_aa",
            },
        },
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )

    assert signals.entry[5].tolist() == [0, 1, 0]

    ordered = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {
            "legacy_security_ids": {
                "000001.SZ": "sec_ff",
                "000002.SZ": "sec_00",
                "000003.SZ": "sec_aa",
            },
        },
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )
    # Preserve the source ranking for the matcher's later daily-buy cap.
    assert ordered.score[5].tolist()[1] > ordered.score[5].tolist()[2]
    assert ordered.score[5].tolist()[2] > ordered.score[5].tolist()[0]


def test_strategy_builtin_legacy_order_reproduces_first_2019_ranking_split() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    start = date(2025, 1, 2)
    rows = []
    for symbol in ("000056.SZ", "002862.SZ", "002869.SZ"):
        for index in range(6):
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": start + timedelta(days=index),
                "open": 10.10 if index == 0 else 9.96,
                "high": 10.60 if index == 0 else 10.35,
                "low": 9.85 if index == 0 else 9.55,
                "close": 10.00 if index == 0 else 9.95,
                "volume": 100.0 if index == 0 else 40.0,
                "consecutive_limit_ups": 1.0 if index == 0 else 0.0,
                "signal_limit_up": index == 0,
            })
    market = build_market_data_matrix(
        pl.DataFrame(rows).sort(["date", "symbol"]),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {"daily_candidates": 1},
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )

    selected = [market.symbols[i] for i in signals.entry[5].nonzero()[0]]
    assert selected == ["002862.SZ"]


def _low_score_panel() -> pl.DataFrame:
    """回踩成立但三分项都落在最低桶: 评分 0.15, 用于验证评分下限。"""
    start = date(2025, 1, 2)
    rows = []
    for index in range(6):
        if index == 0:
            close, high, low, volume = 10.00, 10.60, 9.85, 100.0
        else:
            # 振幅 0.8/约10 ≈ 8%, 最大振幅桶 0.25; 均值振幅桶 0.10。
            close, high, low = 9.95, 10.35, 9.55
            # T+1 量比 0.4 → 成交量桶 0.10。
            volume = 40.0 if index == 1 else 100.0
        rows.append({
            "symbol": "000001.SZ",
            "name": "000001.SZ",
            "date": start + timedelta(days=index),
            "open": 10.10 if index == 0 else 9.96,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "consecutive_limit_ups": 1.0 if index == 0 else 0.0,
            "signal_limit_up": index == 0,
        })
    return pl.DataFrame(rows).sort(["date", "symbol"])


def _run_low_score(params: dict):
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _low_score_panel(),
        field_columns={"consecutive_limit_ups"},
    )
    return MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        params,
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )


def test_min_score_filter_runs_after_top_three_selection() -> None:
    """Low scores remain rankable; the zero-budget tier is applied after Top3."""
    signals = _run_low_score({})
    assert signals.entry[5].tolist() == [1]
    assert float(signals.score[5][0]) == pytest.approx(0.45 / 3, abs=1e-6)


def test_exit_requires_both_ma5_and_ma10_breakdown() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = strategy.matrix_strategy.compute_signals(market, {})

    assert signals.exit[16].tolist() == [1, 1, 1]
    assert signals.exit_signal_ids == ("signal_t74_ma5_ma10_breakdown",)


def test_exit_ma_starts_from_latest_first_board_event() -> None:
    """Source event histories start at T0, so MA10 is unavailable on T+5."""
    start = date(2025, 1, 2)
    rows = []
    for index in range(26):
        close = 20.0 - index * 0.2
        rows.append({
            "symbol": "000001.SZ",
            "name": "000001.SZ",
            "date": start + timedelta(days=index),
            "open": close + 0.02 if index != 15 else close - 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "consecutive_limit_ups": 1.0 if index == 15 else 0.0,
            "signal_limit_up": index == 15,
        })

    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        pl.DataFrame(rows).sort(["date", "symbol"]),
        field_columns={"consecutive_limit_ups"},
    )
    signals = strategy.matrix_strategy.compute_signals(market, {})

    # T+5 has only six event rows; the source's first MA10 is available at T+9.
    assert signals.exit[20].tolist() == [0]
    assert signals.exit[24].tolist() == [1]


def test_exit_ma_does_not_reset_on_unselected_first_board() -> None:
    """A new board unrelated to the held event must not restart MA history."""
    start = date(2025, 1, 2)
    rows = []
    for index in range(15):
        close = 20.0 - index * 0.2
        rows.append({
            "symbol": "000001.SZ",
            "name": "000001.SZ",
            "date": start + timedelta(days=index),
            "open": close + 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "consecutive_limit_ups": 1.0 if index in {0, 5} else 0.0,
            "signal_limit_up": index in {0, 5},
        })

    market = build_market_data_matrix(
        pl.DataFrame(rows).sort(["date", "symbol"]),
        field_columns={"consecutive_limit_ups"},
    )
    entry = np.zeros(market.shape, dtype=bool)
    entry[5, 0] = True
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    event_exit = strategy.matrix_strategy.exit_signal_for_selected_entries(
        market, entry, {},
    )

    assert event_exit[9].tolist() == [1]


def test_exit_ma_uses_raw_close_at_equality_boundary() -> None:
    """The source compares raw closes; adjusted-price rounding must not create a break."""
    start = date(2019, 10, 9)
    raw_closes = [
        13.93, 13.81, 13.69, 13.87, 13.94,
        13.51, 13.34, 13.10, 13.65, 13.40, 12.95,
    ]
    adjusted_closes = [
        8.592850, 8.518826, 8.444803, 8.555838, 8.599018,
        8.333769, 8.228903, 8.080856, 8.420129, 8.265914, 7.988327,
    ]
    rows = []
    for index, (raw_close, adjusted_close) in enumerate(
        zip(raw_closes, adjusted_closes, strict=True)
    ):
        rows.append({
            "symbol": "603970.SH",
            "name": "603970.SH",
            "date": start + timedelta(days=index),
            "open": adjusted_close,
            "high": adjusted_close,
            "low": adjusted_close,
            "close": adjusted_close,
            "raw_close": raw_close,
            "volume": 100.0,
        })

    market = build_market_data_matrix(
        pl.DataFrame(rows).sort(["date", "symbol"]),
        field_columns={"raw_close"},
    )
    entry = np.zeros(market.shape, dtype=bool)
    entry[5, 0] = True
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    event_exit = strategy.matrix_strategy.exit_signal_for_selected_entries(
        market, entry, {},
    )

    assert event_exit[9].tolist() == [0]
    assert event_exit[10].tolist() == [1]


def test_exit_ma_ignores_first_boards_before_the_run_start() -> None:
    """Only first-board events inside the formal backtest window create chains."""
    start = date(2025, 1, 2)
    rows = []
    for index in range(25):
        close = 20.0 - index * 0.2
        rows.append({
            "symbol": "000001.SZ",
            "name": "000001.SZ",
            "date": start + timedelta(days=index),
            "open": close + 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "consecutive_limit_ups": 0.0,
            "signal_limit_up": False,
        })

    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        pl.DataFrame(rows).sort(["date", "symbol"]),
        field_columns={"consecutive_limit_ups"},
    )
    history_start = (start + timedelta(days=10)).isoformat()
    signals = strategy.matrix_strategy.compute_signals(
        market,
        {"_event_start": history_start},
    )

    assert signals.exit[10:].sum() == 0


def test_backtest_defaults_pin_next_open_fills() -> None:
    """331 的已验收成交口径必须写进策略默认值, 防止选中后沿用旧表单口径。"""
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    defaults = strategy.meta["backtest_defaults"]
    assert defaults["entry_fill"] == "open_t+1"
    assert defaults["exit_fill"] == "open_t+1"
