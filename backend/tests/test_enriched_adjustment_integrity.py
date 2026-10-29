"""复权尺度、因子完整性与发布锁回归。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.indicators import pipeline
from app.indicators.price_quality import (
    FactorDataError,
    PriceScaleError,
    load_adj_factors_strict,
    validate_adjusted_scale,
)

CS_RAW = [
    (date(2020, 4, 27), 82.88, 78.5),
    (date(2020, 4, 28), 78.45, 78.1),
    (date(2020, 4, 29), 76.88, 76.17),
    (date(2020, 4, 30), 76.84, 82.7),
    (date(2020, 5, 6), 83.79, 89.49),
    (date(2020, 5, 7), 89.48, 88.5),
    (date(2020, 5, 8), 90.0, 89.0),
    (date(2020, 5, 11), 89.6, 86.3),
    (date(2020, 5, 14), 85.21, 84.49),
    (date(2020, 5, 15), 85.5, 86.45),
]
CS_FACTORS = [
    (date(2020, 6, 5), 1.000511),
    (date(2021, 5, 28), 1.000714),
    (date(2022, 6, 14), 1.301353),
    (date(2023, 6, 2), 1.300512),
]


def _raw_frame(rows=CS_RAW, symbol="600536.SH") -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol] * len(rows),
        "date": [r[0] for r in rows],
        "open": [r[1] for r in rows],
        "high": [max(r[1], r[2]) * 1.01 for r in rows],
        "low": [min(r[1], r[2]) * 0.99 for r in rows],
        "close": [r[2] for r in rows],
        "volume": [1_000_000.0] * len(rows),
        "amount": [1.0e8] * len(rows),
    })


def _factors_frame(rows=CS_FACTORS, symbol="600536.SH") -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol] * len(rows),
        "trade_date": [r[0] for r in rows],
        "ex_factor": [r[1] for r in rows],
    })


def _write_daily(root: Path, frame: pl.DataFrame) -> None:
    for part in frame.partition_by("date"):
        day = part["date"][0]
        path = root / "kline_daily" / f"date={day}" / "part.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        part.write_parquet(path)


def _write_factors(root: Path, frame: pl.DataFrame) -> None:
    path = root / "adj_factor" / "all.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def _setup(tmp: Path) -> None:
    raw = _raw_frame()
    _write_daily(tmp, raw)
    _write_factors(tmp, _factors_frame())


def _hold_generation_lock(data_dir, asset, ready, release, crash):
    """子进程持 generation 文件锁; crash=True 时持锁直接退出 (操作系统释放)。"""
    import os

    from app.enriched_generation import _exclusive_generation_lock

    with _exclusive_generation_lock(Path(data_dir), asset):
        ready.set()
        if crash:
            os._exit(9)
        release.wait(20)


# ── 尺度校验与键集合 ────────────────────────────────────────────


def test_scale_rejects_mixed_basis_and_unexplained_jumps() -> None:
    raw = _raw_frame()
    factors = _factors_frame()
    adjusted = pipeline.compute_enriched(raw, factors=factors)
    validate_adjusted_scale(adjusted, raw, factors)

    mixed = adjusted.with_columns(
        pl.when(pl.col("date") >= date(2020, 5, 8))
        .then(pl.col("raw_close"))
        .otherwise(pl.col("close"))
        .alias("close")
    )
    with pytest.raises(PriceScaleError, match="600536"):
        validate_adjusted_scale(mixed, raw, factors)


def test_scale_keyset_closure_missing_extra_duplicate() -> None:
    raw = _raw_frame()
    factors = _factors_frame()
    adjusted = pipeline.compute_enriched(raw, factors=factors)

    missing = adjusted.filter(pl.col("date") != date(2020, 5, 8))
    with pytest.raises(PriceScaleError, match="缺少"):
        validate_adjusted_scale(missing, raw, factors)

    extra_row = adjusted.head(1).with_columns(pl.lit(date(2020, 5, 9)).alias("date"))
    extra = pl.concat([adjusted, extra_row])
    with pytest.raises(PriceScaleError, match="多余"):
        validate_adjusted_scale(extra, raw, factors)

    duplicated = pl.concat([adjusted, adjusted.head(1)])
    with pytest.raises(PriceScaleError, match="重复"):
        validate_adjusted_scale(duplicated, raw, factors)


def test_strict_factors_fail_closed() -> None:
    with pytest.raises(FactorDataError):
        load_adj_factors_strict(Path("does-not-exist") / "all.parquet")


def test_incremental_matches_full_all_storage_columns(tmp_path: Path) -> None:
    from app.indicators.pipeline import ENRICHED_STORAGE_COLS

    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    _setup(dir_a)
    _setup(dir_b)
    pipeline.run_pipeline(data_dir=dir_a)
    pipeline.run_pipeline(data_dir=dir_b)

    new_day = date(2020, 5, 18)
    new_rows = _raw_frame([(new_day, 87.0, 86.98)])
    _write_daily(dir_a, new_rows)
    _write_daily(dir_b, new_rows)
    pipeline.run_pipeline(data_dir=dir_a, new_dates_only=True)
    pipeline.run_pipeline(data_dir=dir_b)

    part_a = pl.read_parquet(dir_a / "kline_daily_enriched" / f"date={new_day}" / "part.parquet")
    part_b = pl.read_parquet(dir_b / "kline_daily_enriched" / f"date={new_day}" / "part.parquet")
    for column in ENRICHED_STORAGE_COLS:
        if column not in part_a.columns or column not in part_b.columns:
            continue
        left = part_a[column].to_list()
        right = part_b[column].to_list()
        if part_a[column].dtype.is_float():
            assert left == pytest.approx(right, rel=1e-9, abs=1e-9), column
        else:
            assert left == right, column


def test_matrix_load_does_not_require_certification_files(tmp_path: Path) -> None:
    from app.backtest.matrix import load_market_data_matrix_from_parquet

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    assert not list(tmp_path.glob(".enriched_*"))
    assert not (tmp_path / "adj_factor" / "coverage_stock.json").exists()

    market = load_market_data_matrix_from_parquet(
        tmp_path / "kline_daily_enriched",
        date(2020, 4, 27),
        date(2020, 5, 15),
        field_columns=frozenset({"open", "high", "low", "close", "volume"}),
        data_dir=tmp_path,
        asset_type="stock",
    )
    assert market.shape[1] == 1


def test_generation_lock_blocks_submission_across_processes(tmp_path: Path) -> None:
    import multiprocessing

    from app.enriched_generation import (
        EnrichedGenerationUnavailableError,
        _exclusive_generation_lock,
    )

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)

    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    proc = ctx.Process(
        target=_hold_generation_lock,
        args=(str(tmp_path), "stock", ready, release, False),
    )
    proc.start()
    try:
        assert ready.wait(15)
        # 另一进程持锁时, 最终提交必须立即失败, 不能无限等待。
        with pytest.raises(EnrichedGenerationUnavailableError), _exclusive_generation_lock(
            tmp_path, "stock",
        ):
            pass
    finally:
        release.set()
        proc.join(20)
    assert proc.exitcode == 0
    # 释放后可正常取得提交权。
    with _exclusive_generation_lock(tmp_path, "stock"):
        pass


def test_generation_lock_released_after_process_crash(tmp_path: Path) -> None:
    import multiprocessing

    from app.enriched_generation import _exclusive_generation_lock

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)

    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    proc = ctx.Process(
        target=_hold_generation_lock,
        args=(str(tmp_path), "stock", ready, release, True),
    )
    proc.start()
    assert ready.wait(15)
    proc.join(20)
    assert proc.exitcode == 9
    # 进程异常退出后文件锁由操作系统释放, 后续提交可取得。
    with _exclusive_generation_lock(tmp_path, "stock"):
        pass


def test_matrix_direct_entry_rejects_missing_source_and_foreign_root(tmp_path: Path) -> None:
    from app.backtest.matrix import load_market_data_matrix_from_parquet

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)

    with pytest.raises(ValueError, match="必须提供明确的数据根"):
        load_market_data_matrix_from_parquet(
            tmp_path / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15),
            field_columns=frozenset({"open", "high", "low", "close", "volume"}),
        )

    # 用 A 数据根读取 B 目录必须拒绝。
    other = tmp_path / "other"
    (other / "kline_daily_enriched").mkdir(parents=True)
    with pytest.raises(ValueError, match="不属于该数据根"):
        load_market_data_matrix_from_parquet(
            other / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15),
            field_columns=frozenset({"open", "high", "low", "close", "volume"}),
            data_dir=tmp_path,
        )
