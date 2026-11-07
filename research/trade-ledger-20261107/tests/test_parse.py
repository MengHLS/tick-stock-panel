"""解析层：编码识别、脏值还原、分类、去重键。"""
from collections import Counter

import pytest

from tsp_ledger.parse import (
    CATEGORY,
    clean_cell,
    classify_kind,
    detect_encoding,
    normalize_code,
    read_jiaogedan,
    to_float,
    to_int,
)


def test_detect_encoding_utf8():
    assert detect_encoding("a,b\n1,2\n".encode("utf-8")) == "utf-8"


def test_detect_encoding_bom():
    assert detect_encoding("\ufeffa,b\n".encode("utf-8")) == "utf-8-sig"


def test_detect_encoding_gbk():
    raw = "发生日期,证券代码\n2026-01-05,600000\n".encode("gbk")
    assert detect_encoding(raw).startswith("gb")


def test_clean_cell_restores_formula_wrapper():
    assert clean_cell('= "600000      "') == "600000"
    assert clean_cell('="  杭电股份 "') == "杭电股份"


@pytest.mark.parametrize("raw", ["--", "-", "—", "None", "nan", ""])
def test_clean_cell_empty_markers(raw):
    assert clean_cell(raw) == ""


def test_numbers_with_thousands_sep():
    assert to_float("1,234.50") == 1234.5
    assert to_int("1,200") == 1200
    assert to_float("--") == 0.0


def test_normalize_code():
    assert normalize_code('= "600000      "') == "600000"
    assert normalize_code("600000.SH") == "600000"
    assert normalize_code("") == ""


@pytest.mark.parametrize(
    "code,kind",
    [("600000", "股票"), ("300750", "股票"), ("113708", "转债"), ("754019", "发债"), ("510300", "ETF")],
)
def test_classify_kind(code, kind):
    assert classify_kind(code) == kind


def test_category_table_covers_broker_types():
    # 本单出现过的 12 类原始交易类别都必须有明确映射，不能落到 other
    for raw in ["证券买入", "证券卖出", "银行转证券", "证券转银行", "台账间现金划转取",
                "台账间现金划转存", "配售缴款", "新股入账", "红利入账", "股息红利差异扣税",
                "利息归本", "投顾服务费扣收"]:
        assert raw in CATEGORY


def test_unknown_category_warns(tmp_path):
    header = ("交收日期,发生日期,发生时间,证券代码,证券名称,交易类别,成交数量,成交均价,成交金额,"
              "发生金额,佣金,其他费用,印花税,过户费,股份余额,资金余额,成交编号,股东账号,流水号,"
              "交易市场,币种\n")
    row = ("2026-01-05,2026-01-05,09:30:00,600000,浦发银行,融资买入,100,10,1000,-1000,"
           "0,0,0,0,100,0,D1,A1,S1,SH,CNY\n")
    csv_path = tmp_path / "unknown.csv"
    csv_path.write_text(header + row, encoding="utf-8")
    res = read_jiaogedan(csv_path)
    assert res.events[0].category == "other"
    assert res.events[0].cash == -1000.0
    assert any("未知交易类别" in w for w in res.warnings)


def test_missing_header_raises(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("日期,代码\n2026-01-05,600000\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_jiaogedan(csv_path)


def test_sample_file_parses(sample_csv):
    res = read_jiaogedan(sample_csv)
    assert res.encoding == "gb18030"
    assert len(res.events) == 1055
    assert res.skipped_rows == 0
    cats = Counter(e.category for e in res.events)
    assert cats["trade_buy"] == 377
    assert cats["trade_sell"] == 328
    assert cats["deposit_in"] == 135
    assert cats["deposit_out"] == 190
    assert cats["security_in"] == 6
    assert cats["allocation_pay"] == 6
    assert cats["other"] == 0
    assert res.events[0].trade_date <= res.events[-1].trade_date
    assert {res.events[0].trade_date, res.events[-1].trade_date} == {"2025-03-21", "2026-11-06"}


def test_sample_codes_are_restored(sample_csv):
    res = read_jiaogedan(sample_csv)
    assert all(len(e.code) == 6 for e in res.events if e.code)
    assert all(e.code.isdigit() for e in res.events if e.code)


def test_event_uid_is_stable(sample_csv):
    a = read_jiaogedan(sample_csv)
    b = read_jiaogedan(sample_csv)
    assert [e.event_uid for e in a.events] == [e.event_uid for e in b.events]
    assert len({e.event_uid for e in a.events}) == len(a.events)


def test_cash_sum_matches_broker_amounts(sample_csv):
    res = read_jiaogedan(sample_csv)
    assert round(sum(e.cash for e in res.events), 2) == 44.34
