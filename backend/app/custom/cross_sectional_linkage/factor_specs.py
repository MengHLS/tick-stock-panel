"""Factor metadata owned by the cross-sectional linkage extension."""
from __future__ import annotations

from app.factors.registry import FactorSpec

_STOCK_ONLY = frozenset({"stock"})


def _spec(
    factor_id: str,
    label: str,
    description: str,
    *,
    unit: str,
    warmup_bars: int,
    tags: tuple[str, ...],
    intraday_monitor_safe: bool = True,
) -> FactorSpec:
    return FactorSpec(
        id=factor_id,
        label=label,
        group="截面联动",
        formula_text=description,
        unit=unit,  # type: ignore[arg-type]
        warmup_bars=warmup_bars,
        asset_types=_STOCK_ONLY,
        incremental_safe=False,
        intraday_monitor_safe=intraday_monitor_safe,
        tags=tags,
    )


LINKAGE_FACTOR_SPECS = (
    _spec(
        "deviate_3d",
        "3日基准偏离",
        "个股3日收益减所属板块基准3日收益",
        unit="ratio",
        warmup_bars=4,
        tags=("联动", "基准"),
    ),
    _spec(
        "deviate_10d",
        "10日基准偏离",
        "个股10日收益减所属板块基准10日收益",
        unit="ratio",
        warmup_bars=11,
        tags=("联动", "基准"),
    ),
    _spec(
        "deviate_30d",
        "30日基准偏离",
        "个股30日收益减所属板块基准30日收益",
        unit="ratio",
        warmup_bars=31,
        tags=("联动", "基准"),
    ),
    _spec(
        "industry_relative_momentum_20d",
        "行业相对动量(20日)",
        "个股20日动量减同业均值",
        unit="ratio",
        warmup_bars=21,
        tags=("联动", "行业"),
        intraday_monitor_safe=False,
    ),
    _spec(
        "industry_rank_momentum_20d",
        "行业内动量排名(20日)",
        "个股20日动量在所属行业内的平均排名百分位",
        unit="score",
        warmup_bars=21,
        tags=("联动", "行业"),
        intraday_monitor_safe=False,
    ),
    _spec(
        "industry_corr_60d",
        "行业收益相关(60日)",
        "个股日收益与同业等权组合日收益的60日相关系数",
        unit="ratio",
        warmup_bars=61,
        tags=("联动", "行业"),
        intraday_monitor_safe=False,
    ),
    _spec(
        "industry_beta_60d",
        "行业Beta(60日)",
        "个股日收益对同业等权组合日收益的60日Beta",
        unit="ratio",
        warmup_bars=61,
        tags=("联动", "行业"),
        intraday_monitor_safe=False,
    ),
)
