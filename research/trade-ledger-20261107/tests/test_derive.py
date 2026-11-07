"""派生层：FIFO 回合、日频权益、绩效口径。"""
import math

import pytest

from tsp_ledger.analytics import performance
from tsp_ledger.derive import PriceBook, TradingCalendar, build_daily, build_roundtrips, bond_cost_map
from tsp_ledger.parse import Event


def ev(date, time, code, category, qty=0, amount=0.0, cash=0.0, fees=0.0, name="测试", uid=None):
    """按解析层同一口径造一条事件（含费净价由 amount/fees 推出）。"""
    if qty and category == "trade_sell":
        net_px = (abs(amount) - fees) / qty
    elif qty and category in {"trade_buy", "allocation_pay"}:
        net_px = (abs(amount) + fees) / qty
    else:
        net_px = 0.0
    return Event(
        event_uid=uid or f"{date}|{time}|{code}|{category}|{qty}|{amount}",
        trade_date=date, settle_date=date, trade_time=time, code=code, name=name,
        raw_type={"trade_buy": "证券买入", "trade_sell": "证券卖出",
                  "security_in": "新股入账", "allocation_pay": "配售缴款"}.get(category, category),
        category=category, qty=qty, price=amount / qty if qty else 0.0, amount=amount,
        cash=cash, comm=fees, other_fee=0.0, stamp=0.0, transfer_fee=0.0,
        shares_after=0, cash_after=0.0, deal_no=f"D{date}{time}",
        holder="", serial="", market="SH", ccy="CNY",
        kind="", side="B" if category in {"trade_buy", "security_in"} else "S",
        net_px=net_px, row_no=1,
    )


CAL = TradingCalendar(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])


def test_fifo_splits_one_sell_across_lots():
    events = [
        ev("2026-01-05", "09:30:00", "600000", "trade_buy", 100, 1000, -1000),
        ev("2026-01-06", "09:30:00", "600000", "trade_buy", 100, 1200, -1200),
        ev("2026-01-07", "10:00:00", "600000", "trade_sell", 150, 2250, 2250),
    ]
    rts = build_roundtrips(events, CAL)
    assert len(rts) == 2
    assert [r.qty for r in rts] == [100, 50]
    assert [round(r.pnl, 2) for r in rts] == [500.0, 150.0]
    assert round(sum(r.pnl for r in rts), 2) == 650.0
    assert [r.hold_days for r in rts] == [2.0, 1.0]
    assert [r.hold_td for r in rts] == [2.0, 1.0]
    assert rts[0].flags == "" and rts[1].flags == ""


def test_fees_enter_cost_and_proceeds():
    events = [
        ev("2026-01-05", "09:30:00", "600000", "trade_buy", 100, 1000, -1005, fees=5),
        ev("2026-01-06", "09:30:00", "600000", "trade_sell", 100, 1100, 1093, fees=7),
    ]
    (rt,) = build_roundtrips(events, CAL)
    assert rt.buy_px == pytest.approx(10.05)
    assert rt.sell_px == pytest.approx(10.93)
    assert rt.pnl == pytest.approx(88.0)


def test_sell_without_buy_is_flagged_unmatched():
    events = [ev("2026-01-06", "09:30:00", "113708", "trade_sell", 10, 1500, 1500)]
    (rt,) = build_roundtrips(events, CAL)
    assert rt.flags == "unmatched_sell"
    assert rt.unmatched_qty == 10
    assert rt.pnl is None
    assert math.isnan(rt.hold_td)


def test_bond_cost_attaches_to_unmatched_bond():
    events = [ev("2026-01-06", "09:30:00", "113708", "trade_sell", 10, 1500, 1500)]
    (rt,) = build_roundtrips(events, CAL, bond_cost={"113708": 100.0})
    assert rt.buy_px == 100.0
    assert rt.cost == 1000.0
    assert rt.pnl == 500.0
    assert rt.flags == "unmatched_sell"   # 仍是推算成本，不能进胜率分母


def test_allocation_pay_maps_to_bond_code_by_date_qty_name():
    events = [
        ev("2026-01-05", "10:00:00", "754019", "allocation_pay", 10, 1000, -1000, name="曙26配债"),
        ev("2026-01-05", "15:00:00", "113708", "security_in", 10, 0, 0, name="曙26转债"),
    ]
    m = bond_cost_map(events)
    assert m == {"113708": 100.0}


def test_allocation_pay_falls_back_to_unique_name_when_dates_differ():
    events = [
        ev("2026-01-04", "10:00:00", "754019", "allocation_pay", 10, 1000, -1000, name="曙26配债"),
        ev("2026-01-05", "15:00:00", "113708", "security_in", 10, 0, 0, name="曙26转债"),
    ]
    assert bond_cost_map(events) == {"113708": 100.0}


def test_ambiguous_bond_names_are_left_unpaired():
    events = [
        ev("2026-01-05", "10:00:00", "754019", "allocation_pay", 10, 1000, -1000, name="曙26配债"),
        ev("2026-01-05", "10:30:00", "754020", "allocation_pay", 10, 1000, -1000, name="曙26配债"),
        ev("2026-01-06", "15:00:00", "113708", "security_in", 10, 0, 0, name="曙26转债"),
    ]
    assert bond_cost_map(events) == {}


def test_newbond_is_not_a_roundtrip_by_default():
    events = [ev("2026-01-06", "09:30:00", "113708", "security_in", 10)]
    assert build_roundtrips(events, CAL) == []
    compat = build_roundtrips(events, CAL, compat_newbond=True)
    assert len(compat) == 1
    assert compat[0].flags == "unmatched_newbond"
    assert compat[0].qty == 10


def test_daily_equity_counts_external_flow_not_internal_transfer():
    day1 = [
        ev("2026-01-05", "09:30:00", "", "deposit_in", 0, 0, 10000),
        ev("2026-01-05", "10:00:00", "600000", "trade_buy", 100, 1000, -1000),
        ev("2026-01-05", "11:00:00", "", "internal_out", 0, 0, -5000),
        ev("2026-01-05", "11:00:01", "", "internal_in", 0, 0, 5000),
    ]
    day2 = [ev("2026-01-06", "10:00:00", "600000", "trade_sell", 50, 600, 600)]
    prices = PriceBook({"600000": {"2026-01-05": 10.0, "2026-01-06": 12.0}})
    rows, positions, detail = build_daily(day1 + day2, CAL, prices, opening_cash=0.02)

    d1, d2 = rows[0], rows[1]
    assert d1.cumdep == 10000.0          # 台账间划转不计入净入金
    assert d1.equity == pytest.approx(10000.02)
    assert d1.pnl == 0.0
    assert positions["2026-01-05"] == {"600000": 100}

    assert d2.pnl == pytest.approx(200.0)
    assert d2.mv == pytest.approx(600.0)
    assert positions["2026-01-06"] == {"600000": 50}
    assert any(r["price_src"] == "close" for r in detail)


def test_roundtrip_caliber_on_sample(sample_csv):
    from tsp_ledger.parse import read_jiaogedan

    res = read_jiaogedan(sample_csv)
    bond_cost = bond_cost_map(res.events)
    assert len(bond_cost) == 6
    assert set(bond_cost.values()) == {100.0}

    rts = build_roundtrips(res.events, TradingCalendar(), bond_cost=bond_cost)
    assert len(rts) == 441
    paired = [r for r in rts if not r.flags]
    unmatched = [r for r in rts if r.flags]
    assert len(paired) == 435
    assert len(unmatched) == 6
    assert round(sum(r.pnl for r in paired), 2) == -79597.28
    assert round(sum(r.pnl for r in unmatched), 2) == 3374.82
    assert {r.code for r in unmatched} == {"127109", "123259", "123263", "118063", "113708", "123287"}


def test_performance_uses_paired_denominator_only():
    paired = [
        build_roundtrips([ev("2026-01-05", "09:30:00", "600000", "trade_buy", 100, 1000, -1000),
                          ev("2026-01-06", "09:30:00", "600000", "trade_sell", 100, 1100, 1100)], CAL)[0],
    ]
    unmatched = build_roundtrips([ev("2026-01-06", "09:30:00", "113708", "trade_sell", 10, 1500, 1500)],
                                 CAL, bond_cost={"113708": 100.0})
    prices = PriceBook({"600000": {"2026-01-05": 10.0, "2026-01-06": 11.0}})
    daily, _, _ = build_daily(
        [ev("2026-01-05", "09:30:00", "", "deposit_in", 0, 0, 100000),
         ev("2026-01-05", "10:00:00", "600000", "trade_buy", 100, 1000, -1000),
         ev("2026-01-06", "10:00:00", "600000", "trade_sell", 100, 1100, 1100)],
        CAL, prices, opening_cash=0.02,
    )
    perf = performance(paired + unmatched, CAL.span("2026-01-05", "2026-01-06"), daily, [])
    assert perf["roundtrips"] == 2
    assert perf["roundtrips_paired"] == 1
    assert perf["roundtrips_unmatched_sell"] == 1
    assert perf["win_rate"] == 1.0                 # 只按配对回合算
    assert perf["pnl_realized"] == pytest.approx(100.0)
    assert perf["pnl_unmatched_est"] == pytest.approx(500.0)
    assert perf["pnl_total_est"] == pytest.approx(600.0)
    assert perf["max_drawdown"] <= 1.0


def test_pnl_bridge_ties_to_equity_pnl():
    """多批次买入 + 部分卖出 + 剩余持仓：桥接残差应为 0（防重复计算）。"""
    from tsp_ledger.analytics import pnl_bridge

    events = [
        ev("2026-01-05", "09:30:00", "", "deposit_in", 0, 0, 100000, name=""),
        ev("2026-01-05", "10:00:00", "600000", "trade_buy", 100, 1000, -1000),
        ev("2026-01-06", "10:00:00", "600000", "trade_buy", 100, 2000, -2000),
        ev("2026-01-07", "10:00:00", "600000", "trade_sell", 150, 2700, 2700),
    ]
    cal = TradingCalendar(["2026-01-05", "2026-01-06", "2026-01-07"])
    prices = PriceBook({"600000": {"2026-01-05": 10.0, "2026-01-06": 20.0, "2026-01-07": 18.0}})
    daily, _, detail = build_daily(events, cal, prices, opening_cash=0.02)
    rts = build_roundtrips(events, cal)

    bridge = pnl_bridge(rts, daily, events, detail)
    assert bridge["roundtrip_pnl"] == pytest.approx(700.0)   # 100×8 + 50×(−2)
    assert bridge["unrealized_end"] == pytest.approx(-100.0)  # 剩 50 股 @20，现价 18
    assert bridge["equity_cum_pnl"] == pytest.approx(600.0)
    assert abs(bridge["residual"]) <= 0.01


def test_pricebook_coverage_flags_empty_book():
    """缺 polars / 缺行情分区时价格簿为空，coverage 必须显式暴露，供派生入口拦截。"""
    empty = PriceBook({}).coverage()
    assert empty["codes"] == 0 and empty["days"] == 0
    assert empty["day_min"] is None and empty["day_max"] is None

    pb = PriceBook({"600000": {"2026-01-05": 10.0, "2026-01-06": 11.0},
                    "000001": {"2026-01-06": 9.5}})
    cov = pb.coverage()
    assert cov["codes"] == 2 and cov["days"] == 2
    assert cov["day_min"] == "2026-01-05" and cov["day_max"] == "2026-01-06"


def test_derive_refuses_when_prices_missing(tmp_path, sample_csv, monkeypatch):
    """价格为 0 条时必须报错，而不是静默把所有持仓市值算成 0。"""
    from tsp_ledger import cli, store
    from tsp_ledger.parse import read_jiaogedan

    db = tmp_path / "ledger.sqlite"
    con = store.connect(db)
    res = read_jiaogedan(sample_csv)
    store.import_events(con, res.events, sample_csv, res.encoding, res.total_rows, res.skipped_rows)
    con.close()

    monkeypatch.setattr(cli, "load_prices", lambda *a, **k: PriceBook({}))
    args = cli.build_parser().parse_args(
        ["derive", "--db", str(db), "--out", str(tmp_path / "out")]
    )
    with pytest.raises(SystemExit) as exc:
        cli.cmd_derive(args)
    assert "行情价格" in str(exc.value)

    # 显式放行时才继续（供无行情环境下调试）
    args_ok = cli.build_parser().parse_args(
        ["derive", "--db", str(db), "--out", str(tmp_path / "out2"), "--allow-no-prices"]
    )
    cli.cmd_derive(args_ok)  # 不抛错
