"""E3 `in_universe` 计算核心 (契约 v0.7 §2.1–§2.4)。

口径权威 = 研究侧 `research/strategy-search-20261107/scripts/common.py#add_universe`
(`:175-184`), 逐条对应契约 §2.1 的五个条件。生产口径与研究侧的两处**已知且有意**
的差异 (契约 §2.3 注 2 / 注 3, 不是实现瑕疵):

1. `st_flag` 缺失不再 `fill_null(False)` —— 生产口径按三态输出 `null`
   (`st_flag_missing_policy="unknown"`), 因为「未知 ST」不等于「非 ST」。
2. `date > st_history 的 coverageEnd` 一律 `null`, **禁止**用 `join_asof(backward)`
   外推末值 (现实现的 `security_status.py` 只判「前面有没有行」)。

`st_unknown_windows` (默认 `2026-10-20`…`2026-10-29`) 内当日全部 symbol 输出 `null`:
该窗口 `st_history` 被批量写成 `st_flag=false` (198 行), 口径不可判定。

三个条件口径按研究侧原样保留, 但每一条都在注释里写明「为什么不是另一个写法」:
- 停牌 = 当日无 bar 行 (`volume=0` 全库 0 行, 不能用它判停牌)。
- 上市天数 = 交易日轴计数, **不是**自然日差、**不是** bar 序号。
- `prior_amount20` = `amount.shift(1).rolling_mean(20)`, 不含当日, 单位元。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

# 契约 §2.2「参数（带版本）」的默认值 —— 只此一处, 别处不得重复字面量。
DEFAULT_MIN_OBSERVED_BARS = 120
DEFAULT_MIN_PRICE_RAW = 3.0
DEFAULT_MIN_PRIOR_AMOUNT20 = 1e8
DEFAULT_SYMBOL_PREFIXES = ("60", "00")
DEFAULT_ST_UNKNOWN_WINDOWS: tuple[tuple[str, str], ...] = (("2026-10-20", "2026-10-29"),)
# 参数或口径变化必须递增 (契约 §2.2 / §2.4): v0.3 起新增 st_unknown_windows 与
# 「末端不外推」两条硬规则, 口径变了 → 缓存必须重算, 故起始即 2。
UNIVERSE_VERSION = 2

FACTOR_COLUMN_IN_UNIVERSE = "in_universe"
# 中间列前缀: 不与既有 enriched 列 / 指标列 / 用户因子列冲突。
_TMP = "__uf_"


@dataclass(frozen=True)
class UniverseParams:
    """契约 §2.2 的参数集; `universe_version` 随口径变。"""

    min_observed_bars: int = DEFAULT_MIN_OBSERVED_BARS
    min_price_raw: float = DEFAULT_MIN_PRICE_RAW
    min_prior_amount20: float = DEFAULT_MIN_PRIOR_AMOUNT20
    require_volume_gt0: bool = True
    symbol_prefixes: tuple[str, ...] = DEFAULT_SYMBOL_PREFIXES
    exclude_st: bool = True
    st_flag_missing_policy: str = "unknown"  # "unknown" | "treat_non_st"
    st_unknown_windows: tuple[tuple[str, str], ...] = DEFAULT_ST_UNKNOWN_WINDOWS
    universe_version: int = UNIVERSE_VERSION

    def __post_init__(self) -> None:
        if self.st_flag_missing_policy not in {"unknown", "treat_non_st"}:
            raise ValueError(
                f"st_flag_missing_policy 非法: {self.st_flag_missing_policy!r}"
            )
        if self.min_observed_bars < 1:
            raise ValueError("min_observed_bars 必须 ≥ 1")
        if not self.symbol_prefixes:
            raise ValueError("symbol_prefixes 不得为空")

    @property
    def reconciliation_mode(self) -> bool:
        """契约 §2.3: `treat_non_st` 只用于与研究侧 1,429 对账。"""
        return self.st_flag_missing_policy == "treat_non_st"

    def cache_key(self) -> tuple[object, ...]:
        return (
            FACTOR_COLUMN_IN_UNIVERSE,
            self.universe_version,
            self.min_observed_bars,
            self.min_price_raw,
            self.min_prior_amount20,
            self.require_volume_gt0,
            self.symbol_prefixes,
            self.exclude_st,
            self.st_flag_missing_policy,
            self.st_unknown_windows,
        )


def _st_unknown_mask(dates: pl.Expr, windows: tuple[tuple[str, str], ...]) -> pl.Expr:
    """`date ∈ st_unknown_windows` 的布尔表达式 (含首尾, 按交易日判定)。"""
    condition: pl.Expr | None = None
    for start, end in windows:
        current = (dates >= pl.lit(start).str.to_date()) & (dates <= pl.lit(end).str.to_date())
        condition = current if condition is None else (condition | current)
    return condition if condition is not None else pl.lit(False)


def compute_in_universe(
    frame: pl.DataFrame,
    *,
    st_history: pl.DataFrame,
    params: UniverseParams | None = None,
) -> pl.DataFrame:
    """在 `frame` 上追加 `in_universe` 列 (float64: 1.0 / 0.0 / null)。

    `frame` 必须含: symbol, date, volume, amount, raw_close。行序保持调用方原样
    (内部按 (symbol, date) 排序计算, 结果按原行序还原)。
    缺列 / `st_history` 为空 → `ValueError` (fail-closed, 不回退默认值)。
    """
    params = params or UniverseParams()
    required = {"symbol", "date", "volume", "amount", "raw_close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"in_universe 缺少必需列: {sorted(missing)}")
    if st_history is None or st_history.is_empty():
        raise ValueError(
            "in_universe 需要历史 ST 状态 (st_history); 不能用当前名称或默认值代替"
        )
    if frame.is_empty():
        return frame.with_columns(
            pl.lit(None, dtype=pl.Float64).alias(FACTOR_COLUMN_IN_UNIVERSE)
        )

    work = frame.with_row_index(_TMP + "row").sort(["symbol", "date"])

    # --- 条件 1: 上市/可交易交易日数 ≥ 120 (契约 §2.1 坑 1) ---
    # 用「该标的在此面板内的 bar 行数」= 研究侧 `date.cum_count().over("symbol")` 的
    # 等价实现。前置 ≥120 根 warmup 时与「滚动可交易日计数」逐位相同; 不用自然日差
    # (会多纳入 38,627 标的日), 也不用上市日 + 交易日轴 (面板起点 2018-01-08 之前
    # 上市的标的会被系统性低估, 见 E3_DATA_AVAILABILITY §4)。
    # 与研究侧同一表达式 (common.py:129 `date.cum_count().over("symbol")`), 保证逐位相同。
    # `date` 非空, 故 cum_count == 组内行号; 写同一形式是为了让口径可逐字对照。
    work = work.with_columns(
        pl.col("date").cum_count().over("symbol").cast(pl.Int64).alias(_TMP + "observed_bars")
    )

    # --- 条件 2: prior_amount20 = amount.shift(1).rolling_mean(20), 不含当日, 单位元 ---
    work = work.with_columns(
        pl.col("amount")
        .shift(1)
        .rolling_mean(20)
        .over("symbol")
        .alias(_TMP + "prior_amount20")
    )

    # --- 条件 3: 当日 ST (as-of, 生效日回溯) ---
    history = st_history
    if history.schema["flag_date"] == pl.String:
        history = history.with_columns(pl.col("flag_date").str.to_date(strict=False))
    history = (
        history.select(
            pl.col("symbol").cast(pl.String),
            pl.col("flag_date").cast(pl.Date).alias(_TMP + "flag_date"),
            pl.col("st_flag").cast(pl.Boolean).alias(_TMP + "st_flag"),
        )
        .drop_nulls()
        .unique(subset=["symbol", _TMP + "flag_date"])
        .sort([_TMP + "flag_date"])
    )
    coverage_end = history[_TMP + "flag_date"].max()
    if coverage_end is None:
        raise ValueError("st_history 为空, 无法确定 coverageEnd")

    # join_asof 要求左侧**按 on 列全局排序** (不是按 (symbol,date)); 这里临时按 date
    # 排序做合并, 结果按 __uf_row 还原原行序。与 security_status.attach_st_history
    # 的写法一致 —— 不排序会让 as-of 匹配大面积错配 (实测 248 天全 null)。
    work = (
        work.sort("date")
        .join_asof(
            history,
            left_on="date",
            right_on=_TMP + "flag_date",
            by="symbol",
            strategy="backward",
            check_sortedness=False,
        )
        .sort(_TMP + "row")
    )

    # 契约 §2.3 注 2 / 注 3: 两种「ST 口径不可判定」必须输出 null, 且**不得**把
    # coverageEnd 的末值外推到之后 (现实现的 join_asof 只判「前面有没有行」)。
    in_window = _st_unknown_mask(pl.col("date"), params.st_unknown_windows)
    beyond = pl.col("date") > pl.lit(coverage_end)
    st_missing = pl.col(_TMP + "st_flag").is_null()

    # 「不可判定」的两类来源; 顺序即诊断标签优先级 (窗口 > 末端)。
    # 对账模式下这两类**仍然**输出 null: 它们不是「ST 缺失」, 是口径本身不可判定。
    undecidable = in_window | beyond
    if params.st_flag_missing_policy == "unknown":
        # 契约 §2.3: 不把「未知 ST」当「非 ST」; 研究侧 fill_null(False) 是宽容处理。
        undecidable = undecidable | st_missing

    if params.exclude_st:
        if params.st_flag_missing_policy == "unknown":
            # 缺失已在 undecidable 里 → 这里只需「已知且为 False」才放行
            st_ok = pl.col(_TMP + "st_flag").fill_null(False).not_()
        else:
            # 仅对账模式: 缺失按「非 ST」继续 (研究侧 fill_null(False) 口径)
            st_ok = pl.col(_TMP + "st_flag").fill_null(False).not_()
    else:
        st_ok = pl.lit(True)

    # 契约 §2.3: raw_close / prior_amount20 为 null 但 bar 足够 → 0.0
    # (条件不成立, 不是「不可判定」), 故此处 fill_null(False)。
    passes = (
        (pl.col(_TMP + "observed_bars") >= params.min_observed_bars)
        & (pl.col("raw_close") >= params.min_price_raw)
        & (pl.col(_TMP + "prior_amount20") >= params.min_prior_amount20)
        & st_ok
    )
    if params.require_volume_gt0:
        passes = passes & (pl.col("volume") > 0)

    work = work.with_columns(
        pl.when(undecidable)
        .then(pl.lit(None, dtype=pl.Float64))
        .when(passes.fill_null(False))
        .then(pl.lit(1.0, dtype=pl.Float64))
        .otherwise(pl.lit(0.0, dtype=pl.Float64))
        .alias(FACTOR_COLUMN_IN_UNIVERSE)
    )

    drop = [
        _TMP + "observed_bars",
        _TMP + "prior_amount20",
        _TMP + "flag_date",
        _TMP + "st_flag",
    ]
    return work.sort(_TMP + "row").drop(_TMP + "row", *drop)


def universe_diagnostics(
    frame: pl.DataFrame,
    *,
    st_history: pl.DataFrame,
    params: UniverseParams | None = None,
) -> pl.DataFrame:
    """逐日诊断表 (契约 §2.6 A3/A4/A7/A8 的可断言产物)。

    输出列: date / bars(当日有 bar 行数) / in_pool(count == 1.0) /
    not_in_pool(count == 0.0) / unknown(universe_unknown_count) /
    unknown_reason(不可判定原因码: st_unknown_window | beyond_coverage | null)
    """
    params = params or UniverseParams()
    computed = compute_in_universe(frame, st_history=st_history, params=params)
    history = st_history
    if history.schema["flag_date"] == pl.String:
        history = history.with_columns(pl.col("flag_date").str.to_date(strict=False))
    coverage_end = history["flag_date"].max()

    return (
        computed.group_by("date")
        .agg(
            pl.len().alias("bars"),
            (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().alias("in_pool"),
            (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 0.0).sum().alias("not_in_pool"),
            pl.col(FACTOR_COLUMN_IN_UNIVERSE).is_null().sum().alias("unknown"),
            pl.lit(str(coverage_end)).alias("coverage_end"),
        )
        .with_columns(
            pl.when(_st_unknown_mask(pl.col("date"), params.st_unknown_windows))
            .then(pl.lit("st_unknown_window"))
            .when(pl.col("date") > pl.lit(coverage_end))
            .then(pl.lit("beyond_coverage"))
            .when(pl.col("unknown") > 0)
            .then(pl.lit("st_missing"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("unknown_reason")
        )
        .sort("date")
    )
