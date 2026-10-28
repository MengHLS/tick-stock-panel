"""复权认证收口: 仅完整验证签发证据、内容篡改失效、增量/局部不补签、覆盖与键集合。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.backtest.factor import FactorBacktestService
from app.enriched_generation import get_enriched_generation
from app.indicators import pipeline
from app.indicators.price_quality import (
    FactorDataError,
    PriceScaleError,
    coverage_path,
    load_adj_factors_strict,
    read_quality_stamp,
    require_active_token,
    validate_adjusted_scale,
    verify_certification,
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


def _write_coverage(root: Path, symbols, *, status="COMPLETE", start=None, end=None) -> None:
    payload = {
        "asset_type": "stock",
        "basis_date": "2026-10-28",
        "source": "test-fixture:trusted",
        "acquired_at": "2026-10-28T00:00:00+00:00",
        "records": [
            {
                "symbol": symbol,
                "start": str(start or date(2018, 1, 1)),
                "end": str(end or date(2026, 12, 31)),
                "status": status,
                "source": "test-fixture:trusted",
                "acquired_at": "2026-10-28T00:00:00+00:00",
            }
            for symbol in symbols
        ],
    }
    path = coverage_path(root, "stock")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _setup(tmp: Path, *, coverage=True, status="COMPLETE") -> None:
    raw = _raw_frame()
    _write_daily(tmp, raw)
    _write_factors(tmp, _factors_frame())
    if coverage:
        _write_coverage(tmp, raw["symbol"].unique().to_list(), status=status)


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


# ── 认证签发与内容篡改 ──────────────────────────────────────────


def test_full_run_certifies_and_detects_content_tampering(tmp_path: Path) -> None:
    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    stamp = verify_certification(tmp_path, "stock")
    assert stamp["scope"] == "full_history_all_symbols"
    assert stamp["generation"] == get_enriched_generation(tmp_path, "stock")
    require_active_token(tmp_path, "stock")

    # 同 generation 的 enriched 原地改写 -> 内容校验失败。
    part = next((tmp_path / "kline_daily_enriched").glob("date=*/part.parquet"))
    frame = pl.read_parquet(part)
    frame.with_columns((pl.col("close") * 1.01).alias("close")).write_parquet(part)
    with pytest.raises(PriceScaleError, match=r"内容被修改|生成|认证"):
        verify_certification(tmp_path, "stock")

    # 恢复文件后重新全量认证, 再验证 raw 同尺寸改写也会失效。
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")
    raw_part = next((tmp_path / "kline_daily").glob("date=*/part.parquet"))
    raw = pl.read_parquet(raw_part)
    size = raw_part.stat().st_size
    raw.with_columns((pl.col("close") + 0.01).alias("close")).write_parquet(raw_part)
    assert raw_part.stat().st_size == size  # 同大小也要能被识别
    with pytest.raises(PriceScaleError):
        verify_certification(tmp_path, "stock")


def test_partition_added_or_deleted_invalidates_certification(tmp_path: Path) -> None:
    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    partition = next((tmp_path / "kline_daily_enriched").glob("date=*"))
    shutil_target = partition.with_name("date=1999-01-04")
    partition.rename(shutil_target)
    with pytest.raises(PriceScaleError):
        verify_certification(tmp_path, "stock")


# ── 增量/局部不得补签 (审计两例) ─────────────────────────────────


def test_incremental_update_does_not_recertify_old_pollution(tmp_path: Path) -> None:
    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    # 篡改历史污染分区, 再发布一个新日期。
    polluted = tmp_path / "kline_daily_enriched" / "date=2020-04-29" / "part.parquet"
    frame = pl.read_parquet(polluted)
    frame.with_columns(pl.col("raw_close").alias("close")).write_parquet(polluted)
    new_day = date(2020, 5, 18)
    _write_daily(tmp_path, _raw_frame([(new_day, 87.0, 86.98)]))

    pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True)
    with pytest.raises(PriceScaleError, match="认证证据"):
        verify_certification(tmp_path, "stock")
    assert read_quality_stamp(tmp_path, "stock") is None


def test_symbol_update_does_not_certify_other_symbols(tmp_path: Path) -> None:
    _setup(tmp_path)
    other = _raw_frame(
        [(r[0], 100.0 + i, 100.0 + i) for i, r in enumerate(CS_RAW)],
        symbol="000001.SZ",
    )
    _write_daily(tmp_path, other)
    _write_coverage(tmp_path, ["600536.SH", "000001.SZ"])
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    pollution = tmp_path / "kline_daily_enriched" / "date=2020-04-29" / "part.parquet"
    frame = pl.read_parquet(pollution)
    frame = frame.with_columns(
        pl.when(pl.col("symbol") == "000001.SZ").then(pl.col("raw_close")).otherwise(pl.col("close")).alias("close")
    )
    frame.write_parquet(pollution)

    pipeline.run_pipeline(data_dir=tmp_path, symbols=["600536.SH"])
    with pytest.raises(PriceScaleError, match="认证证据"):
        verify_certification(tmp_path, "stock")


# ── 覆盖状态 ────────────────────────────────────────────────────


def test_coverage_unknown_blocks_certification(tmp_path: Path) -> None:
    _setup(tmp_path, coverage=False)
    pipeline.run_pipeline(data_dir=tmp_path)
    assert read_quality_stamp(tmp_path, "stock") is None
    diagnostic = tmp_path / ".enriched_price_quality_stock.diagnostic.json"
    assert diagnostic.exists()
    with pytest.raises(PriceScaleError):
        verify_certification(tmp_path, "stock")


def test_coverage_complete_fixture_allows_certification(tmp_path: Path) -> None:
    _setup(tmp_path, status="COMPLETE")
    pipeline.run_pipeline(data_dir=tmp_path)
    assert verify_certification(tmp_path, "stock")["symbols"] == 1


def test_coverage_incomplete_status_blocks(tmp_path: Path) -> None:
    _setup(tmp_path, status="UNKNOWN")
    pipeline.run_pipeline(data_dir=tmp_path)
    assert read_quality_stamp(tmp_path, "stock") is None


# ── 产品入口: 因子回测 ──────────────────────────────────────────


class _RepoStub:
    def __init__(self, data_dir: Path) -> None:
        self.store = type("Store", (), {"data_dir": data_dir})()


class _EngineStub:
    def __init__(self, data_dir: Path) -> None:
        self.repo = _RepoStub(data_dir)


def test_factor_service_refuses_uncertified_public_entry(tmp_path: Path) -> None:
    from app.backtest.factor import FactorConfig

    service = FactorBacktestService(_EngineStub(tmp_path))
    config = FactorConfig(
        factor_name="momentum_20d",
        symbols=None,
        start=date(2020, 4, 27),
        end=date(2020, 5, 15),
    )
    result = service.run(config)
    assert result.error is not None
    assert "复权认证未通过" in result.error


def test_evidence_write_failure_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    from app.indicators import price_quality as quality

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(quality, "_atomic_write_json", _boom)
    with pytest.raises(OSError):
        pipeline.run_pipeline(data_dir=tmp_path)
    assert read_quality_stamp(tmp_path, "stock") is None
    with pytest.raises(PriceScaleError):
        verify_certification(tmp_path, "stock")


def test_verification_rejects_while_publishing(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    monkeypatch.setattr(
        "app.enriched_generation.enriched_publication_incomplete",
        lambda *args, **kwargs: True,
    )
    with pytest.raises(PriceScaleError, match="发布"):
        verify_certification(tmp_path, "stock")


def test_prepared_token_rejects_missing_and_stale(tmp_path: Path) -> None:
    from app.backtest.strategy import StrategyBacktestService

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")
    service = StrategyBacktestService(_EngineStub(tmp_path), None)  # type: ignore[arg-type]
    config = type("Cfg", (), {"asset_type": "stock"})()
    assert "缺少复权认证令牌" in (service._prepared_token_error(config, None) or "")
    stale = {"generation": "old-generation", "stamp_sha256": "stale"}
    assert "不一致" in (service._prepared_token_error(config, stale) or "")


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


def test_matrix_parquet_direct_entry_requires_certification(tmp_path: Path) -> None:
    from app.backtest.matrix import load_market_data_matrix_from_parquet
    from app.indicators.price_quality import invalidate_certification

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")
    kwargs = dict(
        field_columns=frozenset({"open", "high", "low", "close", "volume"}),
        data_dir=tmp_path,
        asset_type="stock",
    )
    market = load_market_data_matrix_from_parquet(
        tmp_path / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15), **kwargs,
    )
    assert market.shape[1] == 1

    invalidate_certification(tmp_path, "stock", reason="test")
    with pytest.raises(PriceScaleError):
        load_market_data_matrix_from_parquet(
            tmp_path / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15), **kwargs,
        )


def test_generation_lock_blocks_submission_across_processes(tmp_path: Path) -> None:
    import multiprocessing

    from app.enriched_generation import EnrichedGenerationUnavailableError
    from app.indicators.price_quality import certification_submission

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

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
        with pytest.raises(EnrichedGenerationUnavailableError), certification_submission(tmp_path, "stock"):
            pass
    finally:
        release.set()
        proc.join(20)
    assert proc.exitcode == 0
    # 释放后可正常取得提交权。
    with certification_submission(tmp_path, "stock"):
        pass


def test_generation_lock_released_after_process_crash(tmp_path: Path) -> None:
    import multiprocessing

    from app.indicators.price_quality import certification_submission

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

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
    with certification_submission(tmp_path, "stock"):
        pass


def test_matrix_direct_entry_rejects_missing_source_and_foreign_root(tmp_path: Path) -> None:
    from app.backtest.matrix import load_market_data_matrix_from_parquet
    from app.indicators.price_quality import invalidate_certification

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    with pytest.raises(ValueError, match="必须提供明确的数据根"):
        load_market_data_matrix_from_parquet(
            tmp_path / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15),
            field_columns=frozenset({"open", "high", "low", "close", "volume"}),
        )

    # 用 A 数据根的令牌读取 B 目录必须拒绝。
    other = tmp_path / "other"
    (other / "kline_daily_enriched").mkdir(parents=True)
    with pytest.raises(ValueError, match="不属于该认证数据根"):
        load_market_data_matrix_from_parquet(
            other / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15),
            field_columns=frozenset({"open", "high", "low", "close", "volume"}),
            data_dir=tmp_path,
        )

    # 认证失效后旧令牌拒绝; 不依赖 generation 标记是否存在。
    invalidate_certification(tmp_path, "stock", reason="test")
    with pytest.raises(PriceScaleError):
        load_market_data_matrix_from_parquet(
            tmp_path / "kline_daily_enriched", date(2020, 4, 27), date(2020, 5, 15),
            field_columns=frozenset({"open", "high", "low", "close", "volume"}),
            data_dir=tmp_path,
        )


def test_added_partition_after_certification_is_rejected(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.backtest.engine import BacktestEngine

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    src = next((tmp_path / "kline_daily_enriched").glob("date=*/part.parquet"))
    new_dir = tmp_path / "kline_daily_enriched" / "date=2020-05-19"
    new_dir.mkdir(parents=True)
    frame = pl.read_parquet(src).with_columns(
        pl.lit(date(2020, 5, 19)).alias("date"),
        pl.lit(999.0).alias("close"),
    )
    frame.write_parquet(new_dir / "part.parquet")

    with pytest.raises(PriceScaleError, match="新增文件"):
        verify_certification(tmp_path, "stock")

    engine = BacktestEngine(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    with pytest.raises(ValueError, match="认证"):
        engine.load_panel(None, date(2020, 4, 27), date(2020, 4, 30))


def test_active_token_detects_same_generation_content_rewrite(tmp_path: Path) -> None:
    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")
    require_active_token(tmp_path, "stock")

    part = next((tmp_path / "kline_daily_enriched").glob("date=*/part.parquet"))
    frame = pl.read_parquet(part)
    frame.with_columns((pl.col("close") * 1.01).alias("close")).write_parquet(part)
    with pytest.raises(PriceScaleError, match=r"内容被修改|新增文件|删除"):
        require_active_token(tmp_path, "stock")


def test_load_rejects_request_outside_certified_range(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.backtest.engine import BacktestEngine

    _setup(tmp_path)
    pipeline.run_pipeline(data_dir=tmp_path)
    verify_certification(tmp_path, "stock")

    engine = BacktestEngine(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    with pytest.raises(ValueError, match="已认证范围"):
        engine.load_panel(None, date(2026, 1, 1), date(2026, 2, 1))
