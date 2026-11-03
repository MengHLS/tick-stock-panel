from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

pytest.importorskip("sklearn")

from scripts.first_board_right_tail_lab.event_policy import EventPolicyConfig
from scripts.first_board_right_tail_lab.event_policy_study import (
    run_event_policy_study,
)
from scripts.first_board_right_tail_lab.report import sha256_file


def _sessions() -> list[date]:
    start = date(2021, 1, 1)
    return [start + timedelta(days=index) for index in range(950)]


def _decisions(sessions: list[date]) -> pl.DataFrame:
    rows = []
    for index in range(0, len(sessions) - 40, 3):
        day = sessions[index]
        fillable = index % 4 != 0
        base_return = -0.05 + (index % 9) * 0.012
        rows.append(
            {
                "decision_id": f"event-{index:04d}",
                "event_id": f"event-{index:04d}",
                "candidate_id": f"candidate-{index:04d}",
                "symbol": f"{index % 1000:06d}.SZ",
                "decision_date": day,
                "decision_time": datetime.combine(
                    day,
                    time(10, 0),
                ),
                "trigger_rule": "A" if index % 2 else "B",
                "trigger_bar_end": datetime.combine(
                    day,
                    time(10, 0),
                ),
                "signal_available_time": datetime.combine(
                    day,
                    time(10, 0),
                ),
                "days_waited": 1,
                "market_fillable": fillable,
                "market_blocked_reason": (
                    None if fillable else "limit_up_locked"
                ),
                "label_observable": fillable,
                "entry_exec_adj": 10.0 if fillable else None,
                "mfe_touch_20d": 0.25 if fillable else None,
                "mae_touch_20d": -0.07 if fillable else None,
                "peak_day": 6.0 if fillable else None,
                "stop_first": False if fillable else None,
                "ordering_ambiguous": False if fillable else None,
                "mfe_exec_20d": 0.20 if fillable else None,
                "mae_exec_20d": -0.06 if fillable else None,
                "exec_return": base_return if fillable else None,
                "exit_status": "closed" if fillable else None,
                "label_maturity_time": (
                    datetime.combine(
                        day + timedelta(days=30),
                        time(15, 0),
                    )
                    if fillable
                    else None
                ),
                "feature__factor__daily__ret_1d": (
                    index % 13 / 100.0
                ),
                "feature__factor__daily__volatility_20": (
                    index % 7 / 20.0
                ),
            }
        )
    return pl.DataFrame(rows)


def _inputs(
    root: Path,
) -> tuple[Path, Path, list[date], list[dict]]:
    sessions = _sessions()
    decisions_path = root / "decisions.parquet"
    _decisions(sessions).write_parquet(decisions_path)
    sessions_path = root / "sessions.parquet"
    pl.DataFrame({"date": sessions}).write_parquet(sessions_path)
    folds = [
        {
            "name": "2022",
            "test_start": date(2022, 1, 1),
            "test_end": date(2022, 12, 31),
        },
        {
            "name": "2023",
            "test_start": date(2023, 1, 1),
            "test_end": date(2023, 6, 30),
        },
    ]
    return decisions_path, sessions_path, sessions, folds


def _config() -> EventPolicyConfig:
    return EventPolicyConfig(
        max_iter=5,
        min_samples=10,
        calibration_fraction=0.2,
        min_calibration_samples=5,
        fill_gate_fraction=0.5,
        event_budget_fraction=0.2,
        max_entries_per_day=2,
    )


def test_event_policy_study_writes_reproducible_artifacts(
    tmp_path: Path,
):
    decisions_path, sessions_path, sessions, folds = _inputs(tmp_path)
    first = tmp_path / "policy-1"
    second = tmp_path / "policy-2"

    first_manifest = run_event_policy_study(
        decisions_path,
        first,
        _config(),
        sessions_path=sessions_path,
        sessions=sessions,
        folds=folds,
        purge_sessions=10,
    )
    run_event_policy_study(
        decisions_path,
        second,
        _config(),
        sessions_path=sessions_path,
        sessions=sessions,
        folds=folds,
        purge_sessions=10,
    )

    expected = {
        "event_samples.parquet",
        "predictions.parquet",
        "selected_events.parquet",
        "fold_metrics.parquet",
        "calibration.parquet",
        "model_status.parquet",
        "event_policy_manifest.json",
        "RESULTS.md",
    }
    assert {path.name for path in first.iterdir()} == expected
    assert first_manifest["status"] == "complete"
    assert first_manifest["finished_at"]
    assert first_manifest["stats"]["features"] == 2
    assert first_manifest["stats"]["validation_events"] > 0
    assert first_manifest["stats"]["selected_events"] > 0
    assert first_manifest["decisions_sha256"]
    assert first_manifest["sessions_sha256"]
    assert first_manifest["code_sha256"]
    assert first_manifest["calibration"]
    assert first_manifest["model_status"]
    assert first_manifest["checks"]
    assert pl.read_parquet(first / "predictions.parquet").equals(
        pl.read_parquet(second / "predictions.parquet")
    )
    selected = pl.read_parquet(first / "selected_events.parquet")
    predictions = pl.read_parquet(first / "predictions.parquet")
    assert set(selected["event_id"].to_list()).issubset(
        set(predictions["event_id"].to_list())
    )
    assert selected.filter(pl.col("selected")).height == selected.height
    for name, digest in first_manifest["checks"].items():
        assert sha256_file(first / name) == digest


def test_event_policy_study_refuses_existing_output(tmp_path: Path):
    decisions_path, sessions_path, sessions, folds = _inputs(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_event_policy_study(
            decisions_path,
            output,
            _config(),
            sessions_path=sessions_path,
            sessions=sessions,
            folds=folds,
        )

    assert marker.read_text(encoding="utf-8") == "keep"


def test_failed_event_policy_study_has_no_finished_at(tmp_path: Path):
    decisions_path, sessions_path, sessions, folds = _inputs(tmp_path)
    decisions = pl.read_parquet(decisions_path).drop(
        "feature__factor__daily__ret_1d",
        "feature__factor__daily__volatility_20",
    )
    decisions.write_parquet(decisions_path)
    output = tmp_path / "failed"

    with pytest.raises(
        ValueError,
        match="at least one T-day event factor",
    ):
        run_event_policy_study(
            decisions_path,
            output,
            _config(),
            sessions_path=sessions_path,
            sessions=sessions,
            folds=folds,
        )

    manifest = json.loads(
        (output / "event_policy_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "failed"
    assert "finished_at" not in manifest
