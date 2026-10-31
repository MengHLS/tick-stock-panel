"""截面联动因子纯计算金标准。"""
from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl
import pytest

from app.factors.linkage import (
    LINKAGE_FACTOR_IDS,
    compute_linkage_fields,
    normalize_industry,
)

_INDUSTRY_FACTORS = (
    "industry_relative_momentum_20d",
    "industry_rank_momentum_20d",
    "industry_corr_60d",
    "industry_beta_60d",
)
_BOARDS = ("SH", "STAR", "SZ", "GEM", "BJ")
_BOARD_BASE = {
    "SH": 600000,
    "STAR": 688000,
    "SZ": 1,
    "GEM": 300000,
    "BJ": 830000,
}


def _business_dates(start: date, count: int) -> list[date]:
    out: list[date] = []
    day = start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def _symbol(board: str, serial: int) -> str:
    suffix = "SH" if board in {"SH", "STAR"} else ("BJ" if board == "BJ" else "SZ")
    return f"{_BOARD_BASE[board] + serial:06d}.{suffix}"


def _board_of_symbol(symbol: str) -> str:
    code, suffix = symbol.split(".")
    if suffix == "BJ":
        return "BJ"
    if suffix == "SH":
        return "STAR" if code.startswith("68") else "SH"
    return "GEM" if code.startswith("30") else "SZ"


def _empty_benchmarks() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "date": pl.Date,
        "bench_key": pl.String,
        "bench_close": pl.Float64,
    })


def _industry_inputs() -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    list[date],
    dict[str, dict[date, float]],
    dict[str, str],
]:
    dates = _business_dates(date(2025, 1, 6), 75)
    industries = ("银行", "半导体", "医药")
    rows: list[dict] = []
    membership: list[dict] = []
    closes: dict[str, dict[date, float]] = {}
    symbol_industry: dict[str, str] = {}

    for industry_idx, industry in enumerate(industries):
        for stock_idx in range(12):
            board = _BOARDS[stock_idx % len(_BOARDS)]
            sym = _symbol(board, industry_idx * 20 + stock_idx)
            symbol_industry[sym] = industry
            close = 10.0 + industry_idx + stock_idx * 0.1
            closes[sym] = {}
            for day_idx, day in enumerate(dates):
                membership.append({
                    "symbol": sym,
                    "date": day,
                    "industry": f"一级-{industry}-三级",
                })
                if day_idx:
                    ret = (
                        0.0002 * ((stock_idx % 5) - 2)
                        + 0.0007 * math.sin(day_idx * 0.31 + stock_idx * 0.43)
                        + 0.0003 * math.sin(day_idx * 0.11 + industry_idx)
                    )
                    close *= 1.0 + ret
                closes[sym][day] = close
                rows.append({"symbol": sym, "date": day, "close": close})

    benchmarks: list[dict] = []
    by_board: dict[str, float] = {board: 100.0 for board in _BOARDS}
    for day_idx, day in enumerate(dates):
        for board_idx, board in enumerate(_BOARDS):
            if day_idx:
                ret = 0.0004 * math.sin(day_idx * 0.17 + board_idx * 0.9)
                by_board[board] *= 1.0 + ret
            benchmarks.append({
                "date": day,
                "bench_key": board,
                "bench_close": by_board[board],
            })

    return (
        pl.DataFrame(rows),
        pl.DataFrame(benchmarks),
        pl.DataFrame(membership),
        dates,
        closes,
        symbol_industry,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_corr(xs: list[float], ys: list[float]) -> float:
    mx, my = _mean(xs), _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (len(xs) - 1)
    vx = sum((x - mx) ** 2 for x in xs) / (len(xs) - 1)
    vy = sum((y - my) ** 2 for y in ys) / (len(ys) - 1)
    return cov / math.sqrt(vx * vy)


def _sample_beta(xs: list[float], ys: list[float]) -> float:
    mx, my = _mean(xs), _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (len(xs) - 1)
    vy = sum((y - my) ** 2 for y in ys) / (len(ys) - 1)
    return cov / vy


@pytest.mark.parametrize(
    ("value", "level", "expected"),
    [
        ("一级-二级-三级", 2, "二级"),
        (" 一级 - 二级 ", 2, "二级"),
        ("一级-二级-三级", 3, "三级"),
        ("一级-二级", 2, "二级"),
        ("银行", 2, "银行"),
        (None, 2, None),
        ("", 2, None),
    ],
)
def test_normalize_industry(value: str | None, level: int, expected: str | None) -> None:
    assert normalize_industry(value, level) == expected


def test_linkage_factor_ids_are_the_seven_contract_factors() -> None:
    assert frozenset({
        "deviate_3d",
        "deviate_10d",
        "deviate_30d",
        *_INDUSTRY_FACTORS,
    }) == LINKAGE_FACTOR_IDS


def test_linkage_values_match_numeric_goldens() -> None:
    enriched, benchmarks, membership, dates, closes, symbol_industry = _industry_inputs()
    target = dates[-1]

    out = compute_linkage_fields(enriched, benchmarks, membership, {target})

    assert out.height == 36
    assert set(out["date"].unique().to_list()) == {target}
    assert set(_INDUSTRY_FACTORS) <= set(out.columns)

    rows = {row["symbol"]: row for row in out.to_dicts()}
    symbols_by_board = {
        board: next(sym for sym in symbol_industry if _board_of_symbol(sym) == board)
        for board in _BOARDS
    }
    for board in _BOARDS:
        sym = symbols_by_board[board]
        bench_expected = {}
        bench_rows = benchmarks.filter(pl.col("bench_key") == board).sort("date").to_dicts()
        for n in (3, 10, 30):
            stock_mom = closes[sym][target] / closes[sym][dates[-1 - n]] - 1
            bench_mom = bench_rows[-1]["bench_close"] / bench_rows[-1 - n]["bench_close"] - 1
            bench_expected[n] = stock_mom - bench_mom
        for n, expected in bench_expected.items():
            assert math.isclose(rows[sym][f"deviate_{n}d"], expected, rel_tol=1e-9, abs_tol=1e-12)

    for industry in ("银行", "半导体", "医药"):
        group = [
            sym for sym, name in symbol_industry.items()
            if name == industry
        ]
        mom = {
            sym: closes[sym][target] / closes[sym][dates[-21]] - 1
            for sym in group
        }
        sorted_mom = sorted(mom.values())
        for sym in group:
            peer_mean = sum(mom[s] for s in group if s != sym) / (len(group) - 1)
            assert math.isclose(
                rows[sym]["industry_relative_momentum_20d"],
                mom[sym] - peer_mean,
                rel_tol=1e-9,
                abs_tol=1e-12,
            )
            less = sum(value < mom[sym] for value in sorted_mom)
            equal = sum(value == mom[sym] for value in sorted_mom)
            expected_rank = (less + (equal + 1) / 2) / len(group)
            assert math.isclose(
                rows[sym]["industry_rank_momentum_20d"],
                expected_rank,
                rel_tol=1e-9,
                abs_tol=1e-12,
            )

    target_sym = next(iter(rows))
    target_industry = symbol_industry[target_sym]
    group = [sym for sym, name in symbol_industry.items() if name == target_industry]
    xs: list[float] = []
    ys: list[float] = []
    for idx in range(len(dates) - 60, len(dates)):
        day, prev = dates[idx], dates[idx - 1]
        returns = {sym: closes[sym][day] / closes[sym][prev] - 1 for sym in group}
        xs.append(returns[target_sym])
        ys.append(sum(returns[s] for s in group if s != target_sym) / (len(group) - 1))
    assert math.isclose(
        rows[target_sym]["industry_corr_60d"],
        _sample_corr(xs, ys),
        rel_tol=1e-9,
        abs_tol=1e-12,
    )
    assert math.isclose(
        rows[target_sym]["industry_beta_60d"],
        _sample_beta(xs, ys),
        rel_tol=1e-9,
        abs_tol=1e-12,
    )


def test_industry_factors_return_null_for_unknown_insufficient_and_zero_variance() -> None:
    dates = _business_dates(date(2025, 3, 3), 61)
    rows: list[dict] = []
    membership: list[dict] = []

    def add_symbol(sym: str, industry: str | None, returns: list[float]) -> None:
        close = 20.0
        for day_idx, day in enumerate(dates):
            if industry is not None:
                membership.append({
                    "symbol": sym,
                    "date": day,
                    "industry": f"一级-{industry}",
                })
            if day_idx:
                close *= 1.0 + returns[day_idx - 1]
            rows.append({"symbol": sym, "date": day, "close": close})

    add_symbol("600001.SH", "孤立行业", [0.001 * math.sin(i) for i in range(60)])
    add_symbol("600002.SH", "不足行业", [0.001 * math.sin(i + 1) for i in range(60)])
    add_symbol("600003.SH", "不足行业", [0.001 * math.sin(i + 2) for i in range(60)])
    add_symbol("600004.SH", None, [0.001 * math.sin(i + 3) for i in range(60)])

    target_returns = [0.001 * math.sin(i * 0.7) for i in range(60)]
    add_symbol("600010.SH", "零方差行业", target_returns)
    for idx in range(10):
        add_symbol(f"6001{idx:02d}.SH", "零方差行业", [0.0] * 60)

    out = compute_linkage_fields(
        pl.DataFrame(rows),
        _empty_benchmarks(),
        pl.DataFrame(membership),
        {dates[-1]},
        min_peers=10,
    )
    got = {row["symbol"]: row for row in out.to_dicts()}

    for sym in ("600001.SH", "600002.SH", "600003.SH", "600004.SH"):
        assert all(got[sym][name] is None for name in _INDUSTRY_FACTORS)
    assert got["600010.SH"]["industry_relative_momentum_20d"] is not None
    assert got["600010.SH"]["industry_rank_momentum_20d"] is not None
    assert got["600010.SH"]["industry_corr_60d"] is None
    assert got["600010.SH"]["industry_beta_60d"] is None


def test_industry_membership_switches_on_the_same_day() -> None:
    dates = _business_dates(date(2025, 9, 10), 26)
    rows: list[dict] = []
    closes: dict[str, list[float]] = {}
    membership: list[dict] = []
    specs = {
        "600100.SH": 1.0,
        "600101.SH": 2.0,
        "600102.SH": 3.0,
    }
    for sym, phase in specs.items():
        close = 10.0 + phase
        closes[sym] = []
        for day_idx, day in enumerate(dates):
            if day_idx:
                close *= 1.0 + 0.001 * math.sin(day_idx * 0.41 + phase)
            closes[sym].append(close)
            rows.append({"symbol": sym, "date": day, "close": close})
            if sym == "600100.SH":
                industry = "B" if day == dates[-1] else "A"
            elif sym == "600101.SH":
                industry = "A"
            else:
                industry = "B"
            membership.append({
                "symbol": sym,
                "date": day,
                "industry": f"一级-{industry}",
            })
    out = compute_linkage_fields(
        pl.DataFrame(rows),
        _empty_benchmarks(),
        pl.DataFrame(membership),
        {dates[-2], dates[-1]},
        min_peers=1,
    )
    got = {
        (row["symbol"], row["date"]): row
        for row in out.to_dicts()
    }

    def momentum(sym: str, idx: int) -> float:
        return closes[sym][idx] / closes[sym][idx - 20] - 1

    before = got[("600100.SH", dates[-2])]
    expected_before = momentum("600100.SH", len(dates) - 2) - momentum("600101.SH", len(dates) - 2)
    assert math.isclose(
        before["industry_relative_momentum_20d"],
        expected_before,
        rel_tol=1e-9,
        abs_tol=1e-12,
    )

    after = got[("600100.SH", dates[-1])]
    expected_after = momentum("600100.SH", len(dates) - 1) - momentum("600102.SH", len(dates) - 1)
    assert math.isclose(
        after["industry_relative_momentum_20d"],
        expected_after,
        rel_tol=1e-9,
        abs_tol=1e-12,
    )
