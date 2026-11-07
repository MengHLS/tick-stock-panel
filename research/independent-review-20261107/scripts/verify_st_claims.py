#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E3 关键事实独立复算：st_history 表结构与 as-of ST 家数。

只读 D:\\TSP\\data。两种分母都算，用于解释「218→20」与「192→0」的差异：
  A) as-of over ST 表全部 symbol（不要求当日有 K 线 bar）
  B) as-of 只保留当日有 K 线 bar 的 symbol（E3 文档口径）

运行：
  cd <repo> && backend/.venv/Scripts/python.exe \
      research/independent-review-20261107/scripts/verify_st_claims.py <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

ST = "D:/TSP/data/st_history/part.parquet"
K = "D:/TSP/data/kline_daily/date=*/*.parquet"


def main(out: Path) -> int:
    con = duckdb.connect()
    con.execute("SET threads=8")
    res: dict = {}

    res["table_stats"] = con.execute(
        f"""SELECT count(*) n_rows,
                   count(DISTINCT symbol) n_symbols,
                   count(DISTINCT flag_date) n_flag_dates,
                   min(flag_date)::VARCHAR, max(flag_date)::VARCHAR,
                   sum(st_flag::INT) n_true,
                   count(*) FILTER (WHERE st_flag IS NULL) n_null,
                   count(DISTINCT (symbol, flag_date)) n_pairs
            FROM read_parquet('{ST}')"""
    ).fetchone()

    res["bulk_1020"] = con.execute(
        f"""SELECT st_flag, count(*) FROM read_parquet('{ST}')
            WHERE CAST(flag_date AS DATE) = DATE '2026-10-20' GROUP BY 1 ORDER BY 1"""
    ).fetchall()

    con.execute(
        f"CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('{K}', "
        "hive_partitioning=true, union_by_name=true)"
    )
    con.execute(f"CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('{ST}')")

    # A) 全 symbol as-of
    rows = []
    for d in ("2026-10-16", "2026-10-19", "2026-10-20", "2026-10-29"):
        n_true, n_sym = con.execute(
            f"""WITH x AS (SELECT symbol, st_flag,
                     row_number() OVER (PARTITION BY symbol ORDER BY fd DESC) rn
                  FROM st WHERE fd <= DATE '{d}')
                SELECT count(*) FILTER (WHERE st_flag), count(*) FROM x WHERE rn = 1"""
        ).fetchone()
        rows.append({"date": d, "st_true_all_symbols": n_true, "symbols": n_sym})
    res["asof_all_symbols"] = rows

    # B) 只保留当日有 bar 的 symbol
    con.execute(
        "CREATE TABLE bars AS SELECT k.symbol, k.d, s.st_flag FROM k ASOF LEFT JOIN st s "
        "ON k.symbol = s.symbol AND k.d >= s.fd WHERE k.d >= DATE '2026-10-10'"
    )
    res["asof_kline_bars"] = [
        {"date": str(d), "bars": bars, "st_true": t, "st_null": nl}
        for d, bars, t, nl in con.execute(
            "SELECT d, count(*), count(*) FILTER (WHERE st_flag), "
            "count(*) FILTER (WHERE st_flag IS NULL) FROM bars GROUP BY 1 ORDER BY 1"
        ).fetchall()
    ]

    # 最后一条记录为 True 的只数 / 最后一条落在 2026-10-20 的只数
    res["last_record"] = con.execute(
        """WITH last AS (SELECT symbol, max(fd) lf FROM st GROUP BY 1)
           SELECT count(*) FILTER (WHERE lf = DATE '2026-10-20'),
                  count(*) FILTER (WHERE lf = DATE '2026-10-20' AND NOT st_flag),
                  count(*) FILTER (WHERE st_flag)
           FROM last l JOIN st USING (symbol) WHERE st.fd = l.lf"""
    ).fetchone()

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/st_claims.json")))
