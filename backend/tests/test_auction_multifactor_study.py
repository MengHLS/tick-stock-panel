"""Contracts for the auction multifactor research helper."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from scripts import auction_multifactor_study as study


def test_factor_ranks_are_within_date_and_gap_bucket():
    frame = pl.DataFrame({
        "date": [date(2024, 9, 2)] * 6,
        "gap_bucket": ["2-4"] * 3 + ["4-6"] * 3,
        "factor__value": [3.0, 1.0, 2.0, 30.0, 10.0, 20.0],
    })
    ranked = study.add_factor_ranks(frame, ["value"])
    assert ranked["rank__value"].to_list() == pytest.approx(
        [1.0, 0.0, 0.5, 1.0, 0.0, 0.5],
    )


def test_rank_ic_uses_same_day_gap_ranks_and_requires_eight_assets():
    rows = []
    start = date(2024, 9, 2)
    for day in range(10):
        for asset in range(10):
            rows.append({
                "date": start + timedelta(days=day),
                "gap_bucket": "2-4",
                "factor": float(asset),
                "_residual": float(asset),
            })
    metrics = study._rank_ic(pl.DataFrame(rows), "factor")
    assert metrics["mean_ic"] == pytest.approx(1.0)
    assert metrics["event_days"] == 10
    assert metrics["groups"] == 10


def test_rank_ic_drops_constant_groups_instead_of_serializing_nan():
    rows = []
    start = date(2024, 9, 2)
    for day in range(10):
        for asset in range(10):
            rows.append({
                "date": start + timedelta(days=day),
                "gap_bucket": "2-4",
                "factor": 1.0,
                "_residual": float(asset),
            })
    metrics = study._rank_ic(pl.DataFrame(rows), "factor")
    assert metrics["mean_ic"] is None
    assert metrics["groups"] == 0


def _admission_frame() -> pl.DataFrame:
    rows = []
    for year, sign in ((2020, 1.0), (2021, 1.0), (2022, -1.0)):
        for day in range(10):
            for asset in range(12):
                signal = asset + ((day * 3 + asset * 2) % 7) * 0.2
                outcome = sign * (asset + ((day * asset) % 5) * 0.1)
                rows.append({
                    "symbol": f"600{asset:03d}.SH",
                    "date": date(year, 1, 1) + timedelta(days=day),
                    "gap_bucket": "2-4",
                    "horizon": 3,
                    "signal_eligible": True,
                    "tail_strength_signal": False,
                    "tail_strength_score": 0.5,
                    "tail_strength_rank": 0.5,
                    "entry_reason": "ok",
                    "exit_reason": "ok",
                    "entry_vwap": 10.0,
                    "entry_volume": 1_000_000.0,
                    "exit_date": date(year, 1, 20),
                    "net_return": outcome / 1000,
                    "factor__stable": signal,
                    "factor__reverse": sign * signal,
                })
    return study.add_factor_ranks(
        pl.DataFrame(rows),
        ["stable", "reverse"],
    )


def test_admission_rejects_development_yearly_sign_reversal():
    frame = _admission_frame()
    admitted = study.admit_factors(
        frame,
        ["stable", "reverse"],
        {"stable": "趋势", "reverse": "趋势"},
    )
    by_id = {row["factor_id"]: row for row in admitted}
    assert by_id["stable"]["admitted"] is False
    assert by_id["stable"]["yearly_same_sign"] is False
    assert by_id["reverse"]["admitted"] is True


def test_correlated_factors_collapse_to_one_representative(monkeypatch):
    rows = []
    for day in range(20):
        for asset in range(12):
            rows.append({
                "date": date(2021, 1, 1) + timedelta(days=day),
                "gap_bucket": "2-4",
                "entry_reason": "ok",
                "exit_reason": "ok",
                "net_return": asset / 1000,
                "rank__a": asset / 11,
                "rank__b": asset / 11,
            })
    admitted = [
        {
            "factor_id": factor,
            "group": "趋势",
            "admitted": True,
            "direction": "high",
            "sign": 1,
            "metrics": {"mean_ic": 0.05, "icir": icir},
        }
        for factor, icir in (("a", -0.4), ("b", -0.3))
    ]
    monkeypatch.setitem(study.SELECTION, "minimum_correlation_overlap", 10)
    representatives = study.cluster_representatives(
        pl.DataFrame(rows),
        admitted,
        seed=1,
    )
    assert len(representatives) == 1
    assert representatives[0]["factor_id"] == "a"
    assert representatives[0]["members"] == ["a", "b"]


def test_composite_ranks_and_signals_are_gap_neutral():
    rows = []
    for asset in range(10):
        rows.append({
            "symbol": f"600{asset:03d}.SH",
            "date": date(2024, 9, 2),
            "gap_bucket": "2-4",
            "rank__risk": asset / 9,
            "tail_strength_rank": asset / 9,
            "tail_strength_signal": asset >= 7,
        })
    representatives = [{
        "factor_id": "risk",
        "direction": "high",
        "sign": 1,
    }]
    scored = study.build_scores(pl.DataFrame(rows), representatives)
    assert scored["risk_rank"].to_list() == pytest.approx(
        np.arange(10) / 9,
    )
    assert scored["combined_rank"].to_list() == pytest.approx(
        np.arange(10) / 9,
    )
    assert scored.filter(pl.col("_risk_signal")).height == 3
    assert scored.filter(pl.col("_tail_risk_blend")).height == 3
