"""联动 sidecar 的 finalized 会话与稳定读取契约。"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

from app.enriched_generation import (
    EnrichedGenerationUnavailableError,
    bump_enriched_generation,
)
from app.factors.linkage_store import (
    LinkageReadUnstableError,
    finalized_trading_dates,
    stable_linkage_read,
)
from app.market_time import CN_TZ


def _write_daily(
    data_dir: Path,
    day: date,
    closes: dict[str, float],
    *,
    quote_ts: int | None = None,
) -> None:
    out = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame({
        "symbol": list(closes),
        "date": [day] * len(closes),
        "open": [value - 0.1 for value in closes.values()],
        "high": [value + 0.1 for value in closes.values()],
        "low": [value - 0.2 for value in closes.values()],
        "close": list(closes.values()),
        "volume": [1000.0] * len(closes),
        "amount": [10000.0] * len(closes),
    })
    if quote_ts is not None:
        frame = frame.with_columns(pl.lit(quote_ts).alias("quote_ts"))
    frame.write_parquet(out)


def _write_enriched(
    data_dir: Path,
    day: date,
    closes: dict[str, float],
) -> None:
    out = data_dir / "kline_daily_enriched" / f"date={day.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": list(closes),
        "date": [day] * len(closes),
        "raw_close": list(closes.values()),
    }).write_parquet(out)


def test_finalized_dates_exclude_today_before_close(tmp_path: Path) -> None:
    day = date(2026, 10, 30)
    _write_daily(tmp_path, day, {"600000.SH": 10.0})
    _write_enriched(tmp_path, day, {"600000.SH": 10.0})

    midday = datetime(2026, 10, 30, 12, 0, tzinfo=CN_TZ)

    assert finalized_trading_dates(tmp_path, now=midday) == []


def test_finalized_dates_include_today_after_close_when_complete(tmp_path: Path) -> None:
    day = date(2026, 10, 30)
    _write_daily(tmp_path, day, {"600000.SH": 10.0, "000001.SZ": 8.0})
    _write_enriched(tmp_path, day, {"600000.SH": 10.0, "000001.SZ": 8.0})

    after_close = datetime(2026, 10, 30, 15, 30, tzinfo=CN_TZ)

    assert finalized_trading_dates(tmp_path, now=after_close) == [day]


def test_finalized_dates_require_exact_symbol_coverage(tmp_path: Path) -> None:
    day = date(2026, 10, 29)
    _write_daily(tmp_path, day, {"600000.SH": 10.0, "000001.SZ": 8.0})
    _write_enriched(tmp_path, day, {"600000.SH": 10.0})

    assert finalized_trading_dates(
        tmp_path, now=datetime(2026, 11, 1, 12, 0, tzinfo=CN_TZ)
    ) == []


def test_finalized_dates_reject_raw_close_mismatch(tmp_path: Path) -> None:
    day = date(2026, 10, 28)
    _write_daily(tmp_path, day, {"600000.SH": 10.0})
    _write_enriched(tmp_path, day, {"600000.SH": 10.02})

    assert finalized_trading_dates(
        tmp_path, now=datetime(2026, 11, 1, 12, 0, tzinfo=CN_TZ)
    ) == []


def test_finalized_dates_require_both_daily_and_enriched_proof(tmp_path: Path) -> None:
    day = date(2026, 10, 27)
    _write_daily(tmp_path, day, {"600000.SH": 10.0})

    assert finalized_trading_dates(
        tmp_path, now=datetime(2026, 11, 1, 12, 0, tzinfo=CN_TZ)
    ) == []


def test_finalized_dates_reject_old_intraday_snapshot_outside_scan_window(
    tmp_path: Path,
) -> None:
    day = date(2026, 10, 5)
    quote_ts = int(datetime(2026, 10, 5, 10, 0, tzinfo=CN_TZ).timestamp() * 1000)
    _write_daily(tmp_path, day, {"600000.SH": 10.0}, quote_ts=quote_ts)
    _write_enriched(tmp_path, day, {"600000.SH": 10.0})

    assert finalized_trading_dates(
        tmp_path, now=datetime(2026, 11, 1, 12, 0, tzinfo=CN_TZ)
    ) == []


def test_stable_linkage_read_rejects_mid_read_generation_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = bump_enriched_generation(tmp_path, "linkage")
    values = iter([generation, "different-generation"])

    monkeypatch.setattr(
        "app.factors.linkage_store.get_enriched_generation",
        lambda *_args, **_kwargs: next(values),
    )

    with (
        pytest.raises(LinkageReadUnstableError, match="changed"),
        stable_linkage_read(
            tmp_path,
            expected_generation=generation,
        ),
    ):
        pass


def test_stable_linkage_read_fails_closed_when_publication_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.factors.linkage_store.get_enriched_generation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            EnrichedGenerationUnavailableError("publishing")
        ),
    )

    with (
        pytest.raises(EnrichedGenerationUnavailableError, match="publishing"),
        stable_linkage_read(tmp_path),
    ):
        pass
