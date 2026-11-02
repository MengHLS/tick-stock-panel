"""Read normalized risk-warning history without using current instrument names."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from app.backtest.matrix import MarketDataMatrix

ST_HISTORY_SCHEMA = {
    "symbol": pl.String,
    "flag_date": pl.Date,
    "st_flag": pl.Boolean,
}
MISSING_ST_HISTORY = (
    "排除ST需要历史ST状态数据 (st_history)；不能用当前名称过滤历史。"
    "请补齐历史状态，或明确关闭本次回测的排除ST选项。"
)


def read_st_history(data_dir: Path) -> pl.DataFrame:
    paths = sorted((data_dir / "st_history").rglob("*.parquet"))
    if not paths:
        return pl.DataFrame(schema=ST_HISTORY_SCHEMA)
    return normalize_st_history(pl.concat([
        pl.read_parquet(path, columns=list(ST_HISTORY_SCHEMA))
        for path in paths
    ]))


def normalize_st_history(history: pl.DataFrame | None) -> pl.DataFrame:
    """Validate and normalize a provider-supplied effective-dated ST dataset."""
    if history is None or history.is_empty():
        return pl.DataFrame(schema=ST_HISTORY_SCHEMA)
    missing = set(ST_HISTORY_SCHEMA) - set(history.columns)
    if missing:
        raise ValueError(
            "历史ST状态缺少字段: " + ", ".join(sorted(missing))
        )
    flag_date = pl.col("flag_date")
    if history.schema["flag_date"] == pl.String:
        flag_date = flag_date.str.to_date(strict=False)
    else:
        flag_date = flag_date.cast(pl.Date, strict=False)
    history = history.select(
        pl.col("symbol").cast(pl.String),
        flag_date,
        pl.col("st_flag").cast(pl.Boolean, strict=False),
    )
    if history.null_count().sum_horizontal().item():
        raise ValueError("历史ST状态必须包含非空 symbol/string、flag_date/date、st_flag/bool")
    history = history.unique()
    if history.select(pl.struct("symbol", "flag_date").is_duplicated().any()).item():
        raise ValueError("历史ST状态同一股票、生效日存在冲突记录")
    return history.sort(["symbol", "flag_date"])


def attach_st_history(panel: pl.DataFrame, history: pl.DataFrame) -> pl.DataFrame:
    if history.is_empty():
        raise ValueError(MISSING_ST_HISTORY)
    # Sort for the as-of join, then restore the original row alignment.
    return (
        panel.drop("st_flag", strict=False)
        .with_row_index("__st_row")
        .sort("date")
        .join_asof(
            history.sort("flag_date"),
            left_on="date",
            right_on="flag_date",
            by="symbol",
            strategy="backward",
            check_sortedness=False,
        )
        .sort("__st_row")
        .drop("__st_row", "flag_date")
    )


def attach_matrix_st_history(
    market: MarketDataMatrix, history: pl.DataFrame,
) -> MarketDataMatrix:
    if history.is_empty():
        raise ValueError(MISSING_ST_HISTORY)
    dates = np.array([label[:10] for label in market.timestamp_labels], dtype="datetime64[D]")
    flags = np.full(market.shape, np.nan, dtype=np.float32)
    asset_ids = {symbol: index for index, symbol in enumerate(market.symbols)}
    for group in history.partition_by("symbol", maintain_order=True):
        asset_id = asset_ids.get(group["symbol"][0])
        if asset_id is None:
            continue
        group = group.sort("flag_date")
        effective = group["flag_date"].to_numpy().astype("datetime64[D]")
        indices = np.searchsorted(effective, dates, side="right") - 1
        known = indices >= 0
        flags[known, asset_id] = group["st_flag"].to_numpy()[indices[known]]
    flags.flags.writeable = False
    from app.backtest.matrix import _limit_lock_matrices

    raw_close = market.fields.get("raw_close", market.close)
    seen = (
        np.isfinite(market.open)
        & np.isfinite(market.high)
        & np.isfinite(market.low)
        & np.isfinite(market.close)
        & np.isfinite(raw_close)
        & (market.volume > 0)
    )
    trading_dates = tuple(date.fromisoformat(label[:10]) for label in market.timestamp_labels)
    limit_up_locked, limit_down_locked = _limit_lock_matrices(
        market.close,
        raw_close,
        seen,
        trading_dates,
        list(market.symbols),
        list(market.names),
        {},
        historical_st=flags,
        apply_latest_limits=False,
    )
    limit_up_locked.flags.writeable = False
    limit_down_locked.flags.writeable = False
    return replace(
        market,
        limit_up_locked=limit_up_locked,
        limit_down_locked=limit_down_locked,
        fields={**market.fields, "st_flag": flags},
    )


def st_history_fingerprint(history: pl.DataFrame | None) -> str | None:
    """Stable cache key for an effective-dated status snapshot."""
    if history is None or history.is_empty():
        return None
    payload = (
        history.select("symbol", "flag_date", "st_flag")
        .sort(["symbol", "flag_date"])
        .write_json()
        .encode("utf-8")
    )
    return hashlib.blake2b(payload, digest_size=16).hexdigest()
