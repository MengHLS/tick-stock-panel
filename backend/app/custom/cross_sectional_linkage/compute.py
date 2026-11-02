"""截面联动因子纯计算。

输入是全市场 enriched 行情、交易所板块基准和日频行业成员关系；输出只含
symbol/date 与 7 个联动因子列。模块不读写文件，sidecar 管道负责持久化和发布。
"""
from __future__ import annotations

# Pure computation; persistence and request-time wiring live in factor_provider.py.
from datetime import date

import polars as pl

from app.indicators.pipeline import _bench_key_expr

DEVIATION_FACTOR_IDS: frozenset[str] = frozenset({
    "deviate_3d",
    "deviate_10d",
    "deviate_30d",
})

INDUSTRY_LINKAGE_FACTOR_IDS: frozenset[str] = frozenset({
    "industry_relative_momentum_20d",
    "industry_rank_momentum_20d",
    "industry_corr_60d",
    "industry_beta_60d",
})

LINKAGE_FACTOR_IDS: frozenset[str] = (
    DEVIATION_FACTOR_IDS | INDUSTRY_LINKAGE_FACTOR_IDS
)

_DEVIATION_WINDOWS = (3, 10, 30)
_INDUSTRY_FACTORS = (
    "industry_relative_momentum_20d",
    "industry_rank_momentum_20d",
    "industry_corr_60d",
    "industry_beta_60d",
)
_OUTPUT_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    **{name: pl.Float64 for name in (
        "deviate_3d",
        "deviate_10d",
        "deviate_30d",
        *_INDUSTRY_FACTORS,
    )},
}
_MAX_INDUSTRY_AGE_DAYS = 30
_VAR_EPSILON = 1e-18


def normalize_industry(value: str | None, level: int = 2) -> str | None:
    """取行业路径的指定层级；路径层级不足时取最后一个可用层级。"""
    if value is None:
        return None
    parts = [part.strip() for part in str(value).split("-") if part.strip()]
    if not parts:
        return None
    index = min(max(int(level), 1) - 1, len(parts) - 1)
    return parts[index]


def _industry_expr(level: int) -> pl.Expr:
    """normalize_industry 的 Polars 向量化实现。"""
    raw = pl.col("industry").cast(pl.String).str.strip_chars()
    parts = raw.str.split("-")
    index = pl.min_horizontal(
        pl.lit(max(int(level), 1) - 1),
        raw.str.count_matches("-"),
    )
    return (
        parts.list.get(index)
        .str.strip_chars()
        .replace("", None)
        .alias("industry")
    )


def _empty_output() -> pl.DataFrame:
    return pl.DataFrame(schema=_OUTPUT_SCHEMA)


def _safe_momentum(period: int, *, prefix: str = "_stock") -> pl.Expr:
    prior = pl.col("close").shift(period).over("symbol")
    return (
        pl.when((pl.col("close") > 0) & (prior > 0))
        .then(pl.col("close") / prior - 1)
        .otherwise(None)
        .alias(f"{prefix}_mom_{period}")
    )


def compute_linkage_fields(
    enriched: pl.DataFrame,
    benchmarks: pl.DataFrame,
    membership: pl.DataFrame,
    target_dates: set[date],
    *,
    min_peers: int = 10,
) -> pl.DataFrame:
    """计算目标交易日的 7 个截面联动因子。

    行业因子始终基于传入的全市场面板计算；`target_dates` 只裁剪输出，不缩池
    聚合。所有缺失、未知行业、同业不足和零方差均保持 null。
    """
    if enriched.is_empty() or not target_dates:
        return _empty_output()

    required_enriched = {"symbol", "date", "close"}
    missing = required_enriched - set(enriched.columns)
    if missing:
        raise ValueError(f"联动计算缺少 enriched 列: {', '.join(sorted(missing))}")

    base = (
        enriched.select(["symbol", "date", "close"])
        .with_columns(
            pl.col("symbol").cast(pl.String),
            pl.col("date").cast(pl.Date, strict=False),
            pl.col("close").cast(pl.Float64, strict=False),
        )
        .filter(pl.col("symbol").is_not_null() & pl.col("date").is_not_null())
        .unique(subset=["symbol", "date"], keep="last")
        .sort(["symbol", "date"])
        .with_columns(
            [_safe_momentum(period) for period in (3, 10, 20, 30)]
            + [
                (
                    pl.when(
                        (pl.col("close") > 0)
                        & (pl.col("close").shift(1).over("symbol") > 0)
                    )
                    .then(pl.col("close") / pl.col("close").shift(1).over("symbol") - 1)
                    .otherwise(None)
                    .alias("_return")
                )
            ]
        )
    )

    # ── 交易所板块基准偏离 ─────────────────────────────────────────────
    base = base.with_columns(_bench_key_expr().alias("_bench_key"))
    if benchmarks.is_empty():
        bench = pl.DataFrame(schema={
            "bench_key": pl.String,
            "date": pl.Date,
            **{f"_bench_mom_{n}": pl.Float64 for n in _DEVIATION_WINDOWS},
        })
    else:
        bench_missing = {"date", "bench_key", "bench_close"} - set(benchmarks.columns)
        if bench_missing:
            raise ValueError(
                f"联动计算缺少 benchmarks 列: {', '.join(sorted(bench_missing))}"
            )
        bench = (
            benchmarks.select(["date", "bench_key", "bench_close"])
            .with_columns(
                pl.col("date").cast(pl.Date, strict=False),
                pl.col("bench_key").cast(pl.String),
                pl.col("bench_close").cast(pl.Float64, strict=False),
            )
            .filter(
                pl.col("date").is_not_null()
                & pl.col("bench_key").is_not_null()
                & (pl.col("bench_close") > 0)
            )
            .unique(subset=["bench_key", "date"], keep="last")
            .sort(["bench_key", "date"])
            .with_columns([
                (
                    pl.col("bench_close")
                    / pl.col("bench_close").shift(n).over("bench_key")
                    - 1
                ).alias(f"_bench_mom_{n}")
                for n in _DEVIATION_WINDOWS
            ])
        )
    base = base.join(
        bench,
        left_on=["_bench_key", "date"],
        right_on=["bench_key", "date"],
        how="left",
    )
    base = base.with_columns([
        (
            pl.col(f"_stock_mom_{n}") - pl.col(f"_bench_mom_{n}")
        ).alias(f"deviate_{n}d")
        for n in _DEVIATION_WINDOWS
    ])

    # ── 点时行业成员与全市场同业聚合 ───────────────────────────────────
    membership_missing = {"symbol", "date", "industry"} - set(membership.columns)
    if membership_missing:
        raise ValueError(
            f"联动计算缺少 membership 列: {', '.join(sorted(membership_missing))}"
        )
    memberships = (
        membership.select(["symbol", "date", "industry"])
        .with_columns(
            pl.col("symbol").cast(pl.String),
            pl.col("date").cast(pl.Date, strict=False),
        )
        .with_columns(_industry_expr(2))
        .filter(
            pl.col("symbol").is_not_null()
            & pl.col("date").is_not_null()
            & pl.col("industry").is_not_null()
        )
        .unique(subset=["symbol", "date"], keep="last")
        .rename({"date": "_industry_date"})
        .sort(["symbol", "_industry_date"])
    )
    base = base.sort(["symbol", "date"]).join_asof(
        memberships,
        left_on="date",
        right_on="_industry_date",
        by="symbol",
        strategy="backward",
        check_sortedness=False,
    )
    age_days = (pl.col("date") - pl.col("_industry_date")).dt.total_days()
    base = base.with_columns(
        pl.when(age_days <= _MAX_INDUSTRY_AGE_DAYS)
        .then(pl.col("industry"))
        .otherwise(None)
        .alias("industry")
    )

    industry_rows = base.filter(pl.col("industry").is_not_null())
    group_stats = industry_rows.group_by(["date", "industry"]).agg(
        pl.col("_stock_mom_20").count().alias("_mom_count"),
        pl.col("_stock_mom_20").sum().alias("_mom_sum"),
        pl.col("_return").count().alias("_ret_count"),
        pl.col("_return").sum().alias("_ret_sum"),
    )
    base = base.join(group_stats, on=["date", "industry"], how="left")
    enough_peers = pl.col("_mom_count") >= max(int(min_peers), 0) + 1
    peer_mean_mom = (
        (pl.col("_mom_sum") - pl.col("_stock_mom_20"))
        / (pl.col("_mom_count") - 1)
    )
    base = base.with_columns([
        pl.when(
            pl.col("industry").is_not_null()
            & pl.col("_stock_mom_20").is_not_null()
            & enough_peers
        )
        .then(pl.col("_stock_mom_20") - peer_mean_mom)
        .otherwise(None)
        .alias("industry_relative_momentum_20d"),
        pl.when(
            pl.col("industry").is_not_null()
            & pl.col("_stock_mom_20").is_not_null()
            & enough_peers
        )
        .then(
            pl.col("_stock_mom_20").rank(method="average").over(["date", "industry"])
            / pl.col("_mom_count")
        )
        .otherwise(None)
        .alias("industry_rank_momentum_20d"),
        pl.when(
            pl.col("industry").is_not_null()
            & pl.col("_return").is_not_null()
            & (pl.col("_ret_count") >= max(int(min_peers), 0) + 1)
        )
        .then(
            (pl.col("_ret_sum") - pl.col("_return"))
            / (pl.col("_ret_count") - 1)
        )
        .otherwise(None)
        .alias("_peer_return"),
    ])

    # 60 个完整交易日：按 symbol 尾随窗口，且日期序号必须严丝合缝。
    base = base.with_columns(
        pl.col("date").rank("dense").cast(pl.Int64).alias("_day_index")
    ).sort(["symbol", "date"])
    corr_raw = pl.rolling_corr(
        pl.col("_return"),
        pl.col("_peer_return"),
        window_size=60,
        min_samples=60,
    ).over("symbol")
    cov_raw = pl.rolling_cov(
        pl.col("_return"),
        pl.col("_peer_return"),
        window_size=60,
        min_samples=60,
    ).over("symbol")
    var_raw = pl.col("_peer_return").rolling_var(
        window_size=60,
        min_samples=60,
    ).over("symbol")
    window_span = pl.col("_day_index") - pl.col("_day_index").shift(59).over("symbol")
    complete_window = window_span == 59
    base = base.with_columns([
        pl.when(complete_window & corr_raw.is_finite())
        .then(corr_raw)
        .otherwise(None)
        .alias("industry_corr_60d"),
        pl.when(
            complete_window
            & cov_raw.is_finite()
            & var_raw.is_finite()
            & (var_raw > _VAR_EPSILON)
        )
        .then(cov_raw / var_raw)
        .otherwise(None)
        .alias("industry_beta_60d"),
    ])

    date_set = {
        value if isinstance(value, date) else date.fromisoformat(str(value))
        for value in target_dates
    }
    return (
        base.filter(pl.col("date").is_in(sorted(date_set)))
        .select(list(_OUTPUT_SCHEMA))
        .sort(["symbol", "date"])
    )
