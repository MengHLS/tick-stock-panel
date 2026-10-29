"""复权因子与 enriched 价格尺度校验。

发布前校验价格尺度、键集合和因子合法性，不依赖额外的全历史认证文件。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

MIN_EX_FACTOR = 0.2
MAX_EX_FACTOR = 5.0
DEFAULT_SCALE_RTOL = 1e-4

FACTOR_REQUIRED_COLUMNS = ("symbol", "trade_date", "ex_factor")
PRICE_COLUMNS = ("open", "high", "low", "close")


class AdjustmentIntegrityError(RuntimeError):
    """复权链路完整性错误 (消息可直接展示)。"""


class FactorDataError(AdjustmentIntegrityError):
    """复权因子缺失、不可读、非法或冲突。"""


class PriceScaleError(AdjustmentIntegrityError):
    """复权尺度、键集合或价格换算不一致。"""


# ── 因子加载 ─────────────────────────────────────────────────────


def load_adj_factors_strict(
    factor_path: str | Path,
    *,
    symbols: list[str] | None = None,
) -> pl.DataFrame:
    """严格读取复权因子; 不可用状态一律失败, 不允许退化为不复权。"""
    path = Path(factor_path)
    if not path.exists():
        raise FactorDataError(
            f"复权因子文件缺失 ({path.name})，已中止 enriched 生成，避免写出未复权数据"
        )
    try:
        factors = pl.read_parquet(path)
    except Exception as exc:
        raise FactorDataError(
            f"复权因子读取失败 ({path.name}): {exc}; 已中止 enriched 生成"
        ) from exc

    missing = [c for c in FACTOR_REQUIRED_COLUMNS if c not in factors.columns]
    if missing:
        raise FactorDataError(f"复权因子缺少字段: {', '.join(missing)}")
    if factors.is_empty():
        raise FactorDataError("复权因子为空表，已中止 enriched 生成")

    factors = factors.select(*FACTOR_REQUIRED_COLUMNS).with_columns(
        pl.col("symbol").cast(pl.Utf8, strict=False),
        pl.col("trade_date").cast(pl.Date, strict=False),
        pl.col("ex_factor").cast(pl.Float64, strict=False),
    )
    if factors.filter(pl.col("symbol").is_null()).height:
        raise FactorDataError("复权因子存在空 symbol")
    if factors.filter(pl.col("trade_date").is_null()).height:
        raise FactorDataError("复权因子存在空 trade_date")
    bad = factors.filter(
        pl.col("ex_factor").is_null()
        | ~pl.col("ex_factor").is_finite()
        | (pl.col("ex_factor") < MIN_EX_FACTOR)
        | (pl.col("ex_factor") > MAX_EX_FACTOR)
    )
    if bad.height:
        raise FactorDataError(
            f"复权因子存在非法值 (需在 {MIN_EX_FACTOR}~{MAX_EX_FACTOR}): "
            f"{bad.head(3).to_dicts()}"
        )
    dup = (
        factors.group_by(["symbol", "trade_date"])
        .agg(pl.col("ex_factor").n_unique().alias("variants"))
        .filter(pl.col("variants") > 1)
    )
    if dup.height:
        raise FactorDataError(f"同证券同日复权因子冲突: {dup.head(3).to_dicts()}")

    factors = factors.unique(subset=["symbol", "trade_date"], keep="first").sort(
        ["symbol", "trade_date"]
    )
    if symbols:
        factors = factors.filter(pl.col("symbol").is_in(list(symbols)))
    return factors


def factor_fingerprint(factors: pl.DataFrame) -> str:
    if factors.is_empty():
        return hashlib.sha256(b"empty").hexdigest()
    digest = hashlib.sha256()
    for symbol, day, ex_factor in factors.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("trade_date").cast(pl.Date).cast(pl.Utf8),
        pl.col("ex_factor").cast(pl.Float64),
    ).sort(["symbol", "trade_date"]).iter_rows():
        digest.update(f"{symbol}|{day}|{float(ex_factor):.12g}\n".encode())
    return digest.hexdigest()


# ── 尺度校验 (含键集合覆盖断言) ──────────────────────────────────


def _attach_expected_scale(frame: pl.DataFrame, factors: pl.DataFrame) -> pl.DataFrame:
    if factors.is_empty():
        return frame.with_columns(pl.lit(1.0).alias("q_expected"))
    cumulative = factors.with_columns(
        pl.col("ex_factor").cum_prod().over("symbol").alias("cum_factor"),
    ).select(pl.col("symbol"), pl.col("trade_date"), pl.col("cum_factor"))
    total = cumulative.group_by("symbol").agg(
        pl.col("cum_factor").last().alias("total_factor")
    )
    ordered = frame.sort(["symbol", "date"]).join_asof(
        cumulative.sort(["symbol", "trade_date"]),
        left_on="date",
        right_on="trade_date",
        by="symbol",
        strategy="backward",
    ).join(total, on="symbol", how="left")
    return ordered.with_columns(
        (pl.col("cum_factor").fill_null(1.0) / pl.col("total_factor").fill_null(1.0))
        .alias("q_expected")
    ).drop(["trade_date", "cum_factor", "total_factor"])


def _keyset_error(name: str, keys: pl.DataFrame) -> PriceScaleError:
    return PriceScaleError(
        f"复权尺度校验键集合不闭合 ({name}, {keys.height} 行): {keys.head(3).to_dicts()}"
    )


def validate_adjusted_scale(
    adjusted: pl.DataFrame,
    raw: pl.DataFrame,
    factors: pl.DataFrame,
    *,
    rtol: float = DEFAULT_SCALE_RTOL,
) -> dict:
    """发布前尺度校验: 键集合闭合 + OHLC 同比例 + 比例等于因子推算值。"""
    if adjusted.is_empty():
        return {"rows": 0, "symbols": 0, "factor_fingerprint": factor_fingerprint(factors)}
    need = ["symbol", "date", *PRICE_COLUMNS]
    for label, frame in (("enriched", adjusted), ("原始价", raw)):
        missing = [c for c in need if c not in frame.columns]
        if missing:
            raise PriceScaleError(f"{label}缺少字段: {', '.join(missing)}")

    adjusted_keys = adjusted.select(
        pl.col("symbol").cast(pl.Utf8), pl.col("date").cast(pl.Date)
    )
    if adjusted_keys.height != adjusted_keys.unique().height:
        raise _keyset_error("enriched 存在重复键", adjusted_keys)

    # 合法停牌过滤后的预期键集合 (与 compute_enriched 同口径)。
    from app.indicators.pipeline import filter_halt_days

    expected_keys = filter_halt_days(raw).select(
        pl.col("symbol").cast(pl.Utf8), pl.col("date").cast(pl.Date)
    ).unique()
    missing_keys = expected_keys.join(adjusted_keys, on=["symbol", "date"], how="anti")
    if missing_keys.height:
        raise _keyset_error("缺少 enriched 行", missing_keys)
    extra_keys = adjusted_keys.join(expected_keys, on=["symbol", "date"], how="anti")
    if extra_keys.height:
        raise _keyset_error("存在多余 enriched 行", extra_keys)

    raw_px = raw.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("date").cast(pl.Date),
        *[pl.col(c).cast(pl.Float64).alias(f"raw_{c}") for c in PRICE_COLUMNS],
    )
    adj_px = adjusted.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("date").cast(pl.Date),
        *[pl.col(c).cast(pl.Float64).alias(f"adj_{c}") for c in PRICE_COLUMNS],
    )
    joined = adj_px.join(raw_px, on=["symbol", "date"], how="inner")
    if joined.height != adj_px.height:
        raise _keyset_error("enriched 与原始价无法一一匹配", adj_px)

    ratios = joined.with_columns(
        *[(pl.col(f"adj_{c}") / pl.col(f"raw_{c}")).alias(f"q_{c}") for c in PRICE_COLUMNS]
    )
    q_cols = [f"q_{c}" for c in PRICE_COLUMNS]
    invalid = ratios.filter(
        pl.any_horizontal([(pl.col(c) <= 0) | ~pl.col(c).is_finite() for c in q_cols])
    )
    if invalid.height:
        row = invalid.head(1).to_dicts()[0]
        raise PriceScaleError(
            f"复权比例非法: {row['symbol']} {row['date']} "
            f"q={ {c: row[c] for c in q_cols} }"
        )
    inconsistent = ratios.with_columns(
        pl.max_horizontal(*[((pl.col(c) / pl.col("q_close")) - 1).abs() for c in q_cols]).alias("_spread")
    ).filter(pl.col("_spread") > rtol)
    if inconsistent.height:
        row = inconsistent.sort("_spread", descending=True).head(1).to_dicts()[0]
        raise PriceScaleError(
            f"OHLC 复权比例不一致: {row['symbol']} {row['date']} "
            f"q={ {c: row[c] for c in q_cols} }"
        )

    checked = _attach_expected_scale(ratios, factors)
    scale_bad = checked.filter(((pl.col("q_close") / pl.col("q_expected")) - 1).abs().gt(rtol))
    if scale_bad.height:
        row = scale_bad.with_columns(
            ((pl.col("q_close") / pl.col("q_expected")) - 1).abs().alias("_dev")
        ).sort("_dev", descending=True).head(1).to_dicts()[0]
        raise PriceScaleError(
            f"复权尺度与因子不符: {row['symbol']} {row['date']} "
            f"实际 q={row['q_close']:.8g}, 期望 q={row['q_expected']:.8g} "
            f"(无事件跳变或除权幅度与因子不一致)"
        )
    return {
        "rows": checked.height,
        "symbols": int(checked["symbol"].n_unique()),
        "rtol": rtol,
        "factor_fingerprint": factor_fingerprint(factors),
    }
