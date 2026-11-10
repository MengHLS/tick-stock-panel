"""逐标的行情新鲜度守卫。

监控和盘中信号只能基于"该标的自己的最新行情时间"判定: 全市场快照的最后
交易日相同, 不代表每一行都是刚刚成交的价格。停牌、断流、复权因子读取失败
都会留下一行日期正确但价格陈旧的数据; 用它触发买入告警等于按历史价格下单。

本模块只做判定与留痕, 不改价格、不猜成交:
- ``quote_fresh=False`` 的标的不得产生可执行买入信号;
- 每个拒绝都带机器可读原因, 供告警/审计解释。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time

import polars as pl

from app.market_time import CN_TZ, cn_now
from app.services import trading_day

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
class QuoteFreshness:
    def __init__(self, *, now: datetime | None = None, trading: bool | None = None,
                 enabled: bool = True, paused: bool = False, interval: float = 6) -> None:
        self.now = (now or cn_now()).astimezone(CN_TZ)
        self.trading = trading
        self.enabled, self.paused = enabled, paused
        self.max_age_ms = max(90_000, interval * 3_000)

    @classmethod
    def for_request(cls, request):
        now = cn_now()
        qs = getattr(request.app.state, "quote_service", None)
        return cls(now=now, trading=trading_day.cached_verdict(now),
                   enabled=bool(qs and getattr(qs, "_enabled", False)),
                   paused=bool(qs and getattr(qs, "_paused", False)),
                   interval=getattr(qs, "_interval", 6) if qs else 6)

    def describe(self, row: dict | None, *, historical: bool = False) -> dict:
        row = row or {}
        data_date = str(row.get("date") or "")[:10] or None
        stamp = row.get("quote_ts", row.get("timestamp"))
        quote_dt = None
        try:
            stamp = float(stamp)
            if not math.isfinite(stamp) or stamp <= 0:
                raise ValueError
            quote_dt = datetime.fromtimestamp(stamp / 1000, CN_TZ)
            data_date = quote_dt.date().isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            stamp = None
        out = {"data_date": data_date, "quote_ts": stamp,
               "checked_at": int(self.now.timestamp() * 1000), "max_age_ms": self.max_age_ms}

        def result(state, message):
            return {**out, "state": state, "message": message}

        try:
            price = float(row.get("close", row.get("last_price")))
            valid = math.isfinite(price) and price > 0
        except (TypeError, ValueError):
            valid = False
        if not valid:
            return result("missing", "暂无可用行情，请检查数据源或稍后重试")
        if quote_dt and quote_dt > self.now.replace(microsecond=0) and (quote_dt - self.now).total_seconds() > 60:
            return result("unknown", "行情时间异常，请检查数据源时间")
        today, clock = self.now.date(), self.now.time()
        trading = self.trading is not False and self.now.weekday() < 5
        if historical or not trading or clock < time(9, 30):
            return result("historical", "历史行情，按实际数据日期显示")
        if data_date is None or data_date < today.isoformat():
            return result("stale", "行情已过期，保留最近有效数据；请检查连接及所选源对该标的的支持范围")
        if data_date > today.isoformat():
            return result("unknown", "行情日期异常，请检查数据源")
        if row.get("prepared_daily"):
            return result("historical", "日K补齐数据，尚未取得实时行情")
        if self.paused:
            return result("paused", "实时行情暂时暂停，保留最近有效数据")
        if not self.enabled:
            return result("disabled", "实时行情未开启，保留最近有效数据")
        if stamp is None:
            return result("unknown", "当日数据缺少行情时间，无法确认实时性")
        active = clock < time(11, 30) or time(13) <= clock < time(15)
        reference = self.now if active else datetime.combine(today, time(11, 30) if clock < time(13) else time(15), CN_TZ)
        if reference.timestamp() * 1000 - stamp > self.max_age_ms:
            return result("delayed", "行情更新延迟，保留最近有效数据，请检查数据源与连接")
        return result("live", "实时行情") if active else result("historical", "休盘行情，按最后有效时间显示")
