"""每日复盘入口：对账表与产物形态。"""
from pathlib import Path

from tsp_ledger.daily import RECONCILE_COLUMNS, build_reconcile, daily_review
from tsp_ledger.derive import PriceBook, TradingCalendar, build_daily, build_roundtrips
from tsp_ledger.parse import Event

DAY = "2026-11-06"
CAL = TradingCalendar(["2026-11-05", "2026-11-06"])


def ev(date, time, code, category, qty=0, amount=0.0, cash=0.0, fees=0.0, name="杭电股份"):
    if qty and category == "trade_sell":
        net_px = (abs(amount) - fees) / qty
    elif qty and category == "trade_buy":
        net_px = (abs(amount) + fees) / qty
    else:
        net_px = 0.0
    return Event(
        event_uid=f"{date}|{time}|{code}|{category}", trade_date=date, settle_date=date,
        trade_time=time, code=code, name=name, raw_type="证券买入" if category == "trade_buy" else "证券卖出",
        category=category, qty=qty, price=amount / qty if qty else 0.0, amount=amount, cash=cash,
        comm=fees, other_fee=0.0, stamp=0.0, transfer_fee=0.0, shares_after=0, cash_after=0.0,
        deal_no=f"D{time}", holder="", serial="", market="SH", ccy="CNY",
        side="B" if category == "trade_buy" else "S", net_px=net_px, row_no=1,
    )


EVENTS = [
    ev(DAY, "09:33:16", "603618", "trade_buy", 700, 15736.0, -15741.16, fees=5.16),
    ev(DAY, "14:52:31", "603618", "trade_sell", 600, 13860.0, 13847.93, fees=12.07),
]


def test_reconcile_columns_and_link_status():
    signals = {(DAY, "603618", "B"): {"signal_id": "sig-1", "time": "09:30:00", "side": "B",
                                      "qty": "700", "px": "22.45"}}
    rows = build_reconcile(EVENTS, DAY, signals)
    assert len(rows) == 2
    assert all(len(r) == len(RECONCILE_COLUMNS) for r in rows)
    by_side = {r[4]: r for r in rows}
    assert by_side["B"][9] == "sig-1"          # signal_id 回填
    assert by_side["B"][16] == "matched"
    assert by_side["S"][16] == "no_signal"
    assert by_side["B"][14] == "待填"           # 偏离类型留给决策侧


def test_reconcile_without_signals_is_empty_plan_table():
    rows = build_reconcile(EVENTS, DAY, None)
    assert all(r[16] == "no_signal" for r in rows)
    assert all(r[9] == "" and r[13] == "" for r in rows)


def test_daily_review_writes_pack(tmp_path):
    prices = PriceBook({"603618": {"2026-11-05": 22.0, DAY: 23.08}})
    events = [ev("2026-11-05", "09:30:00", "", "deposit_in", 0, 0, 30000, name="")] + EVENTS
    daily, positions, detail = build_daily(events, CAL, prices, opening_cash=0.02)
    rts = build_roundtrips(events, CAL)
    res = daily_review(events, rts, daily, positions, DAY, tmp_path)

    out = Path(res["out_dir"])
    for name in ("events.csv", "fills.csv", "roundtrips.csv", "equity.csv",
                 "positions.csv", "reconcile.csv", "summary.md"):
        assert (out / name).exists(), name

    assert res["fills"] == 2
    assert res["realized_pnl"] > 0          # 卖 23.08 > 买 22.49
    assert res["reconcile_rows"] == 2
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "复盘日报 2026-11-06" in summary
    assert "对账" in summary


def test_daily_review_for_unknown_day_keeps_headers(tmp_path):
    prices = PriceBook({})
    daily, positions, _ = build_daily(EVENTS, CAL, prices, opening_cash=0.02)
    res = daily_review(EVENTS, [], daily, positions, "2026-11-09", tmp_path)
    assert res["fills"] == 0
    assert (Path(res["out_dir"]) / "equity.csv").exists()
    assert (Path(res["out_dir"]) / "reconcile.csv").exists()
