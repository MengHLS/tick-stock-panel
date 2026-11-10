"""SQLite persistence for imported fills, per-trade notes, and cached analysis."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    trade_time TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('B', 'S')),
    qty INTEGER NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    cash_flow REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    other_fee REAL NOT NULL DEFAULT 0,
    stamp_tax REAL NOT NULL DEFAULT 0,
    transfer_fee REAL NOT NULL DEFAULT 0,
    deal_no TEXT NOT NULL DEFAULT '',
    cash_balance REAL,
    source_file TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_symbol_time ON fills(symbol, trade_date, trade_time);
CREATE TABLE IF NOT EXISTS trade_notes (
    trade_key TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_cache (
    trade_key TEXT PRIMARY KEY,
    analysis TEXT NOT NULL,
    analysis_version INTEGER NOT NULL,
    computed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def root(data_dir: Path | str) -> Path:
    path = Path(data_dir) / "user_data" / "trade_analysis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect(data_dir: Path | str) -> sqlite3.Connection:
    path = root(data_dir) / "ledger.sqlite"
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def insert_fills(data_dir: Path | str, rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    inserted = 0
    duplicates = 0
    with _LOCK, _connect(data_dir) as conn:
        for row in rows:
            try:
                conn.execute(
                    """
                    INSERT INTO fills (
                        id, trade_date, trade_time, symbol, name, side, qty, price,
                        amount, cash_flow, commission, other_fee, stamp_tax,
                        transfer_fee, deal_no, cash_balance, source_file, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"], row["trade_date"], row["trade_time"], row["symbol"],
                        row["name"], row["side"], row["qty"], row["price"],
                        row["amount"], row["cash_flow"], row["commission"],
                        row["other_fee"], row["stamp_tax"], row["transfer_fee"],
                        row["deal_no"], row.get("cash_balance"), row["source_file"],
                        row["imported_at"],
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                duplicates += 1
        if inserted:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('last_import_at', ?)",
                (_now(),),
            )
    return inserted, duplicates


def list_fills(data_dir: Path | str) -> list[dict[str, Any]]:
    with _LOCK, _connect(data_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM fills ORDER BY trade_date, trade_time, id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_notes(data_dir: Path | str) -> dict[str, dict[str, Any]]:
    with _LOCK, _connect(data_dir) as conn:
        rows = conn.execute("SELECT * FROM trade_notes").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            tags = json.loads(row["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        result[row["trade_key"]] = {
            "note": row["note"],
            "tags": tags if isinstance(tags, list) else [],
            "updated_at": row["updated_at"],
        }
    return result


def save_note(
    data_dir: Path | str,
    trade_key: str,
    *,
    note: str,
    tags: list[str] | None,
) -> dict[str, Any]:
    clean_tags = [str(tag).strip()[:24] for tag in (tags or []) if str(tag).strip()][:8]
    now = _now()
    with _LOCK, _connect(data_dir) as conn:
        conn.execute(
            """
            INSERT INTO trade_notes(trade_key, note, tags, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trade_key) DO UPDATE SET
                note = excluded.note,
                tags = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (trade_key, note[:4000], json.dumps(clean_tags, ensure_ascii=False), now),
        )
    return {"note": note[:4000], "tags": clean_tags, "updated_at": now}


def get_analysis(data_dir: Path | str) -> dict[str, dict[str, Any]]:
    with _LOCK, _connect(data_dir) as conn:
        rows = conn.execute("SELECT * FROM analysis_cache").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row["analysis"])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload["_version"] = row["analysis_version"]
            payload["_computed_at"] = row["computed_at"]
            result[row["trade_key"]] = payload
    return result


def save_analysis(
    data_dir: Path | str,
    values: dict[str, dict[str, Any]],
    version: int,
) -> None:
    if not values:
        return
    now = _now()
    with _LOCK, _connect(data_dir) as conn:
        conn.executemany(
            """
            INSERT INTO analysis_cache(trade_key, analysis, analysis_version, computed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trade_key) DO UPDATE SET
                analysis = excluded.analysis,
                analysis_version = excluded.analysis_version,
                computed_at = excluded.computed_at
            """,
            [
                (key, json.dumps(value, ensure_ascii=False, allow_nan=False), version, now)
                for key, value in values.items()
            ],
        )


def clear_analysis(data_dir: Path | str) -> None:
    with _LOCK, _connect(data_dir) as conn:
        conn.execute("DELETE FROM analysis_cache")


def get_meta(data_dir: Path | str) -> dict[str, str]:
    with _LOCK, _connect(data_dir) as conn:
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_meta(data_dir: Path | str, key: str, value: str) -> None:
    with _LOCK, _connect(data_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, value),
        )
