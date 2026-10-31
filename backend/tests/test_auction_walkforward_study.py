"""Contracts for the expanding-window auction walk-forward study."""

import json
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from scripts import auction_walkforward_study as study


def _fold(
    *,
    train_start: date,
    train_end: date,
    test_start: date,
    test_end: date,
) -> dict:
    return {
        "name": "fold",
        "train_start": train_start,
        "train_end": train_end,
        "test_start": test_start,
        "test_end": test_end,
    }


def test_validate_folds_rejects_overlapping_test_windows():
    folds = [
        _fold(
            train_start=date(2020, 1, 1),
            train_end=date(2021, 12, 31),
            test_start=date(2022, 1, 1),
            test_end=date(2023, 6, 30),
        ),
        _fold(
            train_start=date(2020, 1, 1),
            train_end=date(2022, 12, 31),
            test_start=date(2023, 1, 1),
            test_end=date(2023, 12, 31),
        ),
    ]

    with pytest.raises(ValueError, match="overlap"):
        study.validate_folds(folds)


def test_load_panel_keeps_all_score_inputs_and_joins_d5_outcomes(tmp_path):
    factor_info = {
        "factor_info": {"available_factor_ids": ["f1", "f2"]},
        "factors": [
            {"factor_id": "f1", "group": "test"},
            {"factor_id": "f2", "group": "test"},
        ],
    }
    factor_path = tmp_path / "factors.json"
    factor_path.write_text(json.dumps(factor_info), encoding="utf-8")
    events = pl.DataFrame({
        "symbol": ["600001.SH", "302001.SZ"],
        "date": [date(2024, 1, 2), date(2024, 1, 2)],
        "horizon": [3, 3],
        "gap_bucket": ["2-4", "2-4"],
        "signal_eligible": [True, True],
        "entry_vwap": [10.0, 10.0],
        "entry_volume": [1_000_000.0, 1_000_000.0],
        "tail_strength_signal": [True, True],
        "tail_strength_rank": [0.8, 0.8],
        "factor__f1": [1.0, 2.0],
        "factor__f2": [2.0, 1.0],
    })
    outcomes = pl.DataFrame({
        "symbol": ["600001.SH", "302001.SZ"],
        "date": [date(2024, 1, 2), date(2024, 1, 2)],
        "entry_reason": ["ok", "ok"],
        "exit_reason": ["ok", "ok"],
        "exit_date": [date(2024, 1, 9), date(2024, 1, 9)],
        "gross_return": [0.02, 0.02],
        "net_return": [0.01, 0.01],
        "horizon": [5, 5],
    })
    events_path = tmp_path / "events.parquet"
    outcomes_path = tmp_path / "d5.parquet"
    events.write_parquet(events_path)
    outcomes.write_parquet(outcomes_path)

    panel, factor_ids = study.load_panel(events_path, factor_path, outcomes_path)

    assert factor_ids == ["f1", "f2"]
    assert panel["symbol"].to_list() == ["600001.SH"]
    assert panel["tail_strength_signal"].to_list() == [True]
    assert panel["rank__f1"].to_list() == [0.5]
    assert panel["rank__f2"].to_list() == [0.5]
    assert panel["net_return"].to_list() == [0.01]


def test_mature_training_rows_excludes_labels_exiting_after_train_end():
    panel = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH"],
        "date": [date(2024, 12, 30), date(2024, 12, 31)],
        "exit_date": [date(2025, 1, 6), date(2024, 12, 31)],
        "entry_reason": ["ok", "ok"],
        "exit_reason": ["ok", "ok"],
        "net_return": [0.10, 0.02],
    })

    mature = study.mature_training_rows(
        panel,
        train_start=date(2024, 1, 1),
        train_end=date(2024, 12, 31),
    )

    assert mature["symbol"].to_list() == ["600002.SH"]


def _calibration_frame() -> pl.DataFrame:
    rows = []
    schedules = (
        (date(2024, 1, 2), (-0.20, 0.02, 0.01)),
        (date(2024, 1, 3), (-0.20, 0.02, 0.01)),
        (date(2025, 1, 2), (1.00, 0.90, 0.80)),
    )
    for day, returns in schedules:
        exit_date = day + timedelta(days=5)
        for bucket, prefix in (("2-4", "601"), ("4-6", "602"), ("6-8", "603")):
            for index, (rank, net_return) in enumerate(
                zip((0.95, 0.85, 0.80), returns, strict=True),
            ):
                rows.append({
                    "symbol": f"{prefix}{index:03d}.SH",
                    "date": day,
                    "gap_bucket": bucket,
                    "combined_rank": rank,
                    "entry_reason": "ok",
                    "exit_reason": "ok",
                    "entry_vwap": 10.0,
                    "entry_volume": 1_000_000.0,
                    "exit_date": exit_date,
                    "net_return": net_return,
                })
    return pl.DataFrame(rows)


def test_band_calibration_filters_to_training_dates_and_respects_minimum(monkeypatch):
    seen_dates = []
    original_baseline = study._with_baseline

    def record_training_dates(frame: pl.DataFrame) -> pl.DataFrame:
        seen_dates.append((frame["date"].min(), frame["date"].max()))
        return original_baseline(frame)

    monkeypatch.setattr(study, "MIN_CALIBRATION_EVENTS", 1)
    monkeypatch.setattr(study, "_with_baseline", record_training_dates)
    chosen, rows = study.calibrate_band(
        _calibration_frame(),
        train_start=date(2024, 1, 1),
        train_end=date(2024, 1, 31),
        seed=7,
    )

    assert seen_dates == [(date(2024, 1, 2), date(2024, 1, 3))]
    assert all(row["selected_n"] >= 1 for row in rows)
    assert chosen["name"] == "70_90"


def test_chain_portfolio_curves_compounds_each_fold_return():
    chained = study.chain_portfolio_curves([
        {
            "name": "first",
            "portfolio": {
                "total_return": 0.10,
                "filled_n": 2,
                "stale_marks": 0,
            },
            "curve": [
                {"date": "2024-01-02", "equity": 1_000_000.0},
                {"date": "2024-01-03", "equity": 1_100_000.0},
            ],
        },
        {
            "name": "second",
            "portfolio": {
                "total_return": -0.10,
                "filled_n": 3,
                "stale_marks": 0,
            },
            "curve": [
                {"date": "2025-01-02", "equity": 1_000_000.0},
                {"date": "2025-01-03", "equity": 900_000.0},
            ],
        },
    ])

    assert chained["total_return"] == pytest.approx(-0.01)
    assert chained["filled_n"] == 5
    assert chained["curve"][-1]["equity"] == pytest.approx(990_000.0)


def _factor_panel() -> pl.DataFrame:
    rng = np.random.default_rng(17)
    rows = []
    for year in (2020, 2021, 2022):
        for day in range(10):
            signal_date = date(year, 1, 2) + timedelta(days=day)
            for asset in range(10):
                outcome = asset + rng.normal(0, 0.35)
                stable_factor = asset + rng.normal(0, 0.50)
                if year == 2020:
                    unstable_factor = asset + rng.normal(0, 0.20)
                elif year == 2021:
                    unstable_factor = 9 - asset + rng.normal(0, 0.20)
                else:
                    unstable_factor = asset + rng.normal(0, 0.20)
                rows.append({
                    "symbol": f"600{asset:03d}.SH",
                    "date": signal_date,
                    "gap_bucket": "2-4",
                    "entry_reason": "ok",
                    "exit_reason": "ok",
                    "entry_vwap": 10.0,
                    "entry_volume": 1_000_000.0,
                    "exit_date": signal_date + timedelta(days=5),
                    "net_return": (outcome - 4.5) / 1000,
                    "tail_strength_signal": True,
                    "tail_strength_rank": 0.5,
                    "factor__stable": stable_factor,
                    "factor__unstable": unstable_factor,
                })
    return study.add_factor_ranks(
        pl.DataFrame(rows),
        ["stable", "unstable"],
    )


def test_fold_representatives_and_scores_use_training_metrics_only():
    panel = _factor_panel()
    admitted = study.admit_fold_factors(
        panel,
        ["stable", "unstable"],
        train_start=date(2020, 1, 1),
        train_end=date(2021, 12, 31),
    )
    by_id = {row["factor_id"]: row for row in admitted}
    representatives = study.cluster_fold_factors(
        panel,
        admitted,
        train_start=date(2020, 1, 1),
        train_end=date(2021, 12, 31),
        seed=5,
    )

    assert by_id["stable"]["admitted"] is True
    assert by_id["unstable"]["admitted"] is False
    assert [row["factor_id"] for row in representatives] == ["stable"]

    future = panel.filter(pl.col("date").dt.year() == 2022)
    scored = study.build_scores(future, representatives)
    assert scored["risk_rank"].is_not_null().all()
    assert scored["combined_rank"].is_not_null().all()
