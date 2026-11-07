"""对账：e3_b2_fixtures_20261107.json vs docs/factors/E3_DATA_AVAILABILITY_20261107.md（17:27）

逐个断言比对，任一条失败 exit 1。只读 JSON 与文档文本，不查库。
用法:
    backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/verify_b2_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
J = PROJECT / "docs/factors/evidence/e3_b2_fixtures_20261107.json"
MD = PROJECT / "docs/factors/E3_DATA_AVAILABILITY_20261107.md"

doc = json.loads(J.read_text(encoding="utf-8"))
md = MD.read_text(encoding="utf-8")

checks: list[tuple[str, object, object]] = []


def ck(name, got, want):
    checks.append((name, got, want))


st = doc["st_unknown_window"]["result"]
rows = st["rows"]
tot = st["totals"]
# 契约 8 日窗口 = 2026-10-20..2026-10-29
win8 = [r for r in rows if "2026-10-20" <= r["date"][:10] <= "2026-10-29"]
ck("st: 逐日行数 = 14（2026-10-20..11-06 交易日）", len(rows), 14)
ck("st: 8 日窗口内交易日数 = 8", len(win8), 8)
ck("st: 8 日内 st_events_true 合计 = 0", sum(r["st_events_true"] for r in win8), 0)
ck("st: 8 日内 st_events_false 合计 = 202", sum(r["st_events_false"] for r in win8), 202)
ck("st: 全 14 日 st_events_true 合计 = 0", tot["win_true_events"], 0)
ck("st: 全 14 日 st_events_false 合计 = 202", tot["win_false_events"], 202)
ck("st: 2026-10-20 批量置 False = 198 行", tot["bulk_false_on_1020"], 198)
ck("st: 14 日内 as-of ST=True 家数最小 = 20", tot["min_st_true_panel"], 20)
ck("st: 14 日内 as-of ST=True 家数最大 = 20", tot["max_st_true_panel"], 20)
ck("md: 文档称 ST=True 由 218 突降 20", "218" in md and "突降 20" in md, True)
ck("st: 14 日 bar 行合计 = 44,654", int(tot["sum_bar_rows"]), 44654)
ck("st: 10-20 bar_rows = 3191（文档表 3,191）", rows[0]["bar_rows"], 3191)
ck("st: 10-29 bar_rows = 3189（文档表 3,189）", [r for r in rows if r["date"][:10] == "2026-10-29"][0]["bar_rows"], 3189)
ck("st: 11-06 bar_rows = 3190（文档表 3,190）", rows[-1]["bar_rows"], 3190)
ck("st: 全部 14 日 st_null_all_symbols = 0", sum(r["st_null_all_symbols"] for r in rows), 0)

dp = doc["delist_proxy"]["result"]
ck("delist: 消失标的数 = 195", len(dp["disappeared"]), 195)
ck("delist: stats.n_symbols = 195", dp["stats"]["n_symbols"], 195)
ck("delist: >=250 交易日无行情 = 171", dp["stats"]["n_ge250"], 171)
ck("delist: <60 日 = 8", dp["stats"]["n_lt60"], 8)
ck("delist: 最后 bar 在评估窗内 = 194，窗后 = 1", 
   (dp["stats"]["n_last_bar_within_eval"], dp["stats"]["n_last_bar_after_eval"]), (194, 1))
yr = {r["y"]: r["n_symbols"] for r in dp["by_last_bar_year"]}
ck("delist: 消失年份分布 = 5,12,18,34,37,43,24,22", [yr[y] for y in sorted(yr)], [5, 12, 18, 34, 37, 43, 24, 22])
ck("delist: 消失年份合计 = 195", sum(yr.values()), 195)
rs = dp["resume_after_gt250"]
ck("delist: >250 复牌段数 = 4", rs["stats"]["n_segments"], 4)
ck("delist: >250 复牌标的数 = 4", rs["stats"]["n_symbols"], 4)
ck("delist: >250 复牌合计标的日 = 1,418", int(rs["stats"]["sum_symbol_days"]), 1418)
ck("delist: 最长缺口 = 589 日", rs["stats"]["max_len"], 589)
ck("delist: 含 000670.SZ 589 日", [s["symbol"] for s in rs["segments"] if s["gap_trading_days"] == 589], ["000670.SZ"])
ck("delist: 4 段全部 resumed=True", all(s["resumed"] for s in rs["segments"]), True)
ck("delist: 每段起止日齐全", all(s["start_date"] and s["end_date"] for s in rs["segments"]), True)
# 缺口长度分布（文档 1日1423/2-5:537/6-20:535/21-60:78/61-120:0/121-250:5/>250:4）
gr = {r["bucket"]: r["n_runs"] for r in doc["suspend_gap"]["result"]["gap_runs"]}
ck("gap: 1 日段 = 1423", gr.get("1"), 1423)
ck("gap: 2-5 日段 = 537", gr.get("2-5"), 537)
ck("gap: 6-20 日段 = 535", gr.get("6-20"), 535)
ck("gap: 21-60 日段 = 78", gr.get("21-60"), 78)
ck("gap: 61-120 日段 = 0（无该键）", gr.get("61-120"), None)
ck("gap: 121-250 日段 = 5", gr.get("121-250"), 5)
ck("gap: >250 日段 = 4", gr.get(">250"), 4)

lp = doc["listing_date_parse"]["result"]
ck("listing: 样例 20 行", len(lp["sample_rows"]), 20)
ck("listing: 维表 5,536 行 / 非空 5,533", 
   (lp["parse_coverage"]["n_inst_rows"], lp["parse_coverage"]["n_listing_nonnull"]), (5536, 5533))
ck("listing: 解析失败 3 行", lp["parse_coverage"]["n_parse_fail"], 3)
ck("listing: 取值域 1990-12-01..2026-11-03", 
   (lp["parse_coverage"]["raw_min"], lp["parse_coverage"]["raw_max"]), ("1990-12-01", "2026-11-03"))
ck("listing: 面板 3,385 只全部有上市日", 
   (lp["bj_and_missing"]["n_panel_symbols"], lp["bj_and_missing"]["n_panel_no_listing_date"]), (3385, 0))
ck("listing: 北交所 355 只有 bar / 维表 0 行", 
   (lp["bj_and_missing"]["n_bj_with_bars"], lp["bj_and_missing"]["n_bj_instruments_rows"]), (355, 0))
ck("listing: 窗内标的日 = 5,510,001", lp["observed_bars_ge120"]["n_symbol_days"], 5510001)
ck("listing: observed_bars>=120 = 5,428,988", lp["observed_bars_ge120"]["n_ge120"], 5428988)
ck("listing: 占比 98.53%", lp["observed_bars_ge120"]["pct_ge120"], 98.53)
ck("listing: 每行含原始串与解析日期", all(r["raw_listing_date"] and r["parsed_listing_date"] for r in lp["sample_rows"]), True)
ck("listing: 含 603056.SH（首根晚于上市日）", 
   [r["first_bar_lags_listing"] for r in lp["sample_rows"] if r["symbol"] == "603056.SH"], [True])
ck("listing: 有 listed_before_panel_start=True 的样例", 
   sum(1 for r in lp["sample_rows"] if r["listed_before_panel_start"]), 5)

sg = doc["suspend_gap"]["result"]
ck("gap: 缺行标的日 = 13,881", sg["totals"]["n_missing_symbol_days"], 13881)
ck("gap: 缺行标的数 = 1,218", sg["totals"]["n_symbols"], 1218)
ck("gap: 窗内行数 = 5,510,001", sg["totals"]["n_rows_eval"], 5510001)
ck("gap: volume=0 行 = 0", sg["volume_zero"]["n_volume_zero"], 0)
ck("gap: amount=0 行 = 0", sg["volume_zero"]["n_amount_zero"], 0)
ck("gap: 采集洞日 = 27", sg["hole_summary"]["n_hole_dates"], 27)
ck("gap: 落在洞日缺行 = 1,113", sg["hole_summary"]["n_gap_on_hole"], 1113)
ck("gap: 洞日缺行占比 = 8.0%", sg["hole_summary"]["pct_gap_on_hole"], 8.0)
ck("gap: 最大单日缺失率 = 2.316%", round(sg["hole_summary"]["max_daily_miss_ratio"] * 100, 3), 2.316)
ck("gap: 非洞日缺行 = 12,768", sg["hole_summary"]["n_gap_attributable_to_suspension"], 12768)
ck("gap: 洞日清单 27 条", len(sg["hole_dates"]), 27)
ck("gap: 洞日全部 miss_ratio > 1%", all(h["miss_ratio"] > 0.01 for h in sg["hole_dates"]), True)
gy = {r["year"]: r["n_missing"] for r in sg["by_year"]}
ck("gap: 按年缺行 = 642/3072/2479/2206/1089/1374/1759/1260",
   [gy[y] for y in sorted(gy)], [642, 3072, 2479, 2206, 1089, 1374, 1759, 1260])
ck("gap: 按年合计 = 13,881", sum(gy.values()), 13881)

# 文档里出现的每个关键数字是否真的在 md 中（防止文档与 JSON 各说各话）
for token in ["13,881", "1,218", "5,510,001", "114,461", "46,606", "171", "195",
              "5,428,988", "98.5", "7,758", "5,817", "1,418", "589", "2,772"]:
    ck(f"md 含数字 {token}", token in md, True)

fails = [(n, g, w) for n, g, w in checks if g != w]
width = max(len(n) for n, _, _ in checks)
for n, g, w in checks:
    mark = "OK  " if g == w else "FAIL"
    print(f"{mark} {n:<{width}}  got={g!r} want={w!r}")
print()
print(f"{len(checks) - len(fails)}/{len(checks)} passed")
if fails:
    print("FAILED:")
    for n, g, w in fails:
        print(f"  - {n}: got={g!r} want={w!r}")
    sys.exit(1)
print("ALL PASS")
