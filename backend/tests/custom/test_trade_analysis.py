from __future__ import annotations

from datetime import date

import pytest

from app.custom.trade_analysis import store
from app.custom.trade_analysis.importer import parse_statement
from app.custom.trade_analysis.roundtrips import analyze_trade, compute_roundtrips


def _statement() -> bytes:
    text = (
        "发生日期,发生时间,证券代码,证券名称,交易类别,成交数量,成交均价,成交金额,"
        "发生金额,佣金,其他费用,印花税,过户费,成交编号,资金余额\n"
        '2026-01-05,09:35:00,= "600000      ",浦发银行,证券买入,100,10.000,1000.000,'
        "-1005.00,5.00,0.00,0.00,0.00,1001,4995.00\n"
        '2026-01-06,09:35:00,= "000001      ",平安银行,证券买入,200,12.000,2400.000,'
        "-2406.00,6.00,0.00,0.00,0.00,1002,2589.00\n"
    )
    return text.encode("gbk")


def _fill(fill_id: str, day: str, symbol: str, side: str, qty: int, price: float) -> dict:
    cash = -qty * price if side == "B" else qty * price
    return {
        "id": fill_id,
        "trade_date": day,
        "trade_time": "09:35:00",
        "symbol": symbol,
        "name": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "amount": qty * price,
        "cash_flow": cash,
        "commission": 0.0,
        "other_fee": 0.0,
        "stamp_tax": 0.0,
        "transfer_fee": 0.0,
    }


def test_parse_statement_normalizes_broker_rows() -> None:
    rows = parse_statement(_statement(), source_file="statement.csv")

    assert [row["symbol"] for row in rows] == ["600000.SH", "000001.SZ"]
    assert [row["side"] for row in rows] == ["B", "B"]
    assert rows[0]["cash_flow"] == pytest.approx(-1005.0)
    assert rows[0]["commission"] == pytest.approx(5.0)
    assert rows[0]["qty"] == 100


def test_import_is_idempotent(tmp_path) -> None:
    rows = parse_statement(_statement(), source_file="statement.csv")

    first = store.insert_fills(tmp_path, rows)
    second = store.insert_fills(tmp_path, rows)

    assert first == (2, 0)
    assert second == (0, 2)
    assert len(store.list_fills(tmp_path)) == 2


def test_partial_sell_keeps_cycle_open_and_tracks_average_cost() -> None:
    fills = [
        _fill("b1", "2026-01-05", "600000.SH", "B", 100, 10.0),
        _fill("b2", "2026-01-06", "600000.SH", "B", 100, 12.0),
        _fill("s1", "2026-01-08", "600000.SH", "S", 150, 15.0),
    ]

    trades, open_lots = compute_roundtrips(fills)

    assert trades == []
    assert open_lots == [{
        "symbol": "600000.SH",
        "name": "600000.SH",
        "qty": 50,
        "avg_cost": 11.0,
        "open_date": "2026-01-05",
        "open_time": "09:35:00",
    }]


def test_one_cycle_contains_all_adds_and_partial_exits_until_flat() -> None:
    fills = [
        _fill("b1", "2026-01-05", "600000.SH", "B", 100, 10.0),
        _fill("b2", "2026-01-06", "600000.SH", "B", 100, 12.0),
        _fill("s1", "2026-01-08", "600000.SH", "S", 150, 15.0),
        _fill("s2", "2026-01-09", "600000.SH", "S", 50, 11.0),
    ]

    trades, open_lots = compute_roundtrips(fills)

    assert open_lots == []
    assert len(trades) == 1
    trade = trades[0]
    assert trade["qty"] == 200
    assert trade["buy_count"] == 2
    assert trade["sell_count"] == 2
    assert trade["cost"] == pytest.approx(2200.0)
    assert trade["proceeds"] == pytest.approx(2800.0)
    assert trade["pnl"] == pytest.approx(600.0)
    assert trade["buy_price"] == pytest.approx(11.0)
    assert trade["sell_price"] == pytest.approx(14.0)
    assert trade["hold_days"] == 4
    assert [leg["side"] for leg in trade["legs"]] == ["B", "B", "S", "S"]


def test_analysis_summarizes_path_and_timing() -> None:
    trade = {
        "trade_key": "k1",
        "symbol": "600000.SH",
        "name": "浦发银行",
        "open_date": "2026-01-05",
        "open_time": "09:35:00",
        "close_date": "2026-01-08",
        "close_time": "14:55:00",
        "qty": 100,
        "buy_price": 10.0,
        "sell_price": 11.0,
        "cost": 1000.0,
        "proceeds": 1100.0,
        "pnl": 100.0,
        "ret": 0.1,
        "fees": 5.0,
        "hold_days": 3,
        "buy_count": 1,
        "sell_count": 1,
        "legs": [{
            "date": "2026-01-05", "time": "09:35:00", "side": "B",
            "qty": 100, "price": 10.0, "cash_flow": -1000.0, "fees": 0.0,
        }],
    }
    bars = [
        {"date": date(2025, 12, 1), "open": 9.0, "high": 9.2, "low": 8.8, "close": 9.0},
        *[
            {"date": date(2025, 12, day), "open": 9.0, "high": 9.5, "low": 8.9, "close": 9.2}
            for day in range(2, 32)
        ],
        {"date": date(2026, 1, 5), "open": 9.8, "high": 10.1, "low": 9.5, "close": 10.0},
        {"date": date(2026, 1, 6), "open": 10.2, "high": 10.9, "low": 10.0, "close": 10.8},
        {"date": date(2026, 1, 7), "open": 10.8, "high": 11.0, "low": 9.6, "close": 10.0},
        {"date": date(2026, 1, 8), "open": 10.0, "high": 11.2, "low": 9.9, "close": 11.0},
        *[
            {"date": date(2026, 1, 9 + offset), "open": 11.0, "high": 12.0, "low": 10.9, "close": 11.5}
            for offset in range(10)
        ],
    ]

    result = analyze_trade(trade, bars)

    assert result["analysis_status"] == "full"
    assert result["hold_td"] == 3
    assert result["mfe"] == pytest.approx(0.12)
    assert result["mae"] == pytest.approx(-0.05)
    assert result["post5"] == pytest.approx(11.5 / 11 - 1)
    assert "盈利" in result["tags"]
    assert "短线" in result["tags"]
    assert "追高" in result["tags"]
