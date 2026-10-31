"""Import monthly opening-auction RARs without expanding the entire CSV dataset.

Run from backend:
    python -m scripts.import_opening_auction --source-dir PATH --output-dir PATH
    python -m scripts.import_opening_auction ... --publish-data-dir PATH

Source volume and book quantities are lots; persisted quantities are shares.
Preopen features use SH/SZ auction semantics only. BJ snapshots are retained.
Final observations have their own extension table and explicit observed times.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

if __name__ == "__main__":
    os.environ.setdefault("POLARS_MAX_THREADS", "4")

import polars as pl

from app.services.fs_utils import atomic_write_text

VERSION = 1
FEATURE_VERSION = 2
CUTOFFS = {
    "c0920": 92000000,
    "c0923": 92300000,
    "c0924": 92400000,
    "c092450": 92450000,
    "last": 92459999,
}
RENAME = {
    "security_id": "symbol",
    "md_date": "date",
    "md_time": "time",
    "min": "source_min",
    "max": "source_max",
    "pre_close": "prev_close",
    "last": "last_price",
    "open": "auction_open",
    "num_trades": "trade_count",
    "total_volume_trade": "cum_volume_shares",
    "total_value_trade": "cum_amount",
    "bid1": "bid_price1",
    "bid2": "bid_price2",
    "bid_size1": "bid_qty1_shares",
    "bid_size2": "bid_qty2_shares",
    "ask1": "ask_price1",
    "ask2": "ask_price2",
    "ask_size1": "ask_qty1_shares",
    "ask_size2": "ask_qty2_shares",
}
QUANTITIES = (
    "total_volume_trade", "bid_size1", "bid_size2", "ask_size1", "ask_size2"
)
KEYS = ["symbol", "date"]
TABLE_LABELS = {
    "preopen": "\u65e9\u76d8\u7ade\u4ef7\u8fc7\u7a0b",
    "result": "\u65e9\u76d8\u7ade\u4ef7\u7ed3\u679c",
}


def _field_label(name: str) -> str:
    labels = {
        "prev_close": "\u6628\u6536\u4ef7",
        "preopen_rows": "\u7ade\u4ef7\u5feb\u7167\u6570",
        "invalid_preopen_rows": "\u5f02\u5e38\u5feb\u7167\u6570",
        "result_time": "\u7ed3\u679c\u89c2\u6d4b\u65f6\u95f4(HHMMSSmmm)",
        "auction_open": "\u7ade\u4ef7\u6210\u4ea4\u4ef7",
        "volume_shares": "\u7ade\u4ef7\u6210\u4ea4\u91cf(\u80a1)",
        "amount": "\u7ade\u4ef7\u6210\u4ea4\u989d(\u5143)",
        "trade_count": "\u7ade\u4ef7\u6210\u4ea4\u7b14\u6570",
        "has_result": "\u6709\u6548\u7ade\u4ef7\u7ed3\u679c",
        "opening_gap": "\u7ade\u4ef7\u6da8\u5e45(\u5c0f\u6570)",
        "last_gap": "\u672b\u5feb\u7167\u53c2\u8003\u6da8\u5e45(\u5c0f\u6570)",
        "last_imbalance": "\u7ade\u4ef7\u4e0d\u5e73\u8861\u5ea6",
        "last_minute_matched_delta_shares":
            "\u672b\u5206\u949f\u5339\u914d\u589e\u91cf(\u80a1)",
        "last_minute_matched_growth": "\u672b\u5206\u949f\u5339\u914d\u589e\u5e45",
        "last_minute_price_change": "\u672b\u5206\u949f\u4ef7\u683c\u53d8\u5316",
        "post0920_matched_growth": "09:20\u540e\u5339\u914d\u589e\u5e45",
    }
    if name in labels:
        return labels[name]
    suffixes = {
        "time": "\u89c2\u6d4b\u65f6\u95f4(HHMMSSmmm)",
        "ref_price": "\u53c2\u8003\u4ef7",
        "matched_shares": "\u5339\u914d\u91cf(\u80a1)",
        "unmatched_buy_shares": "\u4e70\u65b9\u672a\u5339\u914d\u91cf(\u80a1)",
        "unmatched_sell_shares": "\u5356\u65b9\u672a\u5339\u914d\u91cf(\u80a1)",
        "age_ms": "\u5feb\u7167\u6ede\u540e(ms)",
    }
    prefixes = {
        "c0920": "09:20", "c0923": "09:23", "c0924": "09:24",
        "c092450": "09:24:50", "last": "\u672b\u5feb\u7167",
    }
    for prefix, label in prefixes.items():
        if name.startswith(prefix + "_"):
            return label + suffixes.get(name[len(prefix) + 1:], name)
    return name


def _wall_ms(expr: pl.Expr) -> pl.Expr:
    return (
        (expr // 10000000) * 3600000
        + ((expr // 100000) % 100) * 60000
        + ((expr // 1000) % 100) * 1000
        + expr % 1000
    )


def _ratio(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    return pl.when(denominator > 0).then(numerator / denominator)


def normalize_snapshots(source: pl.DataFrame, expected_date: date) -> pl.DataFrame:
    missing = set(RENAME) - set(source.columns)
    if missing or source.is_empty():
        raise ValueError(f"Missing columns or empty day: {sorted(missing)}")
    if source["md_date"].cast(pl.String).unique().to_list() != [
        expected_date.strftime("%Y%m%d")
    ]:
        raise ValueError("Source date does not match archive member date")
    invalid_qty = source.select(pl.any_horizontal([
        pl.col(c).is_null()
        | ~pl.col(c).cast(pl.Float64).is_finite()
        | (pl.col(c) < 0)
        | (pl.col(c).cast(pl.Float64) != pl.col(c).cast(pl.Float64).floor())
        for c in QUANTITIES
    ]).any()).item()
    if invalid_qty:
        raise ValueError("Invalid quantity: expected nonnegative integral lots")
    t = pl.col("md_time").cast(pl.Int64)
    invalid = source.select((
        (t < 91500000) | (t >= 93000000)
        | ((t // 1000) % 100 >= 60) | ((t // 100000) % 100 >= 60)
        | ~pl.col("security_id").str.contains(r"^\d{6}\.(SH|SZ|BJ)$")
    ).any()).item()
    if invalid:
        raise ValueError("Invalid symbol or opening-auction time")
    return (
        source.select(list(RENAME))
        .with_columns(
            pl.col("security_id").cast(pl.String),
            pl.col("md_date").cast(pl.String).str.strptime(pl.Date, "%Y%m%d"),
            pl.col("md_time").cast(pl.Int32),
            pl.col("num_trades").cast(pl.Int64),
            *[(pl.col(c).cast(pl.Int64) * 100).alias(c) for c in QUANTITIES],
            *[
                pl.col(c).cast(pl.Float64)
                for c in RENAME
                if c not in {"security_id", "md_date", "md_time", "num_trades", *QUANTITIES}
            ],
        )
        .rename(RENAME)
        .with_row_index("_row")
        .sort(["symbol", "time", "_row"])
        .unique(subset=[*KEYS, "time"], keep="last", maintain_order=True)
        .drop("_row")
    )


def build_features(snapshots: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    eligible = snapshots.filter(
        pl.col("symbol").str.ends_with(".SH") | pl.col("symbol").str.ends_with(".SZ")
    ).with_columns(*[
        pl.when(pl.col(c).is_finite() & (pl.col(c) > 0)).then(pl.col(c)).alias(c)
        for c in ("prev_close", "auction_open")
    ], *[
        pl.when(pl.col(c).is_finite() & (pl.col(c) >= 0)).then(pl.col(c)).alias(c)
        for c in ("bid_price1", "ask_price1", "cum_amount")
    ])
    base = eligible.group_by(KEYS, maintain_order=True).agg(
        pl.col("prev_close").first(),
    )
    pre = eligible.filter(pl.col("time") < 92500000).with_columns((
        (pl.col("bid_price1") == pl.col("ask_price1"))
        & (pl.col("bid_qty1_shares") == pl.col("ask_qty1_shares"))
        & ((pl.col("bid_price1") > 0) | (pl.col("bid_qty1_shares") == 0))
    ).fill_null(False).alias("_valid"))
    counts = pre.group_by(KEYS).agg(
        pl.len().cast(pl.Int64).alias("preopen_rows"),
        (~pl.col("_valid")).sum().cast(pl.Int64).alias("invalid_preopen_rows"),
    )
    valid = pre.filter(pl.col("_valid")).with_columns(
        pl.when(pl.col("bid_price1") > 0).then(pl.col("bid_price1")).alias("_ref_price")
    )
    fields = {
        "time": "time", "ref_price": "_ref_price", "matched_shares": "bid_qty1_shares",
        "unmatched_buy_shares": "bid_qty2_shares",
        "unmatched_sell_shares": "ask_qty2_shares",
    }
    values = valid.group_by(KEYS).agg([
        pl.col(source).filter(pl.col("time") <= cutoff).last().alias(f"{name}_{field}")
        for name, cutoff in CUTOFFS.items()
        for field, source in fields.items()
    ])
    preopen = base.join(counts, on=KEYS, how="left").join(values, on=KEYS, how="left")
    preopen = preopen.with_columns([
        (
            _wall_ms(pl.lit(92500000 if name == "last" else cutoff))
            - _wall_ms(pl.col(f"{name}_time").cast(pl.Int64))
        ).cast(pl.Int32).alias(f"{name}_age_ms")
        for name, cutoff in CUTOFFS.items()
    ]).with_columns(
        (_ratio(pl.col("last_ref_price"), pl.col("prev_close")) - 1).alias("last_gap"),
        _ratio(
            pl.col("last_unmatched_buy_shares") - pl.col("last_unmatched_sell_shares"),
            pl.col("last_matched_shares")
            + pl.col("last_unmatched_buy_shares") + pl.col("last_unmatched_sell_shares"),
        ).alias("last_imbalance"),
        (pl.col("last_matched_shares") - pl.col("c0924_matched_shares"))
        .alias("last_minute_matched_delta_shares"),
        (_ratio(pl.col("last_matched_shares"), pl.col("c0924_matched_shares")) - 1)
        .alias("last_minute_matched_growth"),
        (_ratio(pl.col("last_ref_price"), pl.col("c0924_ref_price")) - 1)
        .alias("last_minute_price_change"),
        (_ratio(pl.col("last_matched_shares"), pl.col("c0920_matched_shares")) - 1)
        .alias("post0920_matched_growth"),
    )
    final = eligible.filter(pl.col("time") >= 92500000).group_by(KEYS).agg(
        pl.col("time").last().alias("result_time"),
        pl.col("auction_open").last(),
        pl.col("cum_volume_shares").last().alias("volume_shares"),
        pl.col("cum_amount").last().alias("amount"),
        pl.col("trade_count").last(),
    )
    result = base.join(final, on=KEYS, how="left").with_columns(
        ((pl.col("auction_open") > 0) & (pl.col("volume_shares") > 0)
         & pl.col("amount").is_not_null())
        .fill_null(False).cast(pl.Int64).alias("has_result"),
        (_ratio(pl.col("auction_open"), pl.col("prev_close")) - 1).alias("opening_gap"),
    )
    return preopen.sort(KEYS), result.sort(KEYS)


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".parquet.tmp")
    frame.write_parquet(temp, compression="zstd", compression_level=3)
    os.replace(temp, path)


def _day_paths(output: Path, day: str) -> list[Path]:
    return [
        output / kind / f"date={day}" / "part.parquet"
        for kind in ("quotes", "preopen", "result")
    ]


def _completed(output: Path, day: str, signature: str) -> dict | None:
    marker = output / "manifests" / f"{day}.json"
    if not marker.exists():
        if any(path.exists() for path in _day_paths(output, day)):
            raise ValueError(f"Unowned output without manifest: {day}")
        return None
    record = json.loads(marker.read_text(encoding="utf-8"))
    if record["signature"] != signature or record["version"] != VERSION:
        raise ValueError(f"Changed source/version requires a new output directory: {day}")
    if record.get("status") != "complete":
        return None
    for path, size in zip(_day_paths(output, day), record["output_bytes"], strict=True):
        if not path.exists() or path.stat().st_size != size:
            raise ValueError(f"Missing or changed output: {path}")
    if record.get("feature_version", 1) != FEATURE_VERSION:
        return None
    return {**record, "skipped": True}


def store_day(snapshots: pl.DataFrame, output: Path, signature: str) -> dict:
    day = snapshots["date"][0].isoformat()
    done = _completed(output, day, signature)
    if done:
        return done
    marker = output / "manifests" / f"{day}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": VERSION, "feature_version": FEATURE_VERSION,
        "signature": signature, "status": "writing", "date": day,
    }
    atomic_write_text(marker, json.dumps(record))
    preopen, result = build_features(snapshots)
    paths = _day_paths(output, day)
    for frame, path in zip((snapshots, preopen, result), paths, strict=True):
        _write_parquet(frame, path)
    record.update(
        status="complete", rows=snapshots.height, feature_rows=preopen.height,
        unsupported_symbols=snapshots["symbol"].n_unique() - preopen.height,
        result_symbols=result.filter(pl.col("has_result") == 1).height,
        output_bytes=[path.stat().st_size for path in paths],
    )
    atomic_write_text(marker, json.dumps(record))
    return {**record, "skipped": False}


def archive_members(seven_zip: str, archive: Path) -> list[tuple[str, date]]:
    result = subprocess.run(
        [seven_zip, "l", "-slt", "-sccUTF-8", str(archive)], capture_output=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    text = result.stdout.decode("utf-8", errors="strict")
    members = []
    for line in text.splitlines():
        if not line.startswith("Path = "):
            continue
        member = line[7:]
        match = re.search(r"(?:^|[/\\])(\d{8})\.csv$", member, re.IGNORECASE)
        if match:
            raw = match[1]
            day = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
            if raw[:6] != archive.stem:
                raise ValueError(f"Unexpected member date in {archive.name}: {member}")
            members.append((member, day))
    if not members:
        raise ValueError(f"No daily CSV members: {archive}")
    return members


def _import_member(seven_zip: str, archive: Path, member: str, day: date,
                   output: Path, signature: str) -> dict:
    started = time.perf_counter()
    done = _completed(output, day.isoformat(), signature)
    if done:
        return done
    cached = output / "quotes" / f"date={day}" / "part.parquet"
    if cached.exists():
        # _completed already checked ownership/source, including interrupted writes.
        snapshots = pl.read_parquet(cached)
    else:
        result = subprocess.run(
            [seven_zip, "x", "-so", "-mmt=1", str(archive), member],
            capture_output=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        source = pl.read_csv(io.BytesIO(result.stdout), infer_schema_length=10000)
        snapshots = normalize_snapshots(source, day)
    record = store_day(snapshots, output, signature)
    return {**record, "seconds": round(time.perf_counter() - started, 3)}


def publish_features(output: Path, data_dir: Path) -> dict:
    from app.services.ext_data import (
        ExtConfig,
        ExtConfigStore,
        ExtField,
        _invalidate_ext_derived,
        write_ext_parquet,
    )

    complete_days = set()
    for manifest in (output / "manifests").glob("*.json"):
        record = json.loads(manifest.read_text(encoding="utf-8"))
        if record.get("status") != "complete" or not _completed(
            output, record["date"], record["signature"]
        ):
            raise ValueError(f"Day must be complete before publication: {manifest.stem}")
        complete_days.add(record["date"])
    if not complete_days:
        raise ValueError("No complete days to publish")
    for kind in ("preopen", "result"):
        found = {p.parent.name[5:] for p in (output / kind).glob("date=*/part.parquet")}
        if found != complete_days:
            raise ValueError(f"Feature files do not match complete manifests: {kind}")
    marker = output / "published.json"
    prior = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    if prior and prior.get("data_dir") != str(data_dir.resolve()):
        raise ValueError("Publish target differs from existing manifest")
    signatures = prior.get("partitions", {})
    updated = {}
    published = 0
    configs = ExtConfigStore(data_dir)
    for kind in ("preopen", "result"):
        files = sorted((output / kind).glob("date=*/part.parquet"))
        if not files:
            raise ValueError(f"No feature partitions: {kind}")
        sample = pl.read_parquet(files[0])
        fields = [
            ExtField(name, "float" if dtype.is_float() else "int", _field_label(name))
            for name, dtype in sample.schema.items() if name not in KEYS
        ]
        config = ExtConfig(
            id=f"auction_{kind}", label=TABLE_LABELS[kind], mode="timeseries",
            fields=fields,
            description=(
                "SH/SZ only. Quantities: shares; prices: raw CNY. "
                "Observation times use HHMMSSmmm Beijing time. "
                + ("Preopen only; each cutoff uses observations at or before cutoff."
                   if kind == "preopen" else
                   "Final results: available only at result_time, never before 09:25.")
            ),
        )
        existing = configs.get(config.id)
        owner_path = data_dir / "ext_data" / config.id / "import_owner.json"
        ownership = {"output_dir": str(output.resolve()), "version": VERSION}
        if (existing is not None or owner_path.parent.exists()) and (
            not owner_path.exists()
            or json.loads(owner_path.read_text(encoding="utf-8")) != ownership
        ):
            raise ValueError(f"Extension ownership is not established: {config.id}")
        if existing is not None:
            if (existing.mode != "timeseries"
                    or [(f.name, f.dtype) for f in existing.fields]
                    != [(f.name, f.dtype) for f in fields]):
                raise ValueError(f"Existing extension schema differs: {config.id}")
            changed = False
            if existing.label == f"Opening auction {kind}":
                existing.label = config.label
                changed = True
            for field in existing.fields:
                if field.label == field.name:
                    field.label = _field_label(field.name)
                    changed = True
            if changed:
                configs.upsert(existing, keep_strategy_cache=True)
        else:
            owner_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(owner_path, json.dumps(ownership))
            configs.upsert(config, keep_strategy_cache=True)
        for path in files:
            day = path.parent.name[5:]
            target = data_dir / "ext_data" / config.id / "timeseries" / path.parent.name / path.name
            stat = path.stat()
            key = f"{kind}/{day}"
            signature = [stat.st_size, stat.st_mtime_ns]
            old = signatures.get(key)
            if (old and old["source"] == signature and target.exists()
                    and target.stat().st_size == old["target_bytes"]):
                updated[key] = old
                continue
            frame = pl.read_parquet(path).drop("date")
            write_ext_parquet(
                frame, config, data_dir, snapshot_date=date.fromisoformat(day),
                keep_strategy_cache=True,
            )
            published += 1
            updated[key] = {"source": signature, "target_bytes": target.stat().st_size}
    _invalidate_ext_derived(data_dir)
    atomic_write_text(marker, json.dumps({
        "data_dir": str(data_dir.resolve()), "partitions": updated,
    }))
    return {"published_partitions": published, "total_partitions": len(updated)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seven-zip")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--months", nargs="*", help="Optional YYYYMM subset")
    parser.add_argument("--publish-data-dir", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    seven = args.seven_zip or shutil.which("7z") or shutil.which("7zz")
    if not seven:
        candidate = Path(r"C:\Program Files\NVIDIA Corporation\NVIDIA app\7z.exe")
        if candidate.is_file():
            seven = str(candidate)
    if not seven:
        parser.error("7-Zip executable required")
    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    if source == output or output in source.parents:
        parser.error("Output must be separate from source and not its ancestor")
    archives = sorted(
        p for p in source.glob("*.rar")
        if re.fullmatch(r"\d{6}", p.stem)
        and (not args.months or p.stem in args.months)
    )
    if not archives:
        parser.error("No monthly RAR files matched")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    tasks = []
    dates = set()
    for archive in archives:
        stat = archive.stat()
        for member, day in archive_members(seven, archive):
            if day in dates:
                raise ValueError(f"Duplicate source date: {day}")
            dates.add(day)
            signature = json.dumps(
                [str(archive), stat.st_size, stat.st_mtime_ns, member], ensure_ascii=True
            )
            tasks.append((seven, archive, member, day, output, signature))
    print(json.dumps({"event": "start", "days": len(tasks), "archives": len(archives),
                      "workers": args.workers}), flush=True)
    records = []
    skipped = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_import_member, *task) for task in tasks]
        for future in as_completed(futures):
            try:
                record = future.result()
            except Exception:
                for pending in futures:
                    pending.cancel()
                raise
            records.append(record)
            skipped += int(record["skipped"])
            count = len(records)
            if count % 25 == 0 or count == len(tasks):
                elapsed = time.perf_counter() - started
                print(json.dumps({
                    "event": "progress", "done": count, "total": len(tasks),
                    "skipped": skipped, "elapsed_seconds": round(elapsed, 1),
                    "eta_seconds": round(elapsed / count * (len(tasks) - count), 1),
                }), flush=True)
    summary = {
        "version": VERSION, "feature_version": FEATURE_VERSION,
        "archives": len(archives), "days": len(records),
        "skipped": skipped, "first_date": min(dates).isoformat(),
        "last_date": max(dates).isoformat(),
        "snapshot_rows": sum(r["rows"] for r in records),
        "feature_rows": sum(r["feature_rows"] for r in records),
        "result_symbols": sum(r["result_symbols"] for r in records),
        "unsupported_symbol_days": sum(r["unsupported_symbols"] for r in records),
        "output_bytes": sum(sum(r["output_bytes"]) for r in records),
    }
    if args.publish_data_dir:
        print(json.dumps({"event": "publish_start"}), flush=True)
        summary["publication"] = publish_features(output, args.publish_data_dir.resolve())
    summary["seconds"] = round(time.perf_counter() - started, 2)
    atomic_write_text(output / "summary.json", json.dumps(summary, indent=2))
    print(json.dumps({"event": "complete", **summary}), flush=True)


if __name__ == "__main__":
    main()
