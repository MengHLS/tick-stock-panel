"""Repair stock-code typos in the platform limit-up extension table.

The upstream platform is manually maintained and occasionally stores a stock
under the wrong exchange suffix, a truncated code, or a code that belongs to
another company. A repair is only accepted when the candidate symbol also
closed at its limit on that trading day; everything else is left untouched.
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from app.custom.limit_up_platform.service import CONFIG_ID
from app.services.fs_utils import atomic_write_parquet, atomic_write_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodeChange:
    date: str
    record_id: int
    name: str
    old_symbol: str
    new_symbol: str
    rule: str
    action: str  # repair | quarantine | unresolved


def _digits(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").split(".")[0] if ch.isdigit())


def _norm_name(value: object) -> str:
    return "".join(str(value or "").split())


def _confirmed(confirmed: set[tuple[str, str]], day: str, symbol: str) -> bool:
    return (day, symbol) in confirmed


def plan_code_calibration(
    frame: pl.DataFrame,
    instruments: pl.DataFrame,
    confirmed: set[tuple[str, str]],
) -> tuple[pl.DataFrame, list[CodeChange]]:
    """Return a corrected frame plus the change log.

    ``frame`` needs ``id/symbol/date/name`` columns. Rows whose code cannot be
    proven stay as-is so a bad heuristic can never silently rewrite data.
    """
    valid = set(instruments["symbol"].to_list())
    by_code: dict[str, list[str]] = defaultdict(list)
    by_name: dict[str, list[str]] = defaultdict(list)
    current_name: dict[str, str] = {}
    for row in instruments.select("symbol", "name", "code").to_dicts():
        by_code[row["code"]].append(row["symbol"])
        by_name[_norm_name(row["name"])].append(row["symbol"])
        current_name[row["symbol"]] = row["name"]

    rows = frame.to_dicts()
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[str(row["date"])].append(row)

    changes: list[CodeChange] = []
    quarantined: set[int] = set()
    repaired: dict[int, str] = {}

    for day, day_rows in by_day.items():
        present = {row["symbol"] for row in day_rows}

        def pick_candidate(
            row: dict, day_value: str, present_symbols: set[str],
        ) -> tuple[str, str] | None:
            symbol = str(row["symbol"])
            digits = _digits(symbol)
            candidates: list[tuple[str, str]] = []
            if len(digits) < 6:
                candidates += [(s, "pad") for s in by_code.get(digits.zfill(6), [])]
            candidates += [(s, "suffix") for s in by_code.get(digits, [])]
            candidates += [(s, "name") for s in by_name.get(_norm_name(row["name"]), [])]
            for target, rule in candidates:
                if target == symbol or target in present_symbols:
                    continue
                if _confirmed(confirmed, day_value, target):
                    return target, rule
            return None

        def pick_name_candidate(
            row: dict, day_value: str, present_symbols: set[str],
        ) -> str | None:
            symbol = str(row["symbol"])
            hits = sorted({
                target
                for target in by_name.get(_norm_name(row["name"]), [])
                if target != symbol
                and target not in present_symbols
                and _confirmed(confirmed, day_value, target)
            })
            return hits[0] if len(hits) == 1 else None

        for row in day_rows:
            symbol = str(row["symbol"])
            if symbol in valid:
                # A valid code can still belong to the wrong company. Repair it
                # only when the row's name identifies a single confirmed stock.
                if (
                    (day, symbol) not in confirmed
                    and _norm_name(row["name"])
                    != _norm_name(current_name.get(symbol, ""))
                ):
                    target = pick_name_candidate(row, day, present)
                    if target is not None:
                        repaired[int(row["id"])] = target
                        present.add(target)
                        changes.append(CodeChange(
                            day, int(row["id"]), str(row["name"]), symbol,
                            target, "name", "repair",
                        ))
                    else:
                        changes.append(CodeChange(
                            day, int(row["id"]), str(row["name"]), symbol,
                            symbol, "name-unconfirmed", "unresolved",
                        ))
                continue
            picked = pick_candidate(row, day, present)
            if picked is None:
                changes.append(CodeChange(
                    day, int(row["id"]), str(row["name"]), symbol, symbol,
                    "unresolved", "unresolved",
                ))
                continue
            target, rule = picked
            repaired[int(row["id"])] = target
            present.add(target)
            changes.append(CodeChange(
                day, int(row["id"]), str(row["name"]), symbol, target,
                rule, "repair",
            ))

        groups: dict[str, list[dict]] = defaultdict(list)
        for row in day_rows:
            groups[repaired.get(int(row["id"]), str(row["symbol"]))].append(row)
        for symbol, group in groups.items():
            if len(group) < 2:
                continue
            keep = next(
                (r for r in group if _norm_name(r["name"]) == _norm_name(current_name.get(symbol, ""))),
                min(group, key=lambda r: int(r["id"])),
            )
            keep_id = int(keep["id"])
            for row in group:
                if int(row["id"]) == keep_id:
                    continue
                record_id = int(row["id"])
                if record_id in repaired:
                    continue
                target = None
                for candidate in by_name.get(_norm_name(row["name"]), []):
                    if candidate != symbol and candidate not in present and _confirmed(confirmed, day, candidate):
                        target = candidate
                        break
                if target:
                    repaired[record_id] = target
                    present.add(target)
                    changes.append(CodeChange(
                        day, record_id, str(row["name"]), symbol, target,
                        "duplicate-name", "repair",
                    ))
                else:
                    quarantined.add(record_id)
                    changes.append(CodeChange(
                        day, record_id, str(row["name"]), symbol, symbol,
                        "duplicate-unproven", "quarantine",
                    ))

    corrected = frame.filter(~pl.col("id").is_in(list(quarantined)) if quarantined else pl.lit(True))
    if repaired:
        targets = pl.Series("__new", [repaired.get(i) for i in corrected["id"].to_list()], dtype=pl.Utf8)
        corrected = corrected.with_columns(
            pl.coalesce([targets, pl.col("symbol")]).alias("symbol")
        ).with_columns(
            pl.col("symbol").str.split(".").list.first().alias("code")
        )
    return corrected, changes


def build_confirmed_limit_days(
    data_dir: Path,
    dates: list[str],
) -> set[tuple[str, str]]:
    """Return (date, symbol) pairs that closed at the exchange limit price."""
    from app.indicators.pipeline import compute_limit_signals
    from app.tickflow.security_status import attach_st_history, read_st_history

    if not dates:
        return set()
    from datetime import date, timedelta

    start = date.fromisoformat(min(dates)) - timedelta(days=30)
    end = date.fromisoformat(max(dates))
    panel_dates = sorted(
        path.parent.name[5:]
        for path in (data_dir / "kline_daily_enriched").glob("date=*/part.parquet")
        if start <= date.fromisoformat(path.parent.name[5:]) <= end
    )
    if not panel_dates:
        panel_dates = sorted(
            path.parent.name[5:]
            for path in (data_dir / "kline_daily").glob("date=*/part.parquet")
            if start <= date.fromisoformat(path.parent.name[5:]) <= end
        )
    frames = []
    for day in panel_dates:
        path = data_dir / "kline_daily_enriched" / f"date={day}" / "part.parquet"
        if not path.exists():
            path = data_dir / "kline_daily" / f"date={day}" / "part.parquet"
        if not path.exists():
            continue
        schema = pl.scan_parquet(path).collect_schema().names()
        columns = ["symbol", "date", "open", "high", "low", "close"]
        columns += [name for name in ("raw_close", "raw_high", "raw_low") if name in schema]
        frame = pl.read_parquet(path, columns=columns)
        if "raw_close" not in frame.columns:
            frame = frame.with_columns(
                pl.col("close").alias("raw_close"),
                pl.col("high").alias("raw_high"),
                pl.col("low").alias("raw_low"),
            )
        frames.append(frame)
    if not frames:
        return set()
    instruments = pl.read_parquet(data_dir / "instruments" / "instruments.parquet")
    panel = pl.concat(frames).sort(["symbol", "date"])
    panel = attach_st_history(panel, read_st_history(data_dir))
    panel = compute_limit_signals(panel, instruments, needed={"limit_up_price"})
    confirmed: set[tuple[str, str]] = set()
    for row in panel.select(
        "symbol", "date", "raw_close", "raw_high", "limit_up_price"
    ).iter_rows(named=True):
        limit = row["limit_up_price"]
        close = row["raw_close"]
        if limit is None or close is None:
            continue
        day = str(row["date"])
        bj_rounding_hit = (
            row["symbol"].endswith(".BJ")
            and row["raw_high"] is not None
            and abs(row["raw_high"] - limit) <= 0.0101
            and abs(close - row["raw_high"]) <= 1e-9
        )
        if close >= limit or bj_rounding_hit:
            confirmed.add((day, row["symbol"]))
    return confirmed


def apply_code_calibration(data_dir: Path, *, apply: bool) -> dict:
    timestamps = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = data_dir / "ext_data" / CONFIG_ID / "timeseries"
    partitions = sorted(base.glob("date=*/part.parquet"))
    if not partitions:
        raise ValueError(f"no partitions under {base}")

    frames = []
    for path in partitions:
        frame = pl.read_parquet(path).with_columns(
            pl.lit(path.parent.name[5:]).alias("_partition")
        )
        frames.append(frame)
    frame = pl.concat(frames, how="diagonal")
    dates = sorted(frame["_partition"].unique().to_list())
    instruments = pl.read_parquet(data_dir / "instruments" / "instruments.parquet")
    confirmed = build_confirmed_limit_days(data_dir, dates)
    corrected, changes = plan_code_calibration(
        frame.drop("_partition"), instruments, confirmed
    )
    counts = Counter(change.action for change in changes)
    report = {
        "checked_at": datetime.now().isoformat(),
        "partitions": len(partitions),
        "rows_before": frame.height,
        "rows_after": corrected.height,
        "counts": dict(counts),
        "changes": [change.__dict__ for change in changes],
        "applied": False,
        "backup_dir": None,
    }
    if not apply:
        return report

    affected_days = {
        change.date for change in changes
        if change.action in {"repair", "quarantine"}
    }
    affected_partitions = [
        path for path in partitions if path.parent.name[5:] in affected_days
    ]
    backup_dir = data_dir / "backups" / f"{CONFIG_ID}-code-calibration-{timestamps}"
    for path in affected_partitions:
        target = backup_dir / path.parent.name / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())

    repaired = corrected.filter(pl.col("id").is_in([
        change.record_id for change in changes if change.action == "repair"
    ]))
    quarantined = frame.filter(pl.col("id").is_in([
        change.record_id for change in changes if change.action == "quarantine"
    ]))
    if quarantined.height:
        atomic_write_parquet(quarantined, backup_dir / "quarantined_rows.parquet")

    by_partition: dict[str, pl.DataFrame] = {}
    corrected = corrected.with_columns(pl.col("date").alias("_partition"))
    for (day,), group in corrected.group_by(["_partition"]):
        by_partition[day] = group.drop("_partition")
    for path in affected_partitions:
        day = path.parent.name[5:]
        group = by_partition.get(day)
        if group is not None:
            atomic_write_parquet(group, path)

    from app.factors.ext_factors import invalidate_ext_caches

    invalidate_ext_caches(data_dir)

    report["applied"] = True
    report["affected_partitions"] = len(affected_partitions)
    report["backup_dir"] = str(backup_dir)
    report["repaired_rows"] = repaired.height
    atomic_write_text(
        backup_dir / "report.json",
        json.dumps(report, ensure_ascii=False, indent=2),
    )
    logger.info(
        "limit-up code calibration: repaired=%d quarantined=%d",
        counts.get("repair", 0), counts.get("quarantine", 0),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="D:/TSP/data")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = apply_code_calibration(Path(args.data_dir), apply=args.apply)
    print(json.dumps(
        {key: value for key, value in report.items() if key != "changes"},
        ensure_ascii=False, indent=2,
    ))
    for change in report["changes"]:
        if change["action"] != "unresolved":
            print(
                f"{change['date']} {change['record_id']} {change['name']} "
                f"{change['old_symbol']} -> {change['new_symbol']} "
                f"({change['rule']}/{change['action']})"
            )


if __name__ == "__main__":
    main()
