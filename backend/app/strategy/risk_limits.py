"""风控参数的量级校验（请求层 / 策略装载层共用）。

背景（为什么需要）：
- ``stop_loss`` 必须是小数比例（-0.08 = -8%）。若写成 -8（百分数），引擎算出的
  止损线会被 ``_valid_price``（backtest/engine.py）判为无效价并丢弃，回测照常跑完、
  结果是「没有止损」，全程没有任何报错 —— 静默失效。
- ``max_hold_days`` 为 0 或负数等于不设上限 / 无意义，同样应该显式报错。

边界（只这两条，不扩范围）：
- ``|stop_loss| > 0.5``      -> ValueError
- ``max_hold_days < 1``      -> ValueError

本模块不依赖回测引擎，纯函数式校验，供 API 请求模型与策略装载器调用。
"""
from __future__ import annotations

import math

#: stop_loss 的量级上限（小数口径）。0.5 = 50%，再大只能是写错单位。
STOP_LOSS_MAX_ABS = 0.5

#: max_hold_days 的下限（交易日）。
MAX_HOLD_DAYS_MIN = 1


def validate_stop_loss(value: object, *, context: str = "stop_loss") -> float | None:
    """校验 stop_loss 的量级；返回规范化后的 float（None 直通）。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{context} must be a number in fraction form (e.g. -0.08), got {value!r}"
        )
    num = float(value)
    if not math.isfinite(num):
        raise ValueError(f"{context} must be a finite number, got {value!r}")
    if abs(num) > STOP_LOSS_MAX_ABS:
        raise ValueError(
            f"{context}={num:g} 超出量级上限 |{context}| <= {STOP_LOSS_MAX_ABS:g}："
            f"{context} 必须写成小数比例（-0.08 表示 -8%），"
            f"写成 {num:g} 会被价格有效性过滤而静默永不触发"
        )
    return num


def validate_max_hold_days(value: object, *, context: str = "max_hold_days") -> int | None:
    """校验 max_hold_days 的下限；返回规范化后的 int（None 直通）。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be an integer >= 1, got {value!r}")
    num = float(value)
    if not math.isfinite(num):
        raise ValueError(f"{context} must be a finite integer, got {value!r}")
    days = int(num)
    if days < MAX_HOLD_DAYS_MIN:
        raise ValueError(
            f"{context}={value!r} 无效：必须 >= {MAX_HOLD_DAYS_MIN} 个交易日"
        )
    return days


def validate_risk_scale(
    *,
    stop_loss: object = None,
    max_hold_days: object = None,
    context: str = "risk",
) -> tuple[float | None, int | None]:
    """一次校验两个风控字段，返回 (stop_loss, max_hold_days)。"""
    return (
        validate_stop_loss(stop_loss, context=f"{context}.stop_loss"),
        validate_max_hold_days(max_hold_days, context=f"{context}.max_hold_days"),
    )
