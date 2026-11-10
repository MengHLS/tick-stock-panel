"""E4 `month_end` / `week_end` 的 Provider 注册 (契约 v0.7 §4.7, 只落 frame 路径)。

为什么是独立 Provider 而不是纯 DSL 因子:
- 这两个是**日级日历列**, 需要「整个市场的交易日集合」这一帧外信息。DSL 只有逐行/逐标的
  的时序算子 (`ts_max` 等按 symbol 分组), 停牌日缺失会让「本标的 5 根内的最大日期」≠
  「本周最后一个交易日」, 用 DSL 写出来的不是日历。Provider 是既有扩展点, 提供
  `context.data_dir` 读权威日历。
- 计算只调用 `calendar_axis.py`, 不重写口径; 日历来源与周键口径 (`week_rule`) 见该模块
  docstring。`week_rule` 由 `context.params["week_rule"]` 显式传入 (E4-A6), 缺省
  `iso_year_week`; 域外取值 ValueError 不回退。

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
    resolve_week_rule,
)
from app.extensions.factors import FactorProvider, FactorProviderContext
from app.factors.registry import FactorSpec

# 日级日历列只依赖 date; 不声明任何价量列, 免得调用方为了 `month_end` 被迫物化行情列。
CALENDAR_DEPENDENCIES = frozenset({"date"})

#: `context.params` 里携带 `week_rule` 的键名 (E4-A6)。缺省 ISO 口径, 但策略必须显式给。
WEEK_RULE_PARAM = "week_rule"

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
        "date == max(trade_date of week key)  # 周键由 week_rule 参数决定: "
        "iso_year_week(缺省, ISO 二元组) / dt_week(自然年+ISO 周序); 数据末端输出 null"
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
        "week_rule_default": "iso_year_week",
        "week_rule_source": f"context.params[{WEEK_RULE_PARAM!r}]",
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
        return attach_calendar_flags(
            frame,
            days,
            columns=wanted,
            week_rule=self._week_rule(context),
        )

    @staticmethod
    def _week_rule(context: FactorProviderContext) -> str:
        """从 `context.params["week_rule"]` 取周键口径 (E4-A6), 缺省 `iso_year_week`。

        取到域外值直接 ValueError, 不静默回退缺省 —— 静默回退会让策略以为自己选的口径
        生效, 实际跑的是另一套调仓日。
        """
        raw = (context.params or {}).get(WEEK_RULE_PARAM)
        return resolve_week_rule(raw if isinstance(raw, str) else None)

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
        return calendar_diagnostics(frame, days, week_rule=self._week_rule(context))


FACTOR_PROVIDERS = (ResearchCalendarProvider(),)
