"""动态自选分组解析器注册表。

核心只保存 ``kind`` + ``rule``，具体口径由二开扩展注册的解析器负责。
手工分组不经过这里，继续由 ``watchlist.parquet`` 的 ``group_ids`` 维护。
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date
from typing import Any

GroupRule = dict[str, Any]
GroupResolver = Callable[[GroupRule, date, Any], list[dict]]
GroupRuleValidator = Callable[[GroupRule], None]

_LOCK = threading.RLock()
_RESOLVERS: dict[str, tuple[GroupResolver, GroupRuleValidator | None]] = {}


def register(
    kind: str,
    resolver: GroupResolver,
    *,
    validator: GroupRuleValidator | None = None,
) -> None:
    """注册一种动态分组规则；kind 必须稳定且全局唯一。"""
    normalized = str(kind or "").strip()
    if not normalized:
        raise ValueError("动态分组规则类型不能为空")
    if not callable(resolver):
        raise TypeError("动态分组解析器必须可调用")
    with _LOCK:
        if normalized in _RESOLVERS:
            raise ValueError(f"动态分组规则类型已注册: {normalized}")
        _RESOLVERS[normalized] = (resolver, validator)


def is_registered(kind: str | None) -> bool:
    with _LOCK:
        return bool(kind) and kind in _RESOLVERS


def validate(kind: str, rule: GroupRule) -> None:
    with _LOCK:
        entry = _RESOLVERS.get(kind)
    if entry is None:
        raise ValueError(f"不支持的动态分组规则类型: {kind}")
    validator = entry[1]
    if validator is not None:
        validator(rule)


def resolve(kind: str, rule: GroupRule, as_of: date, context: Any) -> list[dict]:
    with _LOCK:
        entry = _RESOLVERS.get(kind)
    if entry is None:
        raise ValueError(f"动态分组规则不可用（未加载对应扩展）: {kind}")
    return entry[0](rule, as_of, context)
