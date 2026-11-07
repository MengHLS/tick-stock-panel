#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""独立复核：不复用 audit_data_gaps.py 的任何函数，只用自己的 DuckDB 会话 + 文件系统普查，
重算 616 / 78 / 355 / 236 / 650 与四类阻塞的关键数字，写出 results/independent_recheck.json。

目的：让「审计脚本自己说对了」变成「第二条独立路径也说对了」。
只读 D:/TSP/data，只写本目录 results/。

用法：
    PYTHONUTF8=1 backend/.venv/Scripts/python.exe \
        research/data-gaps-20261107/scripts/independent_recheck.py
退出码：0 = 全部复核项跑通（不代表数据可用）；2 = 有复核项与报告不一致。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import duckdb

DATA_ROOT = Path(os.environ.get("TSP_DATA_ROOT", r"D:/TSP/data"))
OUT = Path(__file__).resolve().parent.parent / "results" / "independent_recheck.json"

# 报告里的既有结论（用于自动比对，避免"跑通了但数字变了"）
EXPECTED = {
    "panel_symbols": 5813,
    "panel_trading_days": 2141,
    "instruments_symbols": 5536,
    "adj_symbols": 5197,
    "no_adj_in_panel": 616,
    "instr_not_in_panel": 78,
    "panel_not_in_instr": 355,
    "panel_no_financials": 236,
    "instr_no_adj": 650,
    "industry_partitions": 6,
    "industry_panel_days_aligned": 5,
    "etf_dirs_empty": 4,
    "index_symbols": 599,
    "index_constituent_columns": 0,
}


def main() -> int:
    con = duckdb.connect()
    facts: list[dict] = []

    def rec(name: str, value, sql: str | None = None, note: str | None = None) -> None:
        item = {"name": name, "value": value}
        if sql:
            item["sql"] = " ".join(sql.split())
        if note:
            item["note"] = note
        facts.append(item)

    # ---------- 1. 三个宇宙 ----------
    q_panel = (f"select distinct symbol from read_parquet('{DATA_ROOT.as_posix()}/kline_daily/**/*.parquet',"
               " hive_partitioning=1)")
    q_inst = (f"select distinct symbol from read_parquet('{DATA_ROOT.as_posix()}/instruments/**/*.parquet',"
              " hive_partitioning=1)")
    q_adj = f"select distinct symbol from read_parquet('{(DATA_ROOT / 'adj_factor' / 'all.parquet').as_posix()}')"
    q_fin = (f"select distinct symbol from read_parquet('{DATA_ROOT.as_posix()}/financials/**/*.parquet',"
             " hive_partitioning=1)")

    con.sql(f"create or replace view p as {q_panel}")
    con.sql(f"create or replace view i as {q_inst}")
    con.sql(f"create or replace view a as {q_adj}")
    con.sql(f"create or replace view f as {q_fin}")

    def one(sql: str) -> int:
        v = con.sql(sql).fetchone()[0]
        return int(v)

    counts = {
        "panel_symbols": one("select count(*) from p"),
        "panel_trading_days": one(
            f"select count(distinct date) from read_parquet('{DATA_ROOT.as_posix()}/kline_daily/**/*.parquet',"
            " hive_partitioning=1)"),
        "instruments_symbols": one("select count(*) from i"),
        "adj_symbols": one("select count(*) from a"),
        "fin_symbols": one("select count(*) from f"),
        "no_adj_in_panel": one("select count(*) from p where symbol not in (select symbol from a)"),
        "instr_not_in_panel": one("select count(*) from i where symbol not in (select symbol from p)"),
        "panel_not_in_instr": one("select count(*) from p where symbol not in (select symbol from i)"),
        "panel_no_financials": one("select count(*) from p where symbol not in (select symbol from f)"),
        "instr_no_adj": one("select count(*) from i where symbol not in (select symbol from a)"),
        "panel_instr_intersection": one("select count(*) from p where symbol in (select symbol from i)"),
        "adj_outside_panel": one("select count(*) from a where symbol not in (select symbol from p)"),
    }
    rec("三个宇宙与四个差集", counts,
        sql="p=panel(i), i=instruments, a=adj_factor, f=financials; 差集方向见字段名",
        note="78/355 互为反向差集，不可相加对账")

    # 616 的分解：instr / no-instr
    split = con.sql("""
        select
          count(*) filter (where symbol in (select symbol from i)) as no_adj_with_instr,
          count(*) filter (where symbol not in (select symbol from i)) as no_adj_without_instr
        from p where symbol not in (select symbol from a)
    """).fetchone()
    rec("616 的构成分解", {"面板内且有元数据": int(split[0]), "面板内且无元数据": int(split[1])},
        sql="select count(*) filter (where symbol in (select symbol from i)) ... from p where symbol not in (select symbol from a)")

    # ---------- 2. 616 只的复权价一致性（是否真的"没缺"） ----------
    cons = con.sql(f"""
        select count(*) as rows_scanned,
               count(*) filter (where close is not null and raw_close is not null
                                and abs(close - raw_close) > 1e-6) as rows_diff,
               count(distinct symbol) filter (where close is not null and raw_close is not null
                                and abs(close - raw_close) > 1e-6) as syms_diff
        from read_parquet('{DATA_ROOT.as_posix()}/kline_daily_enriched/**/*.parquet', hive_partitioning=1)
        where symbol not in (select symbol from a)
    """).fetchone()
    rec("616 只的 close vs raw_close 一致性",
        {"rows_scanned": int(cons[0]), "rows_with_diff": int(cons[1]), "symbols_with_diff": int(cons[2])},
        sql="... from read_parquet(kline_daily_enriched) where symbol not in (select symbol from a)",
        note="0 差异只证明本地复权价与原始价同值；真实公司行为是否漏记仍未知")

    # ---------- 3. 行业 PIT 覆盖 ----------
    pit_glob = (DATA_ROOT / "ext_data" / "ext_hy_ths_pit" / "timeseries").as_posix()
    parts = sorted((DATA_ROOT / "ext_data" / "ext_hy_ths_pit" / "timeseries").glob("date=*"))
    rec("行业时点快照分区", {"partitions": len(parts), "dates": [p.name.split("=")[-1] for p in parts]},
        note="目录枚举，非 SQL")

    aligned = con.sql(f"""
        with snap as (select distinct cast(date as varchar) as d from
            read_parquet('{pit_glob}/date=*/part.parquet', hive_partitioning=1)),
        panel_days as (select distinct cast(date as varchar) as d from
            read_parquet('{DATA_ROOT.as_posix()}/kline_daily/**/*.parquet', hive_partitioning=1))
        select count(*) from snap where d in (select d from panel_days)
    """).fetchone()[0]
    rec("行业快照与面板交易日同日对齐天数", int(aligned),
        sql="snap(d) ∩ panel_days(d) 计数",
        note="分母是面板 2141 个交易日")

    pit_syms = con.sql(f"""
        select count(distinct symbol) from read_parquet('{pit_glob}/date=*/part.parquet', hive_partitioning=1)
    """).fetchone()[0]
    rec("行业快照累计证券数（6 天并集）", int(pit_syms))

    # ---------- 4. ETF 目录 ----------
    etf = {}
    for name in ("kline_etf_daily", "kline_etf_enriched", "kline_etf_minute", "adj_factor_etf"):
        p = DATA_ROOT / name
        files = [x for x in p.rglob("*") if x.is_file()] if p.is_dir() else []
        etf[name] = {"exists": p.is_dir(), "files": len(files),
                     "bytes": sum(x.stat().st_size for x in files)}
    n_empty = sum(1 for v in etf.values() if v["exists"] and v["files"] == 0)
    rec("ETF 行情目录普查", {"dirs": etf, "empty_dirs": n_empty}, note="os.walk 语义的文件级普查")

    etf_in_stock = con.sql("select count(distinct symbol) from read_parquet("
                           f"'{DATA_ROOT.as_posix()}/kline_daily/**/*.parquet', hive_partitioning=1) "
                           "where regexp_matches(symbol, '^(51|15|56|58|16)')").fetchone()[0]
    rec("股票面板中的 ETF 形态代码数", int(etf_in_stock),
        sql="regexp_matches(symbol,'^(51|15|56|58|16)') on kline_daily")

    # ---------- 5. 指数成分 ----------
    idx_cols = con.sql(f"""
        select column_name from (describe
            select * from read_parquet('{DATA_ROOT.as_posix()}/kline_index_enriched/**/*.parquet', hive_partitioning=1)
        ) where regexp_matches(lower(column_name), 'weight|constituent|member')
    """).fetchall()
    idx_syms = con.sql(f"select count(distinct symbol) from read_parquet("
                       f"'{DATA_ROOT.as_posix()}/kline_index_daily/**/*.parquet', hive_partitioning=1)").fetchone()[0]
    rec("指数数据集里的权重/成分列", {"matches": [list(map(str, r)) for r in idx_cols],
                                "index_symbols": int(idx_syms)},
        sql="describe kline_index_enriched where column_name ~ 'weight|constituent|member'")

    # 数据根下目录名普查
    hits = []
    pat = ("constituent", "weight", "成分", "权重", "member")
    for child in sorted(DATA_ROOT.iterdir()):
        if child.is_dir() and any(k in child.name.lower() for k in pat):
            hits.append(child.name)
    rec("数据根下名称含 成分/权重 的目录", hits, note="实际顶层目录名普查，范围为 DATA_ROOT 直接子目录")

    # ---------- 与报告比对 ----------
    got = {
        "panel_symbols": counts["panel_symbols"],
        "panel_trading_days": counts["panel_trading_days"],
        "instruments_symbols": counts["instruments_symbols"],
        "adj_symbols": counts["adj_symbols"],
        "no_adj_in_panel": counts["no_adj_in_panel"],
        "instr_not_in_panel": counts["instr_not_in_panel"],
        "panel_not_in_instr": counts["panel_not_in_instr"],
        "panel_no_financials": counts["panel_no_financials"],
        "instr_no_adj": counts["instr_no_adj"],
        "industry_partitions": len(parts),
        "industry_panel_days_aligned": int(aligned),
        "etf_dirs_empty": n_empty,
        "index_symbols": int(idx_syms),
        "index_constituent_columns": len(idx_cols),
    }
    diffs = {k: {"expected": EXPECTED[k], "got": got[k]} for k in EXPECTED if EXPECTED[k] != got[k]}

    payload = {
        "schema_version": "1.0",
        "check": "independent_recheck",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_root": str(DATA_ROOT),
        "python": sys.version.split()[0],
        "duckdb": duckdb.__version__,
        "method": "本脚本不复用 audit_data_gaps.py 的任何代码路径；独立 DuckDB 会话 + 独立文件普查",
        "facts": facts,
        "expected": EXPECTED,
        "got": got,
        "diffs": diffs,
        "all_match": not diffs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[independent_recheck] wrote {OUT}")
    print(f"[independent_recheck] diffs={diffs if diffs else 'none'}")
    return 0 if not diffs else 2


if __name__ == "__main__":
    raise SystemExit(main())
