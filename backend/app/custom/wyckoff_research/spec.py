"""规则规格装载：优先研究交付的冻结规格，否则回退到内置未冻结演示口径。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .rules import UNFROZEN_DEMO_SPEC

SPEC_SUBPATH = Path("user_data") / "wyckoff_research" / "spec.json"


class SpecError(ValueError):
    """冻结规格存在但无法安全使用。"""


def spec_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / SPEC_SUBPATH


def load_spec(data_dir: str | Path) -> tuple[dict[str, Any], str | None]:
    """返回 (规格, 来源)。来源为 None 表示没有研究规格，使用内置演示口径。"""
    path = spec_path(data_dir)
    if not path.exists():
        return dict(UNFROZEN_DEMO_SPEC), None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"研究规格无法读取: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecError("研究规格必须是 JSON 对象")
    if payload.get("spec_status") != "frozen" or not payload.get("rule_version"):
        raise SpecError("研究规格必须声明 spec_status=frozen 与 rule_version")
    merged = dict(UNFROZEN_DEMO_SPEC)
    merged.update(payload)
    return merged, str(path)


def spec_warnings(spec: dict[str, Any]) -> list[str]:
    """把规格里的必要字段缺失显式暴露给调用方，不静默补齐参数。"""
    missing: list[str] = []
    for key in ("volume_window", "box_window", "warmup_bars"):
        if not isinstance(spec.get(key), int):
            missing.append(key)
    events = spec.get("events")
    if not isinstance(events, dict) or not events:
        missing.append("events")
        return missing
    for name, rule in events.items():
        if not isinstance(rule, dict) or not isinstance(rule.get("conditions"), list) or not rule["conditions"]:
            missing.append(f"events.{name}.conditions")
            continue
        if not isinstance(rule.get("confirm_bars"), int):
            missing.append(f"events.{name}.confirm_bars")
        for position, condition in enumerate(rule["conditions"]):
            path = f"events.{name}.conditions[{position}]"
            if not isinstance(condition, dict):
                missing.append(path)
                continue
            for field in ("name", "metric", "op", "window"):
                if field not in condition:
                    missing.append(f"{path}.{field}")
            if "reference" not in condition and "threshold" not in condition:
                missing.append(f"{path}.reference_or_threshold")
        for position, marker in enumerate([rule.get("invalidation")]):
            if marker is None:
                continue
            if not isinstance(marker, dict) or not all(field in marker for field in ("name", "op", "reference", "tolerance", "bars")):
                missing.append(f"events.{name}.invalidation[{position}]")
    return missing
