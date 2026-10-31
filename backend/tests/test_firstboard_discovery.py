from __future__ import annotations

import copy
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from app.backtest.stats_v2 import bh_fdr_qvalues
from app.custom.firstboard_discovery.discovery import score_factor, search_rules
from app.custom.firstboard_discovery.negative import (
    build_negative_research,
    fit_negative_model,
    predict_negative_risk,
)
from app.custom.firstboard_discovery.outcomes import build_event_samples
from app.custom.firstboard_discovery.service import (
    DiscoveryParams,
    FirstboardDiscoveryService,
)
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore
from app.factors.registry import FactorSpec
from app.tickflow.repository import DataStore, KlineRepository


def _panel(
    *,
    closes: list[float],
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    raw_opens: list[float] | None = None,
    raw_closes: list[float] | None = None,
    boards: list[int] | None = None,
    limit_prices: list[float | None] | None = None,
) -> pl.DataFrame:
    size = len(closes)
    start = date(2026, 1, 5)
    opens = opens or closes
    highs = highs or [max(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    lows = lows or [min(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    raw_opens = raw_opens or opens
    raw_closes = raw_closes or closes
    boards = boards or [0] * size
    return pl.DataFrame({
        "symbol": ["000001.SZ"] * size,
        "name": ["测试股"] * size,
        "date": [start + timedelta(days=index) for index in range(size)],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "raw_open": raw_opens,
        "raw_close": raw_closes,
        "consecutive_limit_ups": boards,
        "limit_up_price": limit_prices or [None] * size,
    })


def _event(panel: pl.DataFrame, **kwargs) -> dict:
    events = build_event_samples(panel, **kwargs)
    assert events.height == 1
    return events.row(0, named=True)


def test_outcomes_use_next_open_and_twenty_observed_sessions() -> None:
    closes = [10.0] + [10.5] * 19 + [11.0]
    opens = [10.0] + [10.0] * 20
    highs = [10.1] + [10.5] * 19 + [12.0]
    lows = [9.9] + [10.0] * 19 + [9.5]
    panel = _panel(
        closes=closes,
        opens=opens,
        highs=highs,
        lows=lows,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["entry_date"] == date(2026, 1, 6)
    assert row["entry_open"] == pytest.approx(10.0)
    assert row["sessions_observed"] == 20
    assert row["right_censored"] is False
    assert row["mfe_5d"] == pytest.approx(0.05)
    assert row["close_return_5d"] == pytest.approx(0.05)
    assert row["mae_5d"] == pytest.approx(0.0)
    assert row["mfe_10d"] == pytest.approx(0.05)
    assert row["close_return_10d"] == pytest.approx(0.05)
    assert row["mae_10d"] == pytest.approx(0.0)
    assert row["mfe_20d"] == pytest.approx(0.20)
    assert row["close_return_20d"] == pytest.approx(0.10)
    assert row["mae_20d"] == pytest.approx(-0.05)
    assert row["stop_touched"] is False
    assert row["strong"] is True


def test_early_fail_label_uses_only_the_first_five_entry_sessions() -> None:
    closes = [10.0] + [10.0] * 20
    opens = [10.0] * 21
    lows = [9.9, 9.0] + [10.0] * 19
    panel = _panel(
        closes=closes,
        opens=opens,
        lows=lows,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["mae_5d"] == pytest.approx(-0.10)
    assert row["early_fail_5d"] is True


def test_early_fail_includes_exact_eight_percent_touch_and_excludes_locked_entry() -> None:
    panel = _panel(
        closes=[10.0] * 21, lows=[9.9] + [9.2] * 20,
        boards=[1] + [0] * 20,
    )
    assert _event(panel)["early_fail_5d"] is True
    locked = panel.with_columns(pl.lit(10.0).alias("limit_up_price"))
    assert _event(locked)["early_fail_5d"] is None


def test_price_touch_after_five_sessions_is_not_early_fail() -> None:
    closes = [10.0] + [10.0] * 20
    opens = [10.0] * 21
    lows = [9.9] + [10.0] * 6 + [9.0] + [10.0] * 13
    panel = _panel(
        closes=closes,
        opens=opens,
        lows=lows,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["mae_5d"] == pytest.approx(0.0)
    assert row["mae_10d"] == pytest.approx(-0.10)
    assert row["early_fail_5d"] is False


def test_right_censored_event_is_not_labeled() -> None:
    panel = _panel(closes=[10.0] * 10, boards=[1] + [0] * 9)

    row = _event(panel)

    assert row["sessions_observed"] == 9
    assert row["right_censored"] is True
    assert row["mfe_5d"] == pytest.approx(0.0)
    assert row["close_return_5d"] == pytest.approx(0.0)
    assert row["mae_5d"] == pytest.approx(0.0)
    assert row["mfe_10d"] is None
    assert row["close_return_10d"] is None
    assert row["mae_10d"] is None
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_limit_locked_entry_is_excluded() -> None:
    panel = _panel(
        closes=[10.0] + [11.0] * 20,
        raw_opens=[10.0, 11.0] + [11.0] * 19,
        raw_closes=[10.0] + [11.0] * 20,
        boards=[1] + [0] * 20,
        limit_prices=[None, 11.0] + [None] * 19,
    )

    row = _event(panel)

    assert row["entry_limit_locked"] is True
    assert row["strong"] is None


def test_future_rows_do_not_change_an_earlier_event() -> None:
    base = _panel(closes=[10.0] * 21, boards=[1] + [0] * 20)
    changed = base.with_columns(
        pl.when(pl.int_range(pl.len()) > 20)
        .then(pl.col("close") * 100)
        .otherwise(pl.col("close"))
        .alias("close")
    )

    before = build_event_samples(base)
    after = build_event_samples(changed)

    assert before.equals(after)


def test_scale_break_inside_outcome_window_is_flagged() -> None:
    panel = _panel(
        closes=[10.0] + [10.0] * 20,
        raw_closes=[10.0] * 10 + [20.0] * 11,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["scale_break_suspected"] is True
    assert row["strong"] is None


def test_invalid_price_inside_twenty_day_window_is_accounted() -> None:
    panel = _panel(
        closes=[10.0] * 21,
        highs=[10.1] + [10.5] * 19 + [None],
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["right_censored"] is False
    assert row["outcome_unavailable"] is True
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_score_factor_uses_rank_auc_direction_and_missing_values() -> None:
    perfect = score_factor(
        "f",
        "D_close",
        [1, 2, 3, 4],
        [False, False, True, True],
    )
    inverse = score_factor(
        "f",
        "D_close",
        [4, 3, 2, 1],
        [False, False, True, True],
    )
    with_missing = score_factor(
        "f",
        "D_close",
        [1, 2, None, 4],
        [False, False, True, True],
    )

    assert perfect.auc == pytest.approx(1.0)
    assert perfect.direction == "high"
    assert inverse.auc == pytest.approx(0.0)
    assert inverse.direction == "low"
    assert with_missing.coverage == pytest.approx(0.75)
    assert with_missing.train_count == 3


def test_bh_fdr_qvalues_ignores_missing_hypotheses() -> None:
    values = bh_fdr_qvalues([0.01, 0.04, None])

    assert values[0] == pytest.approx(0.02)
    assert values[1] == pytest.approx(0.04)
    assert values[2] is None


def _rule_events(
    *,
    train_count: int = 120,
    validation_count: int = 40,
) -> pl.DataFrame:
    total = train_count + validation_count
    values = [index / max(total - 1, 1) for index in range(total)]
    returns = [value - 0.5 for value in values]
    return pl.DataFrame({
        "date": [date(2026, 1, 1) + timedelta(days=index) for index in range(total)],
        "strong": [value >= 0.5 for value in values],
        "mfe_5d": [0.12 if value >= 0.5 else 0.03 for value in values],
        "close_return_5d": [0.04 if value >= 0.5 else -0.01 for value in values],
        "mae_5d": [-0.01] * total,
        "mfe_10d": [0.20 if value >= 0.5 else 0.04 for value in values],
        "close_return_10d": [0.06 if value >= 0.5 else -0.02 for value in values],
        "mae_10d": [-0.02] * total,
        "mfe_20d": [0.30 if value >= 0.5 else 0.05 for value in values],
        "close_return_20d": returns,
        "mae_20d": [-0.03] * total,
        "D_close__f_good": values,
    })


def test_rule_search_selects_on_training_dates_only() -> None:
    events = _rule_events()
    train_end = events["date"][119]
    original = search_rules(
        events,
        [("f_good", "D_close")],
        train_end=train_end,
        base_rate=0.5,
    )
    changed_validation = events.with_columns(
        pl.when(pl.int_range(pl.len()) >= 120)
        .then(1.0 - pl.col("D_close__f_good"))
        .otherwise(pl.col("D_close__f_good"))
        .alias("D_close__f_good")
    )
    after = search_rules(
        changed_validation,
        [("f_good", "D_close")],
        train_end=train_end,
        base_rate=0.5,
    )

    assert original
    assert original[0]["conditions"] == after[0]["conditions"]
    assert original[0]["train_strong_rate"] > 0.8
    assert "validation_strong_rate" in original[0]
    assert "lift" in original[0]
    assert "validation_lift" in original[0]
    assert "mean_mfe_5d" in original[0]
    assert "mean_close_return_10d" in original[0]
    assert "mean_mae_20d" in original[0]


def test_rule_search_rejects_insufficient_training_support() -> None:
    too_small = _rule_events(train_count=20, validation_count=40)

    assert search_rules(
        too_small,
        [("f_good", "D_close")],
        train_end=too_small["date"][19],
        base_rate=0.5,
    ) == []


def test_rule_search_marks_sparse_validation_without_reselecting() -> None:
    too_few_validation = _rule_events(train_count=120, validation_count=10)

    rules = search_rules(
        too_few_validation,
        [("f_good", "D_close")],
        train_end=too_few_validation["date"][119],
        base_rate=0.5,
    )

    assert rules
    assert all(rule["validation_eligible"] is False for rule in rules)


def _risk_events(
    *, train_count: int = 240, validation_count: int = 80,
) -> pl.DataFrame:
    total = train_count + validation_count
    rng = np.random.default_rng(20261030)
    early_fail = rng.random(total) < 0.42
    risk = early_fail.astype(float) + rng.normal(0.0, 0.55, total)
    unrelated = rng.normal(0.0, 1.0, total)
    return pl.DataFrame({
        "date": [
            date(2026, 1, 1) + timedelta(days=index)
            for index in range(total)
        ],
        "strong": [index % 2 == 0 for index in range(total)],
        "early_fail_5d": early_fail.tolist(),
        "D_close__risk": risk.tolist(),
        "D_close__unrelated": unrelated.tolist(),
    })


def _dense_risk_events(*, days: int = 32, per_day: int = 12) -> pl.DataFrame:
    rng = np.random.default_rng(20261030)
    total = days * per_day
    early_fail = rng.random(total) < 0.42
    risk = early_fail.astype(float) + rng.normal(0.0, 0.55, total)
    return pl.DataFrame({
        "date": [
            date(2026, 1, 1) + timedelta(days=day)
            for day in range(days)
            for _ in range(per_day)
        ],
        "strong": [index % 2 == 0 for index in range(total)],
        "early_fail_5d": early_fail.tolist(),
        "D_close__risk": risk.tolist(),
        "D_minus_1__boll_width": [
            0.5 if index % 2 == 0 else 0.4 for index in range(total)
        ],
        **{
            f"{metric}_{horizon}d": [value] * total
            for horizon in (5, 10, 20)
            for metric, value in (
                ("mfe", 0.15), ("close_return", 0.01), ("mae", -0.05),
            )
        },
    })


def test_negative_model_selects_on_training_early_fail_only() -> None:
    events = _risk_events()
    train_end = events["date"][239]
    model = fit_negative_model(
        events,
        [("risk", "D_close"), ("unrelated", "D_close")],
        train_end=train_end,
    )
    scores = predict_negative_risk(events, model)

    assert model["status"] == "ok"
    assert [feature["factor_id"] for feature in model["features"]] == ["risk"]
    assert model["train_auc"] > 0.70
    assert 0.0 < model["decision_threshold"] < 1.0
    assert scores.shape == (events.height,)
    labels = events["early_fail_5d"].to_numpy()
    assert scores[labels].mean() > scores[~labels].mean()

    changed_validation = events.with_columns(
        pl.when(pl.col("date") > train_end)
        .then(1.0 - pl.col("D_close__risk"))
        .otherwise(pl.col("D_close__risk"))
        .alias("D_close__risk")
    )
    refit = fit_negative_model(
        changed_validation,
        [("risk", "D_close"), ("unrelated", "D_close")],
        train_end=train_end,
    )

    assert [feature["factor_id"] for feature in refit["features"]] == ["risk"]
    assert refit["intercept"] == pytest.approx(model["intercept"])
    assert refit["decision_threshold"] == pytest.approx(model["decision_threshold"])
    assert [feature["coefficient"] for feature in refit["features"]] == pytest.approx(
        [feature["coefficient"] for feature in model["features"]],
    )


def test_negative_model_deduplicates_and_keeps_missing_risk_unknown() -> None:
    events = _risk_events().with_columns(
        (pl.col("D_close__risk") * 2).alias("D_close__risk_copy"),
    )
    model = fit_negative_model(
        events, [("risk", "D_close"), ("risk_copy", "D_close")],
        train_end=events["date"][239],
    )
    assert len(model["features"]) == 1
    missing = events.head(1).with_columns(
        pl.lit(None, dtype=pl.Float64).alias(model["features"][0]["column"]),
    )
    assert np.isnan(predict_negative_risk(missing, model)[0])


def test_negative_model_purges_fit_labels_overlapping_calibration() -> None:
    events = _risk_events().with_columns(
        (pl.col("date") + timedelta(days=20)).alias("outcome_end"),
    )
    model = fit_negative_model(
        events, [("risk", "D_close")], train_end=events["date"][239],
    )
    assert model["status"] == "ok"
    assert model["fit_outcome_end"] < model["calibration_start"]
    changed = events.with_columns(
        pl.when(pl.col("date") > events["date"][239])
        .then(~pl.col("early_fail_5d"))
        .otherwise(pl.col("early_fail_5d")).alias("early_fail_5d"),
    )
    assert fit_negative_model(
        changed, [("risk", "D_close")], train_end=events["date"][239],
    ) == model


def test_negative_research_compares_four_paired_cohorts_and_opportunity_loss() -> None:
    events = _risk_events().with_columns(
        pl.lit(0.5).alias("D_minus_1__boll_width"),
        *[pl.lit(value).alias(f"{metric}_{horizon}d")
          for horizon in (5, 10, 20)
          for metric, value in (("mfe", 0.15), ("close_return", 0.01), ("mae", -0.05))],
    )
    report = build_negative_research(
        events.head(240), events.tail(80), [("risk", "D_close")],
        train_end=events["date"][239],
    )
    assert report["status"] == "ok"
    groups = {row["id"]: row for row in report["groups"]}
    assert set(groups) == {"baseline", "main_only", "negative_only", "combined"}
    assert groups["baseline"]["count"] == 80
    assert groups["combined"]["count"] < groups["main_only"]["count"]
    assert (
        groups["combined"]["early_fail_rate"]
        < groups["main_only"]["early_fail_rate"]
    )
    assert 0 <= report["main_strong_retention"] <= 1
    assert "early_fail_difference_95" in report["combined_vs_main"]
    assert "mean_close_return_10d" in groups["combined"]
    assert report["bootstrap"]["unit"] == "moving_block_event_date"


def test_negative_research_reports_unavailable_main_and_insufficient_model() -> None:
    events = _risk_events()
    missing = build_negative_research(
        events.head(240), events.tail(80), [("risk", "D_close")],
        train_end=events["date"][239],
    )
    assert missing["status"] == "main_feature_unavailable"
    assert missing["groups"] == []
    sparse = build_negative_research(
        events.head(20), events.tail(80), [("risk", "D_close")],
        train_end=events["date"][19],
    )
    assert sparse["status"] == "insufficient_sample"
    assert sparse["groups"] == []


def test_negative_research_marks_short_period_bootstrap_unsupported() -> None:
    events = _dense_risk_events()

    report = build_negative_research(
        events.head(240),
        events.filter(pl.col("date") > events["date"][239]),
        [("risk", "D_close")],
        train_end=events["date"][239],
    )

    assert report["status"] == "ok"
    assert report["bootstrap"]["status"] == "insufficient_temporal_support"
    assert report["combined_vs_main"]["early_fail_difference_95"] is None
    assert report["combined_vs_main"]["early_fail_valid_draws"] == 0
    assert report["combined_vs_main"]["strong_difference_95"] is None
    assert report["combined_vs_main"]["strong_valid_draws"] == 0


class _FakeEngine:
    def __init__(self, panel: pl.DataFrame, generation: str = "gen-1") -> None:
        self.panel = panel
        self.generation = generation
        self.load_calls = 0

    def data_generation(self, asset_type: str = "stock") -> str:
        assert asset_type == "stock"
        return self.generation

    def load_panel(self, *_args, **_kwargs) -> pl.DataFrame:
        self.load_calls += 1
        return self.panel


class _FakeRepository:
    def get_instruments_asset(self, asset_type: str = "stock") -> pl.DataFrame:
        assert asset_type == "stock"
        return pl.DataFrame()

    def get_historical_shares(self) -> None:
        return None


class _TestDiscoveryService(FirstboardDiscoveryService):
    def _candidate_factor_columns(self, snapshot_mode: str) -> list[tuple[str, str]]:
        del snapshot_mode
        return [("momentum_5d", "D_close")]

    def _materialize_factors(
        self,
        panel: pl.DataFrame,
        factor_ids: set[str],
    ) -> pl.DataFrame:
        assert factor_ids == {"momentum_5d"}
        return panel

    def _attach_limit_prices(self, panel: pl.DataFrame) -> pl.DataFrame:
        return panel

    def _market_sessions(self, panel: pl.DataFrame) -> list[date]:
        return sorted(set(panel["date"].to_list()))


def _sample_accounting_panel() -> pl.DataFrame:
    size = 24
    start = date(2026, 1, 5)
    boards = [0] * size
    for index in (0, 1, 2, 3, 23):
        boards[index] = 1
    return pl.DataFrame({
        "symbol": ["000001.SZ"] * size,
        "name": ["测试股"] * size,
        "date": [start + timedelta(days=index) for index in range(size)],
        "open": [10.0] * size,
        "high": [10.5] * size,
        "low": [9.8] * size,
        "close": [10.0] * size,
        "raw_open": [10.0] * size,
        "raw_close": [10.0] * size,
        "consecutive_limit_ups": boards,
        "momentum_5d": [index / size for index in range(size)],
    })


def test_report_excludes_ineligible_events_and_returns_sample_accounting() -> None:
    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    report = service.report(params)

    assert report["sample"]["total_events"] == 5
    assert report["sample"]["eligible_events"] == 4
    assert report["sample"]["excluded"]["right_censored"] == 1
    assert report["split"]["train_end"] < report["split"]["validation_start"]
    assert report["sample"]["status"] == "insufficient_sample"


def test_single_event_date_preserves_training_cohort_without_validation() -> None:
    start = date(2026, 1, 5)
    rows = []
    for index in range(100):
        symbol = f"{index:06d}.SZ"
        for offset in range(21):
            rows.append({
                "symbol": symbol,
                "name": f"样本{index}",
                "date": start + timedelta(days=offset),
                "open": 10.0,
                "high": 13.0 if offset > 0 else 10.5,
                "low": 9.8,
                "close": 10.0,
                "raw_open": 10.0,
                "raw_close": 10.0,
                "consecutive_limit_ups": 1 if offset == 0 else 0,
                "momentum_5d": (index % 10) / 9,
            })
    panel = pl.DataFrame(rows)
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=start, end=start, snapshot_mode="D_close")

    report = service.report(params)
    rows = service.events(params, page_size=200)["rows"]

    assert report["sample"]["eligible_events"] == 100
    assert report["split"]["train_count"] == 100
    assert report["split"]["purged_count"] == 0
    assert report["split"]["validation_count"] == 0
    assert report["factors"]
    assert all(row["split"] == "train" for row in rows)


def test_report_uses_selected_dates_without_a_historical_cutoff() -> None:
    panel = _sample_accounting_panel().with_columns(
        (pl.col("date") + timedelta(days=270)).alias("date"),
    )
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )
    report = service.report(params)
    rows = service.events(params, page_size=50)["rows"]

    assert report["sample"]["total_events"] == 5
    assert report["lockbox_excluded_count"] == 0
    assert report["research_cutoff"] == params.end
    assert report["negative_research"]["evaluation_cutoff"] == params.end
    assert report["negative_research"]["model"]["train_end"] == report["split"]["train_end"]
    assert min(row["date"] for row in rows) >= date(2026, 10, 1)


@pytest.mark.parametrize("empty_events", [False, True])
def test_report_data_as_of_is_latest_loaded_market_date(empty_events) -> None:
    panel = _sample_accounting_panel()
    if empty_events:
        panel = panel.with_columns(pl.lit(0).alias("consecutive_limit_ups"))
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=panel["date"][0], end=panel["date"][3])

    report = service.report(params)

    assert report["data_as_of"] == panel["date"].max()


def test_latest_database_recomputes_and_saved_results_remain_readable(tmp_path) -> None:
    panel = _sample_accounting_panel()
    engine = _FakeEngine(panel)
    store = FirstboardDiscoveryStore(tmp_path)
    service = _TestDiscoveryService(_FakeRepository(), engine=engine, storage=store)
    params = DiscoveryParams(start=panel["date"][0], end=panel["date"][-1])
    original = service.report(params)
    original_rows = service.saved_events(original["run_id"])["rows"]
    engine.panel = panel.with_columns(pl.lit(12.0).alias("high"))
    engine.generation = "corrected-db"

    corrected = service.report(params)

    assert corrected["generation"] == "corrected-db"
    assert corrected["run_id"] != original["run_id"]
    assert service.saved_events(original["run_id"])["rows"] == original_rows
    corrected_rows = service.saved_events(corrected["run_id"])["rows"]
    assert corrected_rows != original_rows
    repeated = _TestDiscoveryService(
        _FakeRepository(), engine=_FakeEngine(engine.panel, generation="corrected-db"),
    )
    assert repeated.events(params)["rows"] == corrected_rows


def _discoverable_panel(event_count: int = 600) -> pl.DataFrame:
    rows: list[dict] = []
    start = date(2025, 1, 1)
    for index in range(event_count):
        symbol = f"{index:06d}.SZ"
        event_date = start + timedelta(days=index)
        strong = index % 10 >= 5
        for offset in range(21):
            rows.append({
                "symbol": symbol,
                "name": f"样本{index}",
                "date": event_date + timedelta(days=offset),
                "open": 10.0,
                "high": 10.5 if offset == 0 else (12.0 if strong else 10.2),
                "low": 9.8,
                "close": 10.0 if offset == 0 else (11.0 if strong else 10.0),
                "raw_open": 10.0,
                "raw_close": 10.0 if offset == 0 else (11.0 if strong else 10.0),
                "consecutive_limit_ups": 1 if offset == 0 else 0,
                "momentum_5d": (index % 10) / 9,
            })
    return pl.DataFrame(rows)


def test_events_endpoint_paginates_and_filters_by_rule() -> None:
    panel = _discoverable_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"].min(),
        end=panel["date"].max(),
        snapshot_mode="D_close",
    )

    report = service.report(params)
    assert report["rules"]
    rule_id = report["rules"][0]["id"]
    payload = service.events(params, rule_id=rule_id, page=1, page_size=2)

    assert payload["page_size"] == 2
    assert len(payload["rows"]) == 2
    assert payload["total"] >= 2
    assert all(rule_id in row["rule_ids"] for row in payload["rows"])
    assert "mfe_5d" in payload["rows"][0]
    assert "close_return_10d" in payload["rows"][0]
    assert "mae_20d" in payload["rows"][0]


def test_training_snapshot_is_persisted_and_reopenable(tmp_path) -> None:
    panel = _sample_accounting_panel()
    store = FirstboardDiscoveryStore(tmp_path)
    service = _TestDiscoveryService(
        _FakeRepository(), engine=_FakeEngine(panel), storage=store,
    )
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    report = service.report(params)
    run_id = report["run_id"]
    assert run_id
    assert report["saved_at"]

    reopened = FirstboardDiscoveryService(
        _FakeRepository(), engine=_FakeEngine(panel.head(0)), storage=store,
    )
    runs = reopened.list_runs()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["event_count"] == report["sample"]["total_events"]
    assert reopened.saved_report(run_id)["sample"] == report["sample"]
    events = reopened.saved_events(run_id, page_size=200)
    assert events["total"] == report["sample"]["total_events"]
    assert len(events["rows"]) == events["total"]


def test_negative_research_and_event_predictions_survive_saved_report(tmp_path) -> None:
    class RiskService(_TestDiscoveryService):
        def _candidate_factor_columns(self, snapshot_mode):
            return [("momentum_5d", "D_close"), ("boll_width", "D_minus_1")]

        def _materialize_factors(self, panel, factor_ids):
            return panel

    panel = _discoverable_panel().with_columns(
        pl.when(pl.col("momentum_5d") >= 0.7).then(9.0).otherwise(9.8).alias("low"),
        pl.lit(0.5).alias("boll_width"),
    )
    before = panel.filter(pl.col("consecutive_limit_ups") == 1).with_columns(
        (pl.col("date") - timedelta(days=1)).alias("date"),
        pl.lit(0, dtype=pl.Int64).alias("consecutive_limit_ups"),
    )
    panel = pl.concat([before, panel])
    service = RiskService(
        _FakeRepository(), engine=_FakeEngine(panel),
        storage=FirstboardDiscoveryStore(tmp_path),
    )
    params = DiscoveryParams(start=panel["date"].min(), end=panel["date"].max())
    report = service.report(params)
    negative = report["negative_research"]
    assert negative["status"] == "ok"
    assert len(negative["groups"]) == 4
    assert service.saved_report(report["run_id"])["negative_research"]["model"]["features"]
    rows = service.saved_events(report["run_id"], page_size=50)["rows"]
    assert all("early_fail_5d" in row for row in rows)
    assert all(0 <= row["early_fail_probability"] <= 1 for row in rows)
    assert all(isinstance(row["negative_veto"], bool) for row in rows)
    assert all(row["frozen_main_hit"] is True for row in rows)


def _saved_negative_study_events() -> pl.DataFrame:
    events = _risk_events().rename({"D_close__risk": "D_close__momentum_5d"})
    events = events.with_columns(
        pl.col("date").cast(pl.String).alias("event_id"),
        pl.lit(0.5).alias("D_minus_1__boll_width"),
        pl.lit(False).alias("entry_unavailable"),
        pl.lit(False).alias("entry_limit_locked"),
        pl.lit(False).alias("right_censored"),
        pl.lit(False).alias("outcome_unavailable"),
        pl.lit(False).alias("scale_break_suspected"),
        (pl.col("date") + timedelta(days=20)).alias("outcome_end"),
        *[pl.lit(value).alias(f"{metric}_{horizon}d")
          for horizon in (5, 10, 20)
          for metric, value in (("mfe", 0.15), ("close_return", 0.01), ("mae", -0.05))],
    ).with_columns(
        pl.when(pl.col("early_fail_5d")).then(-0.1).otherwise(-0.02).alias("mae_5d"),
        pl.when(pl.int_range(pl.len()) < 120)
        .then(None)
        .otherwise(pl.col("D_close__momentum_5d"))
        .alias("D_minus_1__late_factor"),
        pl.when(pl.col("early_fail_5d"))
        .then(1.0)
        .otherwise(0.0)
        .alias("D_close__future_leak"),
    ).drop("early_fail_5d")
    return events.with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(None)
        .otherwise(pl.col("strong"))
        .alias("strong"),
        pl.when(pl.int_range(pl.len()) == 0)
        .then(True)
        .otherwise(pl.col("entry_unavailable"))
        .alias("entry_unavailable"),
    )


def _saved_negative_study_source(events: pl.DataFrame) -> dict:
    from app.custom.firstboard_discovery.service import (
        _CANDIDATE_POLICY,
        ALGORITHM_VERSION,
    )

    train_end = events["date"][199]
    validation_start = events["date"][200]
    source = {
        "algorithm_version": ALGORITHM_VERSION, "generation": "frozen-generation",
        "params": {"start": "2026-01-01", "end": "2026-11-16", "snapshot_mode": "both"},
        "sample": {"status": "ok", "total_events": events.height},
        "factors": [
            {
                "factor_id": "boll_width", "snapshot": "D_minus_1",
                "label": "布林带宽", "validation_auc": 0.11,
                "validation_coverage": 0.11, "validation_count": 999,
            },
            {
                "factor_id": "momentum_5d", "snapshot": "D_close",
                "label": "动量", "validation_auc": 0.22,
                "validation_coverage": 0.22, "validation_count": 999,
            },
        ],
        "rules": [{
            "id": "fbr_contract_test",
            "conditions": [{
                "factor_id": "momentum_5d", "snapshot": "D_close",
                "operator": ">=", "threshold": 0.7,
            }],
            "dimension": 1,
            "validation_hits": 999,
            "validation_strong_rate": 0.99,
            "validation_lift": 9.9,
            "validation_auc": 0.99,
            "mean_mfe_20d": 9.9,
        }],
        "candidate_policy": {
            **copy.deepcopy(_CANDIDATE_POLICY),
            "factor_count": 2,
        },
        "elapsed_ms": 1,
        "split": {
            "train_start": "1999-01-01",
            "train_end": str(train_end),
            "validation_start": str(validation_start),
            "validation_end": str(events["date"][-1]),
            "train_count": 1,
            "purged_count": 0,
            "validation_count": 777,
            "train_base_rate": 0.01,
            "validation_base_rate": 0.02,
        },
    }
    return source


def test_saved_negative_study_creates_new_run_without_modifying_source(tmp_path) -> None:
    from scripts.firstboard_negative_study import run_study

    events = _saved_negative_study_events()
    source = _saved_negative_study_source(events)
    store = FirstboardDiscoveryStore(tmp_path)
    source_id, _ = store.save(source, events.to_dicts())
    source_bytes = (store.root / source_id / "report.json").read_bytes()
    derived = run_study(tmp_path, source_id)
    assert derived["run_id"] != source_id
    assert derived["source_run_id"] == source_id
    assert derived["generation"] == "frozen-generation"
    assert derived["algorithm_version"] == "firstboard-negative-study-v4"
    assert derived["elapsed_ms"] > source["elapsed_ms"]
    assert derived["negative_research"]["status"] == "ok"
    assert len(derived["negative_research"]["groups"]) == 4
    assert all(
        feature["factor_id"] != "future_leak"
        for feature in derived["negative_research"]["model"]["features"]
    )
    assert derived["params"]["end"] == source["params"]["end"]
    cutoff = date.fromisoformat(source["params"]["end"])
    assert derived["split"]["validation_end"] == cutoff
    cutoff_events = events.filter(pl.col("date") <= cutoff)
    assert derived["sample"]["total_events"] == cutoff_events.height
    assert derived["sample"]["eligible_events"] == cutoff_events.height - 1
    assert derived["sample"]["excluded_events"] == 1
    assert derived["sample"]["excluded"]["entry_unavailable"] == 1
    assert derived["lockbox_excluded_count"] == events.height - cutoff_events.height
    assert (store.root / source_id / "report.json").read_bytes() == source_bytes
    saved_events = store.load_events(derived["run_id"])
    assert max(row["date"] for row in saved_events) == events["date"].max()
    assert max(row["date"] for row in saved_events) > date(2026, 10, 1)
    assert {row["mfe_20d"] for row in saved_events} == {0.15}


def test_saved_negative_study_applies_outer_purge_and_refreshes_clipped_stats(
    tmp_path,
) -> None:
    from scripts.firstboard_negative_study import _ensure_early_fail_label, run_study

    events = _ensure_early_fail_label(_saved_negative_study_events())
    source = _saved_negative_study_source(events)
    source["params"]["end"] = "2026-09-23"
    store = FirstboardDiscoveryStore(tmp_path)
    source_id, _ = store.save(source, events.to_dicts())

    derived = run_study(tmp_path, source_id)

    train_end = date.fromisoformat(source["split"]["train_end"])
    validation_start = date.fromisoformat(source["split"]["validation_start"])
    cutoff = date(2026, 9, 23)
    cutoff_events = events.filter(pl.col("date") <= cutoff)
    eligible = cutoff_events.filter(pl.col("strong").is_not_null())
    unpurged_train = eligible.filter(pl.col("date") <= train_end)
    train = unpurged_train.filter(pl.col("outcome_end") < validation_start)
    validation = eligible.filter(pl.col("date") >= validation_start)
    expected_model = fit_negative_model(
        train,
        [("boll_width", "D_minus_1"), ("momentum_5d", "D_close")],
        train_end=train_end,
    )

    assert derived["split"]["train_start"] == train["date"].min()
    assert derived["split"]["train_count"] == train.height
    assert derived["split"]["purged_count"] == unpurged_train.height - train.height
    assert derived["split"]["validation_count"] == validation.height
    assert derived["split"]["train_base_rate"] == pytest.approx(train["strong"].mean())
    assert derived["split"]["validation_base_rate"] == pytest.approx(
        validation["strong"].mean(),
    )
    assert derived["negative_research"]["model"]["fit_count"] == expected_model["fit_count"]
    factor = next(
        row for row in derived["factors"]
        if row["factor_id"] == "momentum_5d" and row["snapshot"] == "D_close"
    )
    expected_score = score_factor(
        "momentum_5d",
        "D_close",
        validation["D_close__momentum_5d"].to_list(),
        validation["strong"].to_list(),
    )
    assert factor["validation_count"] == expected_score.train_count
    assert factor["validation_coverage"] == pytest.approx(expected_score.coverage)
    assert factor["validation_auc"] == pytest.approx(expected_score.auc)
    rule = derived["rules"][0]
    rule_hits = validation.filter(
        pl.col("D_close__momentum_5d").is_finite()
        & (pl.col("D_close__momentum_5d") >= 0.7),
    )
    assert rule["validation_hits"] == rule_hits.height
    assert rule["validation_strong_rate"] == pytest.approx(rule_hits["strong"].mean())
    assert rule["mean_mfe_20d"] == pytest.approx(rule_hits["mfe_20d"].mean())


def test_saved_study_retains_selected_dates_after_last_complete_outcome(tmp_path) -> None:
    from scripts.firstboard_negative_study import run_study

    events = _saved_negative_study_events()
    last_complete = date(2026, 9, 24)
    events = events.with_columns(
        pl.when(pl.col("date") > last_complete)
        .then(None).otherwise(pl.col("strong")).alias("strong"),
        (pl.col("date") > last_complete).alias("right_censored"),
    )
    source = _saved_negative_study_source(events)
    source["split"]["validation_end"] = last_complete.isoformat()
    store = FirstboardDiscoveryStore(tmp_path)
    source_id, _ = store.save(source, events.to_dicts())

    derived = run_study(tmp_path, source_id)

    assert derived["sample"]["total_events"] == events.height
    assert derived["split"]["validation_end"] == last_complete
    assert derived["params"]["end"] == source["params"]["end"]
    assert max(row["date"] for row in store.load_events(derived["run_id"])) == events["date"].max()
    assert derived["lockbox_excluded_count"] == 0


def test_saved_negative_study_rejects_unknown_source_contract(tmp_path) -> None:
    from scripts.firstboard_negative_study import run_study

    events = _saved_negative_study_events()
    store = FirstboardDiscoveryStore(tmp_path)
    unsupported = _saved_negative_study_source(events)
    unsupported["algorithm_version"] = "firstboard-discovery-v2"
    unsupported_id, _ = store.save(unsupported, events.to_dicts())
    mismatched = _saved_negative_study_source(events)
    mismatched["candidate_policy"]["allowed_kinds"].append("custom")
    mismatched_id, _ = store.save(mismatched, events.to_dicts())

    with pytest.raises(ValueError, match="来源算法版本"):
        run_study(tmp_path, unsupported_id)
    with pytest.raises(ValueError, match="候选策略"):
        run_study(tmp_path, mismatched_id)


@pytest.mark.parametrize(
    "version", ["firstboard-discovery-v3", "firstboard-discovery-v5"],
)
def test_saved_negative_study_accepts_legacy_policy_without_extension(
    tmp_path, version,
) -> None:
    from scripts.firstboard_negative_study import run_study

    events = _saved_negative_study_events()
    store = FirstboardDiscoveryStore(tmp_path)
    legacy = _saved_negative_study_source(events)
    legacy["algorithm_version"] = version
    legacy["candidate_policy"].pop("allowed_extension_factor_ids")
    legacy_id, _ = store.save(legacy, events.to_dicts())

    derived = run_study(tmp_path, legacy_id)

    assert derived["source_algorithm_version"] == version
    assert "allowed_extension_factor_ids" not in derived["candidate_policy"]


def test_store_infers_late_float_columns_across_all_event_rows(tmp_path) -> None:
    store = FirstboardDiscoveryStore(tmp_path)
    report = {
        "algorithm_version": "test", "generation": "gen", "params": {},
        "sample": {"status": "ok"}, "split": {}, "factors": [], "rules": [],
        "elapsed_ms": 1.0,
    }
    events = [
        {"event_id": "a", "mfe_5d": None},
        {"event_id": "b", "mfe_5d": 0.08},
    ]

    run_id, _ = store.save(report, events)
    loaded = store.load_events(run_id)

    assert loaded[0]["mfe_5d"] is None
    assert loaded[1]["mfe_5d"] == pytest.approx(0.08)


def test_store_filters_events_before_returning_an_observed_window(tmp_path) -> None:
    store = FirstboardDiscoveryStore(tmp_path)
    report = {
        "algorithm_version": "test", "generation": "gen", "params": {},
        "sample": {"status": "ok"}, "split": {}, "factors": [], "rules": [],
        "elapsed_ms": 1.0,
    }
    events = [
        {"event_id": "before", "date": date(2026, 9, 23), "value": 1.0},
        {"event_id": "after", "date": date(2026, 10, 1), "value": 2.0},
    ]
    run_id, _ = store.save(report, events)

    loaded = store.load_events(run_id, end_date=date(2026, 9, 23))

    assert loaded == [{"event_id": "before", "date": date(2026, 9, 23), "value": 1.0}]


def test_store_normalizes_legacy_json_event_dates(tmp_path) -> None:
    import gzip
    import json

    store = FirstboardDiscoveryStore(tmp_path)
    run_id = "legacy-json-run"
    run_dir = store.root / run_id
    run_dir.mkdir(parents=True)
    rows = [
        {
            "event_id": "before",
            "date": "2026-09-23",
            "entry_date": "2026-09-24",
            "outcome_end": "2026-10-20",
            "value": 1.0,
        },
        {
            "event_id": "after",
            "date": "2026-10-01",
            "entry_date": "2026-10-02",
            "outcome_end": "2026-10-30",
            "value": 2.0,
        },
    ]
    with gzip.open(run_dir / "events.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    loaded = store.load_events(run_id, end_date=date(2026, 9, 23))

    assert loaded == [{
        "event_id": "before",
        "date": date(2026, 9, 23),
        "entry_date": date(2026, 9, 24),
        "outcome_end": date(2026, 10, 20),
        "value": 1.0,
    }]


def test_service_rejects_data_generation_change() -> None:
    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    def changed(generation: str) -> None:
        raise RuntimeError("generation changed") from None

    service._assert_generation = changed  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="generation changed"):
        service.report(params)


@pytest.mark.parametrize("stage", ["generation", "load", "after_load"])
def test_service_retries_transient_database_updates(stage, tmp_path) -> None:
    from app.enriched_generation import EnrichedGenerationUnavailableError

    class UpdatingEngine(_FakeEngine):
        triggered = False

        def data_generation(self, asset_type="stock"):
            if stage == "generation" and not self.triggered:
                self.triggered = True
                raise EnrichedGenerationUnavailableError("publication active")
            return super().data_generation(asset_type)

        def load_panel(self, *args, **kwargs):
            result = super().load_panel(*args, **kwargs)
            if stage in ("load", "after_load") and not self.triggered:
                self.triggered = True
                self.generation = "new-db"
                if stage == "load":
                    raise EnrichedGenerationUnavailableError("publication changed")
            return result

    panel = _sample_accounting_panel()
    engine = UpdatingEngine(panel)
    store = FirstboardDiscoveryStore(tmp_path)
    service = _TestDiscoveryService(_FakeRepository(), engine=engine, storage=store)
    params = DiscoveryParams(start=panel["date"][0], end=panel["date"][-1])

    report = service.report(params)

    assert engine.triggered
    assert report["generation"] == engine.generation
    assert report["sample"]["total_events"] == 5
    assert len(store.list_runs()) == 1
    assert engine.load_calls == (1 if stage == "generation" else 2)


def test_service_bounds_retries_when_database_keeps_updating(tmp_path) -> None:
    from app.enriched_generation import EnrichedGenerationUnavailableError

    class UpdatingEngine(_FakeEngine):
        def load_panel(self, *args, **kwargs):
            super().load_panel(*args, **kwargs)
            raise EnrichedGenerationUnavailableError("publication active")

    panel = _sample_accounting_panel()
    engine = UpdatingEngine(panel)
    store = FirstboardDiscoveryStore(tmp_path)
    service = _TestDiscoveryService(_FakeRepository(), engine=engine, storage=store)
    params = DiscoveryParams(start=panel["date"][0], end=panel["date"][-1])

    with pytest.raises(EnrichedGenerationUnavailableError, match="自动重试"):
        service.report(params)

    assert engine.load_calls == 3
    assert store.list_runs() == []


def test_database_update_after_inputs_are_read_does_not_cancel_calculation() -> None:
    class PublishingService(_TestDiscoveryService):
        def _materialize_factors(self, panel, factor_ids):
            self.engine.generation = "published-during-computation"
            return super()._materialize_factors(panel, factor_ids)

    panel = _sample_accounting_panel()
    engine = _FakeEngine(panel)
    service = PublishingService(_FakeRepository(), engine=engine)
    params = DiscoveryParams(start=panel["date"][0], end=panel["date"][-1])

    report = service.report(params)

    assert report["sample"]["total_events"] == 5
    assert report["generation"] == "gen-1"
    assert engine.load_calls == 1


def test_api_continuous_database_update_returns_retryable_unavailable(monkeypatch) -> None:
    from fastapi import HTTPException

    import app.custom.firstboard_discovery as extension
    from app.enriched_generation import EnrichedGenerationUnavailableError

    class UpdatingEngine(_FakeEngine):
        def load_panel(self, *args, **kwargs):
            super().load_panel(*args, **kwargs)
            raise EnrichedGenerationUnavailableError("publication active")

    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=UpdatingEngine(panel))
    monkeypatch.setattr(extension, "_service", service)

    with pytest.raises(HTTPException) as error:
        extension._call("report", panel["date"][0], panel["date"][-1], "both", 20, 0.2)

    assert error.value.status_code == 503
    assert "自动重试" in error.value.detail


def test_api_routes_validate_parameters_and_return_reports(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.custom.firstboard_discovery as extension
    from app.extensions import BackendExtensionRegistrar

    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    monkeypatch.setattr(extension, "_service", service, raising=False)
    registrar = BackendExtensionRegistrar("official.firstboard-discovery", api_version=1)
    extension.setup(registrar)
    app = FastAPI()
    for router in registrar.routers:
        app.include_router(router)
    client = TestClient(app)
    query = {"start": "2026-01-05", "end": "2026-01-28", "snapshot_mode": "D_close"}
    report = client.get("/api/custom/firstboard-discovery/report", params=query)
    assert report.status_code == 200
    assert report.json()["sample"]["eligible_events"] == 4
    assert client.get(
        "/api/custom/firstboard-discovery/report",
        params={**query, "start": "2026-02-01"},
    ).status_code == 400
    assert client.get(
        "/api/custom/firstboard-discovery/events",
        params={**query, "page_size": 201},
    ).status_code == 422
    monkeypatch.setattr(extension, "_service", None)
    assert client.get(
        "/api/custom/firstboard-discovery/report", params=query,
    ).status_code == 503


def test_saved_result_api_routes_list_and_reopen_runs(monkeypatch, tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.custom.firstboard_discovery as extension
    from app.extensions import BackendExtensionRegistrar

    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(
        _FakeRepository(),
        engine=_FakeEngine(panel),
        storage=FirstboardDiscoveryStore(tmp_path),
    )
    monkeypatch.setattr(extension, "_service", service, raising=False)
    registrar = BackendExtensionRegistrar("official.firstboard-discovery", api_version=1)
    extension.setup(registrar)
    app = FastAPI()
    for router in registrar.routers:
        app.include_router(router)
    client = TestClient(app)
    query = {"start": "2026-01-05", "end": "2026-01-28", "snapshot_mode": "D_close"}

    report = client.get("/api/custom/firstboard-discovery/report", params=query).json()
    run_id = report["run_id"]
    listed = client.get("/api/custom/firstboard-discovery/runs")
    reopened = client.get(f"/api/custom/firstboard-discovery/runs/{run_id}/report")
    events = client.get(
        f"/api/custom/firstboard-discovery/runs/{run_id}/events",
        params={"page_size": 200},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["run_id"] == run_id
    assert reopened.status_code == 200
    assert reopened.json()["run_id"] == run_id
    assert events.status_code == 200
    assert events.json()["total"] == report["sample"]["total_events"]
    assert client.get(
        "/api/custom/firstboard-discovery/runs/not-a-real-run/report",
    ).status_code == 404


def test_training_outcomes_end_strictly_before_validation() -> None:
    panel = _discoverable_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=panel["date"].min(), end=panel["date"].max())
    report = service.report(params)
    rows = service.events(params, page_size=200)["rows"]
    validation_start = date.fromisoformat(str(report["split"]["validation_start"]))
    assert report["split"]["purged_count"] > 0
    assert all(row["outcome_end"] < validation_start for row in rows if row["split"] == "train")


def test_stock_suspension_does_not_move_t_plus_one_to_a_later_session() -> None:
    a = _panel(closes=[10.] * 23, boards=[1] + [0] * 22)
    b = a.with_columns(pl.lit("000002.SZ").alias("symbol"), pl.lit(0, dtype=pl.Int64).alias("consecutive_limit_ups"))
    a = a.filter(pl.col("date") != date(2026, 1, 6))
    row = build_event_samples(pl.concat([a, b])).row(0, named=True)
    assert row["entry_unavailable"] is True
    assert row["strong"] is None


def test_missing_symbol_days_are_reported_as_outcome_unavailable() -> None:
    complete = _panel(closes=[10.] * 21, boards=[0] * 21)
    event_symbol = _panel(closes=[10.] * 21, boards=[1] + [0] * 20).head(11)
    other_symbol = complete.with_columns(
        pl.lit("000002.SZ").alias("symbol"),
    )

    row = build_event_samples(pl.concat([event_symbol, other_symbol])).row(0, named=True)

    assert row["right_censored"] is False
    assert row["entry_unavailable"] is False
    assert row["outcome_unavailable"] is True
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_missing_market_session_prevents_calendar_shift_of_t_plus_one() -> None:
    panel = _panel(closes=[10.0] * 22, boards=[1] + [0] * 21).filter(
        pl.col("date") != date(2026, 1, 6),
    )
    market_sessions = sorted(
        set(panel["date"].to_list()) | {date(2026, 1, 6)},
    )

    row = build_event_samples(panel, sessions=market_sessions).row(0, named=True)

    assert row["entry_unavailable"] is True
    assert row["strong"] is None


def test_tercile_rules_partition_finite_values_without_overlap() -> None:
    from app.custom.firstboard_discovery.discovery import _candidate_mask

    events = pl.DataFrame({"v": [0., 1., 2., 3., None, float("nan")]})
    groups = [
        _candidate_mask(events, [("v", "bucket", (1., 2., bucket))])["v"].to_list()
        for bucket in range(3)
    ]
    assert groups == [[0.], [1.], [2., 3.]]


def test_event_response_contains_no_nan_for_missing_factor_values() -> None:
    import json

    panel = _sample_accounting_panel().with_columns(
        pl.lit(float("nan")).alias("momentum_5d"),
    )
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=panel["date"].min(), end=panel["date"].max())
    payload = service.events(params)
    assert payload["rows"][0]["D_close__momentum_5d"] is None
    json.dumps(payload, default=str, allow_nan=False)


def test_candidate_policy_rejects_custom_mixed_price_raw_scale_and_experimental(
    monkeypatch,
) -> None:
    import app.custom.firstboard_discovery.service as service_module

    specs = [
        FactorSpec(
            id="safe_virtual",
            label="安全虚拟因子",
            group="测试",
            formula_text="close / ma20",
            kind="virtual",
            dependencies=frozenset({"close", "ma20"}),
            scale_free=True,
        ),
        FactorSpec(
            id="vwap_bias",
            label="VWAP乖离",
            group="价格位置",
            formula_text="mix adjusted and raw prices",
            kind="virtual",
            dependencies=frozenset({"close", "amount", "volume"}),
            scale_free=True,
        ),
        FactorSpec(
            id="turnover_virtual",
            label="间接引用未认证换手率",
            group="量能",
            formula_text="turnover_rate / rolling_mean",
            kind="virtual",
            dependencies=frozenset({"turnover_rate"}),
            scale_free=True,
        ),
        FactorSpec(
            id="atr_pct_safe",
            label="ATR除以价格",
            group="波动率",
            formula_text="atr_14 / close",
            kind="virtual",
            dependencies=frozenset({"atr_14", "close"}),
            scale_free=True,
        ),
        FactorSpec(
            id="atr_14",
            label="ATR原值",
            group="波动率",
            formula_text="price units",
            kind="base",
            scale_free=False,
        ),
        FactorSpec(
            id="uf_forward",
            label="自定义未来函数",
            group="自定义",
            formula_text="ctx.col('close').shift(-1)",
            kind="custom",
            lang="python",
            dependencies=frozenset({"close"}),
        ),
        FactorSpec(
            id="experimental",
            label="实验因子",
            group="事件链",
            formula_text="experimental",
            kind="virtual",
            dependencies=frozenset({"close"}),
            stability="experimental",
        ),
    ]
    monkeypatch.setattr(service_module, "all_factors", lambda **_kwargs: specs)
    service = FirstboardDiscoveryService(
        _FakeRepository(),
        engine=_FakeEngine(_sample_accounting_panel()),
    )

    columns = service._candidate_factor_columns("both")

    assert columns == [
        ("safe_virtual", "D_minus_1"),
        ("safe_virtual", "D_close"),
        ("atr_pct_safe", "D_minus_1"),
        ("atr_pct_safe", "D_close"),
    ]


def test_candidate_policy_allows_only_the_limit_board_extension_whitelist(
    monkeypatch,
) -> None:
    import app.custom.firstboard_discovery.service as service_module

    first_seal = "ext_limit_board_events_first_seal_minute"
    observed_open = "ext_limit_board_events_observed_open"
    up_opens = "ext_limit_board_events_limit_up_pool_open_times"
    break_opens = "ext_limit_board_events_break_pool_open_times"
    specs = [
        FactorSpec(
            id=factor_id,
            label=factor_id,
            group="扩展数据",
            formula_text="materialized extension field",
            kind="base",
            scale_free=factor_id != break_opens,
        )
        for factor_id in (
            first_seal,
            observed_open,
            up_opens,
            break_opens,
            "ext_limit_board_events_last_seal_minute",
            "ext_other_unreviewed",
        )
    ]
    monkeypatch.setattr(service_module, "all_factors", lambda **_kwargs: specs)
    service = FirstboardDiscoveryService(
        _FakeRepository(),
        engine=_FakeEngine(_sample_accounting_panel()),
    )

    columns = service._candidate_factor_columns("both")

    assert columns == [
        (first_seal, "D_close"),
        (observed_open, "D_close"),
        (up_opens, "D_close"),
    ]
    assert service_module._CANDIDATE_POLICY["allowed_extension_factor_ids"] == [
        first_seal,
        observed_open,
        up_opens,
    ]
    assert service._candidate_factor_columns("D_minus_1") == []


def test_limit_board_extensions_join_on_event_date_and_keep_missing_unknown(
    tmp_path, monkeypatch,
) -> None:
    from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField

    panel = _sample_accounting_panel().drop("momentum_5d")
    columns = [
        ("ext_limit_board_events_first_seal_minute", "D_close"),
        ("ext_limit_board_events_observed_open", "D_close"),
    ]
    event_dates = panel.filter(pl.col("consecutive_limit_ups") == 1)["date"].unique().sort()
    append = pl.DataFrame({
        "symbol": ["000001.SZ"] * len(event_dates),
        "date": event_dates.to_list(),
        columns[0][0]: [585.0] + [None] * (len(event_dates) - 1),
        columns[1][0]: [None] * len(event_dates),
    })
    ExtConfigStore(tmp_path).upsert(ExtConfig(
        id="limit_board_events",
        label="limit board",
        mode="timeseries",
        fields=[
            ExtField(columns[0][0].removeprefix("ext_limit_board_events_"), "int"),
            ExtField(columns[1][0].removeprefix("ext_limit_board_events_"), "int"),
        ],
    ))
    for row in append.iter_rows(named=True):
        part = (
            tmp_path / "ext_data" / "limit_board_events" / "timeseries"
            / f"date={row['date']}" / "part.parquet"
        )
        part.parent.mkdir(parents=True)
        pl.DataFrame({
            "symbol": [row["symbol"]],
            columns[0][0].removeprefix("ext_limit_board_events_"): [row[columns[0][0]]],
            columns[1][0].removeprefix("ext_limit_board_events_"): [row[columns[1][0]]],
        }).write_parquet(part)

    class ExtensionRepository(_FakeRepository):
        store = type("Store", (), {"data_dir": tmp_path})()

    class ExtensionService(_TestDiscoveryService):
        def _candidate_factor_columns(self, snapshot_mode):
            del snapshot_mode
            return columns

        def _materialize_factors(self, panel, factor_ids):
            assert factor_ids == {columns[0][0], columns[1][0]}
            return panel.drop(columns[0][0], columns[1][0]).join(
                append, on=["symbol", "date"], how="left",
            )

    service = ExtensionService(ExtensionRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    rows = service.events(params, page_size=50)["rows"]
    first = next(row for row in rows if row["date"] == event_dates[0])
    later = next(row for row in rows if row["date"] == event_dates[1])

    assert first[f"D_close__{columns[0][0]}"] == 585.0
    assert first[f"D_close__{columns[1][0]}"] is None
    assert later[f"D_close__{columns[0][0]}"] is None


def test_limit_board_extension_change_invalidates_research_cache(tmp_path) -> None:
    from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField

    panel = _sample_accounting_panel().drop("momentum_5d")
    factor_id = "ext_limit_board_events_first_seal_minute"
    field_name = "first_seal_minute"
    event_dates = panel.filter(pl.col("consecutive_limit_ups") == 1)["date"].unique().sort()
    ExtConfigStore(tmp_path).upsert(ExtConfig(
        id="limit_board_events",
        label="limit board",
        mode="timeseries",
        fields=[ExtField(field_name, "int")],
    ))
    partition = (
        tmp_path / "ext_data" / "limit_board_events" / "timeseries"
        / f"date={event_dates[0]}" / "part.parquet"
    )
    partition.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], field_name: [585]}).write_parquet(partition)

    class ExtensionRepository(_FakeRepository):
        store = type("Store", (), {"data_dir": tmp_path})()

    class ExtensionService(_TestDiscoveryService):
        def _candidate_factor_columns(self, snapshot_mode):
            del snapshot_mode
            return [(factor_id, "D_close")]

        def _materialize_factors(self, panel, factor_ids):
            assert factor_ids == {factor_id}
            return panel

    service = ExtensionService(ExtensionRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )
    first = next(
        row for row in service.events(params, page_size=50)["rows"]
        if row["date"] == event_dates[0]
    )
    pl.DataFrame({"symbol": ["000001.SZ"], field_name: [600]}).write_parquet(partition)
    second = next(
        row for row in service.events(params, page_size=50)["rows"]
        if row["date"] == event_dates[0]
    )
    (tmp_path / "ext_data" / "limit_board_events" / "config.json").unlink()

    assert first[f"D_close__{factor_id}"] == 585.0
    assert second[f"D_close__{factor_id}"] == 600.0
    with pytest.raises(ValueError, match="缺少涨停封板与炸板扩展表"):
        service.events(params, page_size=50)


def test_fixed_training_end_is_reproducible_and_not_moved_by_validation() -> None:
    panel = _discoverable_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    train_end = date(2026, 3, 1)
    params = DiscoveryParams(
        start=panel["date"].min(),
        end=panel["date"].max(),
        train_end=train_end,
    )

    report = service.report(params)

    assert report["split"]["train_end"] == train_end
    assert report["split"]["validation_start"] > train_end
    assert report["params"]["train_end"] == train_end


def test_repository_lists_only_complete_enriched_market_partitions(tmp_path) -> None:
    repository = KlineRepository(DataStore(tmp_path))
    root = tmp_path / "kline_daily_enriched"
    frame = pl.DataFrame({"symbol": ["000001.SZ"], "date": [date(2026, 1, 5)]})
    for day in (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 8)):
        partition = root / f"date={day.isoformat()}"
        partition.mkdir(parents=True)
        frame.write_parquet(partition / "part.parquet")
    (root / "date=2026-01-07").mkdir()

    assert repository.list_enriched_dates(
        date(2026, 1, 5), date(2026, 1, 8),
    ) == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 8)]
