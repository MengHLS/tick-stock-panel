"""E4 独立复算 (不 import 被验收的 calendar_axis 模块)。

口径只用「kline_daily_enriched 的 date=* 分区」这一条源:
  - 月线: 同一 (year, month) 内最后一个交易日
  - 周线: 同一 ISO (iso_year, iso_week) 内最后一个交易日 (Python date.isocalendar, 不用自然周序号)
数据末端 (所在月/ISO 周尚未结束) 不计入 → 与实现口径 null 的语义一致, 这里表现为「该 key 不产出」。

输出: logs/e4_independent.json  (计数 / 逐月样本 / 与实现产物的逐日比对)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("D:/TSP/data/kline_daily_enriched")
OUT = ROOT / "research" / "b4-calendar-20261107" / "logs" / "e4_independent.json"

FRAME_START = dt.date(2018, 1, 8)
WINDOW = (dt.date(2019, 7, 1), dt.date(2026, 10, 30))  # 研究侧评估窗 (与 B2 XS-B2 的 1779 天同窗)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    # 1) 权威日历: distinct trade_date
    days = (
        pl.scan_parquet(str(DATA / "date=*" / "*.parquet"))
        .select(pl.col("date").cast(pl.Date).alias("d"))
        .unique()
        .collect()
        .get_column("d")
        .to_list()
    )
    days = sorted({d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10]) for d in days})
    partitions = sorted(p.name.split("=")[1] for p in DATA.glob("date=*") if p.is_dir())

    # 2) 独立算月/周尾 (纯 Python, 不碰 polars dt.week)
    by_month: dict[tuple[int, int], dt.date] = {}
    by_week: dict[tuple[int, int], dt.date] = {}
    for d in days:
        by_month[(d.year, d.month)] = max(by_month.get((d.year, d.month), d), d)
        iso = d.isocalendar()
        key = (iso.year, iso.week)
        by_week[key] = max(by_week.get(key, d), d)

    month_ends = sorted(v for k, v in by_month.items() if (k[0], k[1]) < (days[-1].year, days[-1].month))
    week_ends = sorted(v for k, v in by_week.items() if v != days[-1])

    in_win = lambda x: WINDOW[0] <= x <= WINDOW[1]  # noqa: E731
    month_win = [d for d in month_ends if in_win(d)]
    week_win = [d for d in week_ends if in_win(d)]

    # 3) 与实现产物逐日比对 (frame 路径物化出来的两列)
    frame_cmp: dict[str, object] = {}
    try:
        from app.custom.research_calendar_pack.calendar_axis import (  # noqa: PLC0415
            FACTOR_COLUMN_MONTH_END,
            FACTOR_COLUMN_WEEK_END,
            attach_calendar_flags,
            load_trading_calendar,
        )

        cal = load_trading_calendar(Path("D:/TSP/data"), asset_type="stock")
        frame = pl.DataFrame({"date": days}).with_columns(pl.col("date").cast(pl.Date))
        mat = attach_calendar_flags(
            frame, cal, columns=(FACTOR_COLUMN_MONTH_END, FACTOR_COLUMN_WEEK_END)
        )
        got_month = {
            r["date"] for r in mat.iter_rows(named=True) if r[FACTOR_COLUMN_MONTH_END] == 1.0
        }
        got_week = {
            r["date"] for r in mat.iter_rows(named=True) if r[FACTOR_COLUMN_WEEK_END] == 1.0
        }
        if False:  # 备用: 若 diagnostics 提供更细的口径
            got_month = set(got_month)
        frame_cmp = {
            "impl_month_n_full": len(got_month),
            "impl_week_n_full": len(got_week),
            "indep_minus_impl_month": sorted(str(d) for d in set(month_ends) - got_month),
            "impl_minus_indep_month": sorted(str(d) for d in got_month - set(month_ends)),
            "indep_minus_impl_week": sorted(str(d) for d in set(week_ends) - got_week),
            "impl_minus_indep_week": sorted(str(d) for d in got_week - set(week_ends)),
            "month_sha_impl": hashlib.sha256(
                ",".join(sorted(str(d) for d in got_month)).encode()
            ).hexdigest(),
            "month_sha_indep": hashlib.sha256(
                ",".join(sorted(str(d) for d in month_ends)).encode()
            ).hexdigest(),
        }
    except Exception as exc:  # pragma: no cover
        frame_cmp = {"error": f"{type(exc).__name__}: {exc}"}

    # 4) 逐月样本 (3 个月): 该月每个交易日的两个标记, 独立算
    sample_months = [(2018, 1), (2023, 6), (2026, 9)]
    samples = {}
    for y, m in sample_months:
        rows = []
        for d in days:
            if (d.year, d.month) != (y, m):
                continue
            iso = d.isocalendar()
            rows.append(
                {
                    "date": d.isoformat(),
                    "iso": [iso.year, iso.week],
                    "month_end": 1 if d in set(month_ends) else 0,
                    "week_end": 1 if d in set(week_ends) else 0,
                }
            )
        samples[f"{y:04d}-{m:02d}"] = {
            "n_days": len(rows),
            "month_end_days": [r["date"] for r in rows if r["month_end"]],
            "week_end_days": [r["date"] for r in rows if r["week_end"]],
            "daily": rows,
        }

    payload = {
        "source": "D:/TSP/data/kline_daily_enriched date=* (distinct date; parquet 列名为 date, 无 trade_date 列)",
        "frame_start": FRAME_START.isoformat(),
        "calendar_first": days[0].isoformat(),
        "calendar_last": days[-1].isoformat(),
        "n_distinct_days": len(days),
        "n_partition_dirs": len(partitions),
        "partition_first": partitions[0],
        "partition_last": partitions[-1],
        "week_key": "ISO (iso_year, iso_week) via date.isocalendar()",
        "month_end_full_frame": len(month_ends),
        "week_end_full_frame": len(week_ends),
        "window": [WINDOW[0].isoformat(), WINDOW[1].isoformat()],
        "window_days": len([d for d in days if in_win(d)]),
        "month_end_in_window": len(month_win),
        "week_end_in_window": len(week_win),
        "cross_year_weeks": {
            "iso_week_1_starting_prev_year": [
                d.isoformat() for d in week_ends if d.isocalendar().week == 1 and d.month == 12
            ],
            "iso_last_week_of_year_starting_dec": [
                d.isoformat() for d in week_ends if d.month == 1 and d.isocalendar().week >= 52
            ],
        },
        "samples": samples,
        "impl_compare": frame_cmp,
        "script_sha256": sha(Path(__file__)),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: payload[k] for k in (
                "n_distinct_days", "month_end_full_frame", "week_end_full_frame",
                "window", "window_days", "month_end_in_window", "week_end_in_window",
            )},
            ensure_ascii=False,
        )
    )
    print("impl_compare", json.dumps({k: v for k, v in frame_cmp.items() if not isinstance(v, list) or len(v) < 5}, ensure_ascii=False))
    print("written", OUT, OUT.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
