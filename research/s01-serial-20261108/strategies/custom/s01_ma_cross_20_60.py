"""S01 双均线 20/60 金叉 —— 研究侧 S01_ma_cross_20_60 的生产可加载定义。

口径来源（不改口径，只做翻译）:
- 入场 e_ma_cross = in_universe & (ma20 > ma60) & (ma20[-1] <= ma60[-1])
  research/strategy-search-20261107/scripts/common.py:223-225
- 出场 x_ma_cross = (ma20 < ma60)（水平式，非穿越式）
  research/strategy-search-20261107/scripts/common.py:226
- 账户参数 ACCOUNT / 撮合 make_config
  research/strategy-search-20261107/scripts/common.py:49-70 / :313-333

信号列由 data_dir/user_data/custom_signals 下的两条 daily 自定义信号提供:
- signal_s01_ma_golden_20_60（入场，含 in_universe 条件）
- signal_s01_ma20_below_ma60（出场）

基础过滤: 引擎默认 basic_filter 会额外施加 price_max=300 / market_cap_min /
amount_min / exclude_new_days 等条件，研究侧股票池没有这些门槛，会改变候选集合，
故此处显式关闭（basic_filter.enabled=False，生产框架既有开关，不改代码）。
研究侧股票池条件已完整表达在入场信号的 in_universe 条件里。
"""

META = {
    "id": "s01_ma_cross_20_60",
    "name": "S01 双均线 20/60 金叉（研究复现）",
    "description": "MA20 上穿 MA60 且在公共股票池内买入；死叉或持有满 60 交易日离场。",
    "tags": ["趋势", "研究复现", "S01"],
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "research_only": True,
    "params": [],
    "basic_filter": {"enabled": False},
    "backtest_defaults": {
        "matching": "open_t+1",
        "entry_fill": "open_t+1",
        "exit_fill": "open_t+1",
        "entry_price_basis": "raw",
        "block_limit_open": True,
        "finalize_open_at_end": True,
        "exit_signal_requires_profit": False,
        "execution_costs": {
            "min_commission": 5.0,
            "transfer_fee_pct": 0.00001,
        },
    },
}

ENTRY_SIGNALS = ["signal_s01_ma_golden_20_60"]
EXIT_SIGNALS = ["signal_s01_ma20_below_ma60"]
MAX_HOLD_DAYS = 60

# in_universe 的 provider 依赖含 raw_close（研究侧股票池用 raw_close 判 >=3.0），
# 面板默认列集不含它，显式声明后才进特征计划。
REQUIRED_FEATURES = ["raw_close", "volume", "amount"]

import polars as pl  # noqa: E402


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    """候选层不做额外过滤: 研究侧的股票池条件在入场信号的 in_universe 条件里,
    由信号物化管线保证列存在 (filter 里再引用会有列缺失即静默清零的风险)。"""
    del df, params
    return pl.lit(True)
