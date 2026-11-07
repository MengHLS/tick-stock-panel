"""E2 截面排名族的小样本判据 (XS-A5 / A6 / A8 / B2) + 6 行负样本反例。

不读磁盘数据: 全部内存构造, 因此可秒级复跑。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")

import polars as pl

from app.factors import dsl

OUT: dict[str, object] = {}


def evaluate(formula: str, frame: pl.DataFrame, col: str = "y") -> pl.DataFrame:
    compiled = dsl.compile_formula(formula)
    if not compiled.ok:
        raise SystemExit(f"{formula!r} 编译失败: {[(e.code, e.message) for e in compiled.errors]}")
    transformed = compiled.frame_transform(frame)
    if transformed is None:
        raise SystemExit(f"{formula!r} 缺依赖列")
    return transformed.with_columns(pl.col(dsl.FACTOR_COLUMN).alias(col))


def rows(pairs):
    """构造单日截面。pairs = (symbol, close 值, 是否在池)。

    `in_universe` 作为**已物化列**直接放进帧 (Provider 不介入): 它的值域
    {1.0, 0.0, null} 正是契约 §2.2 的浮点视图, 由 dsl 的掩码分支转 Boolean。
    """
    return pl.DataFrame({
        "symbol": [p[0] for p in pairs],
        "date": [date(2026, 6, 30)] * len(pairs),
        "close": [p[1] for p in pairs],
        "volume": [1.0] * len(pairs),
        "amount": [1.0] * len(pairs),
        "raw_close": [10.0] * len(pairs),
        "open": [1.0] * len(pairs),
        "high": [1.0] * len(pairs),
        "low": [1.0] * len(pairs),
        "in_universe": [1.0 if p[2] else 0.0 for p in pairs],
    }).with_columns(pl.col("close").cast(pl.Float64))


# ---------------------------------------------------------------- XS-A5
# 池内 3 只、其中 1 只 x 为空 -> {0.5, 1.0}; 得 {0.333, 0.667} = 用了 in_universe.sum()
a5 = rows([("a", 10.0, True), ("b", None, True), ("c", 30.0, True), ("d", 99.0, False)])
r = evaluate("xs_rank_pool(close, in_universe)", a5)
got = sorted([v for v in r["y"].to_list() if v is not None])
OUT["XS-A5_pool_3_one_null"] = {
    "values": got,
    "expected": [0.5, 1.0],
    "forbidden": [0.3333333333333333, 0.6666666666666666],
    "pass": all(abs(a - b) < 1e-12 for a, b in zip(got, [0.5, 1.0]))
            and len(got) == 2,
}

# ---------------------------------------------------------------- XS-A6
# 池空 -> 全 null
a6 = rows([("a", 10.0, False), ("b", 20.0, False)])
r = evaluate("xs_rank_pool(close, in_universe)", a6)
OUT["XS-A6_empty_pool"] = {
    "values": r["y"].to_list(),
    "all_null": all(v is None for v in r["y"].to_list()),
    "pass": all(v is None for v in r["y"].to_list()),
}

# ---------------------------------------------------------------- XS-A8
# tie: 4 只同值 -> 全部 0.625
a8 = rows([(s, 5.0, True) for s in ("a", "b", "c", "d")])
r = evaluate("xs_rank_pool(close, in_universe)", a8)
vals = r["y"].to_list()
OUT["XS-A8_tie_average"] = {
    "values": vals,
    "expected": 0.625,
    "ordinal_would_be": [0.25, 0.5, 0.75, 1.0],
    "pass": all(abs(v - 0.625) < 1e-12 for v in vals if v is not None),
}

# ---------------------------------------------------------------- 6 行负样本
# 契约 §3.2.3: 池内仅 1 只且 x 非空 -> xs_rank_pct 给「当日全样本平均名次」(≠1.0),
# 而 xs_rank_pool 给 1.0。6 行全样本、池内只有 1 只, 证明没把全样本名次当池内名次。
neg = rows([
    ("a", 10.0, True),   # 池内, 全样本名次 = 1
    ("b", 20.0, False),
    ("c", 30.0, False),
    ("d", 40.0, False),
    ("e", 50.0, False),
    ("f", 60.0, False),
])
pool = evaluate("xs_rank_pool(close, in_universe)", neg)["y"].to_list()
pct = evaluate("xs_rank_pct(close, in_universe)", neg)["y"].to_list()
market = evaluate("xs_rank_market(close)", neg)["y"].to_list()
OUT["NEG_pool_one_member"] = {
    "xs_rank_pool": pool,
    "xs_rank_pct": pct,
    "xs_rank_market": market,
    "pool_expect": 1.0,
    # 池内只有 a、全样本 6 只: 分子 = a 的全样本名次 1, 分母 = 池内家数 1 -> 1.0。
    # 这**不是**反例; 真正的反例见 CONTRACT_3_1_four_rows (pct 给 1.5 > 1)。
    "pct_expect": 1.0,
    "market_expect_first": 1 / 6,
    "pass": abs(pool[0] - 1.0) < 1e-12 and abs(pct[0] - 1.0) < 1e-12,
    "note": "池内 1 只时 ① 与 ③ 恰好同值, 不能用来区分; 区分靠 CONTRACT_3_1_four_rows",
}

# 契约 §3.1 四行样例: 池内 a/c, x=10/30, 全样本 a,b,c,d=10,20,30,40
# xs_rank_pct: 分子 = 全样本名次 (a=1, c=3), 分母 = 池内家数 2 -> {0.5, 1.5}
four = rows([("a", 10.0, True), ("b", 20.0, False), ("c", 30.0, True), ("d", 40.0, False)])
pool4 = evaluate("xs_rank_pool(close, in_universe)", four)["y"].to_list()
pct4 = evaluate("xs_rank_pct(close, in_universe)", four)["y"].to_list()
OUT["CONTRACT_3_1_four_rows"] = {
    "xs_rank_pool": pool4,
    "xs_rank_pct": pct4,
    "pool_expect": [0.5, 1.0],   # 池内名次 1,2 / 池内非空 2
    "pct_expect": [0.5, 1.5],    # 全样本名次 1,3 / 池内家数 2  (rk=1.5 反例)
    "pass": (
        abs(pool4[0] - 0.5) < 1e-12 and abs(pool4[2] - 1.0) < 1e-12
        and abs(pct4[0] - 0.5) < 1e-12 and abs(pct4[2] - 1.5) < 1e-12
    ),
}

# ---------------------------------------------------------------- 反例 2 (最强)
# 池内 3 只、全样本 6 只: xs_rank_pool = {1/3, 2/3, 1} (恒 <=1);
# xs_rank_pct = 全样本名次 {2,4,6} / 池内家数 3 = {0.667, 1.333, 2.0} -> 存在 >1。
# 若实现把「全样本名次」当「池内名次」, pct 会退化成 {1/3,2/3,1}, 本断言即失败。
neg2 = rows([
    ("a", 10.0, False), ("b", 20.0, True),
    ("c", 30.0, False), ("d", 40.0, True),
    ("e", 50.0, False), ("f", 60.0, True),
])
pool2 = evaluate("xs_rank_pool(close, in_universe)", neg2)["y"].to_list()
pct2 = evaluate("xs_rank_pct(close, in_universe)", neg2)["y"].to_list()
OUT["NEG_pool3_of_6"] = {
    "xs_rank_pool": pool2,
    "xs_rank_pct": pct2,
    "pool_expect": [1 / 3, 2 / 3, 1.0],
    "pct_expect": [2 / 3, 4 / 3, 2.0],
    "pct_max_gt_1": max(v for v in pct2 if v is not None) > 1.0,
    "pass": (
        all(abs(a - b) < 1e-12 for a, b in zip([v for v in pool2 if v is not None], [1/3, 2/3, 1.0]))
        and all(abs(a - b) < 1e-12 for a, b in zip([v for v in pct2 if v is not None], [2/3, 4/3, 2.0]))
    ),
}

# ---------------------------------------------------------------- XS-B2
# xs_rank_market 值域 (0,1], 当日 max == 1
b2 = rows([("a", 10.0, True), ("b", 20.0, True), ("c", 30.0, False)])
m = evaluate("xs_rank_market(close)", b2)["y"].to_list()
OUT["XS-B2_market_range"] = {
    "values": m,
    "max_is_1": abs(max(v for v in m if v is not None) - 1.0) < 1e-12,
    "all_in_0_1": all(0 < v <= 1.0 for v in m if v is not None),
    "pass": abs(max(v for v in m if v is not None) - 1.0) < 1e-12
            and all(0 < v <= 1.0 for v in m if v is not None),
}

# ---------------------------------------------------------------- A1 值域 (小样本)
OUT["XS-A1_range_fixture"] = {
    "values": [v for v in evaluate("xs_rank_pool(close, in_universe)", b2)["y"].to_list() if v is not None],
    "note": "全样本值域判据在 verify_e2_full.py 里跑",
}

# ---------------------------------------------------------------- E017 反例
e17 = {}
for formula in ("xs_rank_pool(close, volume)", "xs_mean(close, 1)", "xs_rank_pool(close, close)"):
    res = dsl.compile_formula(formula)
    e17[formula] = {"ok": res.ok, "codes": [e.code for e in (res.errors or [])]}
e17["xs_rank_market(close, in_universe)"] = {
    "ok": dsl.compile_formula("xs_rank_market(close, in_universe)").ok,
    "codes": [e.code for e in (dsl.compile_formula("xs_rank_market(close, in_universe)").errors or [])],
}
OUT["E017_rejects"] = e17

# ---------------------------------------------------------------- XS-B1 小样本
b1 = evaluate("rank(close)", b2).with_columns(evaluate("xs_rank_market(close)", b2)["y"].alias("mkt"))
OUT["XS-B1_small_sample"] = {
    "values": b1.select("y", "mkt").to_dicts(),
    "bitwise_equal": all(
        (r["y"] is None and r["mkt"] is None) or (r["y"] == r["mkt"])
        for r in b1.select("y", "mkt").to_dicts()
    ),
}

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
Path("research/b2-engine-20261107/logs").mkdir(parents=True, exist_ok=True)
Path("research/b2-engine-20261107/logs/e2_fixtures.json").write_text(
    json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
)
