"""逐标的行情新鲜度守卫。

监控和盘中信号只能基于"该标的自己的最新行情时间"判定: 全市场快照的最后
交易日相同, 不代表每一行都是刚刚成交的价格。停牌、断流、复权因子读取失败
都会留下一行日期正确但价格陈旧的数据; 用它触发买入告警等于按历史价格下单。

本模块只做判定与留痕, 不改价格、不猜成交:
- ``quote_fresh=False`` 的标的不得产生可执行买入信号;
- 每个拒绝都带机器可读原因, 供告警/审计解释。
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

REASON_MISSING_TS = "missing_quote_ts"
REASON_INVALID_TS = "invalid_quote_ts"
REASON_FUTURE_TS = "future_quote_ts"
REASON_STALE = "stale_quote"
REASON_ADJUSTMENT = "adjustment_unavailable"

REASON_LABELS = {
    REASON_MISSING_TS: "行情时间戳缺失",
    REASON_INVALID_TS: "行情时间戳无效",
    REASON_FUTURE_TS: "行情时间戳超前",
    REASON_STALE: "行情超过最大年龄",
    REASON_ADJUSTMENT: "复权因子不可用",
}


@dataclass(frozen=True)
class FreshnessPolicy:
    # 连续竞价内允许的最大行情年龄。默认 120 秒: 覆盖分钟级轮询的两次间隔,
    # 又不会把"上一分钟的价格"当成当前价。
    max_age_seconds: float = 120.0
    # 供应商时钟可能略快; 超过该容差才算超前, 避免误杀。
    future_tolerance_seconds: float = 60.0

    def max_age_ms(self) -> float:
        return float(self.max_age_seconds) * 1000.0

    def future_tolerance_ms(self) -> float:
        return float(self.future_tolerance_seconds) * 1000.0


def _summary(
    frame: pl.DataFrame,
    *,
    now_ms: float,
    adjustment_error: str | None,
) -> dict:
    if frame.is_empty():
        return {
            "as_of_ms": int(now_ms),
            "symbols": 0,
            "fresh": 0,
            "stale": 0,
            "reasons": {},
            "stale_symbols": [],
            "adjustment_error": adjustment_error,
        }
    stale = frame.filter(~pl.col("quote_fresh"))
    reasons = (
        stale.group_by("quote_stale_reason")
        .len()
        .sort("len", descending=True)
        .rows()
    )
    samples = (
        stale.select(["symbol", "quote_stale_reason", "quote_age_ms"])
        .head(20)
        .to_dicts()
    )
    return {
        "as_of_ms": int(now_ms),
        "symbols": int(frame.height),
        "fresh": int(frame.height - stale.height),
        "stale": int(stale.height),
        "reasons": {str(reason): int(count) for reason, count in reasons},
        "stale_symbols": samples,
        "adjustment_error": adjustment_error,
    }


def annotate_quote_freshness(
    frame: pl.DataFrame,
    *,
    now_ms: float,
    policy: FreshnessPolicy | None = None,
    adjustment_error: str | None = None,
) -> tuple[pl.DataFrame, dict]:
    """给每一行加 ``quote_age_ms`` / ``quote_fresh`` / ``quote_stale_reason``。

    ``adjustment_error`` 非空表示本轮 enriched 以降级口径计算 (例如复权因子
    读取失败): 所有行都判为不可执行, 原因统一为 ``adjustment_unavailable``。
    """
    policy = policy or FreshnessPolicy()
    if frame.is_empty():
        return frame, _summary(frame, now_ms=now_ms, adjustment_error=adjustment_error)

    if "quote_ts" not in frame.columns:
        annotated = frame.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("quote_age_ms"),
            pl.lit(False).alias("quote_fresh"),
            pl.lit(REASON_MISSING_TS).alias("quote_stale_reason"),
        )
        return annotated, _summary(
            annotated, now_ms=now_ms, adjustment_error=adjustment_error
        )

    ts = pl.col("quote_ts")
    if frame.schema["quote_ts"].is_temporal():
        ts = ts.dt.epoch("ms")
    ts = ts.cast(pl.Float64, strict=False)
    age = pl.lit(float(now_ms)) - ts
    annotated = frame.with_columns(
        age.alias("quote_age_ms"),
    ).with_columns(
        pl.when(pl.col("quote_ts").is_null())
        .then(pl.lit(REASON_INVALID_TS))
        .when(~pl.col("quote_age_ms").is_finite())
        .then(pl.lit(REASON_INVALID_TS))
        .when(pl.col("quote_age_ms") < -policy.future_tolerance_ms())
        .then(pl.lit(REASON_FUTURE_TS))
        .when(pl.col("quote_age_ms") > policy.max_age_ms())
        .then(pl.lit(REASON_STALE))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("quote_stale_reason"),
    ).with_columns(
        (pl.col("quote_stale_reason").is_null()).alias("quote_fresh"),
    )
    if adjustment_error:
        annotated = annotated.with_columns(
            pl.lit(False).alias("quote_fresh"),
            pl.lit(REASON_ADJUSTMENT).alias("quote_stale_reason"),
        )
    return annotated, _summary(
        annotated, now_ms=now_ms, adjustment_error=adjustment_error
    )


def fresh_rows(frame: pl.DataFrame) -> pl.DataFrame:
    """只保留判定为新鲜的标的; 未标注的帧原样返回 (兼容旧调用)。"""
    if frame.is_empty() or "quote_fresh" not in frame.columns:
        return frame
    return frame.filter(pl.col("quote_fresh"))


def stale_rejections(frame: pl.DataFrame) -> dict[str, str]:
    """symbol → 拒绝原因。未标注的帧返回空字典。"""
    if frame.is_empty() or "quote_stale_reason" not in frame.columns:
        return {}
    rows = frame.filter(~pl.col("quote_fresh")).select(
        ["symbol", "quote_stale_reason"]
    ).iter_rows()
    return {str(symbol): str(reason) for symbol, reason in rows if symbol}
