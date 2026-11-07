"""研究基线因子包 (B0) 的 FactorSpec 元数据。

口径来源: docs/factors/FACTOR_ENTRY_RULE_20261107.md §4.1 批 A1(9) / §4.2 批 A2(5);
注册字段规则: docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md §7.2。

约束 (逐条实现, 勿放宽):
- 公式原文照抄 §4.1/§4.2 的「可执行定义」, 只把直通项 (指标层已算列) 展开成等价的
  DSL 表达式: ma20=ts_mean(close,20)、ma60=ts_mean(close,60)、boll_*=ma20±2*sd20
  (sd20=ts_std(close,20))。展开是为了让公式只依赖基础列, 物化时不依赖别的因子列
  (DSL 对缺列 fail-closed, 见 dsl.py required_columns)。
- `prior_*` 一律带 ts_delay(...,1) (契约 §7.1 坑 1), 语义 = 此前 N 根, 不含当日。
- `vol60` 是日频未年化 (研究 `COMMON:140` = `ret1.rolling_std(60)`)。分子写法:
  研究侧 `COMMON:126` 用 `pct_change()`, polars 把它实现成 `(x - x.shift(1)) / x.shift(1)`;
  §4.2 表里手写成 `x / x.shift(1) - 1`, 两者数学恒等但二进制差 1 ULP (实测 1.11e-16,
  4.6% 行不等)。这里取 `(close - ts_delay(close,1)) / ts_delay(close,1)`, 与研究代码
  逐位一致 (max_abs_diff=0); 差异已报研究侧对齐 §4.2 文字, 不改语义。
- warmup_bars / dependencies 一律由 DSL 编译推导, 不手填 (契约 §7.2)。
"""
from __future__ import annotations

from app.factors.dsl import compile_formula
from app.factors.registry import FactorSpec

GROUP = "研究补充"
TAGS = ("研究基线", "B0")
STABILITY = "stable"

# (因子 id, 中文名, 公式原文, 单位, 是否无量纲)
_DEFINITIONS: tuple[tuple[str, str, str, str, bool], ...] = (
    # --- 批 A1: 9 个 ---
    ("ma20", "20日均线", "ts_mean(close, 20)", "currency", False),
    ("ma60", "60日均线", "ts_mean(close, 60)", "currency", False),
    (
        "boll_lower",
        "布林下轨(MA20-2σ)",
        "ts_mean(close, 20) - 2 * ts_std(close, 20)",
        "currency",
        False,
    ),
    (
        "boll_upper",
        "布林上轨(MA20+2σ)",
        "ts_mean(close, 20) + 2 * ts_std(close, 20)",
        "currency",
        False,
    ),
    ("sd20", "20日收盘标准差", "ts_std(close, 20)", "currency", False),
    ("prior_high_20", "此前20日最高价", "ts_delay(ts_max(high, 20), 1)", "currency", False),
    ("prior_low_10", "此前10日最低价", "ts_delay(ts_min(low, 10), 1)", "currency", False),
    ("prior_high_55", "此前55日最高价", "ts_delay(ts_max(high, 55), 1)", "currency", False),
    ("prior_vol_20", "此前20日均量", "ts_delay(ts_mean(volume, 20), 1)", "count", False),
    # --- 批 A2: 5 个 ---
    ("ma120", "120日均线", "ts_mean(close, 120)", "currency", False),
    (
        "vol60",
        "60日收益率标准差(日频未年化)",
        "ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)",
        "ratio",
        True,
    ),
    ("prior_high_250", "此前250日最高价", "ts_delay(ts_max(high, 250), 1)", "currency", False),
    ("prior_amount_20", "此前20日均成交额", "ts_delay(ts_mean(amount, 20), 1)", "currency", False),
    ("ma200", "200日均线", "ts_mean(close, 200)", "currency", False),
)


def _spec(factor_id: str, label: str, formula: str, unit: str, scale_free: bool) -> FactorSpec:
    compiled = compile_formula(formula)
    if not compiled.ok:
        first = compiled.errors[0]
        raise RuntimeError(
            f"研究基线因子公式无效 {factor_id} [{first.code}]: {first.message}"
        )
    return FactorSpec(
        id=factor_id,
        label=label,
        group=GROUP,
        formula_text=formula,
        kind="custom",
        lang="dsl",
        version=1,
        dependencies=frozenset(compiled.dependencies),
        warmup_bars=compiled.warmup_bars,
        unit=unit,  # type: ignore[arg-type]
        scale_free=scale_free,
        direction="none",  # 未经检验, 不预填方向 (契约 §7.2)
        stability=STABILITY,
        tags=TAGS,
    )


RESEARCH_BASELINE_FACTOR_SPECS: tuple[FactorSpec, ...] = tuple(
    _spec(*item) for item in _DEFINITIONS
)

RESEARCH_BASELINE_FACTOR_IDS: frozenset[str] = frozenset(
    spec.id for spec in RESEARCH_BASELINE_FACTOR_SPECS
)

SPEC_BY_ID: dict[str, FactorSpec] = {
    spec.id: spec for spec in RESEARCH_BASELINE_FACTOR_SPECS
}
