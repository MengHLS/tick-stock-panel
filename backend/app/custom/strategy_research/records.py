"""Small research ledgers for factor hypotheses and experiment decisions."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .store import (
    ResearchStoreError,
    list_factors,
    new_id,
    read_factor,
    write_factor,
)


def create_factor(
    data_dir: str | Any,
    *,
    factor_key: str,
    name: str,
    version: str | None,
    purpose: str,
    earliest_known_at: str,
    direction: str,
    missing_policy: str,
    hypothesis: str,
    status: str,
    notes: str | None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    factor = {
        "schema_version": 1,
        "factor_id": new_id("fac"),
        "factor_key": factor_key.strip(),
        "name": name.strip(),
        "version": (version or "").strip() or None,
        "purpose": purpose,
        "earliest_known_at": earliest_known_at.strip(),
        "direction": direction.strip(),
        "missing_policy": missing_policy.strip(),
        "hypothesis": hypothesis.strip(),
        "status": status,
        "notes": (notes or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    write_factor(data_dir, factor)
    return factor


def update_factor(
    data_dir: str | Any,
    factor_id: str,
    *,
    status: str | None,
    notes: str | None,
    evidence: str | None,
) -> dict[str, Any]:
    factor = read_factor(data_dir, factor_id)
    if status is not None:
        factor["status"] = status
    if notes is not None:
        factor["notes"] = notes.strip()
    if evidence is not None:
        factor["evidence"] = evidence.strip()
    factor["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    write_factor(data_dir, factor)
    return factor


def get_factor(data_dir: str | Any, factor_id: str) -> dict[str, Any]:
    return read_factor(data_dir, factor_id)


def get_factors(data_dir: str | Any, *, limit: int = 200) -> list[dict[str, Any]]:
    return list_factors(data_dir, limit=limit)


def validate_factor_key(value: str) -> str:
    key = value.strip()
    if not key:
        raise ResearchStoreError("因子标识不能为空")
    return key
