"""B2 接线判据: in_universe 走生产 Provider 入口 (不是直调 compute_in_universe)。

判据:
  W-A   materialize_factor_columns(frame, {"in_universe"}) 产出 Float64 列, 值域 {1.0,0.0,null}
  W-B   与直调 compute_in_universe 逐位相同 (同一帧, sha256)
  W-C   data_dir 无 st_history 时 fail-closed (ValueError), 不静默当非 ST
  W-D   已物化的帧上重复调用不重算 (列已在 -> 原样返回, 值不变)
  W-E   DSL `xs_rank_pool(close, in_universe)` 编译成功, 依赖含 close 与 in_universe,
        frame_transform 后池内 (0,1]、池外 null; 与手工 rank/池内非空家数逐位相同
  W-F   掩码标签: get_factor("in_universe").tags 含 "mask" (E017 静态判定依赖它)
  W-G   E017 负样本: xs_rank_pool(close, volume) 必须被拒 (volume 无 mask 标签)
  W-H   14 日 ST 窗口内经生产入口同样是全 null
  W-I   E009 对四个新键生效: 截面算子嵌进时序窗口一律 E009 (含 xs_mean/xs_rank_market);
        rank/zscore 行为不变; 且 in_universe 作为掩码可被 xs_rank_pool/xs_mean 接受

只读: 不写库、不注册因子、不跑回测。
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb
import polars as pl

from app.config import settings
from app.extensions.factors import FactorProviderContext, materialize_factor_columns
from app.factors.dsl import FACTOR_COLUMN, compile_formula
from app.factors.registry import get_factor
from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE,
    compute_in_universe,
)

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
START, END = date(2026, 1, 5), date(2026, 11, 6)
WIN_START, WIN_END = date(2026, 10, 20), date(2026, 11, 6)
RESULT: dict[str, object] = {"checks": {}}


def _sha(frame: pl.DataFrame, cols: list[str]) -> str:
    h = hashlib.sha256()
    for name in cols:
        s = frame[name]
        h.update(name.encode())
        h.update(str(s.dtype).encode())
        h.update(b"".join(b"\xff" if v is None else repr(v).encode() for v in s.to_list()))
    return h.hexdigest()


def check(name: str, ok: bool, **observed) -> None:
    RESULT["checks"][name] = {"verdict": "PASS" if ok else "FAIL", **observed}


print("[1] 载入面板切片 ...", flush=True)
t0 = time.perf_counter()
con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")
con.sql(f"""create view bars as
  select symbol, date, volume, amount, raw_close, close from {PANEL}
  where (symbol like '60%' or symbol like '00%')
    and date between date '{START.isoformat()}' and date '{END.isoformat()}'""")
frame = con.sql("select * from bars order by symbol, date").pl()
con.close()
print(f"    rows={frame.height:,} symbols={frame['symbol'].n_unique():,} "
      f"{time.perf_counter()-t0:.1f}s", flush=True)

ctx = FactorProviderContext(data_dir=settings.data_dir)

# ---------------------------------------------------------------- W-A / W-B
print("[2] 生产入口 materialize_factor_columns ...", flush=True)
prod = materialize_factor_columns(frame, frozenset({FACTOR_COLUMN_IN_UNIVERSE}), context=ctx)
col = prod[FACTOR_COLUMN_IN_UNIVERSE]
vals = set(v for v in col.to_list() if v is not None)
check(
    "W-A", FACTOR_COLUMN_IN_UNIVERSE in prod.columns and col.dtype == pl.Float64
    and vals <= {0.0, 1.0},
    dtype=str(col.dtype), distinct_nonnull=sorted(vals), null_rows=int(col.null_count()),
    rows=prod.height,
)
direct = compute_in_universe(frame, st_history=__import__(
    "app.tickflow.security_status", fromlist=["read_st_history"]
).read_st_history(settings.data_dir))
check("W-B", _sha(prod, [FACTOR_COLUMN_IN_UNIVERSE]) == _sha(direct, ["in_universe_direct"]
      if "in_universe_direct" in direct.columns else [FACTOR_COLUMN_IN_UNIVERSE]),
      prod_sha=_sha(prod, [FACTOR_COLUMN_IN_UNIVERSE]),
      direct_sha=_sha(direct, [FACTOR_COLUMN_IN_UNIVERSE]))

# ---------------------------------------------------------------- W-D 幂等
again = materialize_factor_columns(prod, frozenset({FACTOR_COLUMN_IN_UNIVERSE}), context=ctx)
check("W-D", again.height == prod.height and
      _sha(again, [FACTOR_COLUMN_IN_UNIVERSE]) == _sha(prod, [FACTOR_COLUMN_IN_UNIVERSE]))

# ---------------------------------------------------------------- W-C fail-closed
with tempfile.TemporaryDirectory() as tmp:
    try:
        materialize_factor_columns(
            frame, frozenset({FACTOR_COLUMN_IN_UNIVERSE}),
            context=FactorProviderContext(data_dir=Path(tmp)),
        )
        check("W-C", False, error=None, note="未抛错 = 静默把未知当非 ST")
    except ValueError as exc:
        _msg = str(exc).replace(str(tmp), "<tmpdir>")  # 临时目录名随机, 归一以保证证据可复算
        check("W-C", True, error_type="ValueError", message=_msg[:160])

# ---------------------------------------------------------------- W-F / W-G
spec = get_factor(FACTOR_COLUMN_IN_UNIVERSE)
check("W-F", spec is not None and "mask" in tuple(spec.tags),
      tags=list(spec.tags) if spec else None, kind=spec.kind if spec else None)

bad = compile_formula("xs_rank_pool(close, volume)")
check("W-G", not bad.ok and [e.code for e in bad.errors] == ["E017"],
      codes=[e.code for e in bad.errors])

# ---------------------------------------------------------------- W-E DSL 端到端
print("[3] DSL 端到端 (xs_rank_pool(close, in_universe)) ...", flush=True)
formula = "xs_rank_pool(close, in_universe)"
compiled = compile_formula(formula)
if not compiled.ok:
    check("W-E", False, errors=[(e.code, e.message) for e in compiled.errors])
else:
    out = compiled.frame_transform(prod)
    out = prod if out is None else out
    col_name = FACTOR_COLUMN
    pool = out.filter(pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0)
    manual = (
        pool.with_columns(
            pl.col("close").rank(method="average").over("date").alias("rk"),
            pl.col("close").count().over("date").alias("n"),
        ).with_columns((pl.col("rk") / pl.col("n")).alias("expect"))
    )
    joined = out.join(
        manual.select(["symbol", "date", "expect"]), on=["symbol", "date"], how="left"
    )
    diff = (joined[col_name] - joined["expect"]).abs().max()
    in_pool_nonnull = pool[col_name].drop_nulls()
    check(
        "W-E",
        col_name in out.columns
        and diff is not None and float(diff) == 0.0
        and in_pool_nonnull.len() > 0
        and float(in_pool_nonnull.max()) <= 1.0
        and float(in_pool_nonnull.min()) > 0.0,
        max_abs_diff=None if diff is None else float(diff),
        pool_rows=pool.height, pool_nonnull=in_pool_nonnull.len(),
        pool_min=None if in_pool_nonnull.len() == 0 else float(in_pool_nonnull.min()),
        pool_max=None if in_pool_nonnull.len() == 0 else float(in_pool_nonnull.max()),
        referenced=sorted(compiled.referenced_factors),
        dependencies=sorted(compiled.dependencies),
        warmup_bars=compiled.warmup_bars,
    )
    # 池外行必须为 null (契约: 池外不是 0)
    out_null = out.filter(
        (pl.col(FACTOR_COLUMN_IN_UNIVERSE) != 1.0) & pl.col(col_name).is_not_null()
    )
    check("W-E2", out_null.height == 0, out_of_pool_nonnull=out_null.height)

# ---------------------------------------------------------------- W-H 14 日窗口
win = prod.filter((pl.col("date") >= pl.lit(WIN_START)) & (pl.col("date") <= pl.lit(WIN_END)))
per_day = (
    win.group_by("date")
    .agg(pl.col(FACTOR_COLUMN_IN_UNIVERSE).is_not_null().sum().alias("nonnull"),
         pl.len().alias("bars"))
    .sort("date")
)
check("W-H", per_day.height > 0 and int(per_day["nonnull"].sum()) == 0,
      window_days=per_day.height, nonnull_total=int(per_day["nonnull"].sum()),
      bars_total=int(per_day["bars"].sum()))

# ---------------------------------------------------------------- W-I E009 / 掩码接受
# v0.8 §10.2 未确证③: 「E009 对四新键的行为只读了代码分支, 未构造嵌入用例实跑」——本条补上。
EMBEDDED = {
    "ts_mean(xs_rank_pool(close, in_universe), 5)": ["E009"],
    "ts_mean(xs_rank_market(close), 5)": ["E009"],
    "ts_mean(xs_rank_pct(close, in_universe), 5)": ["E009"],
    "ts_mean(xs_mean(close, in_universe), 5)": ["E009"],
    # 对照组: 既有截面算子行为不变 (E009 一直是它们的口径)
    "ts_mean(rank(close), 5)": ["E009"],
    "ts_mean(zscore(close), 5)": ["E009"],
    # 正确用法必须编译通过 (证明 in_universe 带 mask 标签被接受)
    "xs_rank_pool(close, in_universe)": [],
    "xs_mean(close, in_universe)": [],
}
e009 = {}
for expr, expect in EMBEDDED.items():
    res = compile_formula(expr)
    got = [e.code for e in res.errors]
    e009[expr] = {"ok": res.ok, "codes": got, "expect": expect}
check("W-I", all(v["codes"] == v["expect"] for v in e009.values()),
      cases=e009, n_cases=len(e009))

print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
out_path = Path(__file__).resolve().parent / "logs" / "wiring_verify.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str, sort_keys=True), encoding="utf-8")
fails = [k for k, v in RESULT["checks"].items() if v["verdict"] != "PASS"]
print(f"[done] {len(RESULT['checks'])} checks, fails={fails}")
sys.exit(1 if fails else 0)
