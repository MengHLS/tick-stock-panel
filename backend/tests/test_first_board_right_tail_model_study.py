from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

pytest.importorskip("sklearn")

import scripts.first_board_right_tail_lab.model_study as model_study_module
from scripts.first_board_right_tail_lab.model import ModelConfig
from scripts.first_board_right_tail_lab.model_study import run_model_study
from scripts.first_board_right_tail_lab.report import sha256_file


def _sessions(count: int = 120) -> list[date]:
    start = date(2022, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def _decision(
    sessions: list[date],
    index: int,
) -> dict:
    day = sessions[index]
    signal = datetime.combine(day, time(10, 0))
    return {
        "decision_id": f"decision-{index:03d}",
        "event_id": f"event-{index:03d}",
        "candidate_id": f"candidate-{index:03d}",
        "symbol": "000001.SZ",
        "decision_date": day,
        "decision_time": signal,
        "trigger_rule": "A",
        "trigger_bar_end": signal,
        "signal_available_time": signal,
        "days_waited": 1,
        "market_fillable": True,
        "label_observable": True,
        "entry_exec_adj": 10.0,
        "mfe_touch_20d": 0.35 if index % 3 == 0 else 0.12,
        "mae_touch_20d": -0.05,
        "peak_day": 5 if index % 2 == 0 else 15,
        "stop_first": index % 7 == 0,
        "ordering_ambiguous": False,
        "mfe_exec_20d": 0.31 if index % 4 == 0 else 0.10,
        "mae_exec_20d": -0.04,
        "exec_return": 0.03 if index % 2 == 0 else -0.01,
        "exit_status": "closed",
        "label_maturity_time": datetime.combine(
            sessions[index + 20],
            time(15, 0),
        ),
        "feature__factor__rank": float(index),
        "feature__factor__aux": float(index % 5),
    }


def _inputs(
    root: Path,
) -> tuple[Path, Path, list[date], list[dict]]:
    sessions = _sessions()
    decisions = pl.DataFrame(
        [
            _decision(sessions, index)
            for index in [*range(10, 50), *range(80, 100)]
        ]
    )
    decisions_path = root / "decisions.parquet"
    decisions.write_parquet(decisions_path)
    sessions_path = root / "sessions.parquet"
    pl.DataFrame({"date": sessions}).write_parquet(sessions_path)
    (root / "feature_contract.json").write_text(
        json.dumps(
            {
                "version": "m2a-v1",
                "features": [
                    "feature__factor__aux",
                    "feature__factor__rank",
                ],
            }
        ),
        encoding="utf-8",
    )
    folds = [
        {
            "name": "fold-1",
            "test_start": sessions[80],
            "test_end": sessions[99],
        }
    ]
    return decisions_path, sessions_path, sessions, folds


def test_model_study_writes_complete_reproducible_artifacts(
    tmp_path: Path,
):
    decisions_path, _, sessions, folds = _inputs(tmp_path)
    first = tmp_path / "model-1"
    second = tmp_path / "model-2"
    config = ModelConfig(max_iter=5)

    first_manifest = run_model_study(
        decisions_path,
        first,
        config,
        sessions=sessions,
        folds=folds,
    )
    second_manifest = run_model_study(
        decisions_path,
        second,
        config,
        sessions=sessions,
        folds=folds,
    )

    expected = {
        "model_manifest.json",
        "predictions.parquet",
        "fold_metrics.parquet",
        "top_decile_events.parquet",
        "frozen_threshold_events.parquet",
        "calibration.parquet",
        "model_status.parquet",
        "RESULTS.md",
    }
    assert expected == {path.name for path in first.iterdir()}
    assert first_manifest["status"] == "complete"
    assert first_manifest["finished_at"]
    assert len(first_manifest["decisions_sha256"]) == 64
    assert first_manifest["features"] == [
        "feature__factor__aux",
        "feature__factor__rank",
    ]
    assert first_manifest["config"]["max_iter"] == 5
    assert first_manifest["calibration"]
    assert first_manifest["stats"]["top_events"] > 0
    assert first_manifest["stats"]["frozen_threshold_events"] > 0
    assert first_manifest["checks"]
    assert "- Status: complete" in (
        first / "RESULTS.md"
    ).read_text(encoding="utf-8")
    assert first_manifest["purge_sessions"] == 30
    assert first_manifest["sessions_sha256"]
    assert first_manifest["code_sha256"]
    assert first_manifest["git_commit"]
    assert isinstance(first_manifest["worktree_dirty"], bool)
    assert first_manifest["folds"][0]["name"] == "fold-1"
    for name, digest in first_manifest["checks"].items():
        assert sha256_file(first / name) == digest
    assert "model_manifest.json" not in first_manifest["checks"]
    predictions = pl.read_parquet(first / "predictions.parquet")
    top_events = pl.read_parquet(first / "top_decile_events.parquet")
    frozen_events = pl.read_parquet(
        first / "frozen_threshold_events.parquet"
    )
    source = pl.read_parquet(decisions_path)
    model_status = pl.read_parquet(first / "model_status.parquet")
    assert set(predictions["decision_id"].to_list()).issubset(
        set(source["decision_id"].to_list())
    )
    assert set(top_events["decision_id"].to_list()).issubset(
        set(predictions["decision_id"].to_list())
    )
    assert set(frozen_events["decision_id"].to_list()).issubset(
        set(predictions["decision_id"].to_list())
    )
    assert predictions.equals(
        pl.read_parquet(second / "predictions.parquet")
    )
    assert first_manifest["decisions_sha256"] == (
        second_manifest["decisions_sha256"]
    )
    assert model_status.height == 8


def test_model_study_refuses_to_overwrite_existing_output(
    tmp_path: Path,
):
    decisions_path, _, sessions, folds = _inputs(tmp_path)
    output = tmp_path / "model-existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_model_study(
            decisions_path,
            output,
            ModelConfig(max_iter=5),
            sessions=sessions,
            folds=folds,
        )

    assert marker.read_text(encoding="utf-8") == "keep"


def test_failed_model_study_has_no_finished_at(tmp_path: Path):
    decisions_path, _, sessions, folds = _inputs(tmp_path)
    decisions = pl.read_parquet(decisions_path).drop(
        "feature__factor__rank",
        "feature__factor__aux",
    )
    decisions.write_parquet(decisions_path)
    output = tmp_path / "model-failed"

    with pytest.raises(
        ValueError,
        match="feature contract declares missing columns",
    ):
        run_model_study(
            decisions_path,
            output,
            ModelConfig(max_iter=5),
            sessions=sessions,
            folds=folds,
        )

    manifest = json.loads(
        (output / "model_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert "finished_at" not in manifest


def test_late_artifact_failure_rewrites_report_as_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    decisions_path, _, sessions, folds = _inputs(tmp_path)
    output = tmp_path / "model-late-failure"

    monkeypatch.setattr(
        model_study_module,
        "artifact_checks",
        lambda output: (_ for _ in ()).throw(
            RuntimeError("checksum failure")
        ),
    )

    with pytest.raises(RuntimeError, match="checksum failure"):
        run_model_study(
            decisions_path,
            output,
            ModelConfig(max_iter=5),
            sessions=sessions,
            folds=folds,
        )

    manifest = json.loads(
        (output / "model_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert "finished_at" not in manifest
    assert "- Status: failed" in (
        output / "RESULTS.md"
    ).read_text(encoding="utf-8")
