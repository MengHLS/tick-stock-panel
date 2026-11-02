from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl

import scripts.first_board_right_tail_lab as lab
from scripts.first_board_right_tail_lab.study import StudyConfig, run_study

SYMBOL = "000001.SZ"


def _session_bar_ends(day: date) -> list[datetime]:
    morning = [
        datetime.combine(day, time(9, 30)) + timedelta(minutes=index)
        for index in range(1, 121)
    ]
    afternoon = [
        datetime.combine(day, time(13, 0)) + timedelta(minutes=index)
        for index in range(1, 121)
    ]
    return [*morning, *afternoon]


class IntegrationDataSource:
    def __init__(self) -> None:
        self.sessions = [
            date(2026, 1, 1) + timedelta(days=index)
            for index in range(55)
        ]
        self.event_day = self.sessions[21]
        self.fill_day = self.sessions[22]
        self.exit_day = self.sessions[23]

    def trading_dates(self, start: date, end: date) -> list[date]:
        return [day for day in self.sessions if start <= day <= end]

    def instruments(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "symbol": [SYMBOL],
                "name": ["测试股"],
                "listing_date": ["2000-01-01"],
            }
        )

    def st_history(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "symbol": [SYMBOL],
                "flag_date": [date(2000, 1, 1)],
                "st_flag": [False],
            }
        )

    def universe_symbols(self, start: date, end: date) -> list[str]:
        return [SYMBOL]

    def daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        rows = []
        for day in self.sessions:
            if day < start or day > end:
                continue
            close = 10.0 if day <= self.fill_day else 10.2
            high = 10.5 if day == self.event_day else close
            low = 9.8 if day == self.event_day else close
            if day == self.exit_day:
                close = 9.2
                high = 9.3
                low = 9.0
            rows.append(
                {
                    "symbol": SYMBOL,
                    "date": day,
                    "open": close,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1_000_000.0,
                    "amount": close * 1_000_000.0,
                    "raw_close": close,
                    "raw_high": high,
                    "raw_low": low,
                    "limit_up_price": 11.0,
                    "limit_down_price": 9.0,
                    "consecutive_limit_ups": (
                        1 if day == self.event_day else 0
                    ),
                }
            )
        return pl.DataFrame(rows).filter(pl.col("symbol").is_in(symbols))

    def minute_batch(
        self,
        symbols: list[str],
        dates: list[date],
    ) -> pl.DataFrame:
        rows = []
        for day in dates:
            for bar_end in _session_bar_ends(day):
                open_price = 10.0
                close_price = 10.0
                high_price = 10.0
                low_price = 10.0
                volume = 10_000.0
                if day == self.fill_day:
                    if bar_end.time() == time(9, 31):
                        high_price = 20.0
                    if bar_end.time() == time(10, 1):
                        open_price = 10.6
                        close_price = 10.6
                        high_price = 10.7
                        low_price = 10.5
                        volume = 100_000.0
                elif day == self.exit_day:
                    open_price = 9.1
                    close_price = 9.1
                    high_price = 9.2
                    low_price = 9.0
                elif day > self.exit_day:
                    open_price = 10.2
                    close_price = 10.2
                    high_price = 10.3
                    low_price = 10.1
                rows.append(
                    {
                        "symbol": SYMBOL,
                        "datetime": bar_end,
                        "bar_start": bar_end - timedelta(minutes=1),
                        "bar_end": bar_end,
                        "volume": volume,
                        "open_raw": open_price,
                        "high_raw": high_price,
                        "low_raw": low_price,
                        "close_raw": close_price,
                        "amount_raw": open_price * volume * 100.0,
                        "open_adj": open_price,
                        "high_adj": high_price,
                        "low_adj": low_price,
                        "close_adj": close_price,
                        "amount_adj": open_price * volume * 100.0,
                    }
                )
        return pl.DataFrame(rows).filter(
            pl.col("symbol").is_in(symbols)
        )

    def data_generation(self) -> str:
        return "integration-generation-v1"


def test_end_to_end_event_uses_one_fill_and_excludes_pre_entry_high(
    tmp_path: Path,
):
    source = IntegrationDataSource()
    output = tmp_path / "integration"
    config = StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("E0", "A"),
    )

    run_study(source, config, output)

    assert lab.RESEARCH_STAGE == "M3-EVENT"
    events = pl.read_parquet(output / "events.parquet")
    triggers = pl.read_parquet(output / "triggers.parquet")
    orders = pl.read_parquet(output / "orders.parquet")
    labels = pl.read_parquet(output / "labels.parquet")
    decisions = pl.read_parquet(output / "decisions.parquet")
    coverage = pl.read_parquet(output / "coverage.parquet")
    summary = pl.read_parquet(output / "event_summary.parquet")
    assert (output / "RESULTS.md").is_file()

    event_id = events["event_id"][0]
    assert set(triggers["event_id"].to_list()) == {event_id}
    assert set(orders["event_id"].to_list()) == {event_id}
    assert set(labels["event_id"].to_list()) == {event_id}
    assert set(decisions["event_id"].to_list()) == {event_id}
    assert set(coverage["event_id"].to_list()) == {event_id}
    assert set(summary["event_id"].to_list()) == {event_id}

    candidates = triggers.filter(pl.col("record_type") == "candidate")
    assert set(candidates["rule"].to_list()) == {"E0", "A"}
    assert candidates.filter(pl.col("rule") == "E0")["order_time"][0] > (
        candidates.filter(pl.col("rule") == "E0")["signal_available_time"][0]
    )
    later_trigger = candidates.filter(pl.col("rule") == "A")["order_time"][0]
    assert decisions.height == 1
    assert set(decisions["candidate_id"].to_list()) == set(
        orders["candidate_id"].to_list()
    )
    assert orders.height == 1
    assert orders["fill_time"][0] < later_trigger
    assert labels["candidate_id"][0] == orders["candidate_id"][0]
    assert labels["mfe_touch_20d"][0] < 0.10
    assert summary["first_filled_candidate_id"][0] == orders["candidate_id"][0]
