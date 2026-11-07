"""Load a completed T74 result while keeping its historical identity explicit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .store import ResearchStoreError, resolve_inbox_file

SUPPORTED_ENTRY_PRICE_BASES = frozenset({"raw", "adjusted"})


@dataclass(frozen=True)
class Baseline:
    baseline_id: str
    label: str
    source: dict[str, Any]
    summary: dict[str, Any]
    trades: tuple[dict[str, Any], ...]
    params: dict[str, Any]


def load_baseline(
    *,
    data_dir: str | Path,
    source_kind: str,
    saved_id: str | None,
    file_name: str | None,
    label: str | None,
    backtest_results: Any = None,
) -> Baseline:
    if source_kind == "saved":
        if not saved_id:
            raise ResearchStoreError("请选择已保存的回测结果")
        if backtest_results is None:
            raise ResearchStoreError("当前运行环境无法读取已保存的回测结果")
        try:
            record = backtest_results.get_saved(saved_id)
        except Exception as exc:
            raise ResearchStoreError("已保存的回测结果不存在或无法读取") from exc
        payload = record.get("result") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            raise ResearchStoreError("已保存结果缺少可读取的回测载荷")
        source = {
            "kind": "saved",
            "saved_id": saved_id,
            "name": record.get("name") if isinstance(record, dict) else None,
        }
        identity_seed = f"saved:{saved_id}"
        default_label = (
            (
                record.get("name")
                or (record.get("meta") or {}).get("strategy_name")
            )
            if isinstance(record, dict)
            else None
        ) or "已保存回测"
    elif source_kind == "file":
        path = resolve_inbox_file(data_dir, file_name or "")
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise ResearchStoreError("基线 JSON 无法读取或解析") from exc
        if not isinstance(payload, dict):
            raise ResearchStoreError("基线 JSON 必须是对象")
        if isinstance(payload.get("result"), dict):
            payload = payload["result"]
        source = {
            "kind": "file",
            "file_name": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        identity_seed = f"file:{source['sha256']}"
        default_label = path.stem
    else:
        raise ResearchStoreError("不支持的基线来源")

    return baseline_from_result_payload(
        payload,
        source=source,
        label=label,
        identity_seed=identity_seed,
        default_label=default_label,
    )


def baseline_from_result_payload(
    payload: dict[str, Any],
    *,
    source: dict[str, Any],
    label: str | None,
    identity_seed: str,
    default_label: str,
) -> Baseline:
    if payload.get("error"):
        raise ResearchStoreError("该回测结果包含错误，不能作为研究基线")
    trades_raw = payload.get("trades")
    if not isinstance(trades_raw, list) or not trades_raw:
        raise ResearchStoreError("基线没有可用的已完成交易记录")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    provenance = (
        payload.get("provenance")
        if isinstance(payload.get("provenance"), dict)
        else {}
    )
    strategy_info = (
        payload.get("strategy_info")
        if isinstance(payload.get("strategy_info"), dict)
        else {}
    )
    trades = _normalize_trades(trades_raw)
    if not trades:
        raise ResearchStoreError("基线交易记录缺少 symbol、entry_date 或 entry_price")
    entry_price_basis = _entry_price_basis(provenance, config)
    stop_loss_pct = _first_finite(
        (provenance.get("execution") or {}).get("stop_loss_pct"),
        (config.get("overrides") or {}).get("stop_loss"),
        strategy_info.get("stop_loss"),
    )
    initial_capital = _first_finite(
        stats.get("initial_capital"),
        config.get("initial_capital"),
    )
    start = _first_text(config.get("start"), (provenance.get("run") or {}).get("start"))
    end = _first_text(config.get("end"), (provenance.get("run") or {}).get("end"))
    params: dict[str, Any] = {}
    if isinstance(provenance.get("params"), dict):
        params.update(provenance["params"])
    if isinstance(config.get("params"), dict):
        params.update(config["params"])
    data_info = provenance.get("data") if isinstance(provenance.get("data"), dict) else {}
    summary = {
        "baseline_id": f"base_{hashlib.sha256(identity_seed.encode()).hexdigest()[:12]}",
        "label": (label or "").strip() or default_label,
        "source": source,
        "strategy_id": (
            config.get("strategy_id")
            or (provenance.get("strategy") or {}).get("id")
            or strategy_info.get("id")
        ),
        "strategy_name": (
            strategy_info.get("name")
            or (provenance.get("strategy") or {}).get("name")
            or default_label
        ),
        "start": start,
        "end": end,
        "initial_capital": initial_capital,
        "trade_count": len(trades),
        "completed_trade_count": stats.get("completed_trade_count"),
        "open_at_end_count": stats.get("open_at_end_count"),
        "stats": {
            key: stats.get(key)
            for key in (
                "total_return",
                "annual_return",
                "max_drawdown",
                "win_rate",
                "n_trades",
                "completed_trade_count",
                "open_at_end_count",
                "final_equity",
                "initial_capital",
                "avg_pnl",
                "avg_win",
                "avg_loss",
                "avg_holding_days",
            )
        },
        "execution": {
            "entry_fill": config.get("entry_fill"),
            "exit_fill": config.get("exit_fill"),
            "entry_price_basis": entry_price_basis,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": _first_finite(
                (provenance.get("execution") or {}).get("take_profit_pct"),
                (config.get("overrides") or {}).get("take_profit"),
                strategy_info.get("take_profit"),
            ),
            "trailing_take_profit_activate_pct": _first_finite(
                (provenance.get("execution") or {}).get(
                    "trailing_take_profit_activate_pct"
                ),
                (config.get("overrides") or {}).get(
                    "trailing_take_profit_activate"
                ),
                strategy_info.get("trailing_take_profit_activate"),
            ),
            "trailing_take_profit_drawdown_pct": _first_finite(
                (provenance.get("execution") or {}).get(
                    "trailing_take_profit_drawdown_pct"
                ),
                (config.get("overrides") or {}).get(
                    "trailing_take_profit_drawdown"
                ),
                strategy_info.get("trailing_take_profit_drawdown"),
            ),
            "max_positions": config.get("max_positions"),
            "holding_days": config.get("holding_days"),
            "position_sizing": config.get("position_sizing"),
        },
        "data": {
            "generation": data_info.get("generation"),
            "generation_source": data_info.get("generation_source"),
            "coverage": data_info.get("coverage"),
            "frozen": data_info.get("frozen"),
            "note": data_info.get("note"),
        },
        "provenance": {
            "algorithm_version": provenance.get("algorithm_version"),
            "app_version": provenance.get("app_version"),
            "definition_sha256": (provenance.get("strategy") or {}).get(
                "definition_sha256"
            ),
        },
        "legacy_config": {
            "event_allowlist_count": _sequence_len(params.get("_event_allowlist")),
            "preclose_gap_count": _mapping_len(params.get("_legacy_preclose_gaps")),
            "corporate_action_gap_count": _mapping_len(
                params.get("_legacy_corporate_action_gaps")
            ),
            "excluded_event_count": _sequence_len(
                params.get("legacy_excluded_events")
            ),
            "param_keys": sorted(params.keys()),
        },
    }
    return Baseline(
        baseline_id=str(summary["baseline_id"]),
        label=str(summary["label"]),
        source=source,
        summary=summary,
        trades=trades,
        params=dict(params),
    )


def _normalize_trades(rows: list[Any]) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip()
        entry_date = _date_text(row.get("entry_date"))
        entry_price = _first_finite(row.get("entry_price"))
        if not symbol or not entry_date or entry_price is None or entry_price <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_date": _date_text(row.get("exit_date")),
                "exit_price": _first_finite(row.get("exit_price")),
                "exit_reason": str(row.get("exit_reason") or ""),
                "pnl_pct": _first_finite(row.get("pnl_pct")),
                "pnl_amount": _first_finite(row.get("pnl_amount")),
                "duration": _first_finite(row.get("duration")),
                "open_at_end": bool(row.get("open_at_end")),
                "entry_score": _first_finite(row.get("entry_score")),
            }
        )
    return tuple(out)


def _entry_price_basis(provenance: dict[str, Any], config: dict[str, Any]) -> str:
    execution = provenance.get("execution")
    if isinstance(execution, dict):
        basis = execution.get("entry_price_basis")
        if basis in SUPPORTED_ENTRY_PRICE_BASES:
            return str(basis)
    overrides = config.get("overrides")
    if isinstance(overrides, dict):
        basis = overrides.get("entry_price_basis")
        if basis in SUPPORTED_ENTRY_PRICE_BASES:
            return str(basis)
    return "raw"


def _date_text(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) >= 10:
        text = value[:10]
        try:
            date.fromisoformat(text)
        except ValueError:
            return None
        return text
    return None


def _first_finite(*values: Any) -> float | None:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sequence_len(value: Any) -> int | None:
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value)
    return None


def _mapping_len(value: Any) -> int | None:
    if isinstance(value, dict):
        return len(value)
    return None
