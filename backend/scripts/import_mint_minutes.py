#!/usr/bin/env python
"""Import QDC/mint 1-minute Parquet files into the canonical minute store.

The source format used by qdc-data/mint is:
  ts, symbol, open, high, low, close, volume, amount, source, ingested_at

It differs from the TSP storage contract in exactly three boundary conversions:
  - symbol: XSHG/XSHE/XBSE -> SH/SZ/BJ
  - datetime: UTC epoch milliseconds -> Asia/Shanghai naive wall clock
  - volume: shares -> lots (divide by 100)

Prices and amount stay unchanged. Each source day is promoted to
`kline_minute/date=YYYY-MM-DD/part.parquet` through a staging directory, and
the raw-basis marker is created once the target is known to contain raw data.

Run from backend/:
    uv run --frozen python -m scripts.import_mint_minutes \
        --source-dir G:/qdc-data/mint --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from app.config import settings
from app.services.minute_adjust import (
    mark_minute_basis_raw,
    minute_basis_is_raw,
)

logger = logging.getLogger(__name__)

CANONICAL_COLUMNS = (
    "symbol",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
SOURCE_COLUMNS = {
    "ts",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
}
MANIFEST_NAME = ".mint_import_manifest.json"
STAGING_DIR = "mint-minutes"
IMPORT_VERSION = 1
_MEMORY_LIMIT_RE = re.compile(r"^\d+(?:\.\d+)?(?:MB|GB)$", re.IGNORECASE)


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    size: int
    mtime_ns: int
    rows: int
    first_ts: int | None
    last_ts: int | None


@dataclass(frozen=True)
class ImportResult:
    source: str
    rows: int
    partitions: int
    skipped_dates: int
    first_date: str | None
    last_date: str | None


def _sql_path(path: Path | str) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace("'", "''")


def _replace_with_retry(source: Path, target: Path, *, attempts: int = 20) -> None:
    """Windows may briefly keep a just-written Parquet handle open."""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            sleep(0.25)


def _wall_time_from_ms(value: int | None) -> datetime | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(value / 1000, tz=UTC)
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .replace(tzinfo=None)
    )


def _china_midnight_ms(day: date) -> int:
    local = datetime.combine(day, time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
    return int(local.timestamp() * 1000)


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {value}") from exc


def _source_info(path: Path) -> SourceInfo:
    parquet = pq.ParquetFile(path)
    metadata = parquet.metadata
    ts_index = metadata.schema.names.index("ts")
    first_ts: int | None = None
    last_ts: int | None = None
    for row_group in range(metadata.num_row_groups):
        stats = metadata.row_group(row_group).column(ts_index).statistics
        if stats is None or not stats.has_min_max:
            continue
        minimum = int(stats.min)
        maximum = int(stats.max)
        first_ts = minimum if first_ts is None else min(first_ts, minimum)
        last_ts = maximum if last_ts is None else max(last_ts, maximum)
    stat = path.stat()
    return SourceInfo(
        path=path,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        rows=metadata.num_rows,
        first_ts=first_ts,
        last_ts=last_ts,
    )


def _validate_source_schema(path: Path) -> None:
    names = set(pq.ParquetFile(path).schema_arrow.names)
    missing = sorted(SOURCE_COLUMNS - names)
    if missing:
        raise ValueError(f"{path.name}: missing source columns: {', '.join(missing)}")


def _discover_files(
    source_dir: Path,
    selected_files: list[Path | str] | None = None,
) -> list[Path]:
    root = source_dir.resolve()
    if selected_files:
        files: list[Path] = []
        for raw in selected_files:
            path = Path(raw)
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if path.parent != root:
                raise ValueError(f"source file must be directly under {root}: {path}")
            if not path.is_file():
                raise FileNotFoundError(path)
            files.append(path)
        files = sorted(set(files))
    else:
        files = sorted(path for path in source_dir.glob("*.parquet") if path.is_file())
    if not files:
        raise FileNotFoundError(f"no completed .parquet files under {source_dir}")
    ignored = sorted(path.name for path in source_dir.glob("*.downloading"))
    if ignored:
        logger.warning(
            "ignoring %d incomplete download(s): %s",
            len(ignored),
            ", ".join(ignored),
        )
    for path in files:
        _validate_source_schema(path)
    return files


def _source_where(start: date | None, end: date | None) -> str:
    clauses: list[str] = []
    if start is not None:
        clauses.append(f"ts >= {_china_midnight_ms(start)}")
    if end is not None:
        clauses.append(f"ts < {_china_midnight_ms(end + timedelta(days=1))}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _connect(
    *,
    threads: int,
    memory_limit: str,
    temp_dir: Path,
) -> duckdb.DuckDBPyConnection:
    if threads < 1:
        raise ValueError("threads must be >= 1")
    if not _MEMORY_LIMIT_RE.fullmatch(memory_limit):
        raise ValueError("memory-limit must look like 512MB or 4GB")
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute(f"PRAGMA threads={threads}")
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET temp_directory='{_sql_path(temp_dir)}'")
    return con


def _source_date_counts(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    where: str,
) -> dict[date, int]:
    rows = con.execute(
        f"""
        SELECT
          CAST(timezone('Asia/Shanghai', to_timestamp(ts / 1000.0)) AS DATE) AS trade_date,
          count(*) AS rows
        FROM read_parquet('{_sql_path(path)}')
        WHERE {where}
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


def _date_filter(dates: list[date]) -> str:
    if not dates:
        return "FALSE"
    values = ", ".join(f"DATE '{day.isoformat()}'" for day in dates)
    return (
        "CAST(timezone('Asia/Shanghai', to_timestamp(ts / 1000.0)) AS DATE) "
        f"IN ({values})"
    )


def _copy_partitioned(
    con: duckdb.DuckDBPyConnection,
    source: Path,
    stage_dir: Path,
    *,
    where: str,
    dates: list[date],
) -> None:
    stage_dir.parent.mkdir(parents=True, exist_ok=True)
    date_clause = _date_filter(dates)
    con.execute(
        f"""
        COPY (
          SELECT
            CASE split_part(symbol, '.', 2)
              WHEN 'XSHG' THEN split_part(symbol, '.', 1) || '.SH'
              WHEN 'XSHE' THEN split_part(symbol, '.', 1) || '.SZ'
              WHEN 'XBSE' THEN split_part(symbol, '.', 1) || '.BJ'
              ELSE NULL
            END AS symbol,
            timezone('Asia/Shanghai', to_timestamp(ts / 1000.0)) AS datetime,
            open,
            high,
            low,
            close,
            volume / 100.0 AS volume,
            amount,
            CAST(timezone('Asia/Shanghai', to_timestamp(ts / 1000.0)) AS DATE)
              AS "date"
          FROM read_parquet('{_sql_path(source)}')
          WHERE ({where}) AND ({date_clause})
        )
        TO '{_sql_path(stage_dir)}'
        (
          FORMAT PARQUET,
          PARTITION_BY ("date"),
          WRITE_PARTITION_COLUMNS FALSE,
          OVERWRITE_OR_IGNORE,
          COMPRESSION ZSTD,
          ROW_GROUP_SIZE 122880
        )
        """
    )


def _rewrite_sorted_partition(
    con: duckdb.DuckDBPyConnection,
    day_dir: Path,
) -> None:
    inputs = sorted(day_dir.glob("*.parquet"))
    if not inputs:
        raise ValueError(f"staged partition has no parquet file: {day_dir}")
    output = day_dir / "part.parquet"
    temp = day_dir / "part.parquet.tmp"
    input_list = ", ".join(f"'{_sql_path(path)}'" for path in inputs)
    columns = ", ".join(CANONICAL_COLUMNS)
    con.execute(
        f"""
        COPY (
          SELECT {columns}
          FROM read_parquet([{input_list}])
          ORDER BY symbol, datetime
        )
        TO '{_sql_path(temp)}'
        (
          FORMAT PARQUET,
          COMPRESSION ZSTD,
          ROW_GROUP_SIZE 122880
        )
        """
    )
    _replace_with_retry(temp, output)
    for path in inputs:
        if path != output:
            path.unlink()


def _validate_partition(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    *,
    expected_rows: int,
    trade_date: date,
) -> None:
    schema = pq.ParquetFile(path).schema_arrow
    if tuple(schema.names) != CANONICAL_COLUMNS:
        raise ValueError(f"{path}: unexpected columns: {schema.names}")
    expected_types = {
        "symbol": pa.string(),
        "datetime": pa.timestamp("us"),
        "open": pa.float64(),
        "high": pa.float64(),
        "low": pa.float64(),
        "close": pa.float64(),
        "volume": pa.float64(),
        "amount": pa.float64(),
    }
    for name, expected in expected_types.items():
        if schema.field(name).type != expected:
            raise ValueError(
                f"{path}: {name} has type {schema.field(name).type}, expected {expected}"
            )

    row = con.execute(
        f"""
        SELECT
          count(*) AS row_count,
          count(*) FILTER (
            WHERE symbol IS NULL
               OR datetime IS NULL
               OR open IS NULL
               OR high IS NULL
               OR low IS NULL
               OR close IS NULL
               OR volume IS NULL
               OR amount IS NULL
          ) AS null_rows,
          count(*) FILTER (
            WHERE symbol IS NULL
               OR NOT regexp_matches(symbol, '^[0-9]{{6}}\\.(SH|SZ|BJ)$')
          ) AS bad_symbols,
          count(*) FILTER (
            WHERE CAST(datetime AS DATE) != DATE '{trade_date.isoformat()}'
          ) AS bad_dates,
          count(*) FILTER (
            WHERE CAST(datetime AS TIME) < TIME '09:30:00'
               OR CAST(datetime AS TIME) > TIME '15:00:00'
               OR (
                 CAST(datetime AS TIME) > TIME '11:30:00'
                 AND CAST(datetime AS TIME) < TIME '13:00:00'
               )
          ) AS bad_times,
          count(*) FILTER (
            WHERE open <= 0
               OR high <= 0
               OR low <= 0
               OR close <= 0
               OR NOT isfinite(open)
               OR NOT isfinite(high)
               OR NOT isfinite(low)
               OR NOT isfinite(close)
               OR high < greatest(open, low, close)
               OR low > least(open, high, close)
               OR volume < 0
               OR amount < 0
          ) AS bad_values,
          count(*) - count(
            DISTINCT coalesce(symbol, '')
              || chr(0)
              || coalesce(CAST(datetime AS VARCHAR), '')
          ) AS duplicate_rows
        FROM read_parquet('{_sql_path(path)}')
        """
    ).fetchone()
    assert row is not None
    details = {
        "row_count": row[0],
        "null_rows": row[1],
        "bad_symbols": row[2],
        "bad_dates": row[3],
        "bad_times": row[4],
        "bad_values": row[5],
        "duplicate_rows": row[6],
    }
    if int(row[0]) != expected_rows:
        raise ValueError(
            f"{path}: row count {row[0]} != source count {expected_rows}"
        )
    invalid = {name: count for name, count in details.items() if name != "row_count" and count}
    if invalid:
        raise ValueError(f"{path}: validation failed: {invalid}")


def _existing_partition_count(root: Path, trade_date: date) -> int | None:
    path = root / f"date={trade_date.isoformat()}" / "part.parquet"
    if not path.exists():
        return None
    return int(pq.ParquetFile(path).metadata.num_rows)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": IMPORT_VERSION, "files": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != IMPORT_VERSION:
        raise ValueError(f"unsupported manifest version in {path}")
    payload.setdefault("files", {})
    return payload


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(UTC).isoformat()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _import_one(
    con: duckdb.DuckDBPyConnection,
    info: SourceInfo,
    *,
    data_dir: Path,
    stage_root: Path,
    where: str,
    manifest: dict[str, Any],
    dry_run: bool,
) -> ImportResult:
    date_counts = _source_date_counts(con, info.path, where)
    if not date_counts:
        return ImportResult(info.path.name, 0, 0, 0, None, None)
    dates = sorted(date_counts)
    minute_root = data_dir / "kline_minute"
    missing_dates: list[date] = []
    skipped = 0
    for trade_date in dates:
        existing = _existing_partition_count(minute_root, trade_date)
        if existing is None:
            missing_dates.append(trade_date)
        elif existing == date_counts[trade_date]:
            skipped += 1
        else:
            raise ValueError(
                f"{info.path.name}: existing {trade_date} partition has {existing} rows, "
                f"source expects {date_counts[trade_date]}; refusing to overwrite"
            )

    imported_rows = sum(date_counts[day] for day in missing_dates)
    if dry_run:
        return ImportResult(
            source=info.path.name,
            rows=imported_rows,
            partitions=len(missing_dates),
            skipped_dates=skipped,
            first_date=dates[0].isoformat(),
            last_date=dates[-1].isoformat(),
        )

    run_stage = stage_root / _run_id() / info.path.stem
    try:
        if missing_dates:
            _copy_partitioned(
                con,
                info.path,
                run_stage,
                where=where,
                dates=missing_dates,
            )
            staged_dirs = sorted(
                path for path in run_stage.glob("date=*") if path.is_dir()
            )
            if len(staged_dirs) != len(missing_dates):
                raise ValueError(
                    f"{info.path.name}: staged {len(staged_dirs)} dates, "
                    f"expected {len(missing_dates)}"
                )
            for index, day_dir in enumerate(staged_dirs, start=1):
                try:
                    trade_date = date.fromisoformat(day_dir.name.removeprefix("date="))
                except ValueError as exc:
                    raise ValueError(f"invalid staged date directory: {day_dir}") from exc
                _rewrite_sorted_partition(con, day_dir)
                _validate_partition(
                    con,
                    day_dir / "part.parquet",
                    expected_rows=date_counts[trade_date],
                    trade_date=trade_date,
                )
                if index == 1 or index % 10 == 0 or index == len(staged_dirs):
                    logger.info(
                        "source %s: staged %d/%d %s rows=%d",
                        info.path.name,
                        index,
                        len(staged_dirs),
                        trade_date,
                        date_counts[trade_date],
                    )

        if missing_dates:
            current = info.path.stat()
            if current.st_size != info.size or current.st_mtime_ns != info.mtime_ns:
                raise RuntimeError(
                    f"{info.path.name}: source changed during import; refusing to promote"
                )
            minute_root.mkdir(parents=True, exist_ok=True)
            has_existing = any(minute_root.glob("date=*/part.parquet"))
            if has_existing and not minute_basis_is_raw(data_dir):
                raise ValueError(
                    "target minute store already contains legacy data without "
                    ".raw_basis; refusing to mix raw and adjusted prices"
                )
            if not has_existing:
                mark_minute_basis_raw(data_dir)
            for day_dir in sorted(run_stage.glob("date=*")):
                target = minute_root / day_dir.name
                if target.exists():
                    raise FileExistsError(f"target partition appeared during import: {target}")
                _replace_with_retry(day_dir, target)

        record = {
            "source_path": str(info.path.resolve()),
            "size": info.size,
            "mtime_ns": info.mtime_ns,
            "source_rows": sum(date_counts.values()),
            "imported_rows": imported_rows,
            "partitions": len(missing_dates),
            "skipped_dates": skipped,
            "first_date": dates[0].isoformat(),
            "last_date": dates[-1].isoformat(),
            "imported_at": datetime.now(UTC).isoformat(),
            "transform": {
                "timezone": "UTC epoch ms -> Asia/Shanghai naive",
                "symbols": "XSHG/XSHE/XBSE -> SH/SZ/BJ",
                "volume": "shares / 100 -> lots",
                "price": "raw, unchanged",
                "amount": "yuan, unchanged",
            },
        }
        manifest["files"][str(info.path.resolve())] = record
        return ImportResult(
            source=info.path.name,
            rows=imported_rows,
            partitions=len(missing_dates),
            skipped_dates=skipped,
            first_date=dates[0].isoformat(),
            last_date=dates[-1].isoformat(),
        )
    finally:
        if run_stage.exists():
            shutil.rmtree(run_stage, ignore_errors=True)


def import_mint_minutes(
    source_dir: Path | str,
    data_dir: Path | str,
    *,
    source_files: list[Path | str] | None = None,
    start: date | None = None,
    end: date | None = None,
    threads: int = 4,
    memory_limit: str = "4GB",
    dry_run: bool = False,
) -> list[ImportResult]:
    """Import every completed mint Parquet file under source_dir.

    The function is fail-closed for malformed rows, duplicate bars, existing
    adjusted-basis data and target date collisions with different row counts.
    Re-running is idempotent: partitions with the same source row count are
    skipped, and source imports are recorded in a runtime manifest.
    """
    if start is not None and end is not None and start > end:
        raise ValueError("start must be <= end")

    source_root = Path(source_dir)
    target_root = Path(data_dir)
    files = _discover_files(source_root, source_files)
    infos = [_source_info(path) for path in files]
    stage_root = target_root / ".staging" / STAGING_DIR
    manifest_path = target_root / "kline_minute" / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    where = _source_where(start, end)

    con = _connect(
        threads=threads,
        memory_limit=memory_limit,
        temp_dir=stage_root / "duckdb-temp",
    )
    results: list[ImportResult] = []
    try:
        for info in infos:
            logger.info(
                "source %s: rows=%d coverage=%s..%s",
                info.path.name,
                info.rows,
                _wall_time_from_ms(info.first_ts),
                _wall_time_from_ms(info.last_ts),
            )
            result = _import_one(
                con,
                info,
                data_dir=target_root,
                stage_root=stage_root,
                where=where,
                manifest=manifest,
                dry_run=dry_run,
            )
            results.append(result)
            logger.info(
                "source %s: imported=%d partitions=%d skipped_dates=%d",
                result.source,
                result.rows,
                result.partitions,
                result.skipped_dates,
            )
        if not dry_run:
            _write_manifest(manifest_path, manifest)
    finally:
        con.close()
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import QDC/mint 1-minute Parquet files into TSP kline_minute"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--source-file",
        action="append",
        help="only import this file directly under --source-dir; repeatable",
    )
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--start", type=_parse_day)
    parser.add_argument("--end", type=_parse_day)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    results = import_mint_minutes(
        args.source_dir,
        args.data_dir,
        source_files=args.source_file,
        start=args.start,
        end=args.end,
        threads=args.threads,
        memory_limit=args.memory_limit,
        dry_run=args.dry_run,
    )
    rows = sum(item.rows for item in results)
    partitions = sum(item.partitions for item in results)
    mode = "would import" if args.dry_run else "imported"
    logger.info(
        "done: %s %d rows across %d partitions from %d files",
        mode,
        rows,
        partitions,
        len(results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
