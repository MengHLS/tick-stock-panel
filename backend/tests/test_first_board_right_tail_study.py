from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

import scripts.first_board_right_tail_lab.model_study as model_study_module
import scripts.first_board_right_tail_lab.study as study_module
from scripts.first_board_right_tail_lab.exit_variants import (
    DEFAULT_EXIT_VARIANTS,
)
from scripts.first_board_right_tail_lab.study import (
    StudyConfig,
    _daily_context,
    _prepare_feature_contract,
    main,
    run_study,
)

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


class FakeDataSource:
    def __init__(self) -> None:
        self.sessions = [
            date(2026, 1, 1) + timedelta(days=index)
            for index in range(55)
        ]
        self.event_day = self.sessions[21]
        self.fail_minute = False

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
            if day < self.event_day:
                close = 10.0
                high = 10.0
                low = 10.0
            elif day == self.event_day:
                close = 10.0
                high = 10.5
                low = 9.8
            elif day == self.event_day + timedelta(days=2):
                close = 9.2
                high = 9.3
                low = 9.0
            else:
                close = 10.2
                high = 10.3
                low = 10.1
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
        if self.fail_minute:
            raise RuntimeError("synthetic minute failure")
        rows = []
        for day in dates:
            price = 10.0
            if day == self.event_day + timedelta(days=2):
                price = 9.1
            for index, bar_end in enumerate(_session_bar_ends(day)):
                open_price = (
                    price
                    if index > 0
                    else (9.1 if day == self.event_day + timedelta(days=2) else price)
                )
                close_price = open_price
                high_price = open_price + 0.1
                low_price = open_price - 0.1
                rows.append(
                    {
                        "symbol": SYMBOL,
                        "datetime": bar_end,
                        "bar_start": bar_end - timedelta(minutes=1),
                        "bar_end": bar_end,
                        "volume": 10_000.0,
                        "open_raw": open_price,
                        "high_raw": high_price,
                        "low_raw": low_price,
                        "close_raw": close_price,
                        "amount_raw": (
                            open_price * 10_000.0 * 100.0
                        ),
                        "open_adj": open_price,
                        "high_adj": high_price,
                        "low_adj": low_price,
                        "close_adj": close_price,
                        "amount_adj": (
                            open_price * 10_000.0 * 100.0
                        ),
                    }
                )
        return pl.DataFrame(rows).filter(
            pl.col("symbol").is_in(symbols)
        )

    def data_generation(self) -> str:
        return "fake-generation-v1"


class SuspendedDaySource(FakeDataSource):
    def __init__(self) -> None:
        super().__init__()
        self.suspended_day = self.event_day + timedelta(days=3)

    def daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        daily = super().daily_batch(symbols, start, end)
        return daily.with_columns(
            pl.when(pl.col("date") == self.suspended_day)
            .then(pl.lit(0.0))
            .otherwise(pl.col("volume"))
            .alias("volume")
        )

    def minute_batch(
        self,
        symbols: list[str],
        dates: list[date],
    ) -> pl.DataFrame:
        return super().minute_batch(
            symbols,
            [day for day in dates if day != self.suspended_day],
        )


class BlockedThenFilledSource(FakeDataSource):
    def minute_batch(
        self,
        symbols: list[str],
        dates: list[date],
    ) -> pl.DataFrame:
        frame = super().minute_batch(symbols, dates)
        fill_day = self.event_day + timedelta(days=1)
        locked_at = datetime.combine(fill_day, time(9, 36))
        breakout_at = datetime.combine(fill_day, time(10, 1))
        return frame.with_columns(
            pl.when(
                pl.col("bar_start") == locked_at
            )
            .then(11.0)
            .when(
                pl.col("bar_start") == breakout_at
            )
            .then(10.6)
            .otherwise(pl.col("open_raw"))
            .alias("open_raw"),
            pl.when(
                pl.col("bar_start") == locked_at
            )
            .then(11.0)
            .when(
                pl.col("bar_start") == breakout_at
            )
            .then(10.7)
            .otherwise(pl.col("high_raw"))
            .alias("high_raw"),
            pl.when(
                pl.col("bar_start") == locked_at
            )
            .then(11.0)
            .when(
                pl.col("bar_start") == breakout_at
            )
            .then(10.5)
            .otherwise(pl.col("low_raw"))
            .alias("low_raw"),
            pl.when(
                pl.col("bar_start") == locked_at
            )
            .then(11.0)
            .when(
                pl.col("bar_start") == breakout_at
            )
            .then(10.6)
            .otherwise(pl.col("close_raw"))
            .alias("close_raw"),
            pl.when(
                pl.col("bar_start") == breakout_at
            )
            .then(100_000.0)
            .otherwise(pl.col("volume"))
            .alias("volume"),
        ).with_columns(
            pl.col("open_raw").alias("open_adj"),
            pl.col("high_raw").alias("high_adj"),
            pl.col("low_raw").alias("low_adj"),
            pl.col("close_raw").alias("close_adj"),
        )


def _config(source: FakeDataSource) -> StudyConfig:
    return StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("E0",),
    )


def test_run_study_writes_reproducible_artifacts(tmp_path: Path):
    source = FakeDataSource()
    first = tmp_path / "run-1"
    second = tmp_path / "run-2"

    manifest = run_study(source, _config(source), first)
    run_study(source, _config(source), second)

    expected = {
        "manifest.json",
        "events.parquet",
        "coverage.parquet",
        "triggers.parquet",
        "orders.parquet",
        "labels.parquet",
        "decisions.parquet",
        "sessions.parquet",
        "feature_contract.json",
        "RESULTS.md",
    }
    assert expected.issubset(
        {path.name for path in first.iterdir()}
    )
    assert manifest["status"] == "complete"
    assert manifest["finished_at"]
    assert manifest["data_generation"] == "fake-generation-v1"
    assert len(manifest["input_sha256"]) == 64
    assert len(manifest["minute_input_sha256"]) == 64
    assert manifest["git_commit"]
    assert isinstance(manifest["worktree_dirty"], bool)
    assert manifest["coverage_by_month"]
    assert manifest["stats"]["decision_count"] == 1
    assert manifest["stats"]["market_fillable_count"] == 1
    assert manifest["stats"]["label_observable_count"] == 1
    assert manifest["checks"]
    assert (
        pl.read_parquet(first / "orders.parquet").equals(
            pl.read_parquet(second / "orders.parquet")
        )
    )
    assert (
        pl.read_parquet(first / "labels.parquet").equals(
            pl.read_parquet(second / "labels.parquet")
        )
    )
    assert (
        pl.read_parquet(first / "coverage.parquet")["status"]
        .unique()
        .to_list()
        == ["complete"]
    )
    decisions = pl.read_parquet(first / "decisions.parquet")
    contract = json.loads(
        (first / "feature_contract.json").read_text(encoding="utf-8")
    )
    assert decisions.height == 1
    assert decisions["decision_id"][0]
    assert "feature__price_vs_t_high" in decisions.columns
    assert "bar_end <= signal_available_time" in contract["cutoff"]
    assert "feature__price_vs_t_high" in contract["features"]
    assert contract["version"] == "m2a-v2-daily-factors"
    assert all(
        decisions[feature].null_count() < decisions.height
        for feature in contract["features"]
    )


def test_feature_contract_drops_all_null_columns():
    decisions = pl.DataFrame(
        {
            "feature__numeric": [1.0, None],
            "feature__empty": pl.Series([None, None], dtype=pl.Null),
            "label": [0.0, 1.0],
        }
    )

    prepared, contract = _prepare_feature_contract(decisions)

    assert "feature__empty" not in prepared.columns
    assert contract["features"] == ["feature__numeric"]
    assert contract["dropped_all_null"] == ["feature__empty"]
    assert contract["factor_coverage"]["feature__numeric"] == 0.5


def test_feature_contract_rejects_non_numeric_feature():
    decisions = pl.DataFrame(
        {
            "feature__text": ["a", "b"],
        }
    )

    with pytest.raises(
        ValueError,
        match="feature columns must be numeric",
    ):
        _prepare_feature_contract(decisions)


def test_run_study_refuses_to_overwrite_existing_output(tmp_path: Path):
    source = FakeDataSource()
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_study(source, _config(source), output)

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (output / "manifest.json").exists()


def test_research_package_import_does_not_eagerly_import_sklearn():
    code = (
        "import sys; "
        "import scripts.first_board_right_tail_lab as lab; "
        "assert lab.RESEARCH_STAGE == 'M3-EVENT'; "
        "assert 'sklearn' not in sys.modules"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_failed_run_manifest_has_no_finished_at(tmp_path: Path):
    source = FakeDataSource()
    source.fail_minute = True
    output = tmp_path / "failed"

    with pytest.raises(RuntimeError, match="synthetic minute failure"):
        run_study(source, _config(source), output)

    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert "finished_at" not in manifest
    assert "synthetic minute failure" in manifest["error"]


def test_run_study_loads_standard_auction_table_for_rule_d(
    tmp_path: Path,
):
    source = FakeDataSource()
    auction_dir = tmp_path / "auction"
    auction_dir.mkdir()
    decision_day = source.event_day + timedelta(days=1)
    pl.DataFrame(
        {
            "symbol": [SYMBOL],
            "date": [decision_day],
            "opening_gap": [0.02],
            "volume_ratio": [1.5],
            "auction_price_adj": [10.0],
        }
    ).write_parquet(auction_dir / "auctions.parquet")
    output = tmp_path / "rule-d"
    config = StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("D",),
        auction_dir=auction_dir,
    )

    run_study(source, config, output)

    triggers = pl.read_parquet(output / "triggers.parquet")
    assert triggers["record_type"].to_list() == ["candidate"]
    assert triggers["rule"].to_list() == ["D"]


def test_daily_context_uses_authoritative_limit_prices():
    day = date(2026, 1, 5)
    daily = pl.DataFrame(
        [
            {
                "symbol": SYMBOL,
                "date": date(2026, 1, 2),
                "raw_close": 10.0,
                "volume": 1_000.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
            },
            {
                "symbol": SYMBOL,
                "date": day,
                "raw_close": 5.0,
                "volume": 1_000.0,
                "limit_up_price": 5.5,
                "limit_down_price": 4.5,
            },
        ]
    )

    context = _daily_context(
        daily,
        SYMBOL,
        [day],
        is_st=False,
    )

    assert context["limit_up_price"][0] == 5.5
    assert context["limit_down_price"][0] == 4.5


def test_study_start_loads_listing_history_before_requested_range(
    tmp_path: Path,
):
    source = FakeDataSource()
    output = tmp_path / "history"
    config = StudyConfig(
        start=source.sessions[20],
        end=source.sessions[-1],
        rules=("E0",),
    )

    run_study(source, config, output)

    events = pl.read_parquet(output / "events.parquet")
    assert events.height == 1


def test_event_with_short_future_is_censored_instead_of_aborting_run(
    tmp_path: Path,
):
    source = FakeDataSource()
    source.sessions = source.sessions[:25]
    output = tmp_path / "short-future"
    config = StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("E0",),
    )

    run_study(source, config, output)

    labels = pl.read_parquet(output / "labels.parquet")
    summary = pl.read_parquet(output / "event_summary.parquet")
    assert labels.height == 0
    assert summary["drop_reason"][0] == "insufficient_label_horizon"


def test_authoritative_suspension_is_not_treated_as_data_missing(
    tmp_path: Path,
):
    source = SuspendedDaySource()
    output = tmp_path / "suspended"

    run_study(source, _config(source), output)

    coverage = pl.read_parquet(output / "coverage.parquet")
    labels = pl.read_parquet(output / "labels.parquet")
    suspended = coverage.filter(pl.col("date") == source.suspended_day)
    assert suspended["status"].to_list() == ["suspended"]
    assert labels.height == 1


def test_late_artifact_failure_does_not_keep_finished_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = FakeDataSource()
    output = tmp_path / "late-failure"

    def fail_results(*args, **kwargs):
        raise RuntimeError("report write failed")

    monkeypatch.setattr(study_module, "write_results", fail_results)

    with pytest.raises(RuntimeError, match="report write failed"):
        run_study(source, _config(source), output)

    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert "finished_at" not in manifest


def test_study_preserves_blocked_attempts_when_later_candidate_fills(
    tmp_path: Path,
):
    source = BlockedThenFilledSource()
    output = tmp_path / "blocked-then-filled"
    config = StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("E0", "A"),
    )

    run_study(source, config, output)

    orders = pl.read_parquet(output / "orders.parquet")
    decisions = pl.read_parquet(output / "decisions.parquet")
    summary = pl.read_parquet(output / "event_summary.parquet")
    assert orders.height == 2
    assert orders["filled"].to_list() == [False, True]
    assert orders["blocked_reason"][0] == "limit_up_locked"
    assert decisions.height == 2
    assert decisions["market_fillable"].to_list() == [False, True]
    assert summary["fill_blocked_counts"][0] == '{"limit_up_locked": 1}'


def test_study_cli_wires_optional_model_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = FakeDataSource()
    output = tmp_path / "with-model-success"
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        study_module,
        "RepositoryDataSource",
        lambda data_dir: source,
    )

    def fake_model_study(
        decisions_path,
        model_output,
        config,
        *,
        sessions_path=None,
        **_kwargs,
    ):
        calls.update(
            {
                "decisions_path": decisions_path,
                "model_output": model_output,
                "config": config,
                "sessions_path": sessions_path,
            }
        )
        return {"status": "complete", "finished_at": "test"}

    monkeypatch.setattr(
        model_study_module,
        "run_model_study",
        fake_model_study,
    )

    main(
        [
            "--data-dir",
            str(tmp_path),
            "--start",
            source.sessions[0].isoformat(),
            "--end",
            source.sessions[-1].isoformat(),
            "--output",
            str(output),
            "--with-model",
        ]
    )

    assert calls["decisions_path"] == output / "decisions.parquet"
    assert calls["model_output"] == output / "model"
    assert calls["sessions_path"] == output / "sessions.parquet"
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert manifest["model"]["status"] == "complete"


def test_study_cli_keeps_completed_data_when_model_stage_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = FakeDataSource()
    output = tmp_path / "with-model-failure"
    monkeypatch.setattr(
        study_module,
        "RepositoryDataSource",
        lambda data_dir: source,
    )
    monkeypatch.setattr(
        model_study_module,
        "run_model_study",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("research-model extra unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="research-model extra"):
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--start",
                source.sessions[0].isoformat(),
                "--end",
                source.sessions[-1].isoformat(),
                "--output",
                str(output),
                "--with-model",
            ]
        )

    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert manifest["finished_at"]
    assert manifest["model"]["status"] == "failed"
    assert "research-model extra unavailable" in manifest["model"]["error"]
    assert (output / "decisions.parquet").is_file()
    assert (output / "sessions.parquet").is_file()


def test_run_study_records_exit_variant_outcomes(tmp_path: Path):
    source = FakeDataSource()
    output = tmp_path / "exit-variants"
    config = StudyConfig(
        start=source.sessions[0],
        end=source.sessions[-1],
        rules=("E0",),
        exit_variants=DEFAULT_EXIT_VARIANTS[:2],
    )

    manifest = run_study(source, config, output)

    variants = pl.read_parquet(output / "exit_variants.parquet")
    assert variants.height == 2
    assert variants["variant"].to_list() == ["baseline", "time10"]
    assert variants["event_id"].n_unique() == 1
    assert variants["net_return"].null_count() == 0
    assert manifest["stats"]["exit_variant_rows"] == 2
