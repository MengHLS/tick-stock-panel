"""交易计划与 AI 复盘报告的原子 JSON 存储。

文件位于 data/user_data/extensions/trade_plan/。读写均在实例锁内完成，
写入走临时文件 + os.replace，避免进程中断留下半截 JSON。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

from app.market_time import cn_now

_LOCK = threading.RLock()
_MAX_REPORTS = 30


def _root(data_dir: Path) -> Path:
    return Path(data_dir) / "user_data" / "extensions" / "trade_plan"


def _plans_path(data_dir: Path) -> Path:
    return _root(data_dir) / "plans.json"


def _reports_path(data_dir: Path) -> Path:
    return _root(data_dir) / "ai_reports.json"


def _read_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _atomic_write(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return cn_now().replace(tzinfo=None).isoformat(timespec="seconds")


def _plan_id() -> str:
    return f"tp_{int(time.time() * 1000)}_{secrets.token_hex(3)}"


def list_plans(
    data_dir: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    setup: str | None = None,
    status: str | None = None,
    query: str | None = None,
) -> list[dict]:
    """按计划日、模式、状态和关键词筛选，按计划日倒序返回。"""
    items = _read_list(_plans_path(data_dir))
    q = (query or "").strip().lower()
    result = []
    for plan in items:
        plan_date = str(plan.get("plan_date") or "")
        if start and plan_date < start:
            continue
        if end and plan_date > end:
            continue
        if setup and plan.get("setup") != setup:
            continue
        if status and plan.get("status") != status:
            continue
        if q:
            haystack = " ".join(
                str(plan.get(key) or "")
                for key in ("symbol", "name", "thesis", "trigger", "invalidation", "review")
            ) + " " + " ".join(str(tag) for tag in plan.get("tags") or [])
            if q not in haystack.lower():
                continue
        result.append(plan)
    result.sort(key=lambda p: (str(p.get("plan_date") or ""), str(p.get("created_at") or "")), reverse=True)
    return result


def get_plan(data_dir: Path, plan_id: str) -> dict | None:
    for plan in _read_list(_plans_path(data_dir)):
        if plan.get("id") == plan_id:
            return plan
    return None


def save_plan(data_dir: Path, plan: dict, *, plan_id: str | None = None) -> dict:
    """新增或更新计划。更新时保留原 created_at 并刷新 updated_at。"""
    with _LOCK:
        plans = _read_list(_plans_path(data_dir))
        now = _now()
        if plan_id is not None:
            index = next((i for i, item in enumerate(plans) if item.get("id") == plan_id), None)
            if index is None:
                raise KeyError(plan_id)
            plan["id"] = plan_id
            plan["created_at"] = plans[index].get("created_at") or now
            plans[index] = plan
        else:
            plan["id"] = _plan_id()
            plan["created_at"] = now
            plans.append(plan)
        plan["updated_at"] = now
        plan["version"] = 1
        _atomic_write(_plans_path(data_dir), plans)
        return plan


def delete_plan(data_dir: Path, plan_id: str) -> bool:
    with _LOCK:
        plans = _read_list(_plans_path(data_dir))
        remaining = [item for item in plans if item.get("id") != plan_id]
        if len(remaining) == len(plans):
            return False
        _atomic_write(_plans_path(data_dir), remaining)
        return True


def list_reports(data_dir: Path) -> list[dict]:
    reports = _read_list(_reports_path(data_dir))
    reports.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return reports


def save_report(data_dir: Path, report: dict) -> dict:
    with _LOCK:
        reports = _read_list(_reports_path(data_dir))
        report = dict(report)
        report["id"] = f"tpr_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
        report["created_at"] = _now()
        reports.append(report)
        reports.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        _atomic_write(_reports_path(data_dir), reports[:_MAX_REPORTS])
        return report


def delete_report(data_dir: Path, report_id: str) -> bool:
    with _LOCK:
        reports = _read_list(_reports_path(data_dir))
        remaining = [item for item in reports if item.get("id") != report_id]
        if len(remaining) == len(reports):
            return False
        _atomic_write(_reports_path(data_dir), remaining)
        return True
