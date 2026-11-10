"""声明式条件动态分组。

规则沿用自定义信号/叠加条件的数据结构:
``{left, op, right, leftDays, rightDays}``，按交易日回看，AND 组合。
不执行用户 SQL/Python，字段和运算符均由现有白名单校验。
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import polars as pl

from app.strategy import custom_signals

_SCHEMA_VERSION = 1
_DEFAULT_MAX_RESULTS = 200
_MAX_RESULTS = 1000

# 返回给自选表格的列。未出现在帧里的列会被忽略；前端缺列显示为 “—”。
_OUTPUT_COLS = (
    "symbol",
    "name",
    "date",
    "asset_type",
    "open",
    "high",
    "low",
    "close",
    "prev_close",
    "change_pct",
    "change_amount",
    "amplitude",
    "volume",
    "amount",
    "turnover_rate",
    "float_shares",
    "consecutive_limit_ups",
    "consecutive_limit_downs",
    "limit_up_price",
    "limit_down_price",
    "raw_close",
    "raw_high",
    "raw_low",
    "ma5",
    "ma10",
    "ma20",
    "ma30",
    "ma60",
    "rsi_6",
    "rsi_14",
    "rsi_24",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "boll_upper",
    "boll_lower",
    "atr_14",
    "vol_ratio_5d",
    "momentum_5d",
    "momentum_10d",
    "momentum_20d",
    "momentum_30d",
    "momentum_60d",
)


def validate(rule: dict[str, Any]) -> None:
    if not isinstance(rule, dict):
        raise ValueError("动态分组规则必须是对象")
    rule_type = str(rule.get("type") or "").strip()
    if rule_type != "conditions":
        raise ValueError(f"不支持的动态分组规则类型: {rule_type}")
    version = rule.get("schema_version", _SCHEMA_VERSION)
    if version != _SCHEMA_VERSION:
        raise ValueError(f"动态分组规则版本不兼容: {version}")
    logic = str(rule.get("logic") or "and").lower()
    if logic != "and":
        raise ValueError("动态分组暂只支持 AND 条件")
    conditions = rule.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("动态分组至少需要 1 个条件")
    custom_signals.validate_overlay_conditions(conditions)
    from app.factors.ext_factors import ext_string_fields

    string_fields = ext_string_fields()
    for index, condition in enumerate(conditions):
        left = str(condition.get("left") or "")
        if left in string_fields:
            raise ValueError(
                f"第 {index + 1} 个条件: 动态分组暂不支持字符串扩展字段 {left}"
            )
        right = condition.get("right")
        if (
            isinstance(right, str)
            and right.startswith("field:")
            and right[len("field:"):] in string_fields
        ):
            right_field = right[len("field:"):]
            raise ValueError(
                f"第 {index + 1} 个条件: 动态分组暂不支持字符串扩展字段 {right_field}"
            )
    max_results = rule.get("max_results", _DEFAULT_MAX_RESULTS)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_results 必须是整数") from exc
    if not 1 <= max_results <= _MAX_RESULTS:
        raise ValueError(f"max_results 必须在 1..{_MAX_RESULTS} 之间")


def resolve(rule: dict[str, Any], as_of: date, context: Any) -> list[dict]:
    validate(rule)
    screener = context["screener"]
    conditions = rule["conditions"]
    lookback_days = max(3, custom_signals.overlay_max_days(conditions) + 2)
    frame = screener.load_enriched_history(as_of, lookback_days)
    if frame is None or frame.is_empty():
        return []

    try:
        expr = custom_signals.build_overlay_expr(conditions)
        if expr is None:
            return []
        frame = custom_signals.materialize_factor_columns(frame, {"dynamic_group": expr})
        # 先在全历史上计算偏移表达式，再裁到目标日；反过来会让 shift 只看到当日一行。
        frame = frame.with_columns(expr.fill_null(False).alias("_dynamic_match"))
        frame = frame.filter(
            (pl.col("date") == as_of) & pl.col("_dynamic_match")
        ).drop("_dynamic_match")
    except Exception as exc:
        raise ValueError(f"动态分组规则无法求值: {exc}") from exc
    if frame.is_empty():
        return []

    max_results = int(rule.get("max_results", _DEFAULT_MAX_RESULTS))
    cols = [column for column in _OUTPUT_COLS if column in frame.columns]
    signal_cols = [
        column
        for column in frame.columns
        if column.startswith(("signal_", "csg_")) and column not in cols
    ]
    frame = frame.select(cols + signal_cols)
    if "date" in frame.columns:
        frame = frame.with_columns(pl.col("date").cast(pl.Utf8))
    frame = frame.sort("symbol").head(max_results)

    rows: list[dict] = []
    for row in frame.to_dicts():
        for key, value in list(row.items()):
            if isinstance(value, float) and not math.isfinite(value):
                row[key] = None
        row.setdefault("asset_type", "stock")
        rows.append(row)
    return rows
