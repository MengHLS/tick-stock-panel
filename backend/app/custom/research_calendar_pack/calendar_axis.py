"""E4 调仓日轴: `month_end` / `week_end` 两个日级日历列 (契约 v0.7 §4.7 E4)。

**权威日历 = `kline_daily_enriched` 数据自身的交易日集合** (partition 键 `date=*`,
与 `select distinct date from read_parquet('.../date=*/*.parquet')` 等价; 判据 E4-A1
逐日比对两者集合相等, 2,141 天)。禁止使用 `services/data_integrity.py#_trading_calendar()`:
它只有近一年真数据 + 「周一到周五」回退, 对 2018–2026 会静默给出错误日历
(周末与节假日全错), 判据 E4-A7 静态拦截。

两个口径决定写死在这里, 不要放宽:

1. `week_end` 的周键由 `week_rule` **显式**决定, 取值只有两个, 缺省 `iso_year_week`:

   * `iso_year_week`(缺省) = `date.isocalendar()` 的 `(iso_year, iso_week)` 二元组。
     跨年时 12 月末与 1 月初可能同属一个 ISO 周 (如 2018-12-31 属 2019-W01)。
   * `dt_week` = `(date.year, iso_week)` —— **自然年** + ISO 周序号。这是 `datetime`
     只取 `dt.year` 的写法; 跨年时它与 ISO 键不一致 (2019-12-31 的 ISO 键是
     2020-W01、自然年键是 2019-W01), 见判据 E4-A6 的集合差异。

   **策略侧必须显式选一个**, 不得依赖缺省值: 两规则在本库实测差 2 个周末日
   (整轴 451 vs 453), 缺省漂移会静默改变调仓日。`week_rule` 不是「只用 week 一位」
   —— 只取 `week` 一位会把不同年份的两个 W01 并成一个「周」, 那是我方禁止的写法
   (2018/2019、2024/2025 的 W01 会合并), 不在两个合法取值内。

2. 数据末端**无法判定**「本月/本周是否已经结束」→ 输出 `null`, 不输出 0.0 / 1.0。
   理由: 若把数据末端 (2026-11-06, 月中) 判成 `month_end=1`, 任何 `month_end == 1`
   触发的调仓都会在 11-06 调仓 —— 这是错的钱, 不是「差不多」。判据 E4-A3 末行。

**帧起点必须固定 `2018-01-08`** (面板起点, 与本文件 `FRAME_START` 一致):
这两个日历列本身与帧起点无关 (日级、只看日历), 但同一帧上如果还要算 `in_universe`,
它的 `observed_bars` 走 `cum_count`, 起点一晚就退化成滚动口径 (池子约 −3.9%), 代码一行
不改、验收全绿 —— 所以起点由调用方固定, 判据 E4-A6 给出退化演示。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import polars as pl

FACTOR_COLUMN_MONTH_END = "month_end"
FACTOR_COLUMN_WEEK_END = "week_end"
CALENDAR_FACTOR_COLUMNS: tuple[str, str] = (FACTOR_COLUMN_MONTH_END, FACTOR_COLUMN_WEEK_END)

# 面板起点: 与 `research/b2-engine-20261107` 的 WARMUP_START / universe AXIS_MIN 同值。
FRAME_START = date(2018, 1, 8)
# 权威日历所在数据集 (asset_type=stock)。ETF/index 的交易日与之一致; 缺目录时才回退。
CALENDAR_DIR = "kline_daily_enriched"
# 口径版本: 日历来源或周键口径变化时递增。
CALENDAR_VERSION = 1

#: `week_rule` 的合法取值 (E4-A6)。缺省 `iso_year_week`; 调用方 (策略/研究) 必须显式选。
WEEK_RULE_ISO = "iso_year_week"
WEEK_RULE_DT = "dt_week"
WEEK_RULES: tuple[str, str] = (WEEK_RULE_ISO, WEEK_RULE_DT)
DEFAULT_WEEK_RULE = WEEK_RULE_ISO

_CACHE: dict[tuple[str, int], tuple[date, ...]] = {}


def _has_parquet(path: Path) -> bool:
    try:
        return any(name.endswith(".parquet") for name in os.listdir(path))
    except OSError:
        return False


def _partition_dates(root: Path) -> tuple[date, ...]:
    """列出 `date=*` 分区中**有 parquet 数据**的日期 (与 repository 的 require_part 同口径)。"""
    days: list[date] = []
    with os.scandir(root) as entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            name = entry.name
            if not name.startswith("date="):
                continue
            try:
                value = date.fromisoformat(name[5:])
            except ValueError:
                continue
            if not _has_parquet(Path(entry.path)):
                continue
            days.append(value)
    return tuple(sorted(days))


def load_trading_calendar(
    data_dir: Path | str,
    *,
    asset_type: str = "stock",
) -> tuple[date, ...]:
    """读权威交易日历 (按数据目录 mtime 缓存; 数据更新后自动失效)。"""
    base = Path(data_dir)
    dirname = {
        "stock": CALENDAR_DIR,
        "etf": "kline_etf_enriched",
        "index": "kline_index_enriched",
    }.get(asset_type, CALENDAR_DIR)
    root = base / dirname
    if not root.is_dir():
        root = base / CALENDAR_DIR          # ETF/index 缺目录时回退到日K enriched
    if not root.is_dir():
        raise ValueError(
            f"E4 需要 {CALENDAR_DIR} 交易日历, 但 {root} 不存在; "
            "不能用『周一到周五』或本机日历代替"
        )
    try:
        stamp = root.stat().st_mtime_ns
    except OSError as exc:
        raise ValueError(f"E4 无法读取日历目录 {root}: {exc}") from exc
    key = (str(root), stamp)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    days = _partition_dates(root)
    if not days:
        raise ValueError(f"E4 在 {root} 未找到任何 date=* 分区, 无法建立交易日历")
    _CACHE.clear()
    _CACHE[key] = days
    return days


def _iso_key(day: date) -> tuple[int, int]:
    """`iso_year_week` 口径: (ISO 年, ISO 周序)。"""
    iso = day.isocalendar()
    return (iso[0], iso[1])


def _dt_week_key(day: date) -> tuple[int, int]:
    """`dt_week` 口径: (自然年, ISO 周序)。跨年周会因此被拆成两段。"""
    return (day.year, day.isocalendar()[1])


def week_key(day: date, week_rule: str = DEFAULT_WEEK_RULE) -> tuple[int, int]:
    """按 `week_rule` 取一个交易日的周键; 域外取值 ValueError (fail-closed)。"""
    if week_rule == WEEK_RULE_ISO:
        return _iso_key(day)
    if week_rule == WEEK_RULE_DT:
        return _dt_week_key(day)
    raise ValueError(f"week_rule 非法: {week_rule!r}（只接受 {list(WEEK_RULES)}）")


def resolve_week_rule(week_rule: str | None = None) -> str:
    """归一 `week_rule`: None → 缺省 `iso_year_week`; 域外抛 ValueError。"""
    if week_rule is None:
        return DEFAULT_WEEK_RULE
    if week_rule not in WEEK_RULES:
        raise ValueError(f"week_rule 非法: {week_rule!r}（只接受 {list(WEEK_RULES)}）")
    return week_rule


def calendar_flags(
    days: tuple[date, ...] | list[date],
    *,
    week_rule: str = DEFAULT_WEEK_RULE,
) -> dict[date, tuple[float | None, float | None]]:
    """逐交易日给 (`month_end`, `week_end`): 1.0 是, 0.0 否, `None` 数据末端不可判。

    `week_rule` 决定 `week_end` 的周键 (E4-A6), 只影响第二列; `month_end` 与它无关。
    """
    rule = resolve_week_rule(week_rule)
    ordered = tuple(days)
    flags: dict[date, tuple[float | None, float | None]] = {}
    for index, day in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if following is None:
            flags[day] = (None, None)       # 末端: 本月/本周是否结束未知
            continue
        month_end = 1.0 if (following.year, following.month) != (day.year, day.month) else 0.0
        week_end = 1.0 if week_key(following, rule) != week_key(day, rule) else 0.0
        flags[day] = (month_end, week_end)
    return flags


def calendar_frame(
    days: tuple[date, ...] | list[date],
    *,
    columns: tuple[str, ...] = CALENDAR_FACTOR_COLUMNS,
    week_rule: str = DEFAULT_WEEK_RULE,
) -> pl.DataFrame:
    """日历列 → 小帧 (date, month_end, week_end), 供 left join。`week_rule` 见 calendar_flags。"""
    flags = calendar_flags(days, week_rule=week_rule)
    rows = [(day, month, week) for day, (month, week) in flags.items()]
    frame = pl.DataFrame(
        rows,
        schema={
            "date": pl.Date,
            FACTOR_COLUMN_MONTH_END: pl.Float64,
            FACTOR_COLUMN_WEEK_END: pl.Float64,
        },
        orient="row",
    )
    keep = ["date", *[name for name in CALENDAR_FACTOR_COLUMNS if name in columns]]
    return frame.select(keep)


def attach_calendar_flags(
    frame: pl.DataFrame,
    days: tuple[date, ...] | list[date],
    *,
    columns: tuple[str, ...] = CALENDAR_FACTOR_COLUMNS,
    week_rule: str = DEFAULT_WEEK_RULE,
) -> pl.DataFrame:
    """把日历列 left join 到面板帧 (不在日历里的日期 → `null`, 不猜)。"""
    wanted = tuple(name for name in columns if name not in frame.columns)
    if not wanted:
        return frame
    if frame.is_empty():
        return frame.with_columns([pl.lit(None, dtype=pl.Float64).alias(name) for name in wanted])
    if "date" not in frame.columns:
        raise ValueError("E4 日历列需要面板帧含 date 列")
    return frame.join(
        calendar_frame(days, columns=wanted, week_rule=week_rule), on="date", how="left"
    )


def calendar_diagnostics(
    frame: pl.DataFrame | None,
    days: tuple[date, ...] | list[date],
    *,
    week_rule: str = DEFAULT_WEEK_RULE,
) -> dict[str, object]:
    """判据用的可观测项: 日历跨度、标记条数、末端 null、帧内缺日历的日期数。"""
    rule = resolve_week_rule(week_rule)
    ordered = tuple(days)
    flags = calendar_flags(ordered, week_rule=rule)
    out: dict[str, object] = {
        "calendar_version": CALENDAR_VERSION,
        "week_rule": rule,
        "n_dates": len(ordered),
        "first_date": ordered[0].isoformat() if ordered else None,
        "last_date": ordered[-1].isoformat() if ordered else None,
        "n_month_end": sum(1 for month, _ in flags.values() if month == 1.0),
        "n_week_end": sum(1 for _, week in flags.values() if week == 1.0),
        "n_unknown_tail": sum(1 for month, _ in flags.values() if month is None),
    }
    if frame is not None and not frame.is_empty() and "date" in frame.columns:
        frame_days = set(frame["date"].unique().to_list())
        out["frame_n_dates"] = len(frame_days)
        out["frame_first_date"] = min(frame_days).isoformat()
        out["frame_last_date"] = max(frame_days).isoformat()
        out["frame_dates_not_in_calendar"] = len(frame_days - set(ordered))
    return out
