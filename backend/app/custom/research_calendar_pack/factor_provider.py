"""E4 `month_end` / `week_end` 的 Provider 注册 (契约 v0.7 §4.7, 只落 frame 路径)。

为什么是独立 Provider 而不是纯 DSL 因子:
- 这两个是**日级日历列**, 需要「整个市场的交易日集合」这一帧外信息。DSL 只有逐行/逐标的
  的时序算子 (`ts_max` 等按 symbol 分组), 停牌日缺失会让「本标的 5 根内的最大日期」≠
  「本周最后一个交易日」, 用 DSL 写出来的不是日历。Provider 是既有扩展点, 提供
  `context.data_dir` 读权威日历。
- 计算只调用 `calendar_axis.py`, 不重写口径; 日历来源与 ISO 周口径见该模块 docstring。

矩阵路径 (`materialize_matrix_field`) 保持基类默认 `None` = 缺能力项 (与 B0/B2 的 pack
因子一致), 矩阵侧接入属 B0b, 本批不动 `matrix.py`。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from app.custom.research_calendar_pack.calendar_axis import (
    CALENDAR_FACTOR_COLUMNS,
    CALENDAR_VERSION,
    FACTOR_COLUMN_MONTH_END,
    FACTOR_COLUMN_WEEK_END,
    FRAME_START,
    attach_calendar_flags,
    calendar_diagnostics,
    load_trading_calendar,
)
from app.extensions.factors import FactorProvider, FactorProviderContext
from app.factors.registry import FactorSpec

# 日级日历列只依赖 date; 不声明任何价量列, 免得调用方为了 `month_end` 被迫物化行情列。
CALENDAR_DEPENDENCIES = frozenset({"date"})

_COMMON = {
    "kind": "custom",
    "lang": "dsl",
    "version": 1,
    "dependencies": CALENDAR_DEPENDENCIES,
    # 日历列无预热: 第一根 bar 就能判 (只需日历本身)。0 而不是 1, 别照抄 DSL 因子的默认值。
    "warmup_bars": 0,
    "direction": "none",
    "unit": "none",
    "scale_free": True,
    "null_policy": "keep",
    "stability": "stable",
    "tags": ("calendar", "E4", "调仓日轴"),
}

_MONTH_END_SPEC = FactorSpec(
    id=FACTOR_COLUMN_MONTH_END,
    label="月末交易日",
    group="日历",
    formula_text=(
        "date == max(trade_date of calendar month)  # 日历 = kline_daily_enriched "
        "distinct date; 数据末端 (本月是否结束未知) 输出 null"
    ),
    **_COMMON,
)

_WEEK_END_SPEC = FactorSpec(
    id=FACTOR_COLUMN_WEEK_END,
    label="周末交易日(ISO周)",
    group="日历",
    formula_text=(
        "date == max(trade_date of ISO week (iso_year, iso_week))  # 跨年按 ISO 二元组, "
        "不用自然周序号; 数据末端输出 null"
    ),
    **_COMMON,
)


class ResearchCalendarProvider(FactorProvider):
    provider_id = "official.research-calendar-pack-e4"
    version = 1
    kind = "frame"
    factor_ids = frozenset({FACTOR_COLUMN_MONTH_END, FACTOR_COLUMN_WEEK_END})
    factor_specs = (_MONTH_END_SPEC, _WEEK_END_SPEC)

    def dependencies(self, factor_id: str) -> frozenset[str]:
        del factor_id
        return CALENDAR_DEPENDENCIES

    def warmup_bars(self, factor_id: str) -> int:
        del factor_id
        return 0

    def params(self, factor_id: str):
        del factor_id
        return {
            "calendar_source": "kline_daily_enriched",
            "week_key": "iso_year+iso_week",
            "tail_policy": "null_until_month_or_week_closes",
            "frame_start": FRAME_START.isoformat(),
            "calendar_version": CALENDAR_VERSION,
        }

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        wanted = tuple(
            name for name in CALENDAR_FACTOR_COLUMNS if name in names and name not in frame.columns
        )
        if not wanted:
            return frame
        if frame.is_empty():
            return frame.with_columns(
                [pl.lit(None, dtype=pl.Float64).alias(name) for name in wanted]
            )
        days = load_trading_calendar(
            self._data_dir(context), asset_type=context.asset_type or "stock"
        )
        return attach_calendar_flags(frame, days, columns=wanted)

    @staticmethod
    def _data_dir(context: FactorProviderContext) -> Path:
        data_dir = context.data_dir
        if data_dir is None:
            # 与 universe pack 同一来源, 不新增配置项。
            from app.config import settings

            data_dir = settings.data_dir
        assert isinstance(data_dir, Path)
        return data_dir

    # 判据/诊断入口 (不参与物化)
    def diagnostics(
        self,
        frame: pl.DataFrame | None,
        context: FactorProviderContext,
    ) -> dict[str, object]:
        days = load_trading_calendar(
            self._data_dir(context), asset_type=context.asset_type or "stock"
        )
        return calendar_diagnostics(frame, days)


FACTOR_PROVIDERS = (ResearchCalendarProvider(),)
