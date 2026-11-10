"""事件快照磁盘缓存：键绑定数据 generation 与规则指纹，换代自动失效。

只缓存 ``ready`` 结果。缓存损坏、字段不匹配或读写失败都按未命中处理，
计算本身仍然 fail-closed，不因缓存问题返回假确认。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

CACHE_VERSION = 1
CACHE_SUBPATH = Path("user_data") / "wyckoff_research" / "cache"
MAX_ENTRIES = 2000
MAX_AGE_DAYS = 30

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def cache_root(data_dir: str | Path) -> Path:
    return Path(data_dir) / CACHE_SUBPATH


def _safe(value: str) -> str:
    return _UNSAFE.sub("_", value).strip("_") or "na"


def _file_name(
    *,
    symbol: str,
    as_of: date,
    window: int,
    rule_version: str,
    params_hash: str,
    generation: str,
) -> str:
    parts = [
        _safe(symbol),
        as_of.isoformat(),
        str(window),
        _safe(rule_version),
        _safe(params_hash),
        _safe(generation),
    ]
    return "__".join(parts) + ".json"


def read(
    data_dir: str | Path,
    *,
    symbol: str,
    as_of: date,
    window: int,
    rule_version: str,
    params_hash: str,
    generation: str,
) -> dict[str, Any] | None:
    path = cache_root(data_dir) / _file_name(
        symbol=symbol,
        as_of=as_of,
        window=window,
        rule_version=rule_version,
        params_hash=params_hash,
        generation=generation,
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expected = {
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "window_bars": window,
        "rule_version": rule_version,
        "params_hash": params_hash,
        "data_generation": generation,
        "status": "ready",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return None
    if not isinstance(payload.get("events"), list):
        return None
    if payload.get("cache_version") != CACHE_VERSION:
        return None
    payload.pop("cache_version", None)
    payload.pop("cached_at", None)
    return payload


def write(
    data_dir: str | Path,
    *,
    payload: dict[str, Any],
    symbol: str,
    as_of: date,
    window: int,
    rule_version: str,
    params_hash: str,
    generation: str,
) -> None:
    """原子写入；任何失败只放弃缓存，不影响本次结果。"""
    root = cache_root(data_dir)
    path = root / _file_name(
        symbol=symbol,
        as_of=as_of,
        window=window,
        rule_version=rule_version,
        params_hash=params_hash,
        generation=generation,
    )
    body = {
        **payload,
        "cache_version": CACHE_VERSION,
        "cached_at": int(time.time()),
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return
    _prune(root)


def _prune(root: Path) -> None:
    """按天数和条数上限清理旧快照；失败忽略。"""
    try:
        files = [item for item in root.glob("*.json") if item.is_file()]
    except OSError:
        return
    cutoff = time.time() - MAX_AGE_DAYS * 86400
    for item in files:
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
        except OSError:
            continue
    remaining = [item for item in files if item.exists()]
    if len(remaining) <= MAX_ENTRIES:
        return
    remaining.sort(key=lambda item: item.stat().st_mtime)
    for item in remaining[: len(remaining) - MAX_ENTRIES]:
        try:
            item.unlink(missing_ok=True)
        except OSError:
            continue
