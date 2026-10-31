"""Contract tests for importing qdc-data/mint minute Parquet."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from app.services.minute_adjust import minute_basis_is_raw
from scripts.import_mint_minutes import import_mint_minutes


def _epoch_ms(y: int, m: int, d: int, hh: int, mm: int) -> int:
    # Source ts uses standard UTC epoch milliseconds.
    return int(datetime(y, m, d, hh - 8, mm, tzinfo=UTC).timestamp() * 1000)


def _write_source(path: Path, rows: list[dict]) -> None:
    defaults = {
        "source": "tdx_mootdx",
        "ingested_at": _epoch_ms(2026, 9, 1, 18, 0),
    }
    pl.DataFrame([{**defaults, **row} for row in rows]).write_parquet(path)


def _bar(
    *,
    ts: int,
    symbol: str,
    close: float = 10.0,
    volume: float = 42_300.0,
    amount: float = 423_000.0,
) -> dict:
    return {
        "ts": ts,
        "symbol": symbol,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
        "amount": amount,
    }


def test_import_preserves_values_and_normalizes_contract(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "2026-09.parquet"
    _write_source(
        source,
        [
            _bar(
                ts=_epoch_ms(2026, 9, 1, 9, 30),
                symbol="600519.XSHG",
                close=1295.0,
            ),
            _bar(
                ts=_epoch_ms(2026, 9, 1, 13, 1),
                symbol="000001.XSHE",
                close=10.25,
                amount=101_000.0,
            ),
            _bar(
                ts=_epoch_ms(2026, 9, 2, 9, 30),
                symbol="920001.XBSE",
                close=8.5,
            ),
        ],
    )
    data_dir = tmp_path / "data"

    result = import_mint_minutes(source_dir, data_dir, threads=2, memory_limit="512MB")

    assert len(result) == 1
    assert result[0].rows == 3
    assert result[0].partitions == 2
    assert minute_basis_is_raw(data_dir)

    first = pl.read_parquet(
        data_dir / "kline_minute" / "date=2026-09-01" / "part.parquet"
    )
    assert first.columns == [
        "symbol",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    assert first["symbol"].to_list() == ["000001.SZ", "600519.SH"]
    assert first["datetime"].to_list() == [
        datetime(2026, 9, 1, 13, 1),
        datetime(2026, 9, 1, 9, 30),
    ]
    assert first["close"].to_list() == [10.25, 1295.0]
    assert first["volume"].to_list() == [423.0, 423.0]

    second = pl.read_parquet(
        data_dir / "kline_minute" / "date=2026-09-02" / "part.parquet"
    )
    assert second["symbol"].to_list() == ["920001.BJ"]

    manifest = data_dir / "kline_minute" / ".mint_import_manifest.json"
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert str(source.resolve()) in payload["files"]


def test_import_is_idempotent_by_partition_row_count(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_source(
        source_dir / "2026-09.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 9, 1, 9, 30),
                symbol="600519.XSHG",
            )
        ],
    )
    data_dir = tmp_path / "data"

    first = import_mint_minutes(source_dir, data_dir, threads=2, memory_limit="512MB")
    second = import_mint_minutes(source_dir, data_dir, threads=2, memory_limit="512MB")

    assert first[0].partitions == 1
    assert second[0].partitions == 0
    assert second[0].skipped_dates == 1
    stored = pl.read_parquet(
        data_dir / "kline_minute" / "date=2026-09-01" / "part.parquet"
    )
    assert stored.height == 1


def test_import_rejects_duplicate_bars_before_promotion(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    duplicate = _bar(
        ts=_epoch_ms(2026, 9, 1, 9, 30),
        symbol="600519.XSHG",
    )
    _write_source(source_dir / "2026-09.parquet", [duplicate, duplicate])
    data_dir = tmp_path / "data"

    with pytest.raises(ValueError, match="duplicate_rows"):
        import_mint_minutes(source_dir, data_dir, threads=2, memory_limit="512MB")

    assert not (
        data_dir / "kline_minute" / "date=2026-09-01" / "part.parquet"
    ).exists()


def test_import_rejects_unknown_symbol_suffix(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_source(
        source_dir / "2026-09.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 9, 1, 9, 30),
                symbol="600519.UNKNOWN",
            )
        ],
    )

    with pytest.raises(ValueError, match="bad_symbols"):
        import_mint_minutes(
            source_dir,
            tmp_path / "data",
            threads=2,
            memory_limit="512MB",
        )


def test_import_refuses_to_mix_legacy_adjusted_partitions(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_source(
        source_dir / "2026-09.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 9, 1, 9, 30),
                symbol="600519.XSHG",
            )
        ],
    )
    legacy = tmp_path / "data" / "kline_minute" / "date=2026-08-31"
    legacy.mkdir(parents=True)
    pl.DataFrame({"symbol": ["600519.SH"], "close": [1.0]}).write_parquet(
        legacy / "part.parquet"
    )

    with pytest.raises(ValueError, match="legacy data without"):
        import_mint_minutes(
            source_dir,
            tmp_path / "data",
            threads=2,
            memory_limit="512MB",
        )


def test_date_range_limits_import(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_source(
        source_dir / "2026-09.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 9, 1, 9, 30),
                symbol="600519.XSHG",
            ),
            _bar(
                ts=_epoch_ms(2026, 9, 2, 9, 30),
                symbol="600519.XSHG",
            ),
        ],
    )

    result = import_mint_minutes(
        source_dir,
        tmp_path / "data",
        start=date(2026, 9, 2),
        end=date(2026, 9, 2),
        threads=2,
        memory_limit="512MB",
    )

    assert result[0].rows == 1
    assert not (
        tmp_path / "data" / "kline_minute" / "date=2026-09-01" / "part.parquet"
    ).exists()
    assert (
        tmp_path / "data" / "kline_minute" / "date=2026-09-02" / "part.parquet"
    ).exists()


def test_source_file_selection_limits_discovery(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_source(
        source_dir / "2026-01.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 1, 5, 9, 30),
                symbol="600519.XSHG",
            )
        ],
    )
    _write_source(
        source_dir / "2026-02.parquet",
        [
            _bar(
                ts=_epoch_ms(2026, 2, 2, 9, 30),
                symbol="600519.XSHG",
            )
        ],
    )

    result = import_mint_minutes(
        source_dir,
        tmp_path / "data",
        source_files=["2026-02.parquet"],
        threads=2,
        memory_limit="512MB",
    )

    assert len(result) == 1
    assert result[0].source == "2026-02.parquet"
    assert not (
        tmp_path / "data" / "kline_minute" / "date=2026-01-05" / "part.parquet"
    ).exists()
    assert (
        tmp_path / "data" / "kline_minute" / "date=2026-02-02" / "part.parquet"
    ).exists()
