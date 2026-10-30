"""Run the DELIVERED replay script, not a re-implementation, under two mutations.

For every one of the 27 events:

  A. truncation  - copy the script and its inputs into a scratch directory, cut
     the price file, the first-board flags and the event list at that event's D,
     run the script, and compare the event's 16 rule rows with the delivered
     table.
  B. injection   - keep the full inputs but add fabricated first boards in the
     five sessions after D to the flags file, run, and compare the same rows.

Only the flags file is mutated in B: the delivered script asserts that every
adjusted row matches the live raw panel, so injecting prices would trip that
assert before writing anything.

The script is never modified and never run in place; every run happens in a
scratch copy, so the review-frozen artifacts stay untouched.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_delivered_script.py
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
REPO = DRAFT.parents[2]
SCRIPT = DRAFT / "replay_events_v01.py"
PATHS = DRAFT / "shape-selection-paths.csv"
FLAGS = DRAFT / "platform-firstboard-flags.csv"
LISTS = DRAFT / "platform-firstboard-date-lists.json"
DELIVERED = DRAFT / "event-replay-v01" / "candidate-classifications.json"
OUT_JSON = HERE / "delivered-script-check.json"
OUT_MD = HERE / "DELIVERED-SCRIPT-CHECK.md"

RULES = [
    f"P{'B' if include else 'A'}_q{q}_G{gate}_R{recursive}"
    for include in (False, True)
    for q in (0.03, 0.05)
    for gate in (0, 1)
    for recursive in (0, 1)
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_script(workdir: Path) -> tuple[bool, str]:
    # Use the interpreter already running this script: a nested "uv run" inside
    # an outer "uv run" contends for the environment and fails.
    result = subprocess.run(
        [sys.executable, str(workdir / SCRIPT.name)],
        cwd=str(REPO / "backend"),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return result.returncode == 0, (result.stdout + result.stderr)[-600:]


def rows_for(path: Path, event: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["rule"]: row for row in data if row["event_id"] == event}


def compare(a: dict, b: dict) -> list[str]:
    problems = []
    for rule in RULES:
        ra, rb = a.get(rule), b.get(rule)
        if ra is None or rb is None:
            problems.append(f"{rule}:missing")
            continue
        ca, cb = ra["classification"], rb["classification"]
        if ca.get("nearest_anchor") != cb.get("nearest_anchor"):
            problems.append(f"{rule}:anchor")
        if ca.get("examined") != cb.get("examined"):
            problems.append(f"{rule}:examined")
        sa, sb = ca.get("selected"), cb.get("selected")
        if (sa is None) != (sb is None):
            problems.append(f"{rule}:selected_null")
            continue
        if sa is None:
            continue
        for key in ("P", "P_date", "P_known_at", "L_setup", "L_setup_date",
                    "first_break", "path_state", "skip", "depth"):
            va, vb = sa.get(key), sb.get(key)
            if isinstance(va, float) and isinstance(vb, (int, float)):
                if abs(va - vb) > 1e-9:
                    problems.append(f"{rule}:{key}")
            elif va != vb:
                problems.append(f"{rule}:{key}")
    return problems


def main() -> int:
    events = [f"{row['event_id']}" for row in json.loads(DELIVERED.read_text(encoding="utf-8"))]
    events = sorted(set(events))
    delivered = {event: rows_for(DELIVERED, event) for event in events}

    path_fields, path_rows = read_csv(PATHS)
    flag_fields, flag_rows = read_csv(FLAGS)
    lists = json.loads(LISTS.read_text(encoding="utf-8"))

    workdir = Path(tempfile.mkdtemp(prefix="replay-check-"))
    shutil.copy2(SCRIPT, workdir / SCRIPT.name)
    shutil.copy2(PATHS, workdir / PATHS.name)
    shutil.copy2(FLAGS, workdir / FLAGS.name)
    shutil.copy2(LISTS, workdir / LISTS.name)

    baseline_path = workdir / "event-replay-v01" / "candidate-classifications.json"
    ok, tail = run_script(workdir)
    baseline = {}
    baseline_run_ok = ok and baseline_path.exists()
    if baseline_path.exists():
        baseline = {}
        for row in json.loads(baseline_path.read_text(encoding="utf-8")):
            baseline.setdefault(row["event_id"], {})[row["rule"]] = row
    if not baseline_run_ok:
        print("baseline run failed:", tail)
    baseline_mismatch = []
    for event in events:
        baseline_mismatch += [f"{event}:{item}" for item in compare(delivered[event], baseline.get(event, {}))]

    truncation_problems: list[str] = []
    injection_problems: list[str] = []
    run_failures: list[str] = []

    for event in events:
        code, day = event.split("@")

        # A. truncation at D
        write_csv(workdir / PATHS.name, path_fields,
                  [row for row in path_rows if row["symbol"] != code or row["date"] <= day])
        write_csv(workdir / FLAGS.name, flag_fields,
                  [row for row in flag_rows if row["symbol"] != code or row["date"] <= day])
        trimmed = [
            {**item, "dates": [d for d in item["dates"] if item["code"] != code or d <= day]}
            for item in lists
        ]
        (workdir / LISTS.name).write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
        ok, tail = run_script(workdir)
        if not baseline_path.exists():
            run_failures.append(f"{event}:truncation:{tail}")
            continue
        got = rows_for(baseline_path, event)
        truncation_problems += [f"{event}:{item}" for item in compare(delivered[event], got)]

        # B. injection of future first boards (flags only)
        symbol_dates = [row["date"] for row in path_rows if row["symbol"] == code]
        future = [d for d in symbol_dates if d > day][:5]
        injected_rows = flag_rows + [
            {"symbol": code, "date": d, **{k: "0" for k in flag_fields if k not in ("symbol", "date")},
             "consecutive_limit_ups": "1"}
            for d in future
        ]
        write_csv(workdir / FLAGS.name, flag_fields, injected_rows)
        (workdir / LISTS.name).write_text(json.dumps(lists, ensure_ascii=False), encoding="utf-8")
        ok, tail = run_script(workdir)
        if not baseline_path.exists():
            run_failures.append(f"{event}:injection:{tail}")
            continue
        got = rows_for(baseline_path, event)
        injection_problems += [f"{event}:{item}" for item in compare(delivered[event], got)]

        # restore full inputs for the next iteration
        write_csv(workdir / PATHS.name, path_fields, path_rows)
        write_csv(workdir / FLAGS.name, flag_fields, flag_rows)

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "script_executed": str(SCRIPT.relative_to(REPO)),
        "runs": 1 + 2 * len(events),
        "baseline_reproduced": not baseline_mismatch,
        "baseline_mismatches": baseline_mismatch[:20],
        "truncation_problems": truncation_problems[:20],
        "truncation_count": len(truncation_problems),
        "injection_problems": injection_problems[:20],
        "injection_count": len(injection_problems),
        "run_failures": run_failures[:5],
        "note": (
            "injection mutates only the first-board flags file; the delivered script asserts every "
            "adjusted row against the live raw panel, so injected prices would abort before writing"
        ),
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 交付脚本·直接执行检查（截断与未来首板注入）",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 执行次数：{report['runs']}（1 次复现基线 + 27 次截断 + 27 次注入）",
        f"- 基线复现：{'一致' if not baseline_mismatch else '不一致'}",
        f"- 截断问题：{len(truncation_problems)}",
        f"- 注入问题：{len(injection_problems)}",
        "",
        "每次运行都在临时目录的副本中进行，交付文件未被修改。",
        "注入只改首板标记文件：交付脚本会逐行用实时原始价校验调整价，注入价格会先触发断言。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({k: report[k] for k in
                      ("runs", "baseline_reproduced", "truncation_count", "injection_count")},
                     ensure_ascii=False))
    for item in (baseline_mismatch[:5] + truncation_problems[:5] + injection_problems[:5]):
        print("  ", item)
    return 0 if not (baseline_mismatch or truncation_problems or injection_problems or run_failures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
