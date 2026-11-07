"""生成 93 个已注册因子的清单（JSON + CSV）。

数据来源（只读）：
- backend/app/factors/registry.py : id / label / group / kind / 声明 warmup / pit / unit /
  null_policy / dependencies / formula_text（元数据单一权威来源）
- backend/app/indicators/pipeline.py : base 因子实际表达式（口径）
- backend/app/strategy/scoring.py : virtual 因子实际表达式（口径）
- backend/app/backtest/fundamentals.py : 7 个财务 PIT 因子的接入口径
- backend/app/custom/cross_sectional_linkage/compute.py : 7 个联动因子
- backend/app/custom/*/ : 首板事件链 provider

口径表（PRICE_BASIS / 是否含当日 / shift / 窗口 / 数据源列 / 有效空值策略）由人工逐条
读代码填写，写入本文件；registry 里的 formula_text 是自然语言描述，不参与口径判定。

运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\docs\\research\\factor-audit-20261107\\scripts\\build_inventory.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[4]
BACKEND = PROJECT / "backend"
OUT_DIR = HERE.parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.factors import registry as R  # noqa: E402

CLOSE = "前复权收盘(close)"
CLOSE_RAW = "不复权收盘(raw_close)"
HIGH = "前复权最高(high)"
LOW = "前复权最低(low)"
OHLC = "前复权 open/high/low/close"

PIPE = "backend/app/indicators/pipeline.py#compute_indicators"
SCORE = "backend/app/strategy/scoring.py#scoring_value_expr"
FUND = "backend/app/backtest/fundamentals.py#attach_fundamental_factors"
XLINK = "backend/app/custom/cross_sectional_linkage/compute.py"
CHAIN = "backend/app/custom/first_board_chain"


def ema_bars(alpha: float, tol: float = 1e-3) -> int:
    """EMA 权重衰减到 tol 所需 bar 数（闭式，非精确 warmup，仅作口径量化）。"""
    return int(math.ceil(math.log(tol) / math.log(1.0 - alpha)))


S = {}  # id -> 口径 dict


def put(fid, **kw):
    base = {
        "price_basis": CLOSE,
        "includes_today": True,
        "shift": "无",
        "window": None,
        "source_cols": ["close"],
        "null_effective": "空值传播(keep)：任一输入为空则因子为空，不填 0",
        "computed_in": PIPE,
        "formula_code": "",
        "warmup_note": "",
    }
    base.update(kw)
    S[fid] = base


# ---------------- 动量 ----------------
for n in (5, 10, 20, 30, 60):
    put(
        f"momentum_{n}d",
        shift=f"shift({n})",
        window=n,
        formula_code=f"close / close.shift({n}) - 1",
        warmup_note=f"需 {n} 根前置 bar；registry 声明 1（见 mismatch 标记）",
        computed_in=f"{PIPE}/Pass4",
    )
put(
    "change_pct",
    shift="shift(1)",
    window=1,
    formula_code="close / close.shift(1) - 1",
    warmup_note="需 1 根前置 bar",
    computed_in=f"{PIPE}/Pass4",
)

# ---------------- 均线偏离（virtual） ----------------
for n in (5, 10, 20, 30, 60):
    put(
        f"ma{n}_bias",
        window=n,
        source_cols=["close", f"ma{n}"],
        formula_code=f"close / ma{n} - 1",  # ma{n} = close.rolling_mean(n)
        warmup_note=f"MA{n} 需 {n} 根 bar；registry 声明 1",
        computed_in=SCORE,
    )
for n in (5, 10, 20, 30, 60):
    put(
        f"ema{n}_bias",
        window=n,
        source_cols=["close", f"ema{n}"],
        formula_code=f"close / ema{n} - 1",  # ewm_mean(alpha=2/(n+1), adjust=False)
        warmup_note=f"EMA{n} alpha=2/{n + 1}，权重衰减到 1e-3 约 {ema_bars(2.0 / (n + 1))} 根；registry 声明 1",
        computed_in=SCORE,
    )

# ---------------- 超买超卖 ----------------
for n in (6, 14, 24):
    put(
        f"rsi_{n}",
        window=n,
        formula_code=(
            f"gain=max(diff(close),0), loss=max(-diff(close),0); "
            f"avg=ewm_mean(alpha=1/{n}, adjust=False); "
            f"RSI=100-100/(1+avg_gain/max(avg_loss,1e-12))"
        ),
        null_effective="空值传播；loss==0 时用 1e-12 兜底（不产生 inf/NaN，平坦行情得 0）",
        warmup_note=f"Wilder EMA alpha=1/{n}，收敛约 {ema_bars(1.0 / n)} 根；registry 声明 1",
        computed_in=f"{PIPE}/Pass5",
    )

# ---------------- 趋势 ----------------
put(
    "macd_hist",
    source_cols=["close"],
    window=26,
    formula_code="dif=ema12-ema26; dea=ema9(dif); hist=(dif-dea)*2",
    warmup_note=f"ema26 收敛约 {ema_bars(2 / 27)} 根 + ema9 约 {ema_bars(0.2)} 根 ≈ 76；registry 声明 1",
    computed_in=f"{PIPE}/Pass1-2",
)
for t in ("dif", "dea", "hist"):
    put(
        f"macd_{t}_pct",
        window=26,
        source_cols=[f"macd_{t}", "close"],
        formula_code=f"macd_{t} / close",
        warmup_note="依赖 macd_* 的 EMA 收敛（≈76 根）；registry 声明 1",
        computed_in=SCORE,
    )
put(
    "kdj_k",
    price_basis=OHLC,
    source_cols=["high", "low", "close"],
    window=9,
    formula_code="RSV=100*(close-min(low,9))/(max(high,9)-min(low,9)); K=ewm_mean(RSV, alpha=1/3, adjust=False, ignore_nulls)",
    null_effective="区间=0 时 RSV 置空，EWM 跳过空值继续递推（不产生 NaN 传染）",
    warmup_note=f"9 根窗口 + EWM alpha=1/3 收敛 ≈ {ema_bars(1 / 3)} 根 ≈ 27；registry 声明 1",
    computed_in=f"{PIPE}/Pass3",
)
put(
    "kdj_d",
    price_basis=OHLC,
    source_cols=["kdj_k"],
    window=9,
    formula_code="D = ewm_mean(K, alpha=1/3, adjust=False, ignore_nulls)",
    warmup_note="依赖 kdj_k（≈27 根）；registry 声明 1",
    computed_in=f"{PIPE}/Pass3",
)
put(
    "kdj_j",
    price_basis=OHLC,
    source_cols=["kdj_k", "kdj_d"],
    window=9,
    formula_code="J = 3*K - 2*D",
    warmup_note="依赖 kdj_k/kdj_d；registry 声明 1",
    computed_in=f"{PIPE}/Pass3",
)
put(
    "boll_position",
    price_basis=OHLC,
    source_cols=["close", "boll_upper", "boll_lower"],
    window=20,
    formula_code="(close - boll_lower) / (boll_upper - boll_lower)，boll = ma20 ± 2*rolling_std(close,20)",
    null_effective="分母<=0 或为空时为空（_ratio 保护）",
    warmup_note="rolling_std(20) 需 19 根；registry 声明 1",
    computed_in=SCORE,
)

# ---------------- 波动率 ----------------
put(
    "annual_vol_20d",
    window=20,
    formula_code="pct_change(close).rolling_std(20) * sqrt(252)",
    warmup_note="需 19 根；registry 声明 1",
    computed_in=f"{PIPE}/Pass4",
)
put(
    "atr_14",
    price_basis="前复权 high/low/close",
    source_cols=["high", "low", "close"],
    window=14,
    formula_code="TR=max(h-l, |h-prev_close|, |l-prev_close|); ATR=ewm_mean(TR, alpha=1/14, adjust=False)",
    warmup_note=f"TR 需 1 根 + EWM 收敛约 {ema_bars(1 / 14)} 根 ≈ 94；registry 声明 1",
    computed_in=f"{PIPE}/Pass4",
)
put(
    "atr_pct",
    price_basis="前复权 high/low/close",
    source_cols=["atr_14", "close"],
    window=14,
    formula_code="atr_14 / close",
    warmup_note="依赖 atr_14（≈94 根）；registry 声明 1",
    computed_in=SCORE,
)
put(
    "amplitude",
    price_basis="前复权 high/low/收盘",
    source_cols=["high", "low", "close"],
    window=1,
    shift="shift(1)（仅用于分母 prev_close）",
    formula_code="(high - low) / prev_close，prev_close>0 否则为空",
    warmup_note="需 1 根前置 bar",
    computed_in=f"{PIPE}/Pass4",
)
put(
    "boll_width",
    window=20,
    source_cols=["ma20", "boll_upper", "boll_lower"],
    formula_code="(boll_upper - boll_lower) / ma20",
    warmup_note="依赖 rolling_std(20)；registry 声明 1",
    computed_in=SCORE,
)

# ---------------- 量价 ----------------
put(
    "vol_ratio_5d",
    source_cols=["volume"],
    window=5,
    shift="shift(1).rolling_mean(5)（分母不含当日）",
    formula_code="volume / volume.shift(1).rolling_mean(5)；盘中按 240/elapsed 折算当日量",
    null_effective="分母为空/为 0 时为空",
    warmup_note="需 5 根前置 bar",
    computed_in=f"{PIPE}/Pass4",
)
put(
    "vol_ratio_10d",
    source_cols=["volume"],
    window=10,
    shift="shift(1).rolling_mean(10)（分母不含当日）",
    formula_code="volume / volume.shift(1).rolling_mean(10)",
    warmup_note="需 10 根前置 bar（registry 声明 11）",
    computed_in=SCORE,
)
put(
    "vol_trend_5_10",
    source_cols=["vol_ma5", "vol_ma10"],
    window=10,
    formula_code="vol_ma5 / vol_ma10 - 1，vol_maN=volume.rolling_mean(N)（含当日）",
    warmup_note="需 9 根；registry 声明 1",
    computed_in=SCORE,
)
put(
    "turnover_rate",
    price_basis="成交量 + 历史时点流通股本",
    source_cols=["volume", "float_shares(按公告日生效)"],
    window=1,
    formula_code="volume(手) * 10000 / float_shares(股)；float_shares<=0 时为空",
    null_effective="无历史流通股本时为空，不填 0",
    warmup_note="无需前置 bar；registry 声明 1",
    computed_in=f"{PIPE}#compute_all/Pass6",
)
put(
    "turnover_ratio_5d",
    source_cols=["turnover_rate"],
    window=5,
    shift="shift(1).rolling_mean(5)",
    formula_code="turnover_rate / turnover_rate.shift(1).rolling_mean(5) - 1",
    warmup_note="需 5 根前置 bar（registry 声明 6）",
    computed_in=SCORE,
)
put(
    "log_amount",
    source_cols=["amount"],
    window=1,
    formula_code="ln(amount + 1)，amount>=0 否则为空",
    warmup_note="无需前置 bar",
    computed_in=SCORE,
)
put(
    "amount_ratio_5d",
    source_cols=["amount"],
    window=5,
    shift="shift(1).rolling_mean(5)",
    formula_code="amount / amount.shift(1).rolling_mean(5) - 1",
    warmup_note="需 5 根前置 bar（registry 声明 6）",
    computed_in=SCORE,
)

# ---------------- 价格位置 ----------------
put(
    "gap_return",
    source_cols=["open", "prev_close"],
    window=1,
    formula_code="open / prev_close - 1",
    warmup_note="需 1 根前置 bar",
    computed_in=SCORE,
)
put(
    "intraday_return",
    source_cols=["open", "close"],
    window=0,
    formula_code="close / open - 1",
    warmup_note="当日即可算",
    computed_in=SCORE,
)
put(
    "close_position",
    price_basis=OHLC,
    source_cols=["high", "low", "close"],
    window=0,
    formula_code="(close - low) / (high - low)",
    null_effective="high==low 时为空（_ratio 保护）",
    warmup_note="当日即可算",
    computed_in=SCORE,
)
put(
    "distance_to_high_60d",
    window=60,
    source_cols=["close", "high_60d"],
    formula_code="close / high_60d - 1；high_60d = close.rolling_max(60)（收盘价、含当日）",
    warmup_note="需 59 根；registry 声明 1",
    computed_in=f"{SCORE} + {PIPE}/Pass1(high_60d)",
)
put(
    "distance_from_low_60d",
    window=60,
    source_cols=["close", "low_60d"],
    formula_code="close / low_60d - 1，low_60d = close.rolling_min(60)（收盘价、含当日）",
    warmup_note="需 59 根；registry 声明 1",
    computed_in=f"{SCORE} + {PIPE}/Pass1(low_60d)",
)
put(
    "vwap_bias",
    source_cols=["close", "volume", "amount"],
    window=0,
    formula_code="close / (amount / (volume*100)) - 1",
    null_effective="volume<=0 时为空",
    warmup_note="当日即可算",
    computed_in=SCORE,
)

# ---------------- 收益形态 ----------------
for fid, code in (
    ("max_ret_20d", "change = close/close.shift(1)-1; rolling_max(change, 20, min_samples=20)"),
    ("ret_skew_20d", "rolling_skew(change, 20, bias=True)"),
    ("up_days_20d", "(change>0).cast(f64).rolling_sum(20, min_samples=20)"),
):
    put(
        fid,
        window=20,
        formula_code=code,
        null_effective="窗口不足 min_samples=20 时为空",
        warmup_note="需 20 根；registry 声明 21",
        computed_in=SCORE,
    )
put(
    "amihud_20d",
    window=20,
    source_cols=["close", "amount"],
    formula_code="rolling_mean(|change| / (amount/1e8), 20, min_samples=20)",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "turnover_z_60d",
    window=60,
    shift="基线用 shift(1)",
    source_cols=["turnover_rate"],
    formula_code="(turnover_rate - mean_60(t.shift(1))) / std_60(t.shift(1))，std<=0 为空",
    warmup_note="需 60 根前置 bar；registry 声明 61",
    computed_in=SCORE,
)
put(
    "vol_price_corr_20d",
    window=20,
    source_cols=["close", "volume"],
    formula_code="Pearson corr(change, volume) over 20（min_samples=20，方差<=0 为空）",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "vol_trend_5_60",
    window=60,
    source_cols=["volume"],
    formula_code="volume.rolling_mean(5) / volume.rolling_mean(60) - 1（均含当日）",
    warmup_note="需 59 根；registry 声明 60",
    computed_in=SCORE,
)

# ---------------- 涨停基因 ----------------
put(
    "limit_up_count_20d",
    source_cols=["consecutive_limit_ups"],
    window=20,
    formula_code="rolling_sum((consecutive_limit_ups.fill_null(0)>0).cast(f64), 20, min_samples=20)",
    null_effective="consecutive_limit_ups 为空按 0 计（不传播空值）",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "limit_up_count_60d",
    source_cols=["consecutive_limit_ups"],
    window=60,
    formula_code="同 limit_up_count_20d，窗口 60",
    null_effective="同上",
    warmup_note="需 60 根；registry 声明 61",
    computed_in=SCORE,
)

# ---------------- 财务（PIT） ----------------
FIN_COLS = {
    "pb_latest": ("close / bps（bps=每股净资产；close 用当日收盘）", True),
    "roe_latest": ("roe（%）", False),
    "gross_margin_latest": ("gross_margin（%）", False),
    "net_margin_latest": ("net_margin（%）", False),
    "revenue_yoy_latest": ("revenue_yoy（%）", False),
    "net_income_yoy_latest": ("net_income_yoy（%）", False),
    "debt_ratio_latest": ("debt_to_asset_ratio（%）", False),
}
for fid, (code, uses_close) in FIN_COLS.items():
    put(
        fid,
        price_basis="当日收盘（仅 pb_latest 参与）" if uses_close else "不涉及价格",
        includes_today=True,
        shift="按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）",
        window=None,
        source_cols=["financials/metrics/part.parquet: " + fid.replace("_latest", "")],
        formula_code=code,
        null_effective="无财务数据或公告日之前的交易日一律为空；绝不填 0",
        warmup_note="PIT 场景无滚动预热；registry 声明 1 正确",
        computed_in=FUND,
    )

# ---------------- 规模 / 长窗口 ----------------
put(
    "log_float_mv",
    window=0,
    source_cols=["close", "volume", "turnover_rate"],
    formula_code="ln(close * volume / turnover_rate)，turnover_rate>0 且 volume>0 否则为空",
    null_effective="换手率缺失则为空（无法反推股本）",
    warmup_note="当日即可算",
    computed_in=SCORE,
)
put(
    "momentum_120d",
    window=120,
    shift="shift(120)",
    formula_code="close / close.shift(120) - 1",
    warmup_note="需 120 根前置 bar；registry 声明 121",
    computed_in=SCORE,
)
put(
    "mom_accel_20_60",
    window=60,
    source_cols=["momentum_20d", "momentum_60d"],
    formula_code="momentum_20d - momentum_60d",
    warmup_note="继承 momentum_60d（60 根）",
    computed_in=SCORE,
)
put(
    "rsi_14_delta_5d",
    window=14,
    shift="rsi_14.shift(5)",
    source_cols=["rsi_14"],
    formula_code="rsi_14 - rsi_14.shift(5)",
    warmup_note="RSI(14) 收敛 + 5 根",
    computed_in=SCORE,
)
put(
    "overnight_ret_20d",
    window=20,
    source_cols=["open", "prev_close"],
    formula_code="rolling_sum(open/prev_close - 1, 20, min_samples=20)",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "intraday_ret_20d",
    window=20,
    source_cols=["open", "close"],
    formula_code="rolling_sum(close/open - 1, 20, min_samples=20)",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "downside_vol_20d",
    window=20,
    formula_code="sqrt(rolling_mean(clip(change, upper=0)^2, 20, min_samples=20))",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "vol_regime_5_60",
    window=60,
    formula_code="rolling_std(change,5) / rolling_std(change,60)，std<=0 为空",
    warmup_note="需 60 根；registry 声明 61",
    computed_in=SCORE,
)
put(
    "amplitude_trend_20_60",
    window=60,
    source_cols=["amplitude"],
    formula_code="rolling_mean(amplitude,20) / rolling_mean(amplitude,60) - 1",
    warmup_note="需 60 根；registry 声明 61",
    computed_in=SCORE,
)
put(
    "obv_trend_20d",
    window=20,
    source_cols=["close", "volume"],
    formula_code="rolling_sum(sign(change)*volume,20) / (rolling_mean(volume,20)*20)",
    null_effective="分母<=0 时为空",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "amount_mean_20d",
    price_basis="成交额",
    source_cols=["amount"],
    window=20,
    formula_code="rolling_mean(amount/1e8, 20, min_samples=20) 单位=亿元",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "turnover_mean_20d",
    source_cols=["turnover_rate"],
    window=20,
    formula_code="rolling_mean(turnover_rate, 20, min_samples=20)",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "turnover_std_20d",
    source_cols=["turnover_rate"],
    window=20,
    formula_code="rolling_std(turnover_rate,20) / rolling_mean(turnover_rate,20)",
    null_effective="均值<=0 时为空",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=SCORE,
)
put(
    "position_240d",
    window=240,
    formula_code="(close - min_240(close)) / (max_240(close) - min_240(close))，min_samples=240",
    null_effective="区间<=0 时为空",
    warmup_note="需 240 根；registry 声明 241",
    computed_in=SCORE,
)
put(
    "distance_to_high_240d",
    window=240,
    formula_code="close / rolling_max(close,240,min_samples=240) - 1",
    warmup_note="需 240 根；registry 声明 241",
    computed_in=SCORE,
)
put(
    "kdj_kd_diff",
    price_basis=OHLC,
    source_cols=["kdj_k", "kdj_d"],
    window=9,
    formula_code="kdj_k - kdj_d",
    warmup_note="继承 KDJ（≈27 根）",
    computed_in=SCORE,
)

# ---------------- 首板事件链（9 个，custom provider） ----------------
CHAIN_NOTE = "回看 250 个交易日、按最近首板递归；warmup 251"
CHAIN_DESC = {
    "first_board_chain_stage": "0 无锚/1 结构不完整/2 回调太浅/3 回攻未过前高/4 目标前已突破/5 首次收盘突破",
    "first_board_chain_anchor_distance": "锚点首板到目标首板的交易日数；未选锚为空",
    "first_board_chain_pullback_pct": "1 - L/P（前高 P、回调低点 L）",
    "first_board_chain_target_above_reference_pct": "目标首板收盘 / P - 1",
    "first_board_chain_strict_rebreak": "目标首板收盘首次突破 P 且此前无收盘突破",
    "first_board_chain_early_breakout": "回调后、目标首板前已收盘突破 P",
    "first_board_chain_recovered_not_breakout": "结构有效且目标首板收盘未突破 P",
    "first_board_chain_seed_close_preserved": "L >= 锚点首板收盘",
    "first_board_chain_seed_low_preserved": "L >= 锚点首板最低",
}
for fid, desc in CHAIN_DESC.items():
    put(
        fid,
        price_basis=OHLC,
        source_cols=["close", "high", "low", "open", "consecutive_limit_ups"],
        window=250,
        shift="事件内只用当日及以前 bar（递归回看，不 shift 未来）",
        formula_code=desc,
        null_effective="无有效结构时为空（不填 0/不填默认类别）",
        warmup_note=CHAIN_NOTE + "；registry 声明 251",
        computed_in=CHAIN,
    )

# ---------------- 截面联动（7 个，custom sidecar） ----------------
for n, fid in ((3, "deviate_3d"), (10, "deviate_10d"), (30, "deviate_30d")):
    put(
        fid,
        price_basis="前复权收盘 + 板块指数收盘",
        source_cols=["close", "板块基准收益(交易所板块指数)"],
        window=n,
        formula_code=f"个股 {n} 日收益 - 所属板块基准 {n} 日收益",
        null_effective="无板块归属/基准缺失时为空",
        warmup_note=f"需 {n} 根前置 bar；registry 声明 {n + 1}",
        computed_in=XLINK,
    )
put(
    "industry_relative_momentum_20d",
    price_basis="前复权收盘 + 行业成员",
    source_cols=["close", "industry(二级行业)"],
    window=20,
    formula_code="个股 20 日动量 - 同业等权均值",
    null_effective="行业缺失（>30 天陈旧）时为空",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=XLINK,
)
put(
    "industry_rank_momentum_20d",
    price_basis="前复权收盘 + 行业成员",
    source_cols=["close", "industry(二级行业)"],
    window=20,
    formula_code="个股 20 日动量在所属行业内的平均排名百分位（1=最强）",
    null_effective="行业缺失时为空",
    warmup_note="需 20 根；registry 声明 21",
    computed_in=XLINK,
)
put(
    "industry_corr_60d",
    price_basis="前复权收盘 + 行业成员",
    source_cols=["close", "industry"],
    window=60,
    formula_code="corr(个股日收益, 同业等权组合日收益) over 60，方差<=1e-18 为空",
    null_effective="方差退化或行业缺失时为空",
    warmup_note="需 60 根；registry 声明 61",
    computed_in=XLINK,
)
put(
    "industry_beta_60d",
    price_basis="前复权收盘 + 行业成员",
    source_cols=["close", "industry"],
    window=60,
    formula_code="cov(个股日收益, 同业等权组合日收益) / var(同业) over 60",
    null_effective="分母方差<=1e-18 时为空",
    warmup_note="需 60 根；registry 声明 61",
    computed_in=XLINK,
)


def derived_warmup(fid: str):
    """可直接闭式判定的 derived warmup；EMA 类给出区间估计（标 estimated）。"""
    sem = S[fid]
    w = sem["window"]
    if fid.startswith(("rsi_", "ema")) or fid in {"macd_hist", "macd_dif_pct", "macd_dea_pct",
                                                   "macd_hist_pct", "atr_14", "atr_pct",
                                                   "kdj_k", "kdj_d", "kdj_j", "kdj_kd_diff"}:
        return None
    if fid.startswith("first_board_chain") or fid.startswith("industry_") or fid.startswith("deviate_"):
        return None
    if fid.endswith("_latest"):
        return 1
    if w is None:
        return 1
    if fid in {"intraday_return", "close_position", "vwap_bias", "log_float_mv", "log_amount"}:
        return 0
    if fid.startswith("momentum_") and not fid.startswith("mom_accel"):
        return w
    if fid in {"change_pct", "amplitude"}:
        return 1
    if fid in {"vol_ratio_5d", "vol_ratio_10d", "turnover_ratio_5d", "amount_ratio_5d"}:
        return w
    if fid in {"gap_return", "overnight_ret_20d", "intraday_ret_20d"}:
        return w
    return max(w, 1)


def main() -> None:
    specs = [s for s in R.all_factors() if s.group != "扩展数据"]
    rows = []
    missing = []
    for s in specs:
        sem = S.get(s.id)
        if sem is None:
            missing.append(s.id)
            continue
        dw = derived_warmup(s.id)
        rows.append(
            {
                "id": s.id,
                "label": s.label,
                "group": s.group,
                "kind": s.kind,
                "formula_text_registry": s.formula_text,
                "formula_code": sem["formula_code"],
                "price_basis": sem["price_basis"],
                "includes_today": sem["includes_today"],
                "shift": sem["shift"],
                "window": sem["window"],
                "data_source_cols": sem["source_cols"],
                "computed_in": sem["computed_in"],
                "warmup_bars_declared": s.warmup_bars,
                "warmup_bars_derived": dw,
                "warmup_note": sem["warmup_note"],
                "warmup_mismatch": (
                    None if dw is None else bool(s.warmup_bars != dw)
                ),
                "null_policy_declared": s.null_policy,
                "null_policy_effective": sem["null_effective"],
                "is_financial_pit": s.pit,
                "pit_source": s.pit_source,
                "unit": s.unit,
                "scale_free": s.scale_free,
                "stability": s.stability,
                "asset_types": sorted(s.asset_types),
                "dependencies": sorted(s.dependencies),
                "version": s.version,
            }
        )
    if missing:
        raise SystemExit(f"口径表缺项: {missing}")

    payload = {
        "generated_at": date.today().isoformat(),
        "source_of_metadata": "backend/app/factors/registry.py (all_factors(), 排除 group=扩展数据)",
        "count": len(rows),
        "counts_by_kind": {
            k: sum(1 for r in rows if r["kind"] == k)
            for k in sorted({r["kind"] for r in rows})
        },
        "count_financial_pit": sum(1 for r in rows if r["is_financial_pit"]),
        "count_warmup_declared_mismatch": sum(
            1 for r in rows if r["warmup_mismatch"] is True
        ),
        "count_warmup_undetermined": sum(
            1 for r in rows if r["warmup_mismatch"] is None
        ),
        "factors": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "factors_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (OUT_DIR / "factors_inventory.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k in ("data_source_cols", "dependencies", "asset_types"):
                out[k] = ";".join(map(str, out[k]))
            w.writerow(out)
    print(
        f"wrote {len(rows)} factors -> {OUT_DIR} "
        f"(kind={payload['counts_by_kind']}, pit={payload['count_financial_pit']}, "
        f"warmup_mismatch={payload['count_warmup_declared_mismatch']}, "
        f"undetermined={payload['count_warmup_undetermined']})"
    )


if __name__ == "__main__":
    main()
