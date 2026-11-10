"""研究侧基准序列（直接调用 common.py，不改表达式）: 入口/出口信号 + 股票池。

输出:
- research_signals.parquet: symbol, date, e_ma_cross, x_ma_cross, in_universe, prior_amount20, observed_bars
- research_meta.json: 指纹、行数、日期范围、口径出处

必须在 data_dir = 生产数据根（D:\\TSP\\data）下运行，与 S01 研究产物同源。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / "research" / "strategy-search-20261107" / "scripts"))

import common as rc  # noqa: E402

m = rc.open_market()
print("[research] settings.data_dir =", m.store.data_dir)

frame = rc.load_panel(m)
print("[research] panel rows", frame.height, "symbols", frame["symbol"].n_unique(),
      "dates", frame["date"].min(), frame["date"].max())

frame = rc.add_indicators(frame)
frame = rc.add_universe(frame)
frame = rc.build_signals(frame)

keep = [
    "symbol", "date", "e_ma_cross", "x_ma_cross", "in_universe",
    "ma20", "ma60", "observed_bars", "prior_amount20", "raw_close",
]
out = frame.select([c for c in keep if c in frame.columns]).sort(["date", "symbol"])
out.write_parquet(HERE / "research_signals.parquet")

meta = {
    "panel_rows": frame.height,
    "symbols": frame["symbol"].n_unique(),
    "date_min": str(frame["date"].min()),
    "date_max": str(frame["date"].max()),
    "entry_true": int(out["e_ma_cross"].sum()),
    "exit_true": int(out["x_ma_cross"].sum()),
    "entry_true_2019": int(
        out.filter(pl.col("date") >= pl.lit("2019-07-01").str.to_date())["e_ma_cross"].sum()
    ),
    "exit_true_2019": int(
        out.filter(pl.col("date") >= pl.lit("2019-07-01").str.to_date())["x_ma_cross"].sum()
    ),
    "in_universe_true": int(out["in_universe"].sum()),
    "fingerprint": rc.fingerprint(frame),
    "source": "research/strategy-search-20261107/scripts/common.py (load_panel/add_indicators/add_universe/build_signals)",
    "signal_def": {
        "entry": "e_ma_cross = in_universe & (ma20 > ma60) & (ma20.shift(1) <= ma60.shift(1))  [common.py:223-225]",
        "exit": "x_ma_cross = (ma20 < ma60)  [common.py:226]",
    },
    "note": "研究侧 in_universe = (observed_bars>=120) & !st_flag & raw_close>=3.0 & prior_amount20>=1e8 & volume>0, st_flag fill_null(False) [common.py:175-184]",
}
(HERE / "research_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(meta, ensure_ascii=False, indent=1))
