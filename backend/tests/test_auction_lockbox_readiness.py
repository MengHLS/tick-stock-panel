"""Contracts for the prospective auction lockbox readiness seal."""

from datetime import date, timedelta

from scripts import auction_lockbox_readiness as lockbox


def test_discover_auction_dates_requires_result_and_preopen(tmp_path):
    for kind in ("result", "preopen"):
        for day in ("2026-10-08", "2026-10-09"):
            (tmp_path / kind / f"date={day}").mkdir(parents=True)
    (tmp_path / "result" / "date=2026-10-12").mkdir()
    dates = lockbox.discover_auction_dates(tmp_path, date(2026, 10, 1))
    assert [day.isoformat() for day in dates] == ["2026-10-08", "2026-10-09"]


def test_readiness_waits_for_more_days_then_matured_outcomes():
    start = date(2026, 10, 1)
    sessions = [start + timedelta(days=index) for index in range(80)]
    short = lockbox.assess_readiness(
        auction_dates=sessions[:40],
        sessions=sessions,
        months={day.strftime("%Y-%m") for day in sessions},
        daily_dates=sessions[:40],
        enriched_dates=sessions[:40],
    )
    assert short["status"] == "waiting_for_more_auction_days"

    no_minutes = lockbox.assess_readiness(
        auction_dates=sessions[:60],
        sessions=sessions,
        months=set(),
        daily_dates=sessions[:60],
        enriched_dates=sessions[:60],
    )
    assert no_minutes["status"] == "waiting_for_mature_outcomes"

    ready = lockbox.assess_readiness(
        auction_dates=sessions[:60],
        sessions=sessions,
        months={day.strftime("%Y-%m") for day in sessions},
        daily_dates=sessions[:60],
        enriched_dates=sessions[:60],
    )
    assert ready["status"] == "ready_for_one_shot_evaluation"
    assert ready["mature_candidate_days"] == 60


def test_minute_months_only_accepts_year_month_files(tmp_path):
    (tmp_path / "2026-09.parquet").write_bytes(b"x")
    (tmp_path / "2026-10.parquet").write_bytes(b"x")
    (tmp_path / "notes.parquet").write_bytes(b"x")
    assert lockbox.minute_months(tmp_path) == ["2026-09", "2026-10"]
