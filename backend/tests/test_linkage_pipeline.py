"""联动 sidecar 全量/增量构建与发布契约。"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.custom.cross_sectional_linkage import store as linkage_store
from app.custom.cross_sectional_linkage.store import (
    LinkageCoverageError,
    attach_linkage_columns,
    rebuild_linkage_sidecar,
)
from app.enriched_generation import (
    CLAIM_STALE_SECONDS,
    EnrichedGenerationUnavailableError,
    EnrichedPublication,
    get_enriched_generation,
    recover_stale_publications,
)
from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField, PullConfig


def _business_dates(start: date, count: int) -> list[date]:
    out: list[date] = []
    day = start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def _write_enriched(
    data_dir: Path,
    day: date,
    *,
    multiplier: float = 1.0,
) -> None:
    out = data_dir / "kline_daily_enriched" / f"date={day.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx, symbol in enumerate(("600000.SH", "000001.SZ")):
        close = (10.0 + idx) * multiplier + (day.toordinal() % 17) * 0.01
        rows.append({"symbol": symbol, "date": day, "close": close})
    pl.DataFrame(rows).write_parquet(out)


def _write_index(
    data_dir: Path,
    dates: list[date],
    *,
    marker: str | None = None,
) -> None:
    symbols = ("000002.SH", "399107.SZ", "000688.SH", "399102.SZ", "899050.BJ")
    for day in dates:
        out = (
            data_dir
            / "kline_index_daily"
            / f"date={day.isoformat()}"
            / "part.parquet"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "symbol": symbol,
                "date": day,
                "close": 100.0 + idx * 10 + (day.toordinal() % 13) * 0.1,
            }
            for idx, symbol in enumerate(symbols)
        ]
        frame = pl.DataFrame(rows)
        if marker is not None:
            frame = frame.with_columns(pl.lit(marker).alias("_marker"))
        frame.write_parquet(out)


def _benchmarks(dates: list[date]) -> pl.DataFrame:
    rows = []
    for board_idx, board in enumerate(("SH", "SZ", "STAR", "GEM", "BJ")):
        close = 100.0
        for day_idx, day in enumerate(dates):
            close *= 1.0 + 0.0003 * board_idx + 0.0002 * ((day_idx + board_idx) % 5 - 2)
            rows.append({"date": day, "bench_key": board, "bench_close": close})
    return pl.DataFrame(rows)


def _sidecar_dates(data_dir: Path) -> list[date]:
    base = data_dir / "kline_daily_linkage"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    return sorted(
        date.fromisoformat(day)
        for day in manifest.get("partitions", {})
    )


def _manifest(data_dir: Path) -> dict:
    return json.loads(
        (data_dir / "kline_daily_linkage" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _sidecar_partition(data_dir: Path, day: date) -> Path:
    base = data_dir / "kline_daily_linkage"
    manifest = _manifest(data_dir)
    return (
        base
        / f"date={day.isoformat()}"
        / manifest["partitions"][day.isoformat()]
    )


def test_full_rebuild_covers_finalized_dates_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 1, 2), 8)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(linkage_store, "finalized_trading_dates", lambda *_args, **_kwargs: dates)
    monkeypatch.setattr(linkage_store, "load_benchmark_momentum", lambda _d: _benchmarks(dates))

    written = rebuild_linkage_sidecar(tmp_path, mode="full")

    assert written == len(dates) * 2
    assert _sidecar_dates(tmp_path) == dates
    manifest = _manifest(tmp_path)
    assert manifest["factor_ids"] == sorted(linkage_store.LINKAGE_FACTOR_IDS)
    assert manifest["coverage_start"] == dates[0].isoformat()
    assert manifest["finalized_through"] == dates[-1].isoformat()
    assert manifest["industry_source"] is None
    assert manifest["unavailable_reason"]

    part = pl.read_parquet(
        _sidecar_partition(tmp_path, dates[-1])
    )
    assert set(linkage_store.LINKAGE_FACTOR_IDS) <= set(part.columns)
    assert part["deviate_3d"].null_count() == 0
    assert part["industry_corr_60d"].null_count() == part.height


def test_incremental_writes_only_new_dates_and_reuses_61_day_warmup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_dates = _business_dates(date(2025, 1, 2), 66)
    initial_dates = all_dates[:-1]
    for day in initial_dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: initial_dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _d: _benchmarks(initial_dates),
    )
    rebuild_linkage_sidecar(tmp_path, mode="full")

    sentinel_path = _sidecar_partition(tmp_path, initial_dates[0])
    sentinel = pl.read_parquet(sentinel_path).with_columns(
        pl.lit("keep").alias("_sentinel")
    )
    sentinel.write_parquet(sentinel_path)

    new_day = all_dates[-1]
    _write_enriched(tmp_path, new_day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: all_dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _d: _benchmarks(all_dates),
    )
    ranges: list[tuple[date, date]] = []
    real_compute = linkage_store.compute_linkage_fields

    def spy(enriched, benchmarks, membership, target_dates, **kwargs):
        ranges.append((
            enriched["date"].min(),
            enriched["date"].max(),
        ))
        return real_compute(enriched, benchmarks, membership, target_dates, **kwargs)

    monkeypatch.setattr(linkage_store, "compute_linkage_fields", spy)

    rebuild_linkage_sidecar(tmp_path, mode="incremental")

    assert _sidecar_dates(tmp_path) == all_dates
    assert ranges == [(all_dates[-62], new_day)]
    assert "_sentinel" in pl.read_parquet(sentinel_path).columns


def test_existing_source_change_forces_full_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 2, 3), 8)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(linkage_store, "finalized_trading_dates", lambda *_args, **_kwargs: dates)
    monkeypatch.setattr(linkage_store, "load_benchmark_momentum", lambda _d: _benchmarks(dates))
    rebuild_linkage_sidecar(tmp_path, mode="full")

    first_part = _sidecar_partition(tmp_path, dates[0])
    pl.read_parquet(first_part).with_columns(
        pl.lit("stale").alias("_sentinel")
    ).write_parquet(first_part)
    _write_enriched(tmp_path, dates[2], multiplier=1.15)

    rebuild_linkage_sidecar(tmp_path, mode="incremental")

    assert "_sentinel" not in pl.read_parquet(
        _sidecar_partition(tmp_path, dates[0])
    ).columns


def test_index_benchmark_change_forces_full_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 2, 17), 8)
    for day in dates:
        _write_enriched(tmp_path, day)
    _write_index(tmp_path, dates)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: dates,
    )
    rebuild_linkage_sidecar(tmp_path, mode="full")

    first_part = _sidecar_partition(tmp_path, dates[0])
    pl.read_parquet(first_part).with_columns(
        pl.lit("stale").alias("_sentinel")
    ).write_parquet(first_part)
    _write_index(tmp_path, [dates[2]], marker="benchmark-revision")

    rebuild_linkage_sidecar(tmp_path, mode="incremental")

    assert "_sentinel" not in pl.read_parquet(
        _sidecar_partition(tmp_path, dates[0])
    ).columns


def test_future_industry_snapshot_and_runtime_config_keep_incremental_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 4, 1), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _data_dir: _benchmarks(dates),
    )
    store = ExtConfigStore(tmp_path)
    industry_fields = [
        ExtField("symbol"),
        ExtField("所属同花顺行业"),
    ]

    def config(last_run: str) -> ExtConfig:
        return ExtConfig(
            id="ext_hy_ths_pit",
            label="行业时点",
            mode="timeseries",
            fields=industry_fields,
            pull=PullConfig(
                fanout={"require_complete": True},
                last_run=last_run,
                last_status="success",
            ),
        )

    store.upsert(config("2025-04-01T00:00:00"))
    rebuild_linkage_sidecar(tmp_path, mode="full")
    generation = get_enriched_generation(tmp_path, "linkage")
    sentinel_path = _sidecar_partition(tmp_path, dates[0])
    pl.read_parquet(sentinel_path).with_columns(
        pl.lit("keep").alias("_sentinel")
    ).write_parquet(sentinel_path)

    future_day = dates[-1] + timedelta(days=1)
    future_part = (
        tmp_path / "ext_data" / "ext_hy_ths_pit" / "timeseries"
        / f"date={future_day.isoformat()}" / "part.parquet"
    )
    future_part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "所属同花顺行业": ["一级-银行-三级"],
    }).write_parquet(future_part)
    store.upsert(config("2025-04-02T00:00:00"))

    assert rebuild_linkage_sidecar(tmp_path, mode="incremental") == 0

    manifest = _manifest(tmp_path)
    assert get_enriched_generation(tmp_path, "linkage") == generation
    assert "_sentinel" in pl.read_parquet(sentinel_path).columns
    assert manifest["industry_coverage_start"] is None
    assert "尚无完整日分区" in manifest["unavailable_reason"]


def test_failed_rebuild_recovery_keeps_previous_complete_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 3, 17), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _data_dir: _benchmarks(dates),
    )
    rebuild_linkage_sidecar(tmp_path, mode="full")

    old = attach_linkage_columns(
        pl.DataFrame({
            "symbol": ["600000.SH", "600000.SH"],
            "date": [dates[-2], dates[-1]],
        }),
        {"deviate_3d"},
        tmp_path,
        expected_generation=get_enriched_generation(tmp_path, "linkage"),
        require_complete=True,
    )
    old_values = old["deviate_3d"].to_list()

    for day in dates:
        _write_enriched(tmp_path, day, multiplier=1.25)
    original_write_json = EnrichedPublication.write_json

    def fail_before_manifest(self, payload, out):
        if out.name == "manifest.json" and "kline_daily_linkage" in str(out):
            raise RuntimeError("injected manifest failure")
        return original_write_json(self, payload, out)

    monkeypatch.setattr(EnrichedPublication, "write_json", fail_before_manifest)
    with pytest.raises(RuntimeError, match="manifest failure"):
        rebuild_linkage_sidecar(tmp_path, mode="incremental")

    marker_path = tmp_path / ".matrix_generation_linkage.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["owner_pid"] = 999_999
    marker["updated_at_ns"] = time.time_ns() - int(
        (CLAIM_STALE_SECONDS + 60) * 1e9
    )
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    assert recover_stale_publications(tmp_path) == ["linkage"]
    recovered = attach_linkage_columns(
        pl.DataFrame({
            "symbol": ["600000.SH", "600000.SH"],
            "date": [dates[-2], dates[-1]],
        }),
        {"deviate_3d"},
        tmp_path,
        expected_generation=get_enriched_generation(tmp_path, "linkage"),
        require_complete=True,
    )
    assert recovered["deviate_3d"].to_list() == pytest.approx(old_values)


def test_failed_sidecar_publish_remains_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 3, 3), 3)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(linkage_store, "finalized_trading_dates", lambda *_args, **_kwargs: dates)
    monkeypatch.setattr(linkage_store, "load_benchmark_momentum", lambda _d: _benchmarks(dates))

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected linkage failure")

    monkeypatch.setattr(linkage_store, "compute_linkage_fields", fail)

    with pytest.raises(RuntimeError, match="injected"):
        rebuild_linkage_sidecar(tmp_path, mode="full")

    with pytest.raises(
        EnrichedGenerationUnavailableError,
        match=r"published|publishing",
    ):
        get_enriched_generation(tmp_path, "linkage")


def test_run_pipeline_selects_sidecar_rebuild_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.indicators import pipeline

    modes: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "_run_pipeline_impl",
        lambda **_kwargs: 7,
    )
    monkeypatch.setattr(
        linkage_store,
        "rebuild_linkage_sidecar",
        lambda _data_dir, *, mode: modes.append(mode) or 0,
    )

    assert pipeline.run_pipeline(tmp_path, new_dates_only=True) == 7
    assert pipeline.run_pipeline(
        tmp_path,
        symbols=["600000.SH"],
        new_dates_only=True,
    ) == 7

    assert modes == ["incremental", "full"]


def test_timeseries_industry_source_is_recorded_and_snapshot_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 4, 1), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(linkage_store, "finalized_trading_dates", lambda *_args, **_kwargs: dates)
    monkeypatch.setattr(linkage_store, "load_benchmark_momentum", lambda _d: _benchmarks(dates))
    store = ExtConfigStore(tmp_path)
    industry_fields = [
        ExtField("symbol"),
        ExtField("所属同花顺行业"),
    ]
    store.upsert(ExtConfig(
        id="ext_hy_ths_pit",
        label="行业时点",
        mode="timeseries",
        fields=industry_fields,
        pull=PullConfig(fanout={"require_complete": True}),
    ))
    store.upsert(ExtConfig(
        id="ext_hy_ths",
        label="行业快照",
        mode="snapshot",
        fields=industry_fields,
    ))
    ext_part = (
        tmp_path / "ext_data" / "ext_hy_ths_pit" / "timeseries"
        / f"date={dates[-1].isoformat()}" / "part.parquet"
    )
    ext_part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "所属同花顺行业": ["一级-银行-三级"],
    }).write_parquet(ext_part)

    rebuild_linkage_sidecar(tmp_path, mode="full")

    manifest = _manifest(tmp_path)
    assert manifest["industry_source"] == "ext_hy_ths_pit"
    assert manifest["industry_pit"] is True
    assert manifest["industry_source_signature"]
    assert manifest["unavailable_reason"] is None


@pytest.mark.parametrize(
    "pull",
    [
        None,
        PullConfig(fanout=None),
        PullConfig(fanout={"concurrency": 8}),
    ],
    ids=["no-pull", "no-fanout", "incomplete-fanout"],
)
def test_incomplete_industry_fanout_is_not_used_as_pit_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pull: PullConfig | None,
) -> None:
    dates = _business_dates(date(2025, 4, 14), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _data_dir: _benchmarks(dates),
    )
    store = ExtConfigStore(tmp_path)
    store.upsert(ExtConfig(
        id="custom_industry",
        label="不完整行业",
        mode="timeseries",
        fields=[ExtField("symbol"), ExtField("所属同花顺行业")],
        pull=pull,
    ))
    ext_part = (
        tmp_path
        / "ext_data"
        / "custom_industry"
        / "timeseries"
        / f"date={dates[-1].isoformat()}"
        / "part.parquet"
    )
    ext_part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "所属同花顺行业": ["一级-银行-三级"],
    }).write_parquet(ext_part)

    rebuild_linkage_sidecar(tmp_path, mode="full")

    manifest = _manifest(tmp_path)
    assert manifest["industry_source"] is None
    assert manifest["industry_pit"] is False
    assert "require_complete" in manifest["unavailable_reason"]


def test_attach_linkage_columns_joins_stable_sidecar_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 5, 1), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(linkage_store, "finalized_trading_dates", lambda *_args, **_kwargs: dates)
    monkeypatch.setattr(linkage_store, "load_benchmark_momentum", lambda _d: _benchmarks(dates))
    rebuild_linkage_sidecar(tmp_path, mode="full")
    generation = get_enriched_generation(tmp_path, "linkage")
    frame = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "date": [dates[-1], dates[-1]],
        "close": [11.0, 12.0],
    })

    attached = attach_linkage_columns(
        frame,
        {"deviate_3d", "industry_corr_60d"},
        tmp_path,
        expected_generation=generation,
        require_complete=True,
    )

    assert attached["symbol"].to_list() == ["000001.SZ", "600000.SH"]
    assert "deviate_3d" in attached.columns
    assert "industry_corr_60d" in attached.columns
    assert attached["deviate_3d"].null_count() == 0

    with pytest.raises(LinkageCoverageError, match="覆盖不足"):
        attach_linkage_columns(
            pl.DataFrame({
                "symbol": ["600000.SH"],
                "date": [date(2025, 6, 2)],
                "close": [10.0],
            }),
            {"deviate_3d"},
            tmp_path,
            expected_generation=generation,
            require_complete=True,
        )


def test_attach_linkage_columns_rejects_missing_symbol_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _business_dates(date(2025, 5, 12), 4)
    for day in dates:
        _write_enriched(tmp_path, day)
    monkeypatch.setattr(
        linkage_store,
        "finalized_trading_dates",
        lambda *_args, **_kwargs: dates,
    )
    monkeypatch.setattr(
        linkage_store,
        "load_benchmark_momentum",
        lambda _data_dir: _benchmarks(dates),
    )
    rebuild_linkage_sidecar(tmp_path, mode="full")

    partition = _sidecar_partition(tmp_path, dates[-1])
    pl.read_parquet(partition).filter(
        pl.col("symbol") == "600000.SH"
    ).write_parquet(partition)

    with pytest.raises(LinkageCoverageError, match="缺标的"):
        attach_linkage_columns(
            pl.DataFrame({
                "symbol": ["000001.SZ", "600000.SH"],
                "date": [dates[-1], dates[-1]],
            }),
            {"deviate_3d"},
            tmp_path,
            expected_generation=get_enriched_generation(tmp_path, "linkage"),
            require_complete=True,
        )
