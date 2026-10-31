"""Contracts for the auction portfolio-construction research helper."""

from datetime import date

import polars as pl
import pytest

from scripts import auction_portfolio_construction_study as study


def _candidate(
    symbol: str,
    *,
    bucket: str = "2-4",
    score: float = 1.0,
    date: date = date(2024, 9, 2),
    exit_date: date = date(2024, 9, 5),
) -> dict:
    return {
        "symbol": symbol,
        "date": date,
        "gap_bucket": bucket,
        "tail_strength_signal": True,
        "tail_strength_rank": score,
        "risk_rank": score,
        "_risk_coverage": 1.0,
        "combined_rank": score,
        "_risk_signal": True,
        "_tail_risk_intersection": True,
        "_tail_risk_blend": True,
        "entry_reason": "ok",
        "exit_reason": "ok",
        "entry_vwap": 10.0,
        "entry_volume": 1_000_000.0,
        "exit_date": exit_date,
        "net_return": 0.01,
    }


def test_bucket_quota_selection_takes_two_two_one_per_day():
    rows = []
    for bucket in ("2-4", "4-6", "6-8"):
        for rank in range(1, 5):
            rows.append(_candidate(
                f"600{bucket[0]}{rank}.SH",
                bucket=bucket,
                score=float(rank) / 10,
            ))
    contract = {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "bucket_quota",
    }
    selected, candidate_n = study.select_candidates(
        pl.DataFrame(rows),
        start=date(2024, 9, 2),
        end=date(2024, 9, 30),
        contract=contract,
        max_new_per_day=5,
    )
    assert candidate_n == 12
    assert selected.height == 5
    assert selected.group_by("gap_bucket").len().sort("gap_bucket").to_dicts() == [
        {"gap_bucket": "2-4", "len": 2},
        {"gap_bucket": "4-6", "len": 2},
        {"gap_bucket": "6-8", "len": 1},
    ]
    assert selected.filter(pl.col("gap_bucket") == "6-8")["combined_rank"].item() == 0.4


def test_global_selection_orders_scores_across_buckets():
    rows = [
        _candidate("600001.SH", bucket="2-4", score=0.9),
        _candidate("600002.SH", bucket="4-6", score=0.8),
        _candidate("600003.SH", bucket="6-8", score=0.7),
        _candidate("600004.SH", bucket="2-4", score=0.6),
        _candidate("600005.SH", bucket="4-6", score=0.5),
        _candidate("600006.SH", bucket="6-8", score=0.4),
    ]
    contract = {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "global",
    }
    selected, _ = study.select_candidates(
        pl.DataFrame(rows),
        start=date(2024, 9, 2),
        end=date(2024, 9, 30),
        contract=contract,
        max_new_per_day=5,
    )
    assert selected["symbol"].to_list() == [
        "600001.SH", "600002.SH", "600003.SH", "600004.SH", "600005.SH",
    ]


def test_daily_mark_portfolio_matches_fixed_costs_and_exit_cash():
    buy = (1 + 0.0005) * (1 + 0.0003)
    sell = (1 - 0.0005) * (1 - 0.0003 - 0.001)
    trade_return = 1.1 * sell / buy - 1
    row = _candidate("600001.SH", score=1.0)
    row.update({
        "date": date(2024, 9, 2),
        "exit_date": date(2024, 9, 3),
        "net_return": trade_return,
    })
    closes = pl.DataFrame({
        "symbol": ["600001.SH", "600001.SH"],
        "date": [date(2024, 9, 2), date(2024, 9, 3)],
        "close": [10.0, 10.8],
    })
    summary, filled, curve = study.simulate_daily_mark_portfolio(
        pl.DataFrame([row]),
        calendar=[date(2024, 9, 2), date(2024, 9, 3)],
        daily_closes=closes,
        start=date(2024, 9, 2),
        end=date(2024, 9, 3),
    )
    assert len(filled) == 1
    assert summary["total_return"] == pytest.approx(0.05 * trade_return)
    assert summary["mean_trade_return"] == pytest.approx(trade_return)
    assert summary["stale_marks"] == 0
    assert [row["open_positions"] for row in curve] == [1, 0]


def test_selection_excludes_same_day_exit_and_unresolved_trades():
    rows = [
        _candidate("600001.SH", exit_date=date(2024, 9, 2)),
        {**_candidate("600002.SH"), "exit_reason": "missing_or_invalid_exit_bar"},
        _candidate("600003.SH"),
    ]
    contract = {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "global",
    }
    selected, candidate_n = study.select_candidates(
        pl.DataFrame(rows),
        start=date(2024, 9, 2),
        end=date(2024, 9, 30),
        contract=contract,
        max_new_per_day=5,
    )
    assert candidate_n == 1
    assert selected["symbol"].to_list() == ["600003.SH"]
