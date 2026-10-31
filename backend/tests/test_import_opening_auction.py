import json
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import polars as pl
import pytest

from scripts.import_opening_auction import (
    _import_member,
    archive_members,
    build_features,
    normalize_snapshots,
    publish_features,
    store_day,
)


def source_rows():
    rows = []
    for symbol in ("600000.SH", "000001.SZ", "920000.BJ"):
        for time, price, matched, buy, sell in (
            (91959000, 10.0, 100, 20, 0),
            (92001000, 10.1, 150, 0, 30),
            (92359000, 10.2, 200, 40, 0),
            (92449000, 10.3, 250, 50, 0),
            (92459000, 10.4, 300, 0, 60),
            (92502000, 10.5, 999, 99, 0),
        ):
            final = time >= 92500000
            rows.append({
                "security_id": symbol,
                "md_date": 20240902,
                "md_time": time,
                "min": 9.0,
                "max": 11.0,
                "pre_close": 10.0,
                "last": price,
                "open": 10.5 if final else 0.0,
                "num_trades": 10 if final else 0,
                "total_volume_trade": 400 if final else 0,
                "total_value_trade": 420000 if final else 0,
                "bid1": price,
                "bid2": 0.0,
                "bid_size1": matched,
                "bid_size2": buy,
                "ask1": price + (0.1 if final else 0),
                "ask2": 0.0,
                "ask_size1": matched,
                "ask_size2": sell,
            })
    return pl.DataFrame(rows)


def test_cutoffs_do_not_use_future_snapshots_or_final_book():
    snapshots = normalize_snapshots(source_rows(), date(2024, 9, 2))
    pre, result = build_features(snapshots)
    row = pre.filter(pl.col("symbol") == "600000.SH").row(0, named=True)
    assert row["c0920_time"] == 91959000
    assert row["c0920_age_ms"] == 1000
    assert row["c0920_matched_shares"] == 10000
    assert row["c0924_matched_shares"] == 20000
    assert row["c092450_matched_shares"] == 25000
    assert row["last_matched_shares"] == 30000
    assert row["last_unmatched_sell_shares"] == 6000
    assert row["last_minute_matched_delta_shares"] == 10000
    assert row["last_gap"] == pytest.approx(0.04)
    assert row["last_imbalance"] == pytest.approx(-1 / 6)
    assert pre["symbol"].to_list() == ["000001.SZ", "600000.SH"]
    assert snapshots.filter(pl.col("symbol") == "920000.BJ").height == 6
    final = result.filter(pl.col("symbol") == "600000.SH").row(0, named=True)
    assert final["result_time"] == 92502000
    assert final["volume_shares"] == 40000
    assert final["amount"] == 420000
    assert final["auction_open"] == 10.5


def test_missing_cutoff_and_final_are_null_not_zero():
    source = source_rows().filter(
        (pl.col("md_time") > 92000000) & (pl.col("md_time") < 92500000)
    )
    pre, result = build_features(normalize_snapshots(source, date(2024, 9, 2)))
    assert pre["c0920_matched_shares"].null_count() == 2
    assert result["volume_shares"].null_count() == 2
    assert result["has_result"].to_list() == [0, 0]


def test_zero_price_keeps_zero_quantity_but_not_negative_100_percent_return():
    source = source_rows().with_columns([
        pl.when(pl.col("md_time") < 92500000).then(0).otherwise(pl.col(c)).alias(c)
        for c in ("bid1", "ask1", "bid_size1", "ask_size1")
    ])
    pre, _ = build_features(normalize_snapshots(source, date(2024, 9, 2)))
    assert pre["last_matched_shares"].to_list() == [0, 0]
    assert pre["last_ref_price"].null_count() == 2
    assert pre["last_gap"].null_count() == 2
    assert pre["last_minute_price_change"].null_count() == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_invalid_result_price_cannot_become_valid_trade(bad):
    source = source_rows().with_columns(
        pl.when(pl.col("md_time") >= 92500000)
        .then(pl.lit(bad)).otherwise(pl.col("open")).alias("open")
    )
    _, result = build_features(normalize_snapshots(source, date(2024, 9, 2)))
    assert result["has_result"].to_list() == [0, 0]
    assert result["auction_open"].null_count() == 2
    assert result["opening_gap"].null_count() == 2


def test_wrong_date_and_fractional_lots_fail_closed():
    with pytest.raises(ValueError, match="date"):
        normalize_snapshots(source_rows(), date(2024, 9, 3))
    invalid = source_rows().with_columns(pl.lit(1.5).alias("bid_size1"))
    with pytest.raises(ValueError, match="quantity"):
        normalize_snapshots(invalid, date(2024, 9, 2))


def test_invalid_preopen_book_is_not_treated_as_matched():
    source = source_rows().with_columns(
        pl.when(pl.col("md_time") == 92459000)
        .then(pl.col("ask1") + 0.1)
        .otherwise(pl.col("ask1"))
        .alias("ask1")
    )
    pre, _ = build_features(normalize_snapshots(source, date(2024, 9, 2)))
    assert pre["invalid_preopen_rows"].to_list() == [1, 1]
    assert pre["last_time"].to_list() == [92449000, 92449000]
    assert pre["last_age_ms"].to_list() == [11000, 11000]


def test_archive_listing_in_non_ascii_directory(tmp_path):
    import shutil

    seven = shutil.which("7z") or shutil.which("7zz")
    bundled = Path(r"C:\Program Files\NVIDIA Corporation\NVIDIA app\7z.exe")
    if not seven and bundled.exists():
        seven = str(bundled)
    if not seven:
        pytest.skip("7-Zip not installed")
    folder = tmp_path / "\u96c6\u5408\u7ade\u4ef7"
    folder.mkdir()
    archive = folder / "202409.rar"
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("202409/20240902.csv", "header\nrow\n")
    members = archive_members(seven, archive)
    assert [(name.replace("\\", "/"), day) for name, day in members] == [
        ("202409/20240902.csv", date(2024, 9, 2))
    ]


def test_resume_verifies_outputs_and_source_signature(tmp_path):
    snapshots = normalize_snapshots(source_rows(), date(2024, 9, 2))
    first = store_day(snapshots, tmp_path, "fixture-v1")
    assert not first["skipped"]
    assert first["feature_rows"] == 2
    second = store_day(snapshots, tmp_path, "fixture-v1")
    assert second["skipped"]
    with pytest.raises(ValueError, match="source"):
        store_day(snapshots, tmp_path, "fixture-v2")
    (tmp_path / "quotes" / "date=2024-09-02" / "part.parquet").unlink()
    with pytest.raises(ValueError, match="output"):
        store_day(snapshots, tmp_path, "fixture-v1")


def test_feature_upgrade_uses_cached_snapshots_without_extractor(tmp_path):
    day = date(2024, 9, 2)
    store_day(normalize_snapshots(source_rows(), day), tmp_path, "fixture-v1")
    marker = tmp_path / "manifests" / "2024-09-02.json"
    record = json.loads(marker.read_text())
    record["feature_version"] = 1
    marker.write_text(json.dumps(record))
    result = _import_member(
        "not-an-executable", Path("not-an-archive"), "unused.csv",
        day, tmp_path, "fixture-v1",
    )
    assert not result["skipped"]
    assert result["feature_version"] == 2
    assert pl.read_parquet(
        tmp_path / "preopen" / "date=2024-09-02" / "part.parquet"
    )["last_matched_shares"].to_list() == [30000, 30000]


def test_published_features_join_existing_historical_factor_path(tmp_path):
    from app.factors import ext_factors
    from app.services.ext_data import _load_all_cache

    output = tmp_path / "processed"
    data_dir = tmp_path / "data"
    store_day(
        normalize_snapshots(source_rows(), date(2024, 9, 2)), output, "fixture-v1"
    )
    stats = publish_features(output, data_dir)
    assert stats["published_partitions"] == 2
    assert publish_features(output, data_dir)["published_partitions"] == 0
    panel = pl.DataFrame({
        "symbol": ["600000.SH", "600000.SH"],
        "date": [date(2024, 9, 2), date(2024, 9, 3)],
    })
    attached = ext_factors.attach_ext_columns(panel, data_dir=data_dir, include_snapshot=False)
    col = "ext_auction_preopen_last_matched_shares"
    assert attached[col].to_list() == [30000.0, None]
    names = ext_factors.numeric_timeseries_ext_columns(data_dir)
    assert col in names
    assert "ext_auction_result_volume_shares" in names
    _load_all_cache.clear()
    ext_factors._frame_cache.clear()


def test_publish_refuses_unowned_existing_extension(tmp_path):
    output = tmp_path / "processed"
    data_dir = tmp_path / "data"
    store_day(normalize_snapshots(source_rows(), date(2024, 9, 2)), output, "fixture-v1")
    publish_features(output, data_dir)
    owner = data_dir / "ext_data" / "auction_preopen" / "import_owner.json"
    owner.unlink(missing_ok=True)
    with pytest.raises(ValueError, match="ownership"):
        publish_features(output, data_dir)


def test_publish_refuses_partial_day_before_creating_extensions(tmp_path):
    output = tmp_path / "processed"
    data_dir = tmp_path / "data"
    store_day(normalize_snapshots(source_rows(), date(2024, 9, 2)), output, "fixture-v1")
    marker = output / "manifests" / "2024-09-02.json"
    state = json.loads(marker.read_text())
    state["status"] = "writing"
    marker.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="complete"):
        publish_features(output, data_dir)
    assert not (data_dir / "ext_data").exists()


def test_publish_human_labels_preserves_custom_labels_without_rewriting_data(tmp_path):
    from app.services.ext_data import ExtConfigStore

    output = tmp_path / "processed"
    data_dir = tmp_path / "data"
    store_day(normalize_snapshots(source_rows(), date(2024, 9, 2)), output, "fixture-v1")
    publish_features(output, data_dir)
    configs = ExtConfigStore(data_dir)
    config = configs.get("auction_preopen")
    assert config.label == "\u65e9\u76d8\u7ade\u4ef7\u8fc7\u7a0b"
    field = next(f for f in config.fields if f.name == "last_matched_shares")
    assert "\u5339\u914d\u91cf" in field.label
    config.label = "My auction table"
    field.label = "My matched quantity"
    configs.upsert(config, keep_strategy_cache=True)
    target = (
        data_dir / "ext_data" / config.id / "timeseries"
        / "date=2024-09-02" / "part.parquet"
    )
    before = target.stat().st_mtime_ns
    assert publish_features(output, data_dir)["published_partitions"] == 0
    assert target.stat().st_mtime_ns == before
    reread = configs.get(config.id)
    assert reread.label == "My auction table"
    assert next(f for f in reread.fields if f.name == field.name).label == "My matched quantity"
