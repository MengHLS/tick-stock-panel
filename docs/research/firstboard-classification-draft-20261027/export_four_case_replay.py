"""冻结四只股票的历史首板回放数据（只读导出，不改数据、不改引擎）。

用途：为"历史首板逐事件回放"提供固定数据副本，使 策略研究师 与 量化验证员
可以在同一份字节上独立复算。所有计算字段都来自冻结 CSV，不重新查询数据库。

口径：
- 行情来自 D:/TSP/data/kline_daily_enriched（前复权 close/high/low + 原始 raw_*）。
- 首板身份 = 平台 consecutive_limit_ups == 1，属平台口径，历史制度未认证。
- 快照上界 2026-10-23；D+20 超出上界的事件标记 right_censored，不加后续行情。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
DATA = "D:/TSP/data"
SYMBOLS = ("000810.SZ", "002687.SZ", "600785.SH", "002354.SZ")
# 2023-10-01 起：保证任一窗口内事件都有 >=250 根前置 K 线用于背景位置
START = "2023-10-01"
END = "2026-10-23"          # 固定截止日，不加入之后行情
LOOKBACK_BARS = 250
FORWARD_DAYS = 20
WINDOW_START = "2025-10-13"  # 长图窗口起点，用于标记"窗口内事件"

QUERY = f"""SELECT symbol,date,open,high,low,close,volume,amount,raw_close,raw_high,raw_low,consecutive_limit_ups
FROM read_parquet('{DATA}/kline_daily_enriched/**/*.parquet',union_by_name=true)
WHERE date BETWEEN DATE '{START}' AND DATE '{END}'
  AND symbol IN ({','.join(repr(s) for s in SYMBOLS)})
ORDER BY symbol,date"""


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    return con


def _limit_rules(con) -> dict[str, dict]:
    """Board / current ST / listing date, straight from the dimension table."""
    rows = con.execute(
        f"""SELECT symbol,name,listing_date FROM read_parquet('{DATA}/instruments/*.parquet')
        WHERE symbol IN ({','.join(repr(s) for s in SYMBOLS)})"""
    ).fetchall()
    out = {}
    for symbol, name, listing in rows:
        if symbol.endswith(".BJ"):
            board, pct = "BJ", 0.30
        elif symbol[:3] in ("688", "689"):
            board, pct = "STAR", 0.20
        elif symbol[:3] in ("300", "301", "302"):
            board, pct = "GEM", 0.20
        else:
            board, pct = "MAIN", 0.10
        out[symbol] = {
            "name_now": name,
            "listing_date": str(listing) if listing else None,
            "board": board,
            "board_limit_pct_now": pct,
            "st_now": "ST" in str(name or "").upper(),
        }
    return out


def main() -> int:
    con = _connect()
    result = con.execute(QUERY)
    names = [d[0] for d in result.description]
    raw_rows = [dict(zip(names, r)) for r in result.fetchall()]
    if not raw_rows:
        raise RuntimeError("no rows; check symbol format")

    rules = _limit_rules(con)
    con.close()

    # ── 1. 路径表：原始价与前复权价并列，附前收与复权比 ──
    by_symbol: dict[str, list[dict]] = {s: [] for s in SYMBOLS}
    for r in raw_rows:
        by_symbol[r["symbol"]].append(r)
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda x: x["date"])
        for i, r in enumerate(rows):
            r["prev_raw_close"] = rows[i - 1]["raw_close"] if i else None
            r["prev_adjusted_close"] = rows[i - 1]["close"] if i else None
            r["adj_ratio"] = (r["close"] / r["raw_close"]) if r["raw_close"] else None
            r["change_pct_raw"] = (
                (r["raw_close"] / r["prev_raw_close"] - 1.0) if r["prev_raw_close"] else None
            )
            r["bar_index_1based"] = i + 1
            r["date"] = str(r["date"])

    path_fields = [
        "symbol", "date", "bar_index_1based", "open", "high", "low", "close",
        "volume", "amount", "raw_close", "raw_high", "raw_low",
        "prev_raw_close", "prev_adjusted_close", "adj_ratio", "change_pct_raw",
        "consecutive_limit_ups",
    ]
    path_csv = HERE / "four-case-paths.csv"
    with path_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=path_fields, extrasaction="ignore")
        w.writeheader()
        for symbol in SYMBOLS:
            w.writerows(by_symbol[symbol])

    # ── 2. 逐事件表：平台口径首板，含覆盖与身份状态 ──
    frozen = list(csv.DictReader(path_csv.open(encoding="utf-8")))
    frozen_by_symbol: dict[str, list[dict]] = {s: [] for s in SYMBOLS}
    for r in frozen:
        frozen_by_symbol[r["symbol"]].append(r)

    events = []
    for symbol in SYMBOLS:
        rows = frozen_by_symbol[symbol]
        info = rules[symbol]
        for i, r in enumerate(rows):
            if float(r["consecutive_limit_ups"] or 0) != 1.0:
                continue
            bars_before = i
            event_date = r["date"]
            # D+1..D+20 可观察的根数（不加截止日之后行情）
            fwd = rows[i + 1 : i + 1 + FORWARD_DAYS]
            in_window = event_date >= WINDOW_START
            if info["st_now"]:
                identity, reasons = "HISTORICAL_REGIME_UNCERTIFIED", ["ST_NOW_5PCT_BACKFILL_NOT_HISTORY"]
            elif info["board"] == "GEM" and event_date <= "2020-08-21":
                identity, reasons = "HISTORICAL_REGIME_UNCERTIFIED", ["GEM_10PCT_REGIME_UNAVAILABLE"]
            else:
                identity, reasons = "HISTORICAL_REGIME_UNCERTIFIED", ["NO_HISTORICAL_ST_SOURCE"]
            if bars_before < LOOKBACK_BARS:
                reasons.append("COVERAGE_SHORT_250BARS")
            if len(fwd) < FORWARD_DAYS:
                reasons.append("FORWARD_RIGHT_CENSORED")
            gap = False
            for a, b in zip(rows[: i + 1], rows[1 : i + 1]):
                if (b["bar_index_1based"] and a["bar_index_1based"]) and (
                    int(b["bar_index_1based"]) - int(a["bar_index_1based"]) != 1
                ):
                    gap = True
            events.append({
                "symbol": symbol,
                "date": event_date,
                "in_display_window": in_window,
                "bars_before": bars_before,
                "lookback_complete": bars_before >= LOOKBACK_BARS,
                "raw_open": r["open"] and r["open"],
                "raw_high": r["raw_high"],
                "raw_low": r["raw_low"],
                "raw_close": r["raw_close"],
                "prev_raw_close": r["prev_raw_close"],
                "change_pct_raw": r["change_pct_raw"],
                "adjusted_close": r["close"],
                "adj_ratio": r["adj_ratio"],
                "board": info["board"],
                "board_limit_pct_now": info["board_limit_pct_now"],
                "st_now": info["st_now"],
                "firstboard_identity": identity,
                "identity_reasons": reasons,
                "forward_bars_available": len(fwd),
                "forward_observable_until": fwd[-1]["date"] if fwd else None,
                "right_censored": len(fwd) < FORWARD_DAYS,
                "path_has_row_gap": gap,
            })

    event_fields = list(events[0].keys())
    events_csv = HERE / "four-case-events.csv"
    with events_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=event_fields)
        w.writeheader()
        for e in events:
            e = dict(e)
            e["identity_reasons"] = ";".join(e["identity_reasons"])
            w.writerow(e)

    # ── 3. 覆盖/身份清单 ──
    per_symbol = {}
    for symbol in SYMBOLS:
        rows = frozen_by_symbol[symbol]
        diffs = [
            int(rows[i]["bar_index_1based"]) - int(rows[i - 1]["bar_index_1based"])
            for i in range(1, len(rows))
        ]
        info = rules[symbol]
        per_symbol[symbol] = {
            "bars_in_snapshot": len(rows),
            "first_date": rows[0]["date"],
            "last_date": rows[-1]["date"],
            "max_calendar_gap_days": None,
            "row_gaps": sum(1 for d in diffs if d != 1),
            "listing_date": info["listing_date"],
            "board": info["board"],
            "board_limit_pct_now": info["board_limit_pct_now"],
            "name_now": info["name_now"],
            "st_now": info["st_now"],
            "firstboard_identity": "HISTORICAL_REGIME_UNCERTIFIED",
            "firstboard_events_in_snapshot": sum(
                1 for e in events if e["symbol"] == symbol
            ),
            "firstboard_events_in_window": sum(
                1 for e in events if e["symbol"] == symbol and e["in_display_window"]
            ),
        }

    manifest = {
        "generated": "2026-10-28",
        "role": "frozen replay snapshot for historical first-board method test",
        "source": f"{DATA}/kline_daily_enriched",
        "dimension_source": f"{DATA}/instruments (as_of 2026-10-26, single snapshot)",
        "query": QUERY,
        "snapshot_upper_date": END,
        "lookback_bars": LOOKBACK_BARS,
        "forward_days": FORWARD_DAYS,
        "display_window_start": WINDOW_START,
        "price_basis": {
            "adjusted": "close/high/low = platform forward-adjusted, unrounded float64, basis = snapshot date; changes retroactively on new ex-rights",
            "raw": "raw_close/raw_high/raw_low = exchange raw prices, 2 decimals; use for limit-up confirmation and tradable prices",
            "adj_ratio": "close / raw_close at this snapshot; not a constant across ex-rights",
        },
        "artifacts": {
            "four-case-paths.csv": {
                "sha256": hashlib.sha256(path_csv.read_bytes()).hexdigest(),
                "rows": len(frozen),
            },
            "four-case-events.csv": {
                "sha256": hashlib.sha256(events_csv.read_bytes()).hexdigest(),
                "rows": len(events),
            },
        },
        "per_symbol": per_symbol,
        "limitations": [
            "首板身份为平台 consecutive_limit_ups 口径，历史 ST 与早期板块制度未认证",
            "无历史 ST 数据集：当前名称不含 ST 不能证明历史非 ST",
            "退市股维表缺失，历史可交易池无法按 as-of 还原",
            "复权基准 = 快照日；新增除权会回溯改变历史复权价，百分比距离不变、绝对价位会变",
            "D+20 超出 2026-10-23 的事件标记 right_censored，不补截止日之后行情",
            "四只股票已被挑选和观察，结果只验证方法，不是策略有效性的独立证据",
        ],
    }
    manifest_path = HERE / "four-case-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"paths: {len(frozen)} rows -> four-case-paths.csv")
    print(f"events: {len(events)} platform first boards -> four-case-events.csv")
    for symbol, s in per_symbol.items():
        print(
            f"  {symbol} {s['board']:4} bars={s['bars_in_snapshot']:4} "
            f"{s['first_date']}..{s['last_date']} gaps={s['row_gaps']} "
            f"events(all={s['firstboard_events_in_snapshot']}, window={s['firstboard_events_in_window']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
