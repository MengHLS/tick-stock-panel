"""截面联动 sidecar 的构建、发布与稳定读取。"""
from __future__ import annotations

# Sidecar publication is exposed to core through the factor provider contract.
import dataclasses
import hashlib
import json
import logging
import shutil
import uuid
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
import polars as pl

from app.custom.cross_sectional_linkage.compute import (
    LINKAGE_FACTOR_IDS,
    compute_linkage_fields,
)
from app.enriched_generation import EnrichedPublication, get_enriched_generation
from app.indicators.pipeline import filter_halt_days, load_benchmark_momentum
from app.market_time import CN_TZ
from app.services.ext_data import ExtConfig, ExtConfigStore

logger = logging.getLogger(__name__)

_SIDECAR_ROOT = "kline_daily_linkage"
_INDUSTRY_FIELD = "所属同花顺行业"
_METHODOLOGY_VERSION = "linkage_v1"
_MIN_PEERS = 10
_INDUSTRY_LEVEL = 2
_BLOCK_TARGET_DATES = 20
_WARMUP_TRADING_DAYS = 61
_FINAL_CUTOFF = time(15, 30)
_PRICE_TOLERANCE = 0.005
_READ_RETRIES = 3
_INDUSTRY_CONFIG_METADATA_KEYS = frozenset({
    "created_at",
    "description",
    "label",
    "updated_at",
})
_INDUSTRY_PULL_RUNTIME_KEYS = frozenset({
    "enabled",
    "last_message",
    "last_rows",
    "last_run",
    "last_status",
    "next_run",
    "schedule_day",
    "schedule_minutes",
    "schedule_period",
    "schedule_time",
    "schedule_trading_only",
    "time_window_end",
    "time_window_start",
    "timeout_seconds",
})


class LinkageReadUnstableError(RuntimeError):
    """Linkage generation changed inside a read window."""


class LinkageCoverageError(ValueError):
    """Requested dates are outside the stable linkage sidecar coverage."""


def _partition_dates(root: Path) -> list[date]:
    if not root.exists():
        return []
    dates: list[date] = []
    for part in root.glob("date=*"):
        try:
            dates.append(date.fromisoformat(part.name[5:]))
        except ValueError:
            continue
    return sorted(set(dates))


def _read_partition_frame(
    part_dir: Path,
    *,
    columns: list[str] | None = None,
    file_name: str | None = None,
) -> pl.DataFrame | None:
    files = (
        [part_dir / file_name]
        if file_name is not None
        else sorted(part_dir.glob("*.parquet"))
    )
    if not files:
        return None
    try:
        return pl.read_parquet(files, columns=columns)
    except Exception as exc:  # noqa: BLE001 — 不可读分区无法证明完整
        logger.warning("联动数据分区读取失败 %s: %s", part_dir, exc)
        return None


def _integrity_issue_dates(data_dir: Path, today: date) -> set[date] | None:
    try:
        from app.services.data_integrity import scan_recent_integrity

        issues = scan_recent_integrity(data_dir, today=today)
    except Exception as exc:  # noqa: BLE001 — 无法证明完整性时 fail-closed
        logger.warning("联动 finalized 完整性扫描失败: %s", exc)
        return None
    return {issue.day for issue in issues if issue.table == "kline_daily"}


def _partition_is_finalized(data_dir: Path, day: date) -> bool:
    daily_dir = data_dir / "kline_daily" / f"date={day.isoformat()}"
    enriched_dir = data_dir / "kline_daily_enriched" / f"date={day.isoformat()}"
    daily = _read_partition_frame(daily_dir)
    enriched = _read_partition_frame(enriched_dir, columns=["symbol", "raw_close"])
    if daily is None or enriched is None or daily.is_empty() or enriched.is_empty():
        return False
    if not {"symbol", "open", "high", "close"}.issubset(daily.columns):
        return False
    if not {"symbol", "raw_close"}.issubset(enriched.columns):
        return False
    try:
        from app.services.data_integrity import (
            _partition_snapshot_defects,
            _quote_ts_max_ms,
        )

        defects = _partition_snapshot_defects(
            day,
            daily_dir,
            _quote_ts_max_ms(daily_dir),
        )
    except Exception as exc:  # noqa: BLE001 — 无法证明收盘完整时 fail-closed
        logger.warning("联动分区完整性检查失败 %s: %s", day, exc)
        return False
    if defects is None or defects:
        return False

    expected = (
        filter_halt_days(daily)
        .select(pl.col("symbol").cast(pl.String))
        .drop_nulls()
        .unique()
    )
    actual = (
        enriched.select(pl.col("symbol").cast(pl.String))
        .drop_nulls()
        .unique()
    )
    if expected.is_empty():
        return False
    expected_symbols = set(expected["symbol"].to_list())
    actual_symbols = set(actual["symbol"].to_list())
    if expected_symbols != actual_symbols:
        return False

    official = filter_halt_days(daily).select(
        pl.col("symbol").cast(pl.String),
        pl.col("close").cast(pl.Float64, strict=False).alias("_official_close"),
    ).unique(subset=["symbol"], keep="last")
    produced = enriched.select(
        pl.col("symbol").cast(pl.String),
        pl.col("raw_close").cast(pl.Float64, strict=False),
    ).unique(subset=["symbol"], keep="last")
    compared = produced.join(official, on="symbol", how="inner").drop_nulls()
    if compared.height != len(expected_symbols):
        return False
    return compared.filter(
        (pl.col("raw_close") - pl.col("_official_close")).abs() > _PRICE_TOLERANCE
    ).is_empty()


def finalized_trading_dates(
    data_dir: Path,
    *,
    now: datetime | None = None,
) -> list[date]:
    """Return only dates proven closed and complete in both daily layers."""
    data_dir = Path(data_dir)
    local_now = now or datetime.now(CN_TZ)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=CN_TZ)
    else:
        local_now = local_now.astimezone(CN_TZ)
    today = local_now.date()
    daily = set(_partition_dates(data_dir / "kline_daily"))
    enriched = set(_partition_dates(data_dir / "kline_daily_enriched"))
    bad_integrity = _integrity_issue_dates(data_dir, today)
    if bad_integrity is None:
        return []

    finalized: list[date] = []
    for day in sorted(daily & enriched):
        if day > today:
            continue
        if day == today and local_now.time() < _FINAL_CUTOFF:
            continue
        if day in bad_integrity:
            continue
        if _partition_is_finalized(data_dir, day):
            finalized.append(day)
    return finalized


@contextmanager
def stable_linkage_read(
    data_dir: Path,
    *,
    expected_generation: str | None = None,
) -> Iterator[str]:
    """Yield a stable linkage generation and reject a mid-read generation flip."""
    before = get_enriched_generation(data_dir, "linkage")
    if expected_generation is not None and before != expected_generation:
        raise LinkageReadUnstableError(
            "linkage generation changed before read: "
            f"expected {expected_generation}, got {before}"
        )
    yield before
    after = get_enriched_generation(data_dir, "linkage")
    if after != before:
        raise LinkageReadUnstableError(
            f"linkage generation changed during read: {before} -> {after}"
        )


def linkage_finalized_through(
    data_dir: Path,
    *,
    expected_generation: str | None,
) -> date:
    with stable_linkage_read(
        data_dir,
        expected_generation=expected_generation,
    ):
        manifest = _read_manifest(data_dir)
        finalized = _manifest_date(manifest, "finalized_through")
    if finalized is None:
        raise LinkageCoverageError("联动因子 manifest 缺少 finalized_through")
    return finalized


def _partition_signature(part_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(part_dir.glob("*.parquet")):
        stat = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _source_signatures(data_dir: Path, dates: list[date]) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for day in dates:
        suffix = f"date={day.isoformat()}"
        digest = hashlib.sha256()
        digest.update(b"enriched:")
        digest.update(
            _partition_signature(data_dir / "kline_daily_enriched" / suffix)
            .encode("ascii")
        )
        digest.update(b"index:")
        digest.update(
            _partition_signature(data_dir / "kline_index_daily" / suffix)
            .encode("ascii")
        )
        signatures[day.isoformat()] = digest.hexdigest()
    return signatures


@dataclasses.dataclass(frozen=True)
class _IndustrySource:
    config_id: str | None
    signature: str
    membership: pl.DataFrame
    coverage_start: date | None
    unavailable_reason: str | None


def _industry_source_signature(
    config_payload: dict[str, Any],
    partition_files: list[Path],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            config_payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )
    for path in partition_files:
        stat = path.stat()
        digest.update(str(path.relative_to(path.parents[2])).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _industry_config_identity(config: ExtConfig) -> dict[str, Any]:
    payload = config.to_dict()
    for key in _INDUSTRY_CONFIG_METADATA_KEYS:
        payload.pop(key, None)
    payload["fields"] = [
        {"name": field["name"], "dtype": field["dtype"]}
        for field in payload.get("fields", [])
    ]
    pull = payload.get("pull")
    if isinstance(pull, dict):
        pull = {
            key: value
            for key, value in pull.items()
            if key not in _INDUSTRY_PULL_RUNTIME_KEYS
        }
        fanout = pull.get("fanout")
        if isinstance(fanout, dict):
            pull["fanout"] = {
                key: value
                for key, value in fanout.items()
                if key not in {"concurrency", "retries"}
            }
        payload["pull"] = pull
    return payload


def _load_industry_source(data_dir: Path, *, through: date) -> _IndustrySource:
    configs = ExtConfigStore(data_dir).load_all()
    industry_timeseries = [
        config
        for config in configs
        if config.mode == "timeseries"
        and any(field.name == _INDUSTRY_FIELD for field in config.fields)
    ]
    candidates = [
        config
        for config in industry_timeseries
        if config.pull is not None
        and (config.pull.fanout or {}).get("require_complete") is True
    ]
    if len(candidates) > 1:
        ids = "、".join(sorted(config.id for config in candidates))
        raise ValueError(f"时序行业来源不唯一: {ids}")
    if not candidates:
        unavailable_reason = (
            "无可用的 timeseries 行业来源; snapshot 行业归属不能回填历史"
        )
        if industry_timeseries:
            ids = "、".join(sorted(config.id for config in industry_timeseries))
            unavailable_reason = (
                f"timeseries 行业来源 {ids} 未启用 require_complete=True; "
                "不完整 fanout 不能作为 PIT 来源"
            )
        return _IndustrySource(
            config_id=None,
            signature="",
            membership=pl.DataFrame(schema={
                "symbol": pl.String,
                "date": pl.Date,
                "industry": pl.String,
            }),
            coverage_start=None,
            unavailable_reason=unavailable_reason,
        )

    config = candidates[0]
    timeseries_root = data_dir / "ext_data" / config.id / "timeseries"
    part_dirs: list[tuple[date, Path]] = []
    for part in timeseries_root.glob("date=*"):
        if not part.is_dir():
            continue
        try:
            snapshot_date = date.fromisoformat(part.name[5:])
        except ValueError:
            continue
        if snapshot_date <= through:
            part_dirs.append((snapshot_date, part))
    part_dirs.sort()

    frames: list[pl.DataFrame] = []
    partition_files: list[Path] = []
    for snapshot_date, part in part_dirs:
        files = sorted(part.glob("*.parquet"))
        if not files:
            continue
        frame = pl.read_parquet(files)
        if not {"symbol", _INDUSTRY_FIELD}.issubset(frame.columns):
            raise ValueError(
                f"时序行业来源 {config.id}/{part.name} 缺少 symbol/{_INDUSTRY_FIELD}"
            )
        frames.append(
            frame.select(
                pl.col("symbol").cast(pl.String),
                pl.lit(snapshot_date).alias("date"),
                pl.col(_INDUSTRY_FIELD).cast(pl.String).alias("industry"),
            )
        )
        partition_files.extend(files)

    membership = (
        pl.concat(frames, how="diagonal_relaxed")
        if frames
        else pl.DataFrame(schema={
            "symbol": pl.String,
            "date": pl.Date,
            "industry": pl.String,
        })
    )
    coverage_start = (
        membership["date"].min() if not membership.is_empty() else None
    )
    signature = _industry_source_signature(
        {
            "config": _industry_config_identity(config),
            "industry_field": _INDUSTRY_FIELD,
            "industry_level": _INDUSTRY_LEVEL,
        },
        partition_files,
    )
    return _IndustrySource(
        config_id=config.id,
        signature=signature,
        membership=membership,
        coverage_start=coverage_start,
        unavailable_reason=(
            None if not membership.is_empty()
            else f"时序行业来源 {config.id} 尚无完整日分区"
        ),
    )


def _load_enriched(data_dir: Path, dates: list[date]) -> pl.DataFrame:
    root = data_dir / "kline_daily_enriched"
    frames: list[pl.DataFrame] = []
    for day in dates:
        frame = _read_partition_frame(
            root / f"date={day.isoformat()}",
            columns=["symbol", "date", "close"],
        )
        if frame is None or frame.is_empty():
            raise LinkageCoverageError(
                f"联动因子覆盖不足: enriched 缺分区 {day.isoformat()}"
            )
        frames.append(frame)
    if not frames:
        return pl.DataFrame(schema={
            "symbol": pl.String,
            "date": pl.Date,
            "close": pl.Float64,
        })
    return pl.concat(frames, how="diagonal_relaxed")


def _read_manifest(data_dir: Path) -> dict[str, Any]:
    path = data_dir / _SIDECAR_ROOT / "manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LinkageCoverageError(
            "联动因子覆盖不足: sidecar 缺失或尚未发布"
        ) from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LinkageCoverageError("联动因子 manifest 损坏") from exc
    if not isinstance(payload, dict):
        raise LinkageCoverageError("联动因子 manifest 格式无效")
    return payload


def _manifest_date(manifest: dict[str, Any], key: str) -> date | None:
    value = manifest.get(key)
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _manifest_partition_files(manifest: dict[str, Any]) -> dict[date, str]:
    raw = manifest.get("partitions")
    if not isinstance(raw, dict):
        return {}
    result: dict[date, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        name = Path(value).name
        if name != value or not name.endswith(".parquet"):
            continue
        try:
            result[date.fromisoformat(key)] = name
        except ValueError:
            continue
    return result


def _assert_manifest_coverage(
    manifest: dict[str, Any],
    dates: set[date],
) -> None:
    coverage_start = _manifest_date(manifest, "coverage_start")
    finalized_through = _manifest_date(manifest, "finalized_through")
    if coverage_start is None or finalized_through is None:
        raise LinkageCoverageError("联动因子 manifest 缺少有效覆盖区间")
    outside = sorted(day for day in dates if not coverage_start <= day <= finalized_through)
    if outside:
        raise LinkageCoverageError(
            "联动因子覆盖不足: "
            f"{outside[0].isoformat()}..{outside[-1].isoformat()} 超出 "
            f"{coverage_start.isoformat()}..{finalized_through.isoformat()}"
        )


def _read_linkage_partitions(
    data_dir: Path,
    dates: set[date],
    columns: list[str],
    *,
    require_complete: bool = True,
    manifest: dict[str, Any] | None = None,
) -> pl.DataFrame:
    root = data_dir / _SIDECAR_ROOT
    partition_files = _manifest_partition_files(manifest or {})
    frames: list[pl.DataFrame] = []
    for day in sorted(dates):
        part_dir = root / f"date={day.isoformat()}"
        file_name = partition_files.get(day) if partition_files else None
        if partition_files and file_name is None:
            if require_complete:
                raise LinkageCoverageError(
                    f"联动因子覆盖不足: manifest 缺 sidecar 分区 {day.isoformat()}"
                )
            continue
        frame = _read_partition_frame(
            part_dir,
            columns=columns,
            file_name=file_name,
        )
        if frame is None:
            if require_complete:
                raise LinkageCoverageError(
                    f"联动因子覆盖不足: 缺 sidecar 分区 {day.isoformat()}"
                )
            continue
        if "date" not in frame.columns:
            frame = frame.with_columns(pl.lit(day).alias("date"))
        frames.append(frame)
    if not frames:
        return pl.DataFrame(schema={
            "symbol": pl.String,
            "date": pl.Date,
            **{name: pl.Float64 for name in columns if name not in {"symbol", "date"}},
        })
    return pl.concat(frames, how="diagonal_relaxed")


def _assert_sidecar_rows(
    sidecar: pl.DataFrame,
    expected: pl.DataFrame,
) -> None:
    if expected.is_empty():
        return
    expected_keys = (
        expected.select(
            pl.col("symbol").cast(pl.String),
            pl.col("date").cast(pl.Date, strict=False),
        )
        .drop_nulls()
        .unique()
    )
    actual_keys = (
        sidecar.select(
            pl.col("symbol").cast(pl.String),
            pl.col("date").cast(pl.Date, strict=False),
        )
        .drop_nulls()
        .unique()
    )
    missing = expected_keys.join(actual_keys, on=["symbol", "date"], how="anti")
    if not missing.is_empty():
        first = missing.row(0, named=True)
        raise LinkageCoverageError(
            "联动因子覆盖不足: sidecar 缺标的 "
            f"{first['symbol']} @ {first['date'].isoformat()}"
        )


def attach_linkage_columns(
    frame: pl.DataFrame,
    names: Collection[str],
    data_dir: Path,
    *,
    expected_generation: str | None,
    require_complete: bool,
) -> pl.DataFrame:
    """Attach materialized linkage fields without reading a mixed publication."""
    requested = sorted(set(names) & LINKAGE_FACTOR_IDS)
    if frame.is_empty() or not requested:
        return frame
    if not {"symbol", "date"}.issubset(frame.columns):
        raise ValueError("联动因子附着需要 symbol/date 列")

    frame_dates = {
        value if isinstance(value, date) else date.fromisoformat(str(value))
        for value in frame["date"].drop_nulls().unique().to_list()
    }
    if not require_complete and not frame_dates:
        return frame.with_columns([
            pl.lit(None, dtype=pl.Float64).alias(name) for name in requested
        ])
    last_error: Exception | None = None
    for _attempt in range(_READ_RETRIES):
        try:
            with stable_linkage_read(
                data_dir,
                expected_generation=expected_generation,
            ):
                try:
                    manifest = _read_manifest(data_dir)
                except LinkageCoverageError:
                    if require_complete:
                        raise
                    return frame.with_columns([
                        pl.lit(None, dtype=pl.Float64).alias(name)
                        for name in requested
                    ])
                if require_complete:
                    _assert_manifest_coverage(manifest, frame_dates)
                    read_dates = frame_dates
                else:
                    coverage_start = _manifest_date(manifest, "coverage_start")
                    finalized_through = _manifest_date(manifest, "finalized_through")
                    if coverage_start is None or finalized_through is None:
                        read_dates = set()
                    else:
                        read_dates = {
                            day for day in frame_dates
                            if coverage_start <= day <= finalized_through
                        }
                if not read_dates:
                    return frame.with_columns([
                        pl.lit(None, dtype=pl.Float64).alias(name)
                        for name in requested
                    ])
                sidecar = _read_linkage_partitions(
                    data_dir,
                    read_dates,
                    ["symbol", "date", *requested],
                    require_complete=require_complete,
                    manifest=manifest,
                )
            break
        except LinkageReadUnstableError as exc:
            last_error = exc
            if expected_generation is not None:
                raise
            continue
    else:
        raise LinkageReadUnstableError(
            "联动因子稳定读取重试耗尽"
        ) from last_error

    left = (
        frame.drop([name for name in requested if name in frame.columns])
        .with_row_index("_linkage_order")
        .with_columns(pl.col("date").cast(pl.Date, strict=False).alias("_linkage_date"))
    )
    sidecar = sidecar.with_columns(
        pl.col("symbol").cast(pl.String),
        pl.col("date").cast(pl.Date, strict=False),
    ).unique(subset=["symbol", "date"], keep="last")
    joined = left.join(
        sidecar,
        left_on=["symbol", "_linkage_date"],
        right_on=["symbol", "date"],
        how="left",
    )
    if require_complete:
        _assert_sidecar_rows(
            sidecar,
            left.select(
                pl.col("symbol").cast(pl.String),
                pl.col("_linkage_date").alias("date"),
            ),
        )
    return joined.sort("_linkage_order").drop("_linkage_order", "_linkage_date")


def _matrix_dates(market: Any) -> list[date]:
    labels = getattr(market, "timestamp_labels", ())
    return sorted({
        date.fromisoformat(str(label)[:10])
        for label in labels
        if str(label)[:10]
    })


def attach_matrix_linkage_fields(
    market: Any,
    data_dir: Path,
    names: Collection[str],
    *,
    expected_generation: str | None,
) -> Any:
    """Inject stable daily linkage fields into a MarketDataMatrix copy."""
    requested = sorted(set(names) & LINKAGE_FACTOR_IDS)
    if not requested:
        return market
    dates = _matrix_dates(market)
    symbols = tuple(str(symbol) for symbol in market.symbols)
    if not dates or not symbols:
        raise LinkageCoverageError("联动因子矩阵注入缺少交易日或标的")

    with stable_linkage_read(
        data_dir,
        expected_generation=expected_generation,
    ):
        manifest = _read_manifest(data_dir)
        _assert_manifest_coverage(manifest, set(dates))
        sidecar = _read_linkage_partitions(
            data_dir,
            set(dates),
            ["symbol", "date", *requested],
            require_complete=True,
            manifest=manifest,
        )

    grouped = {
        day: set(symbols)
        for day, symbols in (
            sidecar.group_by("date")
            .agg(pl.col("symbol").cast(pl.String).unique().alias("symbols"))
            .iter_rows()
        )
        if isinstance(day, date)
    }
    sidecar_dates = set(grouped)
    for row_id, label in enumerate(market.timestamp_labels):
        day = date.fromisoformat(str(label)[:10])
        if day not in sidecar_dates:
            raise LinkageCoverageError(
                f"联动因子覆盖不足: sidecar 缺分区 {day.isoformat()}"
            )
        expected = {
            symbols[asset_id]
            for asset_id in np.flatnonzero(np.isfinite(market.close[row_id]))
        }
        missing = expected - grouped.get(day, set())
        if missing:
            raise LinkageCoverageError(
                "联动因子覆盖不足: sidecar 缺标的 "
                f"{sorted(missing)[0]} @ {day.isoformat()}"
            )

    axis = pl.DataFrame({
        "_row": list(range(len(market.timestamp_labels))),
        "date": [
            date.fromisoformat(str(label)[:10])
            for label in market.timestamp_labels
        ],
    })
    assets = pl.DataFrame({
        "_asset": list(range(len(symbols))),
        "symbol": list(symbols),
    })
    grid = (
        axis.join(assets, how="cross")
        .join(
            sidecar.with_columns(
                pl.col("symbol").cast(pl.String),
                pl.col("date").cast(pl.Date, strict=False),
            ).unique(subset=["symbol", "date"], keep="last"),
            on=["symbol", "date"],
            how="left",
        )
        .sort(["_row", "_asset"])
    )
    shape = (len(market.timestamp_labels), len(symbols))
    extra: dict[str, np.ndarray] = {}
    for name in requested:
        values = (
            grid[name]
            .cast(pl.Float64, strict=False)
            .fill_null(float("nan"))
            .to_numpy()
            .reshape(shape)
            .astype(np.float32, copy=False)
        )
        values.flags.writeable = False
        extra[name] = values
    merged = {**dict(market.fields), **extra}
    return dataclasses.replace(market, fields=MappingProxyType(merged))


def _target_blocks(
    finalized: list[date],
    targets: list[date],
) -> list[tuple[list[date], list[date]]]:
    position = {day: idx for idx, day in enumerate(finalized)}
    blocks: list[tuple[list[date], list[date]]] = []
    for start in range(0, len(targets), _BLOCK_TARGET_DATES):
        chunk = targets[start:start + _BLOCK_TARGET_DATES]
        first_idx = position[chunk[0]]
        warmup = finalized[max(0, first_idx - _WARMUP_TRADING_DAYS):first_idx]
        blocks.append((warmup + chunk, chunk))
    return blocks


def _rebuild_linkage_sidecar(
    data_dir: Path,
    *,
    mode: str,
    target_dates: list[date] | None,
    publication: EnrichedPublication,
) -> int:
    if mode not in {"full", "incremental"}:
        raise ValueError(f"未知 linkage 构建模式: {mode}")
    finalized = finalized_trading_dates(data_dir)
    requested = finalized if target_dates is None else sorted(set(target_dates) & set(finalized))
    if not requested:
        return 0

    industry = _load_industry_source(data_dir, through=finalized[-1])
    benchmark_frame = load_benchmark_momentum(data_dir)
    benchmarks = benchmark_frame if benchmark_frame is not None else pl.DataFrame()
    current_signatures = _source_signatures(data_dir, finalized)
    manifest_path = data_dir / _SIDECAR_ROOT / "manifest.json"

    effective_mode = mode
    existing_manifest: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            existing_manifest = _read_manifest(data_dir)
        except LinkageCoverageError:
            existing_manifest = None
    existing_partitions = _manifest_partition_files(existing_manifest or {})
    existing_dates = (
        sorted(existing_partitions)
        if existing_partitions
        else _partition_dates(data_dir / _SIDECAR_ROOT)
    )
    if effective_mode == "incremental":
        if existing_manifest is None:
            effective_mode = "full"
        else:
            if not all(
                existing_manifest.get(key) == value
                for key, value in (
                    ("methodology_version", _METHODOLOGY_VERSION),
                    ("min_peers", _MIN_PEERS),
                    ("industry_level", _INDUSTRY_LEVEL),
                    ("industry_source", industry.config_id),
                    ("industry_source_signature", industry.signature),
                )
            ):
                effective_mode = "full"
            stored = existing_manifest.get("source_signatures")
            if not isinstance(stored, dict):
                effective_mode = "full"
            else:
                for day in existing_dates:
                    key = day.isoformat()
                    if stored.get(key) != current_signatures.get(key):
                        effective_mode = "full"
                        break

    if effective_mode == "full":
        targets = requested
    else:
        existing = set(existing_dates)
        targets = [day for day in requested if day not in existing]
        if not targets:
            return 0

    publication.begin()
    # Linkage readers must stay blocked after any partial replacement, even if
    # the failure occurs before the first target partition is written.
    publication.mark_changed()
    rows_written = 0
    run_token = uuid.uuid4().hex[:16]
    next_partitions = (
        {} if effective_mode == "full" else dict(existing_partitions)
    )
    try:
        root = data_dir / _SIDECAR_ROOT

        for read_dates, target_chunk in _target_blocks(finalized, targets):
            publication.heartbeat()
            enriched = _load_enriched(data_dir, read_dates)
            computed = compute_linkage_fields(
                enriched,
                benchmarks,
                industry.membership,
                set(target_chunk),
                min_peers=_MIN_PEERS,
            )
            got_dates = set(computed["date"].unique().to_list())
            missing = sorted(set(target_chunk) - got_dates)
            if missing:
                raise LinkageCoverageError(
                    "联动因子计算未覆盖目标日期: "
                    + "、".join(day.isoformat() for day in missing[:5])
                )
            for day in target_chunk:
                part = computed.filter(pl.col("date") == day).sort("symbol")
                file_name = f"part.{run_token}.parquet"
                publication.write_parquet(
                    part,
                    root / f"date={day.isoformat()}" / file_name,
                )
                next_partitions[day] = file_name
                rows_written += part.height

        all_sidecar_dates = sorted(next_partitions)
        manifest = {
            "version": 1,
            "methodology_version": _METHODOLOGY_VERSION,
            "factor_ids": sorted(LINKAGE_FACTOR_IDS),
            "min_peers": _MIN_PEERS,
            "industry_source": industry.config_id,
            "industry_level": _INDUSTRY_LEVEL,
            "industry_source_signature": industry.signature,
            "industry_pit": industry.config_id is not None,
            "industry_coverage_start": (
                industry.coverage_start.isoformat()
                if industry.coverage_start is not None else None
            ),
            "coverage_start": (
                all_sidecar_dates[0].isoformat() if all_sidecar_dates else None
            ),
            "finalized_through": (
                all_sidecar_dates[-1].isoformat() if all_sidecar_dates else None
            ),
            "unavailable_reason": industry.unavailable_reason,
            "source_signatures": current_signatures,
            "partitions": {
                day.isoformat(): next_partitions[day]
                for day in all_sidecar_dates
            },
        }
        publication.write_json(manifest, manifest_path)
        publication.commit()
        _cleanup_linkage_partitions(root, next_partitions)
        return rows_written
    except BaseException:
        publication.abandon()
        raise


def _cleanup_linkage_partitions(
    root: Path,
    active: dict[date, str],
) -> None:
    for part_dir in root.glob("date=*"):
        try:
            day = date.fromisoformat(part_dir.name[5:])
        except ValueError:
            continue
        active_name = active.get(day)
        if active_name is None:
            shutil.rmtree(part_dir, ignore_errors=True)
            continue
        for path in part_dir.glob("*.parquet"):
            if path.name != active_name:
                path.unlink(missing_ok=True)


def rebuild_linkage_sidecar(
    data_dir: Path,
    *,
    mode: Literal["full", "incremental"],
    target_dates: list[date] | None = None,
) -> int:
    """Build or incrementally extend the independently published linkage sidecar."""
    publication = EnrichedPublication(
        Path(data_dir),
        "linkage",
        recover=True,
    )
    return _rebuild_linkage_sidecar(
        Path(data_dir),
        mode=mode,
        target_dates=target_dates,
        publication=publication,
    )
