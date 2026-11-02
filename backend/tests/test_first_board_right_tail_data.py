from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

from scripts.first_board_right_tail_lab.data import (
    RepositoryDataSource,
    build_event_factor_frame,
    canonicalize_minute_bars,
    canonicalize_raw_minute_bars,
    enrich_daily_factors,
    prepare_daily_context,
    validate_minute_layout,
)


def _minute_frame(
    symbol: str = "600001.SH",
    *,
    day: date = date(2026, 1, 5),
    rows: int = 2,
) -> pl.DataFrame:
    base = datetime(day.year, day.month, day.day, 9, 31)
    return pl.DataFrame(
        {
            "symbol": [symbol] * rows,
            "datetime": [
                base.replace(minute=31 + index)
                for index in range(rows)
            ],
            "open": [11.0 + index for index in range(rows)],
            "high": [11.2 + index for index in range(rows)],
            "low": [10.8 + index for index in range(rows)],
            "close": [11.1 + index for index in range(rows)],
            "volume": [100.0] * rows,
            "amount": [111_000.0 + index for index in range(rows)],
        }
    )


def test_canonicalize_uses_bar_end_timestamp_and_maps_prices():
    day = date(2026, 1, 5)
    frame = _minute_frame(day=day)
    ratios = pl.DataFrame(
        {
            "symbol": ["600001.SH"],
            "_d": [day],
            "_ratio": [0.8],
        }
    )

    out = canonicalize_minute_bars(frame, ratios)

    assert out.columns == [
        "symbol",
        "datetime",
        "bar_start",
        "bar_end",
        "volume",
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "amount_raw",
        "open_adj",
        "high_adj",
        "low_adj",
        "close_adj",
        "amount_adj",
    ]
    assert out["bar_end"][0] == datetime(2026, 1, 5, 9, 31)
    assert out["bar_start"][0] == datetime(2026, 1, 5, 9, 30)
    for base in ("open", "high", "low", "close", "amount"):
        assert out[f"{base}_raw"][0] == pytest.approx(
            out[f"{base}_adj"][0] / 0.8
        )
        assert out[f"{base}_raw"][0] * 0.8 == pytest.approx(
            out[f"{base}_adj"][0]
        )


def test_canonicalize_raw_keeps_raw_and_applies_adjustment_ratio():
    day = date(2026, 1, 5)
    frame = _minute_frame(day=day)
    ratios = pl.DataFrame(
        {
            "symbol": ["600001.SH"],
            "_d": [day],
            "_ratio": [0.8],
        }
    )

    out = canonicalize_raw_minute_bars(frame, ratios)

    assert out.columns == [
        "symbol",
        "datetime",
        "bar_start",
        "bar_end",
        "volume",
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "amount_raw",
        "open_adj",
        "high_adj",
        "low_adj",
        "close_adj",
        "amount_adj",
    ]
    for base in ("open", "high", "low", "close", "amount"):
        assert out[f"{base}_raw"][0] == pytest.approx(frame[base][0])
        assert out[f"{base}_adj"][0] == pytest.approx(
            frame[base][0] * 0.8
        )


def test_canonicalize_raw_drops_pre_session_auction_bar():
    day = date(2026, 1, 5)
    frame = _minute_frame(day=day, rows=2).with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(pl.datetime(day.year, day.month, day.day, 9, 30))
        .otherwise(pl.col("datetime"))
        .alias("datetime")
    )
    ratios = pl.DataFrame(
        {
            "symbol": ["600001.SH"],
            "_d": [day],
            "_ratio": [1.0],
        }
    )

    out = canonicalize_raw_minute_bars(frame, ratios)

    assert out.height == 1
    assert out["bar_end"][0] == datetime(2026, 1, 5, 9, 32)


def test_validate_minute_layout_reports_missing_symbol_day():
    day = date(2026, 1, 5)
    frame = _minute_frame(day=day)
    ratios = pl.DataFrame(
        {
            "symbol": ["600001.SH"],
            "_d": [day],
            "_ratio": [0.8],
        }
    )
    canonical = canonicalize_minute_bars(frame, ratios)
    expected = {
        ("600001.SH", day),
        ("600002.SH", day),
    }

    report = validate_minute_layout(canonical, expected)

    assert report.columns == [
        "date",
        "symbol",
        "expected_bars",
        "actual_bars",
        "status",
        "missing_first",
        "missing_last",
    ]
    missing = report.filter(pl.col("symbol") == "600002.SH").row(0, named=True)
    assert missing == {
        "date": day,
        "symbol": "600002.SH",
        "expected_bars": 240,
        "actual_bars": 0,
        "status": "missing",
        "missing_first": True,
        "missing_last": True,
    }


def test_repository_source_rejects_legacy_adjusted_minute_basis(
    tmp_path: Path,
):
    day = date(2026, 1, 5)
    partition = tmp_path / "kline_minute" / f"date={day.isoformat()}"
    partition.mkdir(parents=True)
    _minute_frame(day=day).write_parquet(partition / "part.parquet")
    source = RepositoryDataSource(tmp_path)

    with pytest.raises(RuntimeError, match="raw minute basis"):
        source.minute_batch(["600001.SH"], [day])


def test_repository_source_reads_raw_date_partition_and_evicts_cache(
    tmp_path: Path,
):
    first_day = date(2026, 1, 5)
    second_day = date(2026, 1, 6)
    minute_root = tmp_path / "kline_minute"
    minute_root.mkdir()
    (minute_root / ".raw_basis").touch()
    for day in (first_day, second_day):
        partition = minute_root / f"date={day.isoformat()}"
        partition.mkdir()
        _minute_frame(day=day).write_parquet(partition / "part.parquet")
    source = RepositoryDataSource(tmp_path, minute_cache_days=1)

    first = source.minute_batch(["600001.SH"], [first_day])
    second = source.minute_batch(["600001.SH"], [second_day])

    assert first.height == 2
    assert second.height == 2
    assert first["close_raw"][0] == pytest.approx(11.1)
    assert first["close_adj"][0] == pytest.approx(11.1)
    assert len(source._minute_cache) == 1
    assert second_day in source._minute_cache


def test_prepare_daily_context_computes_authoritative_main_board_limits():
    days = [date(2026, 1, 5), date(2026, 1, 6)]
    daily = pl.DataFrame(
        {
            "symbol": ["600001.SH", "600001.SH"],
            "date": days,
            "open": [10.0, 11.0],
            "high": [10.0, 11.0],
            "low": [10.0, 11.0],
            "close": [10.0, 11.0],
            "volume": [100.0, 100.0],
            "amount": [1000.0, 1100.0],
            "raw_close": [10.0, 11.0],
            "raw_high": [10.0, 11.0],
            "raw_low": [10.0, 11.0],
            "consecutive_limit_ups": [0, 1],
        }
    )

    prepared = prepare_daily_context(daily)

    second = prepared.row(1, named=True)
    assert second["limit_up_price"] == pytest.approx(11.0)
    assert second["limit_down_price"] == pytest.approx(9.0)
    assert prepared.row(0, named=True)["limit_up_price"] is None


def test_enrich_daily_factors_uses_completed_history_only():
    days = [date(2026, 1, 5) + timedelta(days=index) for index in range(25)]
    daily = pl.DataFrame(
        {
            "symbol": ["600001.SH"] * 25,
            "date": days,
            "open": [10.0 + index * 0.01 for index in range(25)],
            "high": [10.2 + index * 0.01 for index in range(25)],
            "low": [9.8 + index * 0.01 for index in range(25)],
            "close": [10.0 + index * 0.01 for index in range(25)],
            "volume": [1000.0 + index for index in range(25)],
            "amount": [1_000_000.0 + index for index in range(25)],
            "raw_close": [10.0 + index * 0.01 for index in range(25)],
            "raw_high": [10.2 + index * 0.01 for index in range(25)],
            "raw_low": [9.8 + index * 0.01 for index in range(25)],
            "turnover_rate": [1.0 + index / 100 for index in range(25)],
            "consecutive_limit_ups": [0] * 25,
        }
    )

    enriched = enrich_daily_factors(daily)

    assert enriched["daily__ret_1d"][0] is None
    assert enriched["daily__ret_20d"][20] == pytest.approx(
        daily["close"][20] / daily["close"][0] - 1
    )
    assert enriched["daily__close_ma20_ratio"][20] is not None
    assert enriched["daily__volatility_20"][21] is not None
    assert enriched["daily__turnover_rate"][0] == pytest.approx(1.0)
    assert enriched["daily__volume"][0] == pytest.approx(1000.0)
    assert "market__up_ratio" in enriched.columns
    assert "market__above_ma20_ratio" in enriched.columns


def test_market_features_are_cross_sectional_and_known_at_t_close():
    days = [date(2026, 1, 5), date(2026, 1, 6)]
    daily = pl.DataFrame(
        {
            "symbol": [
                "600001.SH",
                "600001.SH",
                "600002.SH",
                "600002.SH",
            ],
            "date": [*days, *days],
            "open": [10.0, 11.0, 20.0, 19.0],
            "high": [10.1, 11.1, 20.1, 19.1],
            "low": [9.9, 10.9, 19.9, 18.9],
            "close": [10.0, 11.0, 20.0, 19.0],
            "volume": [1000.0, 1200.0, 2000.0, 1800.0],
            "amount": [
                1_000_000.0,
                1_200_000.0,
                4_000_000.0,
                3_600_000.0,
            ],
            "raw_close": [10.0, 11.0, 20.0, 19.0],
            "raw_high": [10.1, 11.1, 20.1, 19.1],
            "raw_low": [9.9, 10.9, 19.9, 18.9],
            "limit_up_price": [11.0, 12.1, 22.0, 20.9],
            "limit_down_price": [9.0, 9.9, 18.0, 17.1],
        }
    )

    enriched = enrich_daily_factors(daily)
    second_day = enriched.filter(pl.col("date") == days[1])

    assert second_day["market__up_ratio"].unique().to_list() == [
        pytest.approx(0.5)
    ]
    assert second_day["market__median_ret_1d"].unique().to_list() == [
        pytest.approx(0.025)
    ]
    assert second_day["market__limit_up_ratio"].unique().to_list() == [
        pytest.approx(0.0)
    ]


def test_event_factor_frame_uses_event_date_only():
    day = date(2026, 1, 5)
    daily = pl.DataFrame(
        {
            "symbol": ["600001.SH", "600001.SH"],
            "date": [day, date(2026, 1, 6)],
            "daily__ret_5d": [0.1, 0.2],
            "linkage__deviate_3d": [0.3, 0.4],
            "market__up_ratio": [0.6, 0.7],
        }
    )
    events = pl.DataFrame(
        {
            "event_id": ["600001.SH:2026-01-05"],
            "symbol": ["600001.SH"],
            "event_date": [day],
        }
    )

    factors = build_event_factor_frame(daily, events)

    assert factors.height == 1
    assert factors["daily__ret_5d"][0] == pytest.approx(0.1)
    assert factors["linkage__deviate_3d"][0] == pytest.approx(0.3)
    assert factors["market__up_ratio"][0] == pytest.approx(0.6)


def test_universe_symbols_reads_daily_history_instead_of_current_instruments(
    tmp_path: Path,
):
    day = date(2026, 1, 5)
    partition = tmp_path / "kline_daily" / f"date={day.isoformat()}"
    partition.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600001.SH"],
            "date": [day],
        }
    ).write_parquet(partition / "part.parquet")
    source = RepositoryDataSource(tmp_path)

    assert source.universe_symbols(day, day) == ["600001.SH"]


def test_validate_minute_layout_rejects_wrong_bar_end_set():
    day = date(2026, 1, 5)
    morning = [
        datetime.combine(day, time(9, 30)) + timedelta(minutes=index)
        for index in range(1, 121)
    ]
    afternoon = [
        datetime.combine(day, time(13, 0)) + timedelta(minutes=index)
        for index in range(1, 121)
    ]
    bar_ends = [*morning, *afternoon]
    bar_ends = [
        (
            datetime.combine(day, time(12, 0))
            if value.time() == time(10, 0)
            else value
        )
        for value in bar_ends
    ]
    frame = pl.DataFrame(
        {
            "symbol": ["600001.SH"] * 240,
            "datetime": bar_ends,
            "bar_start": [
                value - timedelta(minutes=1) for value in bar_ends
            ],
            "bar_end": bar_ends,
            "volume": [100.0] * 240,
            "open_raw": [10.0] * 240,
            "high_raw": [10.1] * 240,
            "low_raw": [9.9] * 240,
            "close_raw": [10.0] * 240,
            "amount_raw": [100_000.0] * 240,
            "open_adj": [10.0] * 240,
            "high_adj": [10.1] * 240,
            "low_adj": [9.9] * 240,
            "close_adj": [10.0] * 240,
            "amount_adj": [100_000.0] * 240,
        }
    )

    report = validate_minute_layout(
        frame,
        {("600001.SH", day)},
    )

    assert report["status"][0] != "complete"
