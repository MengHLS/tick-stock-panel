"""As-of consistency and future-perturbation checks for historical first-board labels.

Scope of this script (deliberately narrow):
1. Verify the frozen snapshot hashes match the manifest.
2. For every first board D in the frozen snapshot, recompute the production
   event-chain kernel on the prefix ending at D and compare with the value the
   kernel produced when run once over the whole series.
3. Re-run the whole series after fabricating future data after D (new first
   boards / extreme highs / extreme lows) and compare the label AT D.
4. Emit a machine-readable report listing every compared field.

It does NOT certify the new classification rules, factor snapshots, or
first-board identity. Those stay separate.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_asof_consistency.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
REPO = DRAFT.parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.factors.event_chain import (  # noqa: E402
    EVENT_CHAIN_FIELDS,
    DEFAULT_EVENT_CHAIN_CONFIG,
    compute_event_chain_outputs,
)

PATHS_CSV = DRAFT / "four-case-paths.csv"
EVENTS_CSV = DRAFT / "four-case-events.csv"
MANIFEST = DRAFT / "four-case-manifest.json"
KERNEL = BACKEND / "app" / "factors" / "event_chain.py"
OUT_JSON = HERE / "asof-consistency-report.json"
OUT_MD = HERE / "ASOF-CONSISTENCY.md"

FIELD_LIST = list(EVENT_CHAIN_FIELDS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def series_for(rows: list[dict[str, str]]) -> dict[str, np.ndarray]:
    def column(name: str) -> np.ndarray:
        return np.array([float(row[name]) for row in rows], dtype=np.float64).reshape(-1, 1)

    return {
        "open": column("open"),
        "high": column("high"),
        "low": column("low"),
        "close": column("close"),
        "consecutive_limit_ups": column("consecutive_limit_ups"),
    }


def run_kernel(data: dict[str, np.ndarray], stopper_after: int | None = None) -> dict[str, np.ndarray]:
    cut = slice(None, None if stopper_after is None else stopper_after)
    return compute_event_chain_outputs(
        data["open"][cut],
        data["high"][cut],
        data["low"][cut],
        data["close"][cut],
        data["consecutive_limit_ups"][cut],
    )


def same(a: float, b: float) -> bool:
    if np.isnan(a) and np.isnan(b):
        return True
    return float(a) == float(b)


def perturb(data: dict[str, np.ndarray], index: int, mode: str) -> dict[str, np.ndarray]:
    """Fabricate future data strictly after ``index``; nothing at or before changes."""
    out = {key: value.copy() for key, value in data.items()}
    stop = min(index + 6, len(out["close"]))
    for j in range(index + 1, stop):
        if mode in {"future_board", "future_board_extreme"}:
            out["consecutive_limit_ups"][j, 0] = 1.0
        if mode in {"future_extreme", "future_board_extreme"}:
            # A huge later high and a deep later low: the two shapes that would
            # move a P/L anchored on "some later extreme" if the kernel leaked.
            out["high"][j, 0] = data["high"][j, 0] * 3.0
            out["low"][j, 0] = data["low"][j, 0] * 0.3
            out["close"][j, 0] = data["close"][j, 0] * 2.5
            out["open"][j, 0] = data["open"][j, 0] * 2.5
    return out


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = read_rows(PATHS_CSV)
    events = read_rows(EVENTS_CSV)

    hashes = {
        "four-case-paths.csv": sha256(PATHS_CSV),
        "four-case-events.csv": sha256(EVENTS_CSV),
        "event_chain.py": sha256(KERNEL),
        "verify_asof_consistency.py": sha256(Path(__file__).resolve()),
    }
    hash_checks = {
        name: hashes[name] == manifest["artifacts"][name]["sha256"]
        for name in ("four-case-paths.csv", "four-case-events.csv")
    }
    row_checks = {
        "four-case-paths.csv": len(rows) == manifest["artifacts"]["four-case-paths.csv"]["rows"],
        "four-case-events.csv": len(events) == manifest["artifacts"]["four-case-events.csv"]["rows"],
    }

    by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append(row)
    for symbol_rows in by_symbol.values():
        symbol_rows.sort(key=lambda item: item["date"])

    date_index = {
        symbol: {row["date"]: i for i, row in enumerate(symbol_rows)}
        for symbol, symbol_rows in by_symbol.items()
    }

    comparison_rows: list[dict[str, object]] = []
    asof_mismatches = 0
    perturbation_rows: list[dict[str, object]] = []
    perturbation_mismatches = 0

    for symbol, symbol_rows in by_symbol.items():
        data = series_for(symbol_rows)
        batch = run_kernel(data)
        event_dates = [event["date"] for event in events if event["symbol"] == symbol]
        for date in event_dates:
            index = date_index[symbol].get(date)
            if index is None:
                raise SystemExit(f"event date {date} for {symbol} missing from frozen paths")
            prefix = run_kernel(data, stopper_after=index + 1)
            record = {
                "symbol": symbol,
                "date": date,
                "stage_batch": None if np.isnan(batch["first_board_chain_stage"][index, 0])
                else int(batch["first_board_chain_stage"][index, 0]),
                "stage_asof": None if np.isnan(prefix["first_board_chain_stage"][index, 0])
                else int(prefix["first_board_chain_stage"][index, 0]),
                "fields_compared": len(FIELD_LIST),
                "mismatched_fields": [],
            }
            for field in FIELD_LIST:
                a = batch[field][index, 0]
                b = prefix[field][index, 0]
                if not same(a, b):
                    record["mismatched_fields"].append(
                        {"field": field, "batch": None if np.isnan(a) else float(a),
                         "asof": None if np.isnan(b) else float(b)}
                    )
                    asof_mismatches += 1
            comparison_rows.append(record)

            for mode in ("future_board", "future_extreme", "future_board_extreme"):
                perturbed = run_kernel(perturb(data, index, mode))
                for field in FIELD_LIST:
                    a = batch[field][index, 0]
                    b = perturbed[field][index, 0]
                    if not same(a, b):
                        perturbation_rows.append(
                            {"symbol": symbol, "date": date, "mode": mode, "field": field,
                             "batch": None if np.isnan(a) else float(a),
                             "perturbed": None if np.isnan(b) else float(b)}
                        )
                        perturbation_mismatches += 1

    dividend_rows = []
    for symbol, symbol_rows in by_symbol.items():
        differing = sum(
            1 for row in symbol_rows if abs(float(row["close"]) - float(row["raw_close"])) > 1e-9
        )
        dividend_rows.append({"symbol": symbol, "rows_where_adjusted_differs_from_raw": differing})

    total_fields = len(comparison_rows) * len(FIELD_LIST)
    perturbations = len(comparison_rows) * 3 * len(FIELD_LIST)
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "kernel": "app.factors.event_chain.compute_event_chain_outputs",
            "kernel_config": {
                "lookback_bars": DEFAULT_EVENT_CHAIN_CONFIG.lookback_bars,
                "min_pullback_pct": DEFAULT_EVENT_CHAIN_CONFIG.min_pullback_pct,
                "require_new_high_after_anchor": DEFAULT_EVENT_CHAIN_CONFIG.require_new_high_after_anchor,
            },
            "events": len(comparison_rows),
            "symbols": sorted(by_symbol),
            "fields": FIELD_LIST,
            "perturbation_range": "5 个交易日，位于事件日之后且不含事件日本身",
            "perturbation_modes": ["future_board", "future_extreme", "future_board_extreme"],
            "not_covered": [
                "new classification rules (P/L/path-state) - event table not delivered at run time",
                "factor snapshots",
                "first-board identity / historical ST / board regime",
                "adjusted-vs-raw basis comparison on this basket (no ex-rights inside these windows)",
            ],
        },
        "inputs": {
            "data_snapshot": manifest["source"],
            "snapshot_upper_date": manifest["snapshot_upper_date"],
            "frozen_files": hashes,
            "manifest_hash_checks": hash_checks,
            "row_count_checks": row_checks,
        },
        "asof_truncation": {
            "fields_compared": total_fields,
            "mismatches": asof_mismatches,
            "per_event": comparison_rows,
        },
        "future_perturbation": {
            "comparisons": perturbations,
            "mismatches": perturbation_mismatches,
            "details": perturbation_rows,
        },
        "adjusted_vs_raw_coverage": dividend_rows,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 首板历史标签·截断一致性与未来扰动检查",
        "",
        f"生成时间：{report['generated']}",
        "",
        "## 口径",
        "",
        f"- 内核：`app.factors.event_chain.compute_event_chain_outputs`"
        f"（lookback={DEFAULT_EVENT_CHAIN_CONFIG.lookback_bars}，"
        f"min_pullback={DEFAULT_EVENT_CHAIN_CONFIG.min_pullback_pct}，"
        f"require_new_high_after_anchor={DEFAULT_EVENT_CHAIN_CONFIG.require_new_high_after_anchor}）",
        f"- 固定输入：`four-case-paths.csv` / `four-case-events.csv`，"
        f"快照上界 {manifest['snapshot_upper_date']}",
        f"- 事件数：{len(comparison_rows)}；股票：{', '.join(sorted(by_symbol))}",
        f"- 比对字段：{len(FIELD_LIST)} 个事件链字段",
        "",
        "## 结果",
        "",
        f"- 截断一致性：{total_fields} 项字段比对，**{asof_mismatches} 项不一致**",
        f"- 未来扰动：{perturbations} 项比对，**{perturbation_mismatches} 项不一致**",
        "",
        "## 文件哈希",
        "",
        "| 文件 | SHA256 | 与清单一致 |",
        "|---|---|---|",
    ]
    for name in ("four-case-paths.csv", "four-case-events.csv"):
        lines.append(f"| {name} | `{hashes[name][:16]}…` | {hash_checks[name]} |")
    lines += [
        f"| event_chain.py | `{hashes['event_chain.py'][:16]}…` | 记录用 |",
        f"| verify_asof_consistency.py | `{hashes['verify_asof_consistency.py'][:16]}…` | 记录用 |",
        "",
        "## 覆盖边界",
        "",
    ]
    lines += [f"- 未覆盖：{item}" for item in report["scope"]["not_covered"]]
    lines += [
        "",
        "## 复权覆盖",
        "",
        "| 股票 | 复权价≠原始价的行数 |",
        "|---|---:|",
    ]
    lines += [
        f"| {row['symbol']} | {row['rows_where_adjusted_differs_from_raw']} |" for row in dividend_rows
    ]
    lines += [
        "",
        "四只股票窗口内无除权，故本批**不能**检验复权口径；含除权样本需另列。",
        "",
        "## 复跑",
        "",
        "```powershell",
        "cd backend",
        "uv run --frozen python ../docs/research/firstboard-classification-draft-20261027/verification/verify_asof_consistency.py",
        "```",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"hash checks: {hash_checks}")
    print(f"row checks:  {row_checks}")
    print(f"events: {len(comparison_rows)}  as-of fields: {total_fields}  mismatches: {asof_mismatches}")
    print(f"perturbation comparisons: {perturbations}  mismatches: {perturbation_mismatches}")
    print(f"wrote {OUT_JSON.name} and {OUT_MD.name}")
    return 0 if asof_mismatches == 0 and perturbation_mismatches == 0 and all(hash_checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
