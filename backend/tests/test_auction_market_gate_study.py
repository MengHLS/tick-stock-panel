"""Contracts for the D-1 market-regime gate."""

from datetime import date, timedelta

import polars as pl

from scripts import auction_market_gate_study as study


def test_market_features_use_only_prior_completed_close():
    start = date(2024, 1, 1)
    closes = [100.0] * 80 + [50.0]
    index = pl.DataFrame({
        "date": [start + timedelta(days=offset) for offset in range(len(closes))],
        "close": closes,
    })

    features = study.compute_market_features(index)
    last = features.row(-1, named=True)

    assert last["market_prev_close"] == 100.0
    assert last["trend_gate"] is True
    assert last["vol_gate"] is True


def test_build_market_features_reads_index_partitions(tmp_path, monkeypatch):
    start = date(2024, 1, 1)
    index = pl.DataFrame({
        "symbol": ["000001.SH"] * 100,
        "date": [start + timedelta(days=offset) for offset in range(100)],
        "close": [100.0 + offset / 100 for offset in range(100)],
        "quote_ts": [0] * 100,
    })
    path = tmp_path / "part.parquet"
    index.write_parquet(path)
    monkeypatch.setattr(study, "_partitions", lambda *_args: [path])

    features = study.build_market_features(tmp_path, start, date(2024, 4, 9))

    assert features.height == 100
    assert features["market_prev_close"].null_count() == 1


def test_market_variants_filter_without_refilling():
    frame = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH", "600004.SH"],
        "trend_gate": [True, False, True, False],
        "vol_gate": [True, True, False, False],
    })

    assert study.apply_market_variant(frame, "trend_gate")["symbol"].to_list() == [
        "600001.SH", "600003.SH",
    ]
    assert study.apply_market_variant(frame, "vol_gate")["symbol"].to_list() == [
        "600001.SH", "600002.SH",
    ]
    assert study.apply_market_variant(
        frame,
        "trend_vol_gate",
    )["symbol"].to_list() == ["600001.SH"]
