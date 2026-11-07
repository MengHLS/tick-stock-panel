"""改动前基线: rank/zscore/winsorize 与 14 个 B0 因子的列哈希 (XS-A3 回归保护对照)."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402
from app.factors.dsl import FACTOR_COLUMN, compile_formula_cached  # noqa: E402
from app.indicators.pipeline import compute_indicators  # noqa: E402
from app.strategy.scoring import materialize_scoring_columns  # noqa: E402

COLS = ["symbol", "date", "open", "high", "low", "close",
        "raw_close", "raw_high", "raw_low", "volume", "amount"]

m = FileMarketData(settings.data_dir)
frame = m.get_daily_batch([], date(2018, 1, 1), date(2026, 11, 6), COLS)
frame = frame.filter(
    pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
).sort(["symbol", "date"])

symbols = frame["symbol"].unique().sort().head(300).to_list()
sub = frame.filter(pl.col("symbol").is_in(symbols))
print("sub rows", sub.height, "symbols", sub["symbol"].n_unique())

EXPRS = {
    "rank_close": "rank(close)",
    "rank_vol60": "rank(vol60)",
    "rank_momentum_20d": "rank(momentum_20d)",
    "rank_amount": "rank(amount)",
    "zscore_close": "zscore(close)",
    "winsorize_close_3": "winsorize(close, 3)",
    "rank_ts_inner": "rank(ts_mean(close, 5))",
}
B0 = ["ma20", "ma60", "boll_lower", "boll_upper", "sd20", "prior_high_20",
      "prior_low_10", "prior_high_55", "prior_vol_20", "ma120", "vol60",
      "prior_high_250", "prior_amount_20", "ma200"]


def col_hash(s: pl.Series) -> str:
    return hashlib.sha256(pl.DataFrame({"x": s}).hash_rows(seed=73).to_numpy().tobytes()).hexdigest()


out: dict[str, object] = {"rows": sub.height, "symbols": len(symbols), "exprs": {}, "b0": {}}
all_refs = set()
for text in EXPRS.values():
    all_refs |= set(compile_formula_cached(text).referenced_factors)
work = compute_indicators(sub, assume_sorted=True)
work = materialize_scoring_columns(work, sorted(all_refs))
print("materialized refs", sorted(all_refs))

for name, text in EXPRS.items():
    c = compile_formula_cached(text)
    assert c.ok, (name, [e.message for e in c.errors])
    res = c.frame_transform(work)
    assert res is not None, (name, sorted(c.dependencies | c.referenced_factors))
    s = res.get_column(FACTOR_COLUMN)
    out["exprs"][name] = {
        "sha256": col_hash(s), "null": int(s.null_count()), "n": int(s.len()),
    }
mat = materialize_scoring_columns(sub, B0)
for fid in B0:
    s = mat.get_column(fid)
    out["b0"][fid] = {"sha256": col_hash(s), "null": int(s.null_count())}

Path(r"C:\work\sourcecode\tick-stock-panel\research\b2-engine-20261107\baseline_after.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False, indent=2))
