"""纯规则计算：输入已按 as_of 截断的日线序列，输出 as_of 当时可知的研究事件。

口径约束：
- 条件只引用第 0..i 根，任何判断不得访问 i 之后的数据；
- 事件标记落在 ``confirmed_at``（右侧确认完成的那一根），形态位置只留在 ``pattern_date``；
- 确认窗口未走完的形态在 as_of 上输出为候选（``status="candidate"``，无确认日）；
- 失效作为独立事件输出，用 ``linked_event_id`` 关联原事件，原事件历史输出不被改写；
- 失效阈值使用形态日当时已知的水平（``levels`` 随事件冻结），避免后续极值把阈值漂移改写。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

TIMEFRAME = "1d"
ASSET_TYPE = "stock"

# 规则未冻结：内置演示口径只用于页面形态与状态验收，不构成已验证有效的交易规则。
# 研究规格交付后（spec.json 声明 spec_status=frozen 与 rule_version）整体覆盖这里的阈值。
UNFROZEN_DEMO_SPEC: dict[str, Any] = {
    "spec_status": "unfrozen_demo",
    "timeframe": TIMEFRAME,
    "warmup_bars": 30,
    "box_window": 30,
    "volume_window": 5,
    "events": {
        "Spring": {
            "phase": "吸筹区间",
            "confirm_bars": 3,
            "break_tolerance": 0.008,
            "conditions": [
                {"name": "下探支撑", "metric": "low", "op": "<", "reference": "support", "window": 1},
                {"name": "下探支撑后收回", "metric": "close", "op": ">", "reference": "support", "window": 1},
                {"name": "量比", "metric": "volume_ratio", "op": ">=", "threshold": 1.5, "window": 5},
            ],
            "invalidation": {"name": "收盘跌破支撑", "op": "<", "reference": "support", "tolerance": 0.008, "bars": 1},
        },
        "Test": {
            "phase": "二次测试",
            "confirm_bars": 1,
            "conditions": [
                {"name": "低点高于弹簧低点", "metric": "low", "op": ">", "reference": "spring_low", "window": 1},
                {"name": "量能收缩", "metric": "volume_ratio", "op": "<=", "threshold": 0.8, "window": 5},
            ],
            "invalidation": None,
        },
        "SOS": {
            "phase": "吸筹突破",
            "confirm_bars": 3,
            "conditions": [
                {"name": "收盘突破上沿", "metric": "close", "op": ">", "reference": "resistance", "window": 1},
                {"name": "量比", "metric": "volume_ratio", "op": ">=", "threshold": 1.5, "window": 5},
            ],
            "invalidation": {"name": "收盘回落至上沿下方", "op": "<", "reference": "resistance", "tolerance": 0.015, "bars": 1},
        },
        "LPS": {
            "phase": "回踩确认",
            "confirm_bars": 3,
            "conditions": [
                {"name": "回踩不破上沿", "metric": "low", "op": ">=", "reference": "resistance_low_band", "window": 1},
                {"name": "缩量回踩", "metric": "volume_ratio", "op": "<=", "threshold": 0.8, "window": 5},
                {"name": "收盘转强", "metric": "close", "op": ">", "reference": "prior_close_high", "window": 3},
            ],
            "invalidation": {"name": "收盘跌破回踩低点", "op": "<", "reference": "pattern_low", "tolerance": 0.017, "bars": 1},
        },
        "UTAD": {
            "phase": "派发候选",
            "confirm_bars": 3,
            "conditions": [
                {"name": "冲高至上沿上方", "metric": "close", "op": ">=", "reference": "resistance_high_band", "window": 1},
                {"name": "量比", "metric": "volume_ratio", "op": ">=", "threshold": 2.0, "window": 5},
                {"name": "连续转弱", "metric": "weaker_closes", "op": ">=", "threshold": 3, "window": 3},
            ],
            "invalidation": None,
        },
    },
}


def params_hash(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def rule_version(spec: dict[str, Any]) -> str:
    return str(spec.get("rule_version") or f"wyckoff-daily-{spec.get('spec_status', 'unfrozen_demo')}")


class _Series:
    """已按 as_of 截断的日线序列；只提供第 i 根及之前的读数。"""

    def __init__(self, rows: list[dict[str, Any]], *, volume_window: int, box_window: int) -> None:
        self.rows = rows
        self.volume_window = volume_window
        self.box_window = box_window

    def __len__(self) -> int:
        return len(self.rows)

    def _value(self, index: int, column: str) -> float | None:
        if not 0 <= index < len(self.rows):
            return None
        value = self.rows[index].get(column)
        return float(value) if value is not None else None

    def close(self, index: int) -> float | None:
        return self._value(index, "close")

    def low(self, index: int) -> float | None:
        return self._value(index, "low")

    def day(self, index: int) -> date:
        return self.rows[index]["date"]

    def volume_ratio(self, index: int) -> float | None:
        """已完成日线的量比：当前量 / 前 N 根均量，不做盘中时间折算。"""
        current = self._value(index, "volume")
        prior = [self._value(j, "volume") for j in range(index - self.volume_window, index)]
        if current is None or len(prior) < self.volume_window or any(v is None for v in prior):
            return None
        mean = sum(prior) / len(prior)  # type: ignore[arg-type]
        return current / mean if mean > 0 else None

    def levels(self, index: int) -> dict[str, float]:
        """第 index 根之前 box_window 根已知的箱体；不含当前 bar。"""
        start = max(0, index - self.box_window)
        lows = [self._value(j, "low") for j in range(start, index)]
        highs = [self._value(j, "high") for j in range(start, index)]
        if len(lows) < self.box_window or any(v is None for v in lows):
            return {}
        if len(highs) < self.box_window or any(v is None for v in highs):
            return {}
        return {"support": min(lows), "resistance": max(highs)}  # type: ignore[arg-type]

    def prior_close_high(self, index: int, bars: int) -> float | None:
        window = [self._value(j, "close") for j in range(index - bars, index)]
        if len(window) < bars or any(v is None for v in window):
            return None
        return max(window)  # type: ignore[arg-type]

    def weaker_close_streak(self, index: int, cap: int) -> int:
        """截至第 index 根连续走低的收盘根数（含当前根），上限 cap；数据不足按 0 处理。"""
        streak = 1
        previous = self._value(index, "close")
        if previous is None:
            return 0
        for offset in range(1, cap):
            current = self._value(index - offset, "close")
            if current is None or previous >= current:
                break
            streak += 1
            previous = current
        return streak


def _reference_value(series: _Series, index: int, reference: str, levels: dict[str, float], anchors: dict[str, float]) -> float | None:
    support = levels.get("support")
    resistance = levels.get("resistance")
    if reference == "support":
        return support
    if reference == "resistance":
        return resistance
    if reference == "resistance_low_band":
        return resistance * 0.995 if resistance is not None else None
    if reference == "resistance_high_band":
        return resistance * 1.02 if resistance is not None else None
    if reference == "spring_low":
        return anchors.get("spring_low")
    if reference == "prior_close_high":
        return series.prior_close_high(index, 3)
    return None


def _matches(op: str, actual: float, limit: float) -> bool:
    if op == ">":
        return actual > limit
    if op == ">=":
        return actual >= limit
    if op == "<":
        return actual < limit
    return actual <= limit


def _evaluate(series: _Series, rule: dict[str, Any], index: int, levels: dict[str, float], anchors: dict[str, float]) -> tuple[bool, list[dict[str, Any]]]:
    """逐条件给出实际值/阈值/窗口；缺数据标为不可计算且不视为满足。"""
    evidence: list[dict[str, Any]] = []
    satisfied = True
    for condition in rule["conditions"]:
        window = f"{condition['window']} 日"
        name = condition["name"]
        op = condition["op"]
        metric = condition["metric"]
        if metric == "close":
            actual = series.close(index)
        elif metric == "low":
            actual = series.low(index)
        elif metric == "volume_ratio":
            actual = series.volume_ratio(index)
        elif metric == "weaker_closes":
            actual = float(series.weaker_close_streak(index, int(condition["threshold"])))
        else:
            actual = None
        unit = " 根" if metric == "weaker_closes" else ""
        if "reference" in condition:
            limit = _reference_value(series, index, condition["reference"], levels, anchors)
        else:
            limit = float(condition["threshold"])
        if actual is None or limit is None:
            evidence.append({
                "name": name,
                "actual": None,
                "threshold": "不可计算",
                "window": window,
                "computable": False,
            })
            satisfied = False
            continue
        evidence.append({
            "name": name,
            "actual": round(actual, 4),
            "threshold": f"{op} {round(limit, 4)}{unit}",
            "window": window,
            "computable": True,
        })
        satisfied = satisfied and _matches(op, actual, limit)
    return satisfied, evidence


def _invalidation_rule_text(rule: dict[str, Any], levels: dict[str, float]) -> str:
    marker = rule.get("invalidation")
    if not marker:
        return "未定义"
    reference = levels.get("pattern_low") if marker["reference"] == "pattern_low" else levels.get(marker["reference"])
    if reference is None:
        return "不可计算"
    tolerance = float(marker["tolerance"])
    limit = reference * (1 - tolerance) if marker["op"] == "<" else reference * (1 + tolerance)
    return f"{marker['name']}：{marker['op']} {round(limit, 2)}（{int(marker['bars'])} 日）"


def _event(
    *,
    sequence: int,
    symbol: str,
    as_of: date,
    meta: dict[str, Any],
    event_type: str,
    phase: str,
    pattern_index: int,
    confirmed_index: int | None,
    series: _Series,
    levels: dict[str, float],
    evidence: list[dict[str, Any]],
    invalidation_rule: str,
    linked_event_id: str | None = None,
    event_id_prefix: str = "wky",
) -> dict[str, Any]:
    pattern_date = series.day(pattern_index)
    confirmed_date = series.day(confirmed_index) if confirmed_index is not None else None
    return {
        "event_id": f"{event_id_prefix}-{sequence:03d}",
        "symbol": symbol,
        "asset_type": ASSET_TYPE,
        "timeframe": TIMEFRAME,
        "rule_version": meta["rule_version"],
        "params_hash": meta["params_hash"],
        "data_generation": meta["data_generation"],
        "as_of": as_of.isoformat(),
        "event_type": event_type,
        "phase": phase,
        "pattern_date": pattern_date.isoformat(),
        "confirmed_at": confirmed_date.isoformat() if confirmed_date else None,
        "available_at": confirmed_date.isoformat() if confirmed_date else None,
        "available_at_basis": "daily_close",
        "status": "confirmed" if confirmed_date else "candidate",
        "evidence": evidence,
        "invalidation_rule": invalidation_rule,
        "levels": levels,
        "linked_event_id": linked_event_id,
    }


def compute_events(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    as_of: date,
    spec: dict[str, Any],
    data_generation: str | None,
) -> dict[str, Any]:
    """逐交易日推进；只用 <= as_of 的输入，输出不携带未来信息。"""
    if any(row["date"] > as_of for row in rows):
        raise ValueError("输入序列必须在 as_of 处截断")

    series = _Series(rows, volume_window=int(spec["volume_window"]), box_window=int(spec["box_window"]))
    meta = {
        "rule_version": rule_version(spec),
        "params_hash": params_hash(spec),
        "data_generation": data_generation,
    }
    warmup = int(spec["warmup_bars"])
    events: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    anchors: dict[str, float] = {}
    spring_index: int | None = None
    sequence = 0

    def next_id() -> int:
        nonlocal sequence
        sequence += 1
        return sequence

    for index in range(warmup, len(series)):
        levels = series.levels(index)

        # 1) 失效检查：对已确认事件逐根比对形态当时冻结的水平，命中即另立事件。
        for done in [item for item in events if item["status"] == "confirmed" and item["event_type"] != "失效"]:
            if any(e["linked_event_id"] == done["event_id"] for e in events):
                continue
            marker = spec["events"][done["event_type"]].get("invalidation")
            if not marker:
                continue
            frozen = done["levels"]
            reference = frozen.get("pattern_low") if marker["reference"] == "pattern_low" else frozen.get(marker["reference"])
            current = series.close(index)
            if reference is None or current is None:
                continue
            limit = reference * (1 - float(marker["tolerance"])) if marker["op"] == "<" else reference * (1 + float(marker["tolerance"]))
            if not _matches(marker["op"], current, limit):
                continue
            events.append(_event(
                sequence=next_id(),
                symbol=symbol,
                as_of=as_of,
                meta=meta,
                event_type="失效",
                phase="事件失效",
                pattern_index=index,
                confirmed_index=index,
                series=series,
                levels=dict(frozen),
                evidence=[{
                    "name": marker["name"],
                    "actual": round(current, 4),
                    "threshold": f"{marker['op']} {round(limit, 4)}",
                    "window": f"{int(marker['bars'])} 日",
                    "computable": True,
                }],
                invalidation_rule="失效事件不再二次失效",
                linked_event_id=done["event_id"],
            ))

        # 2) 推进候选：确认窗口走满才落确认日；确认前破位则撤销候选。
        still_pending: list[dict[str, Any]] = []
        for item in pending:
            rule = spec["events"][item["event_type"]]
            tolerance = rule.get("break_tolerance")
            support = item["levels"].get("support")
            current = series.close(index)
            if tolerance and support is not None and current is not None and current < support * (1 - float(tolerance)):
                continue
            item["held_bars"].append(index)
            if len(item["held_bars"]) >= int(rule["confirm_bars"]):
                event = _event(
                    sequence=next_id(),
                    symbol=symbol,
                    as_of=as_of,
                    meta=meta,
                    event_type=item["event_type"],
                    phase=rule["phase"],
                    pattern_index=item["pattern_index"],
                    confirmed_index=index,
                    series=series,
                    levels=item["levels"],
                    evidence=item["evidence"],
                    invalidation_rule=_invalidation_rule_text(rule, item["levels"]),
                )
                events.append(event)
                if item["event_type"] == "Spring":
                    anchors["spring_low"] = item["levels"]["pattern_low"]
                    spring_index = item["pattern_index"]
            else:
                still_pending.append(item)
        pending = still_pending

        # 3) 新形态：条件全满足才登记；确认窗口未走完前不作为已确认输出。
        for event_type, rule in spec["events"].items():
            if event_type == "Test" and (spring_index is None or index - spring_index > int(spec["box_window"])):
                continue
            if event_type == "LPS" and not any(e["event_type"] == "SOS" and e["status"] == "confirmed" for e in events):
                continue
            if any(e["event_type"] == event_type and e["pattern_date"] == series.day(index).isoformat() for e in events):
                continue
            if any(p["event_type"] == event_type and p["pattern_index"] == index for p in pending):
                continue
            satisfied, evidence = _evaluate(series, rule, index, levels, anchors)
            if not satisfied:
                continue
            pattern_low = series.low(index)
            if pattern_low is None:
                continue
            frozen_levels = {**levels, "pattern_low": pattern_low}
            confirm_bars = int(rule["confirm_bars"])
            if confirm_bars <= 1:
                event = _event(
                    sequence=next_id(),
                    symbol=symbol,
                    as_of=as_of,
                    meta=meta,
                    event_type=event_type,
                    phase=rule["phase"],
                    pattern_index=index,
                    confirmed_index=index,
                    series=series,
                    levels=frozen_levels,
                    evidence=evidence,
                    invalidation_rule=_invalidation_rule_text(rule, frozen_levels),
                )
                events.append(event)
                if event_type == "Spring":
                    anchors["spring_low"] = pattern_low
                    spring_index = index
            else:
                pending.append({
                    "event_type": event_type,
                    "pattern_index": index,
                    "evidence": evidence,
                    "levels": frozen_levels,
                    "held_bars": [],
                })

    candidates = [
        _event(
            sequence=offset,
            symbol=symbol,
            as_of=as_of,
            meta=meta,
            event_type=item["event_type"],
            phase=spec["events"][item["event_type"]]["phase"],
            pattern_index=item["pattern_index"],
            confirmed_index=None,
            series=series,
            levels=item["levels"],
            evidence=item["evidence"],
            invalidation_rule=_invalidation_rule_text(spec["events"][item["event_type"]], item["levels"]),
            event_id_prefix="wky-c",
        )
        for offset, item in enumerate(pending, start=1)
    ]
    return {
        "rule_version": meta["rule_version"],
        "params_hash": meta["params_hash"],
        "spec_status": spec.get("spec_status", "unfrozen_demo"),
        "warmup_bars": warmup,
        "events": events,
        "candidates": candidates,
    }
