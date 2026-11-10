"""汇总四个变体的实测数字（只读 result_*.json / trades_*.parquet）。

用法: backend\\.venv\\Scripts\\python.exe research\\matrix-native-risk-20261108\\summarize.py
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
TAGS = [
    ("base_2y", "STOP_LOSS=None（基线）"),
    ("sl_2y", "STOP_LOSS=-0.08"),
    ("tp_2y", "TRAILING_TAKE_PROFIT 0.10/0.05"),
    ("ts_2y", "TRAILING_STOP=0.05"),
    ("mh_2y", "MAX_HOLD_DAYS=20"),
]


def main() -> int:
    rows = []
    for tag, label in TAGS:
        r = json.loads((HERE / f"result_{tag}.json").read_text(encoding="utf-8"))
        h = r["headline"]
        trades = pl.read_parquet(HERE / f"trades_{tag}.parquet")
        durations = trades["duration"].to_list()
        reasons = (
            trades.group_by("exit_reason").len().sort("exit_reason").to_dicts()
        )
        rows.append(
            {
                "tag": tag,
                "label": label,
                "error": r["error"],
                "n_trades": h["n_trades"],
                "avg_holding_days": round(sum(durations) / len(durations), 2),
                "max_holding_days": max(durations),
                "total_return": h["total_return"],
                "annual_return": h["annual_return"],
                "max_drawdown": h["max_drawdown"],
                "win_rate_recomputed": round(
                    sum(1 for v in trades["pnl_pct"].to_list() if v > 0) / len(durations), 4
                ),
                "exit_reason_counts": {d["exit_reason"]: d["len"] for d in reasons},
                "matcher_config": r["matcher_config_seen_by_engine"],
            }
        )
    out = {"window": "2019-07-01..2021-06-30", "rows": rows}
    (HERE / "summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("| 变体 | 成交笔数 | 平均持有(交易日) | 最长持有 | 总收益率 | 年化 | 最大回撤 | 退出原因 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print(
            f"| {r['label']} | {r['n_trades']} | {r['avg_holding_days']} | {r['max_holding_days']} "
            f"| {r['total_return']:.4f} | {r['annual_return']:.4f} | {r['max_drawdown']:.4f} "
            f"| {json.dumps(r['exit_reason_counts'], ensure_ascii=False)} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
