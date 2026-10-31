"""Execution and comparison contracts for the ordinary high-open study."""

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from scripts import auction_high_open_study as study


def test_first_bar_uses_exact_beijing_0930_and_share_vwap():
    frame = pl.DataFrame({
        "ts": [
            int(datetime(2024, 9, 2, 1, 30, tzinfo=UTC).timestamp() * 1000),
            int(datetime(2024, 9, 2, 1, 35, tzinfo=UTC).timestamp() * 1000),
        ],
        "symbol": ["000001.XSHE"] * 2,
        "open": [10.0, 99.0], "high": [11.0, 99.0],
        "low": [10.0, 99.0], "close": [11.0, 99.0],
        "volume": [200.0, 100.0], "amount": [2100.0, 9900.0],
    })
    result = study.normalize_first_bars(frame)
    assert result.height == 1
    assert result["date"].to_list() == [date(2024, 9, 2)]
    assert result["symbol"].to_list() == ["000001.SZ"]
    assert result["vwap"].to_list() == [10.5]


@pytest.mark.parametrize(
    ("gap", "expected"),
    [(-0.001, None), (0.0, "0-2"), (0.019, "0-2"), (0.02, "2-4"), (0.04, "4-6"),
     (0.06, "6-8"), (0.08, "8+"), (float("nan"), None), (None, None)],
)
def test_gap_boundaries(gap, expected):
    result = pl.DataFrame({"opening_gap": [gap]}).with_columns(study.gap_bucket())
    assert result["gap_bucket"][0] == expected


def test_duplicate_first_bars_fail_closed():
    ts = int(datetime(2024, 9, 2, 1, 30, tzinfo=UTC).timestamp() * 1000)
    frame = pl.DataFrame({
        "ts": [ts, ts], "symbol": ["000001.XSHE"] * 2,
        **{name: [10.0, 10.0] for name in ("open", "high", "low", "close")},
        "volume": [100.0, 100.0], "amount": [1000.0, 1000.0],
    })
    with pytest.raises(ValueError, match="Duplicate"):
        study.normalize_first_bars(frame)


def sample():
    return {
        "symbol": "000001.SZ",
        "date": date(2024, 9, 2), "exit_date": date(2024, 9, 3),
        "prev_date": date(2024, 8, 30), "expected_prev_date": date(2024, 8, 30),
        "prev_boards": 0, "opening_gap": 0.04, "has_result": 1,
        "result_time": 92500000, "auction_open": 10.4, "daily_open": 10.4,
        "daily_volume": 10000.0, "entry_open": 10.4,
        "entry_low": 10.3, "entry_high": 10.5, "entry_vwap": 10.4,
        "entry_volume": 1000.0, "limit_up": 11.0, "st_flag": False,
        "listing_date": date(2000, 1, 1), "sessions_since_listing": 500,
        "entry_scale": 0.8,
        "exit_scale": 0.8, "exit_vwap": 10.608,
        "exit_low": 10.5, "exit_high": 10.7, "exit_volume": 1000.0,
        "exit_limit_down": 9.36, "exit_st_known": True,
        "exit_daily_open": 10.6, "exit_open": 10.6, "exit_daily_volume": 10000.0,
        "exit_prev_date": date(2024, 9, 2),
        "exit_expected_prev_date": date(2024, 9, 2),
    }


def evaluate(row, **kwargs):
    return study.evaluate_execution(pl.DataFrame([row]), **kwargs).row(0, named=True)


def test_t_plus_one_return_includes_explicit_bilateral_costs():
    result = evaluate(sample(), commission_bps=3, stamp_tax_bps=5, slippage_bps=5)
    expected = 1.02 * (1 - 0.0005) * (1 - 0.0003 - 0.0005)
    expected /= (1 + 0.0005) * (1 + 0.0003)
    assert result["gross_return"] == pytest.approx(0.02)
    assert result["net_return"] == pytest.approx(expected - 1)
    assert result["entry_reason"] == "ok"
    assert result["exit_reason"] == "ok"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"prev_boards": 1}, "previous_first_board"),
        ({"prev_boards": None}, "previous_day_unknown"),
        ({"prev_date": date(2024, 8, 29)}, "previous_day_unknown"),
        ({"result_time": 93000000}, "auction_result_unavailable_before_open"),
        ({"sessions_since_listing": 5}, "recent_listing"),
        ({"entry_vwap": None}, "missing_or_invalid_first_bar"),
        ({"entry_volume": 0.0}, "missing_or_invalid_first_bar"),
        ({"entry_vwap": float("inf")}, "missing_or_invalid_first_bar"),
        ({"entry_vwap": 104.0}, "missing_or_invalid_first_bar"),
        ({"entry_open": 11.0, "daily_open": 11.0, "auction_open": 11.0,
          "entry_low": 11.0, "entry_high": 11.0, "entry_vwap": 11.0},
         "entry_limit_locked"),
        ({"entry_open": 8.32, "entry_low": 8.3, "entry_high": 8.4,
          "entry_vwap": 8.32}, "price_basis_mismatch"),
        ({"st_flag": None}, "historical_status_unknown"),
        ({"listing_date": None}, "listing_date_unknown"),
        ({"limit_up": None}, "entry_price_limit_unknown"),
    ],
)
def test_unavailable_entry_never_gets_a_return(changes, reason):
    result = evaluate({**sample(), **changes})
    assert result["entry_reason"] == reason
    assert result["net_return"] is None


def test_twentieth_trading_session_is_no_longer_treated_as_recent_listing():
    result = evaluate({**sample(), "sessions_since_listing": 20})
    assert result["entry_reason"] == "ok"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"exit_date": date(2024, 9, 2)}, "t_plus_one_required"),
        ({"exit_vwap": None}, "missing_or_invalid_exit_bar"),
        ({"exit_scale": 0.9}, "corporate_action_or_basis_change"),
        ({"exit_limit_down": None}, "exit_price_limit_unknown"),
        ({"exit_daily_volume": 0.0}, "exit_daily_volume_unavailable"),
        ({"exit_prev_date": date(2024, 8, 30)}, "exit_previous_session_unknown"),
        ({"exit_vwap": 9.36, "exit_low": 9.36, "exit_high": 9.36,
          "exit_open": 9.36, "exit_daily_open": 9.36}, "exit_limit_locked"),
    ],
)
def test_unavailable_exit_is_counted_and_not_fabricated(changes, reason):
    result = evaluate({**sample(), **changes})
    assert result["entry_reason"] == "ok"
    assert result["exit_reason"] == reason
    assert result["net_return"] is None


def test_same_date_gap_ranks_have_neutral_ties_and_missing_remains_missing():
    frame = pl.DataFrame({
        "date": [date(2024, 9, 2)] * 9, "symbol": [str(i) for i in range(9)],
        "gap_bucket": ["2-4"] * 4 + ["4-6"] * 5,
        "last_imbalance": [0., 1., 2., 3., 100., 100., 100., 100., None],
        "tail_price_change": [0., 1., 2., 3., 4., 5., 6., 7., None],
        "post0920_matched_growth": [1.] * 9,
        "volume_vs_prev": [1.] * 9,
        "last_minute_matched_growth": [1.] * 9,
    })
    ranked = study.rank_signals(frame)
    assert ranked["rank_last_imbalance"].to_list()[:4] == [0., 1 / 3, 2 / 3, 1.]
    assert ranked["rank_last_imbalance"].to_list()[4:8] == [0.5] * 4
    assert ranked["combo_score"][-1] is None


def test_ranks_freeze_before_entry_bar_and_count_only_complete_cases():
    rows = [
        {
            **sample(), "symbol": f"60000{i}.SH", "last_imbalance": float(i),
            "tail_price_change": float(i) / 10,
            "last_minute_matched_growth": 1.0, "post0920_matched_growth": 1.0,
            "volume_vs_prev": 1.0, "gap_bucket": "2-4",
        } for i in range(6)
    ]
    a = study.freeze_signals(pl.DataFrame(rows))
    rows[-1]["entry_vwap"] = None
    b = study.freeze_signals(pl.DataFrame(rows))
    assert a["combo_rank"].to_list() == b["combo_rank"].to_list()
    assert b["combo_rank"][3] == pytest.approx(0.6)
    assert b["signal_eligible"].to_list() == [True] * 6
    rows[0]["last_imbalance"] = None
    rows[1]["last_imbalance"] = None
    rows[2]["last_imbalance"] = None
    c = study.freeze_signals(pl.DataFrame(rows))
    assert c["population_last_imbalance"].to_list() == [3] * 6
    assert c["combo_population"].to_list() == [3] * 6


def test_tail_strength_is_gap_neutral_and_excludes_growth_and_star_boards():
    rows = []
    symbols = [
        "600000.SH", "000001.SZ", "300001.SZ", "301001.SZ",
        "302001.SZ", "688001.SH", "689009.SH",
    ]
    for index, symbol in enumerate(symbols):
        rows.append({
            **sample(), "symbol": symbol, "gap_bucket": "0-2",
            "tail_price_change": float(index + 1) / 10,
            "last_imbalance": float(index + 1),
            "last_minute_matched_growth": float(index + 1),
            "post0920_matched_growth": 1.0, "volume_vs_prev": 1.0,
        })
    ranked = study.freeze_signals(pl.DataFrame(rows))
    assert ranked["board_allowed"].to_list() == [
        True, True, False, False, False, False, False,
    ]
    assert ranked["signal_eligible"].to_list() == [
        True, True, False, False, False, False, False,
    ]
    assert ranked["tail_strength_score"].null_count() == 5
    assert ranked.filter(pl.col("signal_eligible"))["tail_strength_rank"].max() == 1.0


def test_tail_portfolio_caps_daily_entries_and_sorts_by_frozen_score():
    rows = []
    for index in range(12):
        rows.append({
            **sample(), "symbol": f"6000{index:02d}.SH",
            "date": date(2024, 9, 2), "exit_date": date(2024, 9, 5),
            "horizon": 3, "signal_eligible": True,
            "tail_strength_signal": True,
            "tail_strength_score": float(index) / 12,
            "tail_strength_rank": float(index) / 11,
            "entry_reason": "ok", "exit_reason": "ok",
            "entry_vwap": 10.0, "entry_volume": 1_000_000.0,
            "net_return": float(index) / 1000,
        })
    summary, selected, curve = study.simulate_tail_portfolio(
        pl.DataFrame(rows), start=date(2024, 9, 2), end=date(2024, 9, 30),
    )
    assert summary["candidate_n"] == 12
    assert summary["n_trades"] == 5
    assert summary["rejected"]["daily_limit"] == 7
    assert [row["tail_strength_score"] for row in selected] == [11 / 12, 10 / 12, 9 / 12, 8 / 12, 7 / 12]
    assert curve[0]["open_positions"] == 5


def test_generic_portfolio_uses_requested_signal_and_score_columns():
    rows = []
    for index in range(3):
        rows.append({
            **sample(), "symbol": f"6000{index:02d}.SH",
            "date": date(2024, 9, 2), "exit_date": date(2024, 9, 5),
            "horizon": 3, "signal_eligible": True,
            "custom_signal": index != 1,
            "custom_score": float(index),
            "entry_reason": "ok", "exit_reason": "ok",
            "entry_vwap": 10.0, "entry_volume": 1_000_000.0,
            "net_return": 0.01,
        })
    summary, selected, _ = study.simulate_signal_portfolio(
        pl.DataFrame(rows),
        start=date(2024, 9, 2),
        end=date(2024, 9, 30),
        signal_column="custom_signal",
        score_column="custom_score",
    )
    assert summary["candidate_n"] == 2
    assert summary["n_trades"] == 2
    assert [row["symbol"] for row in selected] == ["600002.SH", "600000.SH"]


def test_empty_first_bar_request_returns_empty_typed_frame(tmp_path):
    frame, sources = study._first_bars(
        tmp_path, pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date}),
    )
    assert frame.is_empty()
    assert frame.schema["vwap"] == pl.Float64
    assert sources == {}


def test_unrequested_duplicate_minute_dates_do_not_contaminate_requested_scope(tmp_path):
    rows = []
    for day in (2, 3, 3):
        rows.append({
            "ts": int(datetime(2024, 9, day, 1, 30, tzinfo=UTC).timestamp() * 1000),
            "symbol": "000001.XSHE", "open": 10., "high": 11., "low": 10.,
            "close": 10.5, "volume": 100., "amount": 1050.,
        })
    pl.DataFrame(rows).write_parquet(tmp_path / "2024.parquet")
    result, _ = study._first_bars(
        tmp_path, pl.DataFrame({"symbol": ["000001.SZ"], "date": [date(2024, 9, 2)]}),
    )
    assert result["vwap"].to_list() == [10.5]


def test_sparse_combo_and_stale_sell_fields_do_not_create_selected_events():
    rows = []
    for i in range(6):
        rows.append({
            **sample(), "symbol": f"60000{i}.SH", "gap_bucket": "4-6",
            "last_imbalance": float(i) - 6,
            "tail_price_change": float(i) / 10,
            "last_minute_matched_growth": 1., "post0920_matched_growth": 1.,
            "volume_vs_prev": 1., "last_age_ms": 1000,
            "c0924_age_ms": 60000, "last_unmatched_sell_shares": 200.,
            "c0924_unmatched_sell_shares": 100., "horizon": 1,
        })
    events = study.evaluate_execution(study.freeze_signals(pl.DataFrame(rows)))
    report = study.build_report(events, bootstrap_samples=10, seed=7)
    sell = next(r for r in report["results"]
                if r["variant"] == "B3_sell_expansion" and r["gap_bucket"] == "main_2_8")
    assert sell["n"] == sell["signal_n"] == 0
    for row in rows[:3]:
        row["last_imbalance"] = None
    events = study.evaluate_execution(study.freeze_signals(pl.DataFrame(rows)))
    report = study.build_report(events, bootstrap_samples=10, seed=7)
    combo = next(r for r in report["results"]
                 if r["variant"] == "B2_buy_not_crowded" and r["gap_bucket"] == "main_2_8")
    assert combo["n"] == combo["signal_n"] == 0
    for row in rows[:3]:
        row["last_imbalance"] = float(rows.index(row))
        row["c0924_age_ms"] = 1000
    events = study.evaluate_execution(study.freeze_signals(pl.DataFrame(rows)))
    report = study.build_report(events, bootstrap_samples=10, seed=7)
    sell = next(r for r in report["results"]
                if r["variant"] == "B3_sell_expansion" and r["gap_bucket"] == "main_2_8")
    assert sell["n"] == sell["signal_n"] == 0


def test_cluster_interval_does_not_treat_duplicate_same_day_events_as_independent():
    rows = [
        {"date": date(2024, 9, 2) + timedelta(days=i),
         "net_return": value, "incremental_return": value,
         "win_increment": 0.0}
        for i, value in enumerate([-0.1, 0.1, -0.2, 0.2])
    ]
    a = study.summarize(pl.DataFrame(rows), bootstrap_samples=1000, seed=7)
    b = study.summarize(pl.DataFrame(rows * 10), bootstrap_samples=1000, seed=7)
    assert a["event_days"] == b["event_days"] == 4
    assert a["cluster_bootstrap_95"] == b["cluster_bootstrap_95"]


def test_period_boundary_censor_is_reported_without_fabricating_an_exit():
    row = {
        **sample(), "date": date(2024, 12, 31), "exit_date": date(2025, 1, 2),
        "gap_bucket": "4-6", "horizon": 1, "signal_eligible": True,
        "entry_reason": "ok", "exit_reason": "ok", "net_return": 0.02,
        "tail_price_change": 0.1,
        "last_imbalance": 0.1, "last_minute_matched_growth": 0.1,
        "post0920_matched_growth": 0.1, "volume_vs_prev": 1.0,
        "rank_tail_price_change": 1.0, "population_tail_price_change": 10,
        "rank_last_imbalance": 1.0, "rank_last_minute_matched_growth": 1.0,
        "rank_post0920_matched_growth": 1.0, "rank_volume_vs_prev": 1.0,
        "population_last_imbalance": 10, "population_last_minute_matched_growth": 10,
        "population_post0920_matched_growth": 10, "population_volume_vs_prev": 10,
        "combo_score": 1.0, "combo_rank": 1.0, "combo_population": 10,
        "tail_strength_score": 1.0, "tail_strength_rank": 1.0,
        "tail_strength_population": 10, "tail_strength_signal": True,
        "population_sell_expansion": 10,
        "last_age_ms": 1000, "c0924_age_ms": 1000,
        "last_unmatched_sell_shares": 0, "c0924_unmatched_sell_shares": 0,
    }
    report = study.build_report(pl.DataFrame([row]), bootstrap_samples=10, seed=7)
    validation = next(
        item for item in report["results"]
        if item["period"] == "validation" and item["gap_bucket"] == "main_2_8"
        and item["variant"] == "B0_all"
    )
    assert validation["signal_n"] == 1
    assert validation["period_boundary_censored_n"] == 1
    assert validation["n"] == 0


def test_mode2b_requires_top_tail_growth_and_volume_outside_top_quartile():
    rows = []
    for index, (tail_rank, volume_rank, tail_n, volume_n) in enumerate((
        (0.80, 0.70, 4, 4),
        (0.75, 0.749, 4, 4),
        (0.75, 0.75, 4, 4),
        (0.749, 0.10, 4, 4),
        (0.90, 0.10, 3, 4),
    )):
        rows.append({
            **sample(), "symbol": str(index), "date": date(2024, 9, 2),
            "exit_date": date(2024, 9, 5), "gap_bucket": "4-6", "horizon": 3,
            "signal_eligible": True, "entry_reason": "ok", "exit_reason": "ok",
            "net_return": 0.01,
            "rank_last_minute_matched_growth": tail_rank,
            "rank_volume_vs_prev": volume_rank,
            "population_last_minute_matched_growth": tail_n,
            "population_volume_vs_prev": volume_n,
            "last_imbalance": 0.1, "post0920_matched_growth": 0.1,
            "tail_price_change": 0.1,
            "volume_vs_prev": 1.0, "last_minute_matched_growth": 0.1,
            "rank_tail_price_change": 0.5, "population_tail_price_change": 4,
            "rank_last_imbalance": 0.5, "rank_post0920_matched_growth": 0.5,
            "population_last_imbalance": 4,
            "population_post0920_matched_growth": 4,
            "combo_score": 0.0, "combo_rank": 0.5, "combo_population": 4,
            "tail_strength_score": 0.8, "tail_strength_rank": 0.8,
            "tail_strength_population": 4, "tail_strength_signal": True,
            "population_sell_expansion": 4, "last_age_ms": 1000,
            "c0924_age_ms": 1000, "last_unmatched_sell_shares": 0,
            "c0924_unmatched_sell_shares": 0,
        })
    report = study.build_report(pl.DataFrame(rows), bootstrap_samples=10, seed=7)
    mode2b = next(
        item for item in report["results"]
        if item["period"] == "validation" and item["horizon"] == 3
        and item["gap_bucket"] == "main_2_8"
        and item["variant"] == "M2B_tail_strength_low_volume"
    )
    assert mode2b["signal_n"] == 2
    assert mode2b["n"] == 2
    assert report["frozen_candidates"] == [
        study.TAIL_STRENGTH_RULE,
        study.MODE2B_RULE,
    ]
    assert not any(
        item["variant"] == "M2B_tail_strength_low_volume" and item["horizon"] == 1
        for item in report["results"]
    )


def test_baseline_matches_selected_date_gap_and_coverage():
    events = pl.DataFrame({
        "date": [date(2024, 9, 2)] * 6,
        "gap_bucket": ["2-4"] * 3 + ["6-8"] * 3,
        "net_return": [0.01, 0.03, 0.99, 0.1, 0.2, 0.99],
        "last_imbalance": [0., 1., None, 0., 1., None],
    })
    compared = study.attach_baseline(events, eligible=pl.col("last_imbalance").is_not_null())
    assert compared["baseline_return"].to_list() == pytest.approx([0.02, 0.02, 0.15, 0.15])
    assert compared["incremental_return"].to_list() == pytest.approx([-.01, .01, -.05, .05])


def test_real_parquet_pipeline_uses_market_calendar_and_keeps_sources_readonly(tmp_path):
    from argparse import Namespace

    data, auction, minute = [tmp_path / name for name in ("data", "auction", "minute")]
    days = [date(2024, 8, 29), date(2024, 8, 30), date(2024, 9, 2),
            date(2024, 9, 3), date(2024, 9, 4), date(2024, 9, 5)]
    for index, day in enumerate(days):
        price = 10.4 if index == 2 else 10.5 if index > 2 else 10.0
        raw = pl.DataFrame({
            "symbol": ["000001.SZ"], "date": [day], "open": [price],
            "high": [price + .1], "low": [price - .1], "close": [price],
            "volume": [10000.0],
        })
        enriched = raw.with_columns(
            pl.col("close").alias("raw_close"), pl.lit(0).alias("consecutive_limit_ups"),
        )
        for folder, frame in (("kline_daily", raw), ("kline_daily_enriched", enriched)):
            target = data / folder / f"date={day}"
            target.mkdir(parents=True)
            frame.write_parquet(target / "part.parquet")
        index_target = data / "kline_index_daily" / f"date={day}"
        index_target.mkdir(parents=True)
        pl.DataFrame({"symbol": ["000001.SH"], "date": [day]}).write_parquet(
            index_target / "part.parquet",
        )
    (data / "instruments").mkdir()
    pl.DataFrame({"symbol": ["000001.SZ"], "listing_date": ["2000-01-01"]}).write_parquet(
        data / "instruments" / "instruments.parquet",
    )
    (data / "st_history").mkdir()
    pl.DataFrame({
        "symbol": ["000001.SZ"], "flag_date": [days[0]], "st_flag": [False],
    }).write_parquet(data / "st_history" / "all.parquet")
    day = date(2024, 9, 2)
    result = {
        "symbol": ["000001.SZ"], "date": [day], "opening_gap": [.04],
        "prev_close": [10.0],
        "auction_open": [10.4], "has_result": [1], "result_time": [92500000],
        "volume_shares": [10000],
    }
    pre = {
        "symbol": ["000001.SZ"], "date": [day], "c0924_ref_price": [10.0],
        "last_ref_price": [10.1], "c0924_matched_shares": [100],
        "last_matched_shares": [150], "last_imbalance": [.1],
        "last_unmatched_buy_shares": [0], "c0924_unmatched_buy_shares": [0],
        "last_minute_matched_growth": [.5], "post0920_matched_growth": [1.0],
        "last_time": [92459000], "last_age_ms": [1000],
        "c0920_age_ms": [1000], "c0924_age_ms": [1000],
        "last_unmatched_sell_shares": [0], "c0924_unmatched_sell_shares": [0],
    }
    for name, frame in (("result", result), ("preopen", pre)):
        target = auction / name / f"date={day}"
        target.mkdir(parents=True)
        pl.DataFrame(frame).write_parquet(target / "part.parquet")
    minute.mkdir()
    pl.DataFrame([
        {
            "ts": int(datetime(2024, 9, d, 1, 30, tzinfo=UTC).timestamp() * 1000),
            "symbol": "000001.XSHE", "open": price, "high": price + .1,
            "low": price - .1, "close": price, "volume": 1000.0, "amount": price * 1000,
        }
        for d, price in ((2, 10.4), (3, 10.5), (5, 10.5))
    ]).write_parquet(minute / "2024.parquet")
    args = Namespace(
        data_dir=data, auction_dir=auction, minute_dir=minute, start=day, end=day,
        output=tmp_path / "output", commission_bps=3, stamp_tax_bps=10,
        slippage_bps=5, bootstrap_samples=10, seed=7,
        allow_missing_auction_days=False,
    )
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.parquet")}
    report = study.run_study(args)
    events = pl.read_parquet(args.output / "events.parquet")
    assert events["prev_date"].to_list() == [date(2024, 8, 30)] * 2
    assert events["exit_date"].to_list() == [date(2024, 9, 3), date(2024, 9, 5)]
    assert events["gross_return"].to_list() == pytest.approx([10.5 / 10.4 - 1] * 2)
    assert report["coverage"]["unique_events"] == 1
    assert report["coverage"]["main_2_8"] == {
        "event_rows": 1, "unique_events": 1, "signal_candidates": 1,
        "entry_executable": 1, "resolved_next_day": 1,
    }
    assert all(p.read_bytes() == content for p, content in before.items())
    with pytest.raises(FileExistsError):
        study.run_study(args)
    original_result = pl.read_parquet(auction / "result" / f"date={day}" / "part.parquet")
    original_result.with_columns(pl.lit(0).alias("has_result")).write_parquet(
        auction / "result" / f"date={day}" / "part.parquet",
    )
    minute_file = minute / "2024.parquet"
    minute_file.rename(minute / "2024.parquet.bak")
    ineligible, _, _ = study.build_year(
        data, auction, minute, day, day,
        commission_bps=3, stamp_tax_bps=10, slippage_bps=5,
    )
    assert ineligible["signal_eligible"].to_list() == [False, False]
    minute_file = minute / "2024.parquet.bak"
    minute_file.rename(minute / "2024.parquet")
    original_result.write_parquet(auction / "result" / f"date={day}" / "part.parquet")
    # A missing stock-data session must not turn Wednesday into D+1.
    (data / "kline_daily" / "date=2024-09-03" / "part.parquet").unlink()
    (data / "kline_daily_enriched" / "date=2024-09-03" / "part.parquet").unlink()
    frame, _, _ = study.build_year(
        data, auction, minute, day, day,
        commission_bps=3, stamp_tax_bps=10, slippage_bps=5,
    )
    next_day = frame.filter(pl.col("horizon") == 1).row(0, named=True)
    assert next_day["exit_date"] == date(2024, 9, 3)
    assert next_day["net_return"] is None
    # A zero-event window is a valid study, with a complete empty report.
    target = auction / "result" / f"date={day}" / "part.parquet"
    pl.read_parquet(target).with_columns(pl.lit(-0.01).alias("opening_gap")).write_parquet(
        target,
    )
    args.output = tmp_path / "empty-output"
    empty = study.run_study(args)
    assert empty["coverage"]["unique_events"] == 0
    assert empty["results"] == []
    enriched_path = data / "kline_daily_enriched" / "date=2024-09-04" / "part.parquet"
    pl.read_parquet(enriched_path).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("raw_close"),
    ).write_parquet(enriched_path)
    with pytest.raises(ValueError, match="raw close mismatch"):
        study.build_year(
            data, auction, minute, day, day,
            commission_bps=3, stamp_tax_bps=10, slippage_bps=5,
        )


def test_missing_auction_partition_fails_instead_of_shrinking_requested_window(tmp_path):
    data, auction, minute = [tmp_path / name for name in ("data", "auction", "minute")]
    days = [date(2024, 9, 2), date(2024, 9, 3)]
    for day in days:
        for folder, columns in (
            ("kline_daily", {
                "symbol": ["000001.SZ"], "date": [day], "open": [10.],
                "high": [11.], "low": [9.], "close": [10.], "volume": [1.],
            }),
            ("kline_daily_enriched", {
                "symbol": ["000001.SZ"], "date": [day], "close": [10.],
                "raw_close": [10.], "consecutive_limit_ups": [0],
            }),
            ("kline_index_daily", {"symbol": ["000001.SH"], "date": [day]}),
        ):
            target = data / folder / f"date={day}"
            target.mkdir(parents=True, exist_ok=True)
            pl.DataFrame(columns).write_parquet(target / "part.parquet")
    (data / "instruments").mkdir()
    pl.DataFrame({"symbol": ["000001.SZ"], "listing_date": ["2000-01-01"]}).write_parquet(
        data / "instruments" / "instruments.parquet",
    )
    (data / "st_history").mkdir()
    pl.DataFrame({
        "symbol": ["000001.SZ"], "flag_date": [days[0]], "st_flag": [False],
    }).write_parquet(data / "st_history" / "all.parquet")
    frame = pl.DataFrame({
        "symbol": ["000001.SZ"], "date": [days[0]], "opening_gap": [.04],
        "prev_close": [10.], "auction_open": [10.4], "has_result": [1],
        "result_time": [92500000], "volume_shares": [100],
    })
    pre = pl.DataFrame({
        "symbol": ["000001.SZ"], "date": [days[0]], "c0924_ref_price": [10.0],
        "last_ref_price": [10.1], "c0924_matched_shares": [100],
        "last_matched_shares": [150], "last_imbalance": [.1],
        "last_unmatched_buy_shares": [0], "c0924_unmatched_buy_shares": [0],
        "last_minute_matched_growth": [.1], "post0920_matched_growth": [.1],
        "last_time": [92459000], "last_age_ms": [1000], "c0920_age_ms": [1000],
        "c0924_age_ms": [1000], "last_unmatched_sell_shares": [0],
        "c0924_unmatched_sell_shares": [0],
    })
    for name, content in (("result", frame), ("preopen", pre)):
        target = auction / name / f"date={days[0]}"
        target.mkdir(parents=True)
        content.write_parquet(target / "part.parquet")
    minute.mkdir()
    (data / "kline_daily" / f"date={days[1]}" / "part.parquet").unlink()
    (data / "kline_daily_enriched" / f"date={days[1]}" / "part.parquet").unlink()
    with pytest.raises(ValueError, match="Auction partitions incomplete"):
        study.build_year(
            data, auction, minute, days[0], days[1],
            commission_bps=3, stamp_tax_bps=10, slippage_bps=5,
        )
    for path in auction.rglob("part.parquet"):
        path.unlink()
    empty, _, gaps = study.build_year(
        data, auction, minute, days[0], days[1],
        commission_bps=3, stamp_tax_bps=10, slippage_bps=5,
        allow_missing_auction=True,
    )
    assert empty.is_empty()
    assert gaps == {"result": ["2024-09-02", "2024-09-03"],
                    "preopen": ["2024-09-02", "2024-09-03"]}
