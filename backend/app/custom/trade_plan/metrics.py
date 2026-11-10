"""交易计划执行口径。

所有收益/风险均为“百分比点”（4.0 表示 4%），与前端 fmtPctPoint 对齐。
计划价使用用户填写的原始价，不引入复权/行情推断。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _mid(low: float | None, high: float | None) -> float | None:
    if low is not None and high is not None:
        return (low + high) / 2
    return low if low is not None else high


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def derive_plan(plan: dict) -> dict:
    """返回展示与分析所需的派生指标，不写回持久化数据。"""
    low = _num(plan.get("planned_entry_low"))
    high = _num(plan.get("planned_entry_high"))
    mid = _mid(low, high)
    stop = _num(plan.get("stop_loss"))
    target = _num(plan.get("target_price"))
    entry = _num(plan.get("actual_entry_price"))
    exit_price = _num(plan.get("actual_exit_price"))
    planned_position = _num(plan.get("planned_position_pct"))
    actual_position = _num(plan.get("actual_position_pct"))
    status = str(plan.get("status") or "planned")

    planned_risk_pct = None
    if mid and stop is not None and stop < mid:
        planned_risk_pct = (mid - stop) / mid * 100
    actual_risk_pct = None
    if entry and stop is not None and stop < entry:
        actual_risk_pct = (entry - stop) / entry * 100
    planned_rr = None
    if mid and target is not None and target > mid and planned_risk_pct:
        planned_rr = (target - mid) / mid * 100 / planned_risk_pct

    entry_deviation_pct = None
    if entry is not None and mid:
        entry_deviation_pct = (entry - mid) / mid * 100
    chase_pct = None
    if entry is not None and high and entry > high:
        chase_pct = (entry - high) / high * 100

    pnl_pct = None
    if entry and exit_price:
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = _num(plan.get("manual_pnl_pct"))

    risk_for_r = actual_risk_pct if actual_risk_pct else planned_risk_pct
    r_multiple = pnl_pct / risk_for_r if pnl_pct is not None and risk_for_r else None

    entry_in_plan = None
    if entry is not None and low is not None and high is not None:
        entry_in_plan = low <= entry <= high

    position_in_plan = None
    if actual_position is not None and planned_position is not None and planned_position > 0:
        position_in_plan = actual_position <= planned_position * 1.2 + 1e-9

    stop_respected = None
    exit_reason = str(plan.get("exit_reason") or "")
    if exit_price is not None and stop is not None:
        # 允许千分之五的报价/滑点容差，显著跌破止损视为纪律失败。
        stop_respected = True if exit_reason == "stop" else exit_price >= stop * 0.995

    checks: list[bool] = []
    if status in ("entered", "exited"):
        checks.append(stop is not None)
    if entry_in_plan is not None:
        checks.append(bool(entry_in_plan))
    if position_in_plan is not None:
        checks.append(bool(position_in_plan))
    if stop_respected is not None:
        checks.append(bool(stop_respected))
    discipline_score = round(sum(checks) / len(checks) * 100) if checks else None

    entry_dt = _parse_dt(plan.get("entry_at"))
    exit_dt = _parse_dt(plan.get("exit_at"))
    hold_minutes = None
    if entry_dt and exit_dt and exit_dt >= entry_dt:
        hold_minutes = round((exit_dt - entry_dt).total_seconds() / 60)

    return {
        "planned_entry_mid": _round(mid, 3),
        "planned_risk_pct": _round(planned_risk_pct),
        "actual_risk_pct": _round(actual_risk_pct),
        "planned_rr": _round(planned_rr),
        "entry_deviation_pct": _round(entry_deviation_pct),
        "chase_pct": _round(chase_pct),
        "pnl_pct": _round(pnl_pct),
        "r_multiple": _round(r_multiple),
        "entry_in_plan": entry_in_plan,
        "position_in_plan": position_in_plan,
        "stop_respected": stop_respected,
        "discipline_score": discipline_score,
        "hold_minutes": hold_minutes,
    }


def with_metrics(plan: dict) -> dict:
    metrics = derive_plan(plan)
    return {**plan, "metrics": metrics, "flags": derive_flags(plan, metrics)}


def derive_flags(plan: dict, metrics: dict) -> list[dict]:
    stop = _num(plan.get("stop_loss"))
    status = str(plan.get("status") or "planned")
    flags: list[dict] = []
    if status in ("entered", "exited") and stop is None:
        flags.append({"code": "no_stop", "label": "未设止损", "tone": "danger"})
    chase_pct = metrics.get("chase_pct")
    if chase_pct is not None and chase_pct > 0.3:
        flags.append({"code": "chase", "label": "追高入场", "tone": "danger"})
    elif (
        _num(plan.get("actual_entry_price")) is not None
        and _num(plan.get("planned_entry_low")) is not None
        and _num(plan.get("actual_entry_price")) < _num(plan.get("planned_entry_low"))
    ):
        flags.append({"code": "below_plan", "label": "低于计划价", "tone": "info"})
    if metrics.get("stop_respected") is False:
        flags.append({"code": "stop_breach", "label": "跌破止损未离场", "tone": "danger"})
    if metrics.get("position_in_plan") is False:
        flags.append({"code": "oversize", "label": "仓位超计划", "tone": "warn"})
    if status == "missed":
        flags.append({"code": "missed", "label": "未执行", "tone": "muted"})
    if status == "exited" and not str(plan.get("review") or "").strip():
        flags.append({"code": "no_review", "label": "未写复盘", "tone": "muted"})
    return flags


def summarize(plans: list[dict]) -> dict:
    """按已筛选计划计算执行统计。未结束计划只计执行率，不计胜率/收益。"""
    rows = [with_metrics(plan) for plan in plans]
    closed = [row for row in rows if row["metrics"].get("pnl_pct") is not None]
    executed = [row for row in rows if row.get("status") in ("entered", "exited")]
    eligible = [row for row in rows if row.get("status") != "cancelled"]
    wins = [row for row in closed if (row["metrics"].get("pnl_pct") or 0) > 0]
    losses = [row for row in closed if (row["metrics"].get("pnl_pct") or 0) < 0]
    pnls = [float(row["metrics"]["pnl_pct"]) for row in closed]
    rs = [float(row["metrics"]["r_multiple"]) for row in closed if row["metrics"].get("r_multiple") is not None]
    discipline = [
        float(row["metrics"]["discipline_score"])
        for row in rows
        if row["metrics"].get("discipline_score") is not None
    ]
    win_sum = sum(float(row["metrics"]["pnl_pct"]) for row in wins)
    loss_sum = abs(sum(float(row["metrics"]["pnl_pct"]) for row in losses))

    flag_counts: dict[str, dict] = {}
    for row in rows:
        for flag in row["flags"]:
            item = flag_counts.setdefault(
                flag["code"], {"code": flag["code"], "label": flag["label"], "tone": flag["tone"], "count": 0}
            )
            item["count"] += 1

    return {
        "total": len(rows),
        "planned": sum(1 for row in rows if row.get("status") == "planned"),
        "entered": sum(1 for row in rows if row.get("status") == "entered"),
        "exited": sum(1 for row in rows if row.get("status") == "exited"),
        "missed": sum(1 for row in rows if row.get("status") == "missed"),
        "cancelled": sum(1 for row in rows if row.get("status") == "cancelled"),
        "executed": len(executed),
        "execution_rate": _round(len(executed) / len(eligible) * 100) if eligible else None,
        "closed": len(closed),
        "win_rate": _round(len(wins) / len(closed) * 100) if closed else None,
        "avg_pnl_pct": _round(sum(pnls) / len(pnls)) if pnls else None,
        "total_pnl_pct": _round(sum(pnls)) if pnls else None,
        "avg_r": _round(sum(rs) / len(rs)) if rs else None,
        "total_r": _round(sum(rs)) if rs else None,
        "avg_win_pct": _round(win_sum / len(wins)) if wins else None,
        "avg_loss_pct": _round(-loss_sum / len(losses)) if losses else None,
        "profit_factor": _round(win_sum / loss_sum) if loss_sum > 0 else None,
        "discipline_score": _round(sum(discipline) / len(discipline)) if discipline else None,
        "chase_count": sum(1 for row in rows if any(flag["code"] == "chase" for flag in row["flags"])),
        "stop_breach_count": sum(
            1 for row in rows if any(flag["code"] == "stop_breach" for flag in row["flags"])
        ),
        "flag_counts": sorted(flag_counts.values(), key=lambda item: (-item["count"], item["code"])),
        "by_setup": _group(closed, executed, "setup"),
        "by_mood": _group(closed, executed, "market_mood"),
        "equity_curve": _equity_curve(closed),
    }


def _group(closed: list[dict], executed: list[dict], field: str) -> list[dict]:
    keys = sorted({str(row.get(field) or "other") for row in executed + closed})
    result = []
    for key in keys:
        group_closed = [row for row in closed if str(row.get(field) or "other") == key]
        group_executed = [row for row in executed if str(row.get(field) or "other") == key]
        pnls = [float(row["metrics"]["pnl_pct"]) for row in group_closed]
        rs = [
            float(row["metrics"]["r_multiple"])
            for row in group_closed
            if row["metrics"].get("r_multiple") is not None
        ]
        result.append(
            {
                "key": key,
                "count": len(group_executed),
                "closed": len(group_closed),
                "win_rate": _round(
                    sum(1 for pnl in pnls if pnl > 0) / len(pnls) * 100
                ) if pnls else None,
                "avg_pnl_pct": _round(sum(pnls) / len(pnls)) if pnls else None,
                "avg_r": _round(sum(rs) / len(rs)) if rs else None,
            }
        )
    result.sort(key=lambda item: (-item["count"], -item["closed"], item["key"]))
    return result


def _equity_curve(closed: list[dict]) -> list[dict]:
    ordered = sorted(
        closed,
        key=lambda row: (str(row.get("exit_at") or row.get("plan_date") or ""), str(row.get("id") or "")),
    )
    cumulative = 0.0
    curve = []
    for row in ordered:
        pnl = float(row["metrics"]["pnl_pct"])
        cumulative += pnl
        curve.append(
            {
                "date": str(row.get("exit_at") or row.get("plan_date") or "")[:10],
                "symbol": row.get("symbol") or "",
                "pnl_pct": _round(pnl),
                "cum_pct": _round(cumulative),
            }
        )
    return curve
