"""Recompute historical minute-derived last-seal times without replacing rows."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from pathlib import Path

import polars as pl

from app.config import settings
from app.custom.limit_board_events import service
from app.custom.limit_board_events.minute_adapter import fetch_minute_limit_board_events
from app.factors.ext_factors import invalidate_ext_caches
from app.market_time import CN_TZ
from app.services.ext_data import cast_df_to_schema
from app.services.fs_utils import atomic_write_parquet

_INVARIANT_FIELDS = (
    "in_limit_up_pool",
    "in_limit_break_pool",
    "observed_open",
    "first_seal_minute",
    "limit_up_pool_open_times",
    "break_pool_open_times",
)
_SOURCE_FIELDS = ("up_source_ready_at", "break_source_ready_at")


def _partition_path(data_dir: Path, day: date) -> Path:
    return (
        Path(data_dir) / "ext_data" / service.CONFIG_ID / "timeseries"
        / f"date={day}" / "part.parquet"
    )


def _signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _is_fuyao(frame: pl.DataFrame) -> bool:
    """Source-ready timestamps are written only by the Fuyao adapter."""
    return any(
        name in frame.columns and frame[name].is_not_null().any()
        for name in _SOURCE_FIELDS
    )


def _validate_same_events(existing: pl.DataFrame, fresh: pl.DataFrame) -> None:
    existing_symbols = set(existing["symbol"].to_list())
    fresh_symbols = set(fresh["symbol"].to_list())
    if existing_symbols != fresh_symbols:
        raise ValueError("event membership changed; refusing to rewrite last-seal fields")
    if existing["symbol"].n_unique() != existing.height or fresh["symbol"].n_unique() != fresh.height:
        raise ValueError("event membership contains duplicate symbols")

    left = existing.sort("symbol")
    right = fresh.sort("symbol")
    for name in _INVARIANT_FIELDS:
        if name not in left.columns or name not in right.columns:
            raise ValueError(f"event invariant {name} is unavailable")
        left_values = left[name].cast(pl.Int64, strict=False)
        right_values = right[name].cast(pl.Int64, strict=False)
        if not left_values.equals(right_values):
            raise ValueError(f"event invariant {name} changed; refusing to rewrite")


def _changed_rows(existing: pl.DataFrame, updated: pl.DataFrame) -> int:
    compared = existing.select("symbol", "last_seal_time", "last_seal_minute").join(
        updated.select("symbol", "last_seal_time", "last_seal_minute"),
        on="symbol",
        how="inner",
        suffix="_new",
    )
    return compared.filter(
        (pl.col("last_seal_time").fill_null("") != pl.col("last_seal_time_new").fill_null(""))
        | (
            pl.col("last_seal_minute").fill_null(-1)
            != pl.col("last_seal_minute_new").fill_null(-1)
        )
    ).height


def recompute_partition(
    data_dir: Path,
    day: date,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """Recompute one minute-derived partition and atomically update two columns."""
    path = _partition_path(data_dir, day)
    if not path.exists():
        return {"date": day.isoformat(), "status": "skipped_missing_partition", "rows": 0}
    before = _signature(path)
    existing = pl.read_parquet(path)
    if existing.is_empty():
        return {"date": day.isoformat(), "status": "skipped_empty", "rows": 0}
    if _is_fuyao(existing):
        return {
            "date": day.isoformat(),
            "status": "skipped_fuyao",
            "rows": existing.height,
        }

    current = now or datetime.combine(day, time(15, 30), tzinfo=CN_TZ)
    try:
        fresh_rows = fetch_minute_limit_board_events(data_dir, day, now=current)
    except FileNotFoundError:
        return {
            "date": day.isoformat(),
            "status": "skipped_missing_source",
            "rows": existing.height,
        }
    if not fresh_rows:
        raise ValueError("minute source produced no events for an existing partition")
    fresh = pl.DataFrame(fresh_rows, infer_schema_length=None)
    _validate_same_events(existing, fresh)
    if fresh["last_seal_time"].null_count() or fresh["last_seal_minute"].null_count():
        raise ValueError("recomputed last-seal values contain nulls")

    updates = fresh.select(
        "symbol",
        pl.col("last_seal_time").alias("__last_seal_time"),
        pl.col("last_seal_minute").alias("__last_seal_minute"),
    )
    updated = (
        existing.join(updates, on="symbol", how="left", validate="1:1")
        .with_columns(
            pl.col("__last_seal_time").alias("last_seal_time"),
            pl.col("__last_seal_minute").cast(pl.Int64).alias("last_seal_minute"),
        )
        .drop("__last_seal_time", "__last_seal_minute")
    )
    changed = _changed_rows(existing, updated)
    result = {
        "date": day.isoformat(),
        "rows": existing.height,
        "rows_changed": changed,
        "status": "would_update" if dry_run and changed else "updated" if changed else "unchanged",
    }
    if dry_run or not changed:
        return result

    updated = cast_df_to_schema(updated, service.limit_board_config().fields)
    with service._commit_lock(data_dir):
        if _signature(path) != before:
            raise RuntimeError("partition changed during recompute; refusing to overwrite")
        atomic_write_parquet(updated, path)
    return result


def recompute_range(
    data_dir: Path,
    days: list[date],
    *,
    workers: int = 8,
    dry_run: bool = False,
) -> list[dict]:
    """Recompute independent partitions concurrently; each file is written atomically."""
    if not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    current = datetime.now(CN_TZ)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                recompute_partition,
                data_dir,
                day,
                dry_run=dry_run,
                now=current,
            ): day
            for day in days
        }
        for future in as_completed(futures):
            day = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - report every independent partition
                results.append({
                    "date": day.isoformat(),
                    "status": "error",
                    "message": str(exc),
                })
    return sorted(results, key=lambda row: row["date"])


def _partition_dates(data_dir: Path, start: date | None, end: date | None) -> list[date]:
    base = Path(data_dir) / "ext_data" / service.CONFIG_ID / "timeseries"
    if not base.exists():
        return []
    dates = []
    for path in base.glob("date=*/part.parquet"):
        try:
            day = date.fromisoformat(path.parent.name[5:])
        except ValueError:
            continue
        if (start is None or day >= start) and (end is None or day <= end):
            dates.append(day)
    return sorted(dates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.start and args.end and args.end < args.start:
        parser.error("--end must not be earlier than --start")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    days = _partition_dates(args.data_dir, args.start, args.end)
    if not days:
        print(json.dumps({"status": "no_partitions", "workers": args.workers}))
        return 0
    results = recompute_range(
        args.data_dir,
        days,
        workers=args.workers,
        dry_run=args.dry_run,
    )
    progress_step = max(1, len(days) // 20)
    for completed, row in enumerate(results, start=1):
        if row["status"] == "error" or completed % progress_step == 0:
            print(
                json.dumps({"done": completed, "total": len(days), **row}, ensure_ascii=False),
                flush=True,
            )

    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = {
        "status": "completed" if not any(
            row["status"] in {"error", "skipped_missing_source"} for row in results
        ) else "incomplete",
        "dry_run": args.dry_run,
        "workers": args.workers,
        "partitions": len(results),
        "rows": sum(int(row.get("rows") or 0) for row in results),
        "rows_changed": sum(int(row.get("rows_changed") or 0) for row in results),
        "statuses": counts,
    }
    if not args.dry_run and counts.get("updated"):
        invalidate_ext_caches(args.data_dir)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
