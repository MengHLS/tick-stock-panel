"""Atomic, mtime-cached persistence for user-defined stock themes."""
from __future__ import annotations

import json
import logging
import re
import threading
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl

from app.extensions.contracts import MarketDataRead
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

STORE_VERSION = 1
MAX_THEMES = 100
MAX_SYMBOLS_PER_THEME = 500
SYMBOL_RE = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")
THEME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_COLOR = "#F59E0B"
PALETTE = (
    "#F59E0B",
    "#22D3EE",
    "#FB7185",
    "#A78BFA",
    "#A3E635",
    "#60A5FA",
    "#FB923C",
    "#34D399",
)

_cache: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}
_cache_lock = threading.Lock()
_mutation_lock = threading.RLock()


class ThemeStoreError(ValueError):
    """The existing theme store cannot be safely overwritten."""


def _serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with _mutation_lock:
            return function(*args, **kwargs)

    return wrapper


def empty_document() -> dict[str, Any]:
    return {"version": STORE_VERSION, "themes": []}


def normalize_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
        if len(result) >= MAX_SYMBOLS_PER_THEME:
            break
    return result


def _path(data_dir: Path | str) -> Path:
    return Path(data_dir) / "user_data" / "theme_analyzer" / "themes.json"


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sanitize_theme(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    theme_id = str(raw.get("id") or "").strip()
    if not THEME_ID_RE.fullmatch(theme_id):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    color = str(raw.get("color") or DEFAULT_COLOR)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = PALETTE[index % len(PALETTE)]
    symbols = raw.get("symbols")
    if not isinstance(symbols, list):
        symbols = []
    return {
        "id": theme_id,
        "name": name[:40],
        "description": str(raw.get("description") or "").strip()[:300],
        "color": color.upper(),
        "symbols": normalize_symbols([str(item) for item in symbols]),
        "industry_source": raw.get("industry_source") or {},
        "excluded_symbols": normalize_symbols(raw.get("excluded_symbols") or []),
        "created_at": str(raw.get("created_at") or _now_iso()),
        "updated_at": str(raw.get("updated_at") or raw.get("created_at") or _now_iso()),
    }


def _sanitize_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("version") != STORE_VERSION:
        return empty_document()
    themes = raw.get("themes")
    if not isinstance(themes, list):
        return empty_document()
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(themes):
        theme = _sanitize_theme(item, index)
        if theme is None or theme["id"] in seen:
            continue
        seen.add(theme["id"])
        clean.append(theme)
        if len(clean) >= MAX_THEMES:
            break
    return {"version": STORE_VERSION, "themes": clean}


def load_document(data_dir: Path | str) -> dict[str, Any]:
    path = _path(data_dir)
    signature = _signature(path)
    if signature is None:
        return empty_document()
    with _cache_lock:
        cached = _cache.get(path)
        if cached is not None and cached[0] == signature:
            return deepcopy(cached[1])
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("theme analyzer store read failed: %s", exc)
        return empty_document()
    document = _sanitize_document(raw)
    with _cache_lock:
        _cache[path] = (signature, deepcopy(document))
    return document


def _load_document_strict(data_dir: Path | str) -> dict[str, Any]:
    """Read for a mutation: existing corruption or version drift must fail closed."""
    path = _path(data_dir)
    if not path.exists():
        return empty_document()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ThemeStoreError("主题文件损坏或不可读，已拒绝覆盖") from exc
    if not isinstance(raw, dict) or raw.get("version") != STORE_VERSION:
        raise ThemeStoreError("主题文件版本不兼容，已拒绝覆盖")
    themes = raw.get("themes")
    if not isinstance(themes, list):
        raise ThemeStoreError("主题文件内容损坏，已拒绝覆盖")
    if len(themes) > MAX_THEMES:
        raise ThemeStoreError("主题数量超过上限，已拒绝覆盖")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(themes):
        theme = _sanitize_theme(item, index)
        if theme is None or theme["id"] in seen:
            raise ThemeStoreError("主题文件内容损坏，已拒绝覆盖")
        seen.add(theme["id"])
        clean.append(theme)
    return {"version": STORE_VERSION, "themes": clean}


def _get_theme_strict(data_dir: Path | str, theme_id: str) -> dict[str, Any] | None:
    for theme in _load_document_strict(data_dir)["themes"]:
        if theme["id"] == theme_id:
            return deepcopy(theme)
    return None


def save_document(data_dir: Path | str, document: dict[str, Any]) -> None:
    path = _path(data_dir)
    clean = _sanitize_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True),
    )
    with _cache_lock:
        signature = _signature(path)
        if signature is not None:
            _cache[path] = (signature, deepcopy(clean))


def list_themes(data_dir: Path | str) -> list[dict[str, Any]]:
    return list(load_document(data_dir)["themes"])


def get_theme(data_dir: Path | str, theme_id: str) -> dict[str, Any] | None:
    for theme in load_document(data_dir)["themes"]:
        if theme["id"] == theme_id:
            return deepcopy(theme)
    return None


@_serialized
def create_theme(
    data_dir: Path | str,
    *,
    name: str,
    description: str = "",
    color: str = DEFAULT_COLOR,
    symbols: list[str] | None = None,
    industry_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = _load_document_strict(data_dir)
    if len(document["themes"]) >= MAX_THEMES:
        raise ValueError(f"主题数量最多 {MAX_THEMES} 个")
    now = _now_iso()
    theme = {
        "id": f"theme-{uuid4().hex[:10]}",
        "name": name.strip()[:40],
        "description": description.strip()[:300],
        "color": color.upper(),
        "symbols": normalize_symbols(symbols or []),
        "industry_source": deepcopy(industry_source or {}),
        "excluded_symbols": [],
        "created_at": now,
        "updated_at": now,
    }
    document["themes"].insert(0, theme)
    save_document(data_dir, document)
    return deepcopy(theme)


@_serialized
def update_theme(
    data_dir: Path | str,
    theme_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
    symbols: list[str] | None = None,
    industry_source: dict[str, Any] | None = None,
    excluded_symbols: list[str] | None = None,
) -> dict[str, Any] | None:
    document = _load_document_strict(data_dir)
    for index, current in enumerate(document["themes"]):
        if current["id"] != theme_id:
            continue
        updated = deepcopy(current)
        if name is not None:
            updated["name"] = name.strip()[:40]
        if description is not None:
            updated["description"] = description.strip()[:300]
        if color is not None:
            updated["color"] = color.upper()
        if symbols is not None:
            updated["symbols"] = normalize_symbols(symbols)
        if industry_source is not None:
            updated["industry_source"] = deepcopy(industry_source)
        if excluded_symbols is not None:
            updated["excluded_symbols"] = normalize_symbols(excluded_symbols)
        updated["updated_at"] = _now_iso()
        document["themes"][index] = updated
        save_document(data_dir, document)
        return deepcopy(updated)
    return None


@_serialized
def delete_theme(data_dir: Path | str, theme_id: str) -> bool:
    document = _load_document_strict(data_dir)
    remaining = [theme for theme in document["themes"] if theme["id"] != theme_id]
    if len(remaining) == len(document["themes"]):
        return False
    document["themes"] = remaining
    save_document(data_dir, document)
    return True


@_serialized
def add_symbols(
    data_dir: Path | str,
    theme_id: str,
    symbols: list[str],
    *,
    inherited_symbols: list[str] | None = None,
) -> dict[str, Any] | None:
    theme = _get_theme_strict(data_dir, theme_id)
    if theme is None:
        return None
    inherited = set(inherited_symbols or [])
    merged = normalize_symbols([*theme["symbols"], *(symbol for symbol in symbols if symbol not in inherited)])
    return update_theme(
        data_dir, theme_id, symbols=merged,
        excluded_symbols=[item for item in theme.get("excluded_symbols", []) if item not in symbols],
    )


@_serialized
def remove_symbol(
    data_dir: Path | str,
    theme_id: str,
    symbol: str,
    *,
    inherited: bool = False,
) -> tuple[dict[str, Any] | None, bool]:
    theme = _get_theme_strict(data_dir, theme_id)
    if theme is None:
        return None, False
    target = symbol.strip().upper()
    remaining = [item for item in theme["symbols"] if item != target]
    if len(remaining) == len(theme["symbols"]) and not inherited:
        return theme, False
    updated = update_theme(
        data_dir, theme_id, symbols=remaining,
        excluded_symbols=[*theme.get("excluded_symbols", []), target] if inherited else None,
    )
    return updated, True


@_serialized
def seed_default_theme(data_dir: Path | str, market_data: MarketDataRead) -> dict[str, Any] | None:
    """Seed the current name-theme once; never revive a theme the user deleted."""

    root = Path(data_dir) / "user_data" / "theme_analyzer"
    marker = root / ".seeded"
    if marker.exists() or _path(data_dir).exists():
        return None
    try:
        instruments = market_data.get_instruments("stock")
    except Exception as exc:  # noqa: BLE001 - seeding must not block startup
        logger.warning("theme analyzer seed skipped: %s", exc)
        return None
    if instruments.is_empty() or "name" not in instruments.columns:
        return None
    names = instruments.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("name").cast(pl.Utf8),
    ).filter(pl.col("name").str.contains("阳|洋|羊"))
    symbols = normalize_symbols(names["symbol"].to_list())
    document = empty_document()
    now = _now_iso()
    document["themes"].append({
        "id": "yang",
        "name": "阳 / 洋 / 羊",
        "description": "名称含阳、洋、羊的股票池。可继续增删股票，并用于任意主题的同类分析。",
        "color": DEFAULT_COLOR,
        "symbols": symbols,
        "created_at": now,
        "updated_at": now,
    })
    save_document(data_dir, document)
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, now)
    return deepcopy(document["themes"][0])

