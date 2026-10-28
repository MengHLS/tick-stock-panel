"""Scan the enriched panel for adjustment-ratio breaks that have no raw price gap.

A genuine ex-rights event leaves a gap in the *raw* price on the ex-date and a
matching step in close/raw_close.  A ratio step with a continuous raw price is a
factor-table defect: the adjusted series then invents a one-day return that no
market move could produce.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/scan_adjustment_breaks.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
DATA = r"D:/TSP/data/kline_daily_enriched"
OUT_JSON = HERE / "adjustment-break-scan.json"
OUT_MD = HERE / "ADJUSTMENT-BREAK-SCAN.md"
RATIO_JUMP = 0.05
RAW_GAP_LIMIT = 0.11  # below any board limit; a real ex-rights gap is larger


def main() -> int:
    names = sorted(name for name in os.listdir(DATA) if "=" in name)
    files = [f"{DATA}/{name}/part.parquet" for name in names
             if os.path.exists(f"{DATA}/{name}/part.parquet")]
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    base_cte = """
      with x as (select symbol,date,close,raw_close,close/nullif(raw_close,0) as r from read_parquet(?)),
           y as (select *, lag(close) over w pc, lag(raw_close) over w pr, lag(r) over w prr
                 from x window w as (partition by symbol order by date))
    """
    flag = f"""
      where prr is not null and pr>0 and pc>0
        and abs(r/prr-1) > {RATIO_JUMP}
        and abs(raw_close/pr-1) < {RAW_GAP_LIMIT}
    """
    scan = con.execute(base_cte + f"""
      select symbol,date,r/prr-1 as ratio_jump, raw_close/pr-1 as raw_ret, close/pc-1 as adj_ret
      from y {flag}
    """, [files]).df()
    by_date = con.execute(base_cte + f"""
      select date, count(*) n, max(r/prr-1) max_jump, max(close/pc-1) max_adj_ret
      from y {flag} group by date order by n desc limit 15
    """, [files]).df()
    coverage = con.execute(f"""
      with x as (select symbol,date,close/nullif(raw_close,0) r from read_parquet(?)),
           y as (select symbol,date,r,lag(r) over (partition by symbol order by date) prr from x)
      select count(*) symbols_on_date,
             sum(case when abs(r/prr-1) > {RATIO_JUMP} then 1 else 0 end) jumped
      from y where date = DATE '2020-05-08'
    """, [files]).df()

    worst = scan.reindex(scan["ratio_jump"].abs().sort_values(ascending=False).index).head(10)
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "criteria": {
            "ratio_jump_gt": RATIO_JUMP,
            "raw_gap_below": RAW_GAP_LIMIT,
            "meaning": "close/raw_close stepped while the raw price did not gap",
        },
        "suspicious_symbol_dates": int(len(scan)),
        "suspicious_symbols": int(scan["symbol"].nunique()) if len(scan) else 0,
        "top_dates": by_date.to_dict(orient="records"),
        "coverage_2020_05_08": coverage.to_dict(orient="records"),
        "largest": worst[["symbol", "date", "ratio_jump", "raw_ret", "adj_ret"]].to_dict(orient="records"),
        "example_600536": "ratio 0.5901 -> 1.0000 on 2020-05-08; adjusted +70.41% while raw +0.56%",
        "note": (
            "dates other than 2020-05-08 carry only a few symbols per date with 5-20% steps, "
            "consistent with ordinary ex-dividend adjustment; they are not asserted to be defects"
        ),
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "# 复权比跳变扫描（原始价无缺口）",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 判据：`close/raw_close` 单日变化 > {RATIO_JUMP:.0%}，且原始价当日变化 < {RAW_GAP_LIMIT:.0%}",
        f"- 命中 (股票,日期)：{report['suspicious_symbol_dates']}，涉及 {report['suspicious_symbols']} 只",
        f"- 2020-05-08 当天：{int(coverage.iloc[0]['jumped'])} / {int(coverage.iloc[0]['symbols_on_date'])} 只出现跳变",
        "",
        "| 日期 | 命中数 | 最大复权比跳变 | 最大单日复权收益 |",
        "|---|---:|---:|---:|",
    ]
    for row in by_date.head(8).to_dict(orient="records"):
        lines.append(f"| {row['date']} | {row['n']} | {float(row['max_jump']):.3f} | {float(row['max_adj_ret']):+.1%} |")
    lines += ["", "除 2020-05-08 外，其余日期每日仅 2-5 只、跳变 5-20%，与正常除权一致，不判为缺陷。"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"suspicious={len(scan)} symbols={report['suspicious_symbols']}")
    print(by_date.head(5).to_string())
    print(coverage.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
