"""`market_breadth` (全市场站上 ma60 的宽度) 的登记与计算。

门票权威 = 台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §16.4（策略经理裁定，
逐项冻结，实现不许改口径）：

| 字段 | 值 |
| --- | --- |
| `id` | `market_breadth`（单侧，**不建** `uf_market_breadth` 双胞胎） |
| `formula_text` | `xs_mean(close > ma60, in_universe)` |
| `warmup_bars` | `120` |
| `dependencies` | `{close, ma60, in_universe}` |
| `strategy_usable` | `true` |

**计算不在这里重写**：本模块只持有一条公式原文，求值走
`app.factors.dsl.compile_formula_cached(...).frame_transform`（与因子检验 / 评分 / 回测
同一条计算路径）。`xs_mean` 的「按日聚合、按标的广播」语义由 dsl 实现（池外行同值
广播、池内无有效样本 → null），本模块不另写一套聚合。

**约束（§16.4 强制条，本版尚未被执行）**：禁止再对 `market_breadth` 套任何截面算子
或排名（否则按标的广播后重复计数，约 3,000 倍）。`FactorSpec` 今天没有
`semantics` / `cross_sectional` 载体（G6），闸门也没有「不许再聚合」这一条判据 ——
故该约束**只写在文档与注释里，尚未被任何代码执行**（§16.6 要求如实登记，不许当已落实）。
"""
from __future__ import annotations

import polars as pl

from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE,
    UniverseParams,
    compute_in_universe,
)
from app.factors.dsl import FACTOR_COLUMN, compile_formula_cached
from app.factors.registry import FactorSpec

MARKET_BREADTH_ID = "market_breadth"
MARKET_BREADTH_FORMULA = "xs_mean(close > ma60, in_universe)"
# §16.4 冻结值：不是从 compile 推导（推导只能给出物理列，给不出 ma60 / in_universe）。
MARKET_BREADTH_DEPENDENCIES = frozenset({"close", "ma60", FACTOR_COLUMN_IN_UNIVERSE})
MARKET_BREADTH_WARMUP = 120

MARKET_BREADTH_SPEC = FactorSpec(
    id=MARKET_BREADTH_ID,
    label="全市场站上60日均线占比",
    group="研究补充",
    formula_text=MARKET_BREADTH_FORMULA,
    kind="custom",
    lang="dsl",
    version=1,
    dependencies=MARKET_BREADTH_DEPENDENCIES,
    warmup_bars=MARKET_BREADTH_WARMUP,
    unit="ratio",
    direction="none",  # 未经检验, 不预填方向 (契约 §7.2)
    scale_free=True,
    null_policy="keep",
    stability="stable",
    tags=("研究基线", "E5"),
    # §7.16.5: 单侧件不是 alias, alias_of 必须为 None 且 strategy_usable=True。
    alias_of=None,
    strategy_usable=True,
)


def _ensure_ma60(frame: pl.DataFrame) -> pl.DataFrame:
    """在帧上补 `ma60` 列（缺列时）。

    公式原文取自 B0 包的 `ma60` 定义（`SPEC_BY_ID["ma60"].formula_text`），本模块不
    另写 `ts_mean(close, 60)` 字面量 —— 口径只有一处。B0 包里 `ma60` 排在
    `market_breadth` 之前，正常路径走它的物化结果；这里只兜住「只请求 market_breadth」
    的调用方。
    """
    if "ma60" in frame.columns:
        return frame
    from app.custom.research_factor_pack.factor_specs import SPEC_BY_ID as _B0_SPECS

    compiled = compile_formula_cached(_B0_SPECS["ma60"].formula_text)
    if not compiled.ok or compiled.frame_transform is None:
        raise ValueError("market_breadth 依赖 ma60, 但 B0 的 ma60 公式不可编译 (fail-closed)")
    transformed = compiled.frame_transform(frame)
    if transformed is None:
        raise ValueError("market_breadth 依赖 ma60, 但求值时缺列 (fail-closed)")
    column = transformed.get_column(FACTOR_COLUMN).alias("ma60")
    temps = [c for c in transformed.columns if c not in frame.columns and c != FACTOR_COLUMN]
    return transformed.drop([FACTOR_COLUMN, *temps]).with_columns(column)


def compute_market_breadth(
    frame: pl.DataFrame,
    *,
    st_history: pl.DataFrame | None,
    params: UniverseParams | None = None,
) -> pl.DataFrame:
    """在 `frame` 上追加 `market_breadth` 列（当日全市场 `close > ma60` 的池内均值）。

    `st_history` 为空 / None → `ValueError`（`in_universe` 拿不到历史 ST 时 fail-closed，
    契约 §2.3；宽度是在该掩码上取的均值，掩码不可判就不能把「未知」当「非 ST」）。
    """
    work = _ensure_ma60(frame)
    if FACTOR_COLUMN_IN_UNIVERSE not in work.columns:
        work = compute_in_universe(work, st_history=st_history, params=params)
    compiled = compile_formula_cached(MARKET_BREADTH_FORMULA)
    if not compiled.ok or compiled.frame_transform is None:
        raise ValueError(
            f"market_breadth 公式不可编译: {MARKET_BREADTH_FORMULA} (fail-closed)"
        )
    transformed = compiled.frame_transform(work)
    if transformed is None:
        raise ValueError(
            "market_breadth 求值时缺列: "
            f"{sorted({'close', 'ma60', FACTOR_COLUMN_IN_UNIVERSE} - set(work.columns))}"
        )
    column = transformed.get_column(FACTOR_COLUMN).alias(MARKET_BREADTH_ID)
    temps = [c for c in transformed.columns if c not in work.columns and c != FACTOR_COLUMN]
    return transformed.drop([FACTOR_COLUMN, *temps]).with_columns(column)
