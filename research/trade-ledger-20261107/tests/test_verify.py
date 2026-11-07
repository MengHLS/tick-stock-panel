"""与临时基准目录的比对回归（只跑解析层，不读行情，秒级）。"""
from tsp_ledger.derive import TradingCalendar, build_roundtrips, bond_cost_map
from tsp_ledger.parse import read_jiaogedan
from tsp_ledger.verify import compare_roundtrips, compare_trades


def test_trades_match_baseline_exactly(sample_csv, baseline_dir):
    res = read_jiaogedan(sample_csv)
    report = compare_trades(res.events, baseline_dir)
    assert report["rows_baseline"] == 717
    assert report["rows_mine"] == 717
    assert report["only_baseline"] == 0
    assert report["only_mine"] == 0
    assert report["field_diffs"] == {}
    assert report["match"] is True


def test_roundtrips_match_baseline_except_newbond_rows(sample_csv, baseline_dir):
    res = read_jiaogedan(sample_csv)
    rts = build_roundtrips(res.events, TradingCalendar(), bond_cost=bond_cost_map(res.events))
    report = compare_roundtrips(rts, baseline_dir)
    assert report["rows_baseline"] == 447
    assert report["rows_mine"] == 441
    assert report["only_mine"] == 0
    # 基准多出来的 6 行就是「新股入账被当成 0 价卖出」的伪回合
    assert report["only_baseline"] == 6
    assert report["pnl_diff_count"] == 0


def test_compat_mode_reproduces_baseline_row_count(sample_csv, baseline_dir):
    res = read_jiaogedan(sample_csv)
    rts = build_roundtrips(
        res.events, TradingCalendar(), bond_cost=bond_cost_map(res.events), compat_newbond=True
    )
    report = compare_roundtrips(rts, baseline_dir)
    assert report["rows_mine"] == 447
    assert report["only_baseline"] == 0
    assert report["only_mine"] == 0
    assert report["pnl_diff_count"] == 0
