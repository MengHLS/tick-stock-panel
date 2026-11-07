"""策略搜索统一数据、信号与评估设施（独立研究代码，只读调用正式读接口与撮合器）。

约束：
- 不修改正式系统源码；仅 import 现有的数据读取接口、涨跌停/ST 口径和撮合器。
- 所有信号只用当日收盘及以前可知的信息；执行固定为「信号日收盘决策、下一交易日开盘成交」。
- 参数在运行前写死在本文件中，脚本不接受按结果调参的入口。
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

PROJECT = Path(__file__).resolve().parents[3]
if str(PROJECT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT / "backend"))

from app.backtest.engine import (  # noqa: E402
    BacktestEngine,
    ExecutionCostPolicy,
    MatcherConfig,
    SimulationOptions,
)
from app.backtest.matrix import build_market_matrix  # noqa: E402
from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402
from app.indicators.pipeline import compute_limit_signals  # noqa: E402
from app.price_limits import polars_price_limit_pct  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402
from app.tickflow.security_status import attach_st_history  # noqa: E402

COLUMNS = [
    "symbol", "date", "open", "high", "low", "close",
    "raw_close", "raw_high", "raw_low", "volume", "amount",
]

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
WARMUP_START = date(2018, 1, 8)          # 数据实际起点
IS_END = date(2022, 12, 30)              # 样本内参考段终点（训练期只用来看稳定性，不调参）

ACCOUNT = dict(
    initial_capital=1_000_000.0,
    max_positions=5,
    max_exposure_pct=0.6,
    entry_price_basis="raw",
    block_limit_open=True,
    finalize_open_at_end=True,
    commission_pct=0.0003,
    stamp_tax_pct=0.001,
    transfer_fee_pct=0.00001,
    min_commission=5.0,
    slippage_scenarios=(10.0, 30.0),     # 双边各 X bp
)

# 公共股票池门槛（全部为 as-of 当日可得量）
UNIVERSE = dict(
    min_price_raw=3.0,
    min_prior_amount20=1e8,
    min_observed_bars=120,
)


# ------------------------------------------------------------------ 数据
@dataclass
class Market:
    market: FileMarketData
    instruments: pl.DataFrame
    st_history: pl.DataFrame
    engine: BacktestEngine
    store: DataStore


def open_market() -> Market:
    market = FileMarketData(settings.data_dir)
    store = DataStore(settings.data_dir)
    return Market(
        market=market,
        instruments=market.get_instruments(),
        st_history=market.get_st_history(),
        engine=BacktestEngine(KlineRepository(store)),
        store=store,
    )


def load_panel(m: Market, start: date = WARMUP_START, end: date = EVAL_END) -> pl.DataFrame:
    frame = m.market.get_daily_batch([], start, end, COLUMNS)
    frame = frame.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    ).sort(["symbol", "date"])
    dup = frame.select(pl.struct("symbol", "date").is_duplicated().sum()).item()
    if dup:
        raise ValueError(f"duplicate symbol/date rows: {dup}")
    frame = attach_st_history(frame, m.st_history)
    frame = compute_limit_signals(
        frame, m.instruments, needed={"limit_up_price", "limit_down_price"},
    ).with_columns(
        (pl.col("raw_close") >= pl.col("limit_up_price")).fill_null(False).alias("signal_limit_up"),
        (pl.col("raw_close") <= pl.col("limit_down_price")).fill_null(False).alias("signal_limit_down"),
        polars_price_limit_pct(
            pl.col("symbol"), pl.col("date"), pl.col("st_flag"),
        ).alias("price_limit_pct"),
    )
    return frame


def fingerprint(frame: pl.DataFrame) -> str:
    return hashlib.sha256(frame.hash_rows(seed=74).to_numpy().tobytes()).hexdigest()


# ------------------------------------------------------------------ 指标
def add_indicators(frame: pl.DataFrame) -> pl.DataFrame:
    """全部为 trailing 指标；shift(1) 表示「此前」，避免把当日纳入自身分位。"""
    f = frame.sort(["symbol", "date"]).with_columns(
        pl.col("close").rolling_mean(20).over("symbol").alias("ma20"),
        pl.col("close").rolling_mean(60).over("symbol").alias("ma60"),
        pl.col("close").rolling_mean(120).over("symbol").alias("ma120"),
        pl.col("close").rolling_mean(200).over("symbol").alias("ma200"),
        pl.col("close").pct_change().over("symbol").alias("ret1"),
        (pl.col("close") / pl.col("close").shift(5).over("symbol") - 1).alias("ret5"),
        (pl.col("close") / pl.col("close").shift(20).over("symbol") - 1).alias("ret20"),
        (pl.col("close") / pl.col("close").shift(60).over("symbol") - 1).alias("ret60"),
        (pl.col("close") / pl.col("close").shift(120).over("symbol") - 1).alias("ret120"),
        pl.col("high").shift(1).rolling_max(20).over("symbol").alias("prior_high20"),
        pl.col("high").shift(1).rolling_max(55).over("symbol").alias("prior_high55"),
        pl.col("high").shift(1).rolling_max(250).over("symbol").alias("prior_high250"),
        pl.col("low").shift(1).rolling_min(10).over("symbol").alias("prior_low10"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("prior_amount20"),
        pl.col("volume").shift(1).rolling_mean(20).over("symbol").alias("prior_vol20"),
        pl.col("date").cum_count().over("symbol").alias("observed_bars"),
    )
    f = f.with_columns(
        pl.col("ret1").rolling_std(60).over("symbol").alias("vol60"),
        pl.col("ret1").ewm_mean(alpha=1 / 14, adjust=False).over("symbol").alias("_avg_gain_src"),
    )
    # Wilder RSI(14)：用 ewm 近似（alpha=1/14），公开口径差异已在规格中标注
    gains = pl.when(pl.col("ret1") > 0).then(pl.col("ret1")).otherwise(0.0)
    losses = pl.when(pl.col("ret1") < 0).then(-pl.col("ret1")).otherwise(0.0)
    f = f.with_columns(
        gains.ewm_mean(alpha=1 / 14, adjust=False).over("symbol").alias("_ag"),
        losses.ewm_mean(alpha=1 / 14, adjust=False).over("symbol").alias("_al"),
    ).with_columns(
        (100 - 100 / (1 + pl.col("_ag") / pl.col("_al"))).alias("rsi14"),
    ).with_columns(
        pl.col("close").rolling_std(20).over("symbol").alias("sd20"),
    ).with_columns(
        (pl.col("ma20") - 2 * pl.col("sd20")).alias("bb_lower"),
        (pl.col("ma20") + 2 * pl.col("sd20")).alias("bb_upper"),
        ((pl.col("close") - pl.col("ma20")) / pl.col("sd20")).alias("bb_z"),
        (pl.col("close") / pl.col("prior_high250") - 1).alias("dist_52w_high"),
    )
    # 交易日期轴与再平衡日（月末/周末最后一个交易日，信号在收盘产生）
    dates = f["date"].unique().sort()
    d = pl.DataFrame({"date": dates})
    nxt = d["date"].shift(-1)
    d = d.with_columns(
        pl.Series("next_date", nxt),
    ).with_columns(
        (pl.col("next_date").is_null()
         | (pl.col("next_date").dt.month() != pl.col("date").dt.month())).alias("month_end"),
        (pl.col("next_date").is_null()
         | (pl.col("next_date").dt.week() != pl.col("date").dt.week())).alias("week_end"),
    ).select("date", "month_end", "week_end")
    f = f.join(d, on="date", how="left")
    return f


def add_universe(frame: pl.DataFrame) -> pl.DataFrame:
    """公共股票池与截面排名；所有列仅用当日及以前信息。"""
    base = (
        (pl.col("observed_bars") >= UNIVERSE["min_observed_bars"])
        & (pl.col("st_flag").fill_null(False) == False)  # noqa: E712
        & (pl.col("raw_close") >= UNIVERSE["min_price_raw"])
        & (pl.col("prior_amount20") >= UNIVERSE["min_prior_amount20"])
        & (pl.col("volume") > 0)
    )
    f = frame.with_columns(base.fill_null(False).alias("in_universe"))
    # 市场宽度：当日可计算 MA60 的股票中收盘在 MA60 上方的比例（收盘可知）
    f = f.with_columns(
        pl.when(pl.col("in_universe") & pl.col("ma60").is_not_null())
        .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
        .otherwise(None)
        .mean().over("date").alias("market_breadth"),
    )
    # 截面排名：仅在公共股票池内计算，rank 越大表示数值越大
    for col, name in (("ret5", "rk_ret5"), ("ret20", "rk_ret20"), ("vol60", "rk_vol60"),
                      ("ret60", "rk_ret60"), ("dist_52w_high", "rk_near_high")):
        f = f.with_columns(
            pl.when(pl.col("in_universe") & pl.col(col).is_not_null())
            .then(pl.col(col).rank("average").over("date")
                  / pl.col("in_universe").sum().over("date"))
            .otherwise(None)
            .alias(name),
        )
    return f


# ------------------------------------------------------------------ 策略定义
@dataclass(frozen=True)
class Strategy:
    key: str
    family: str
    title: str
    entry: str            # 列名（bool）
    exit: str             # 列名（bool）
    score: str            # 列名（float，越大越优先）
    max_hold_days: int | None
    holding: str


def build_signals(f: pl.DataFrame) -> pl.DataFrame:
    """一次性生成全部策略信号列。参数为公开文献默认值，运行前固定。"""
    u = pl.col("in_universe")
    out = f.with_columns(
        # S01 双均线 20/60：金叉且价在长期均线上方
        (u & (pl.col("ma20") > pl.col("ma60"))
         & (pl.col("ma20").shift(1).over("symbol") <= pl.col("ma60").shift(1).over("symbol"))
         ).fill_null(False).alias("e_ma_cross"),
        (pl.col("ma20") < pl.col("ma60")).fill_null(False).alias("x_ma_cross"),
        pl.col("ret20").fill_null(0).alias("s_ma_cross"),
        # S02 唐奇安 20/10 突破
        (u & (pl.col("close") > pl.col("prior_high20"))).fill_null(False).alias("e_donchian"),
        (pl.col("close") < pl.col("prior_low10")).fill_null(False).alias("x_donchian"),
        pl.col("ret20").fill_null(0).alias("s_donchian"),
        # S03 时序动量 60 日、月末再平衡
        (u & pl.col("month_end") & (pl.col("ret60") > 0) & (pl.col("close") > pl.col("ma120"))
         & (pl.col("ma20") > pl.col("ma60"))).fill_null(False).alias("e_tsmom"),
        (pl.col("month_end") & ((pl.col("ret60") <= 0) | (pl.col("close") < pl.col("ma120"))))
        .fill_null(False).alias("x_tsmom"),
        pl.col("ret60").fill_null(0).alias("s_tsmom"),
        # S04 RSI(14) 超卖反转
        (u & (pl.col("rsi14") < 30)).fill_null(False).alias("e_rsi"),
        (pl.col("rsi14") > 55).fill_null(False).alias("x_rsi"),
        (-pl.col("rsi14")).fill_null(0).alias("s_rsi"),
        # S05 布林带下轨反转
        (u & (pl.col("sd20") > 0) & (pl.col("close") < pl.col("bb_lower")))
        .fill_null(False).alias("e_boll"),
        (pl.col("close") > pl.col("ma20")).fill_null(False).alias("x_boll"),
        (-pl.col("bb_z")).fill_null(0).alias("s_boll"),
        # S06 截面 5 日反转：周度再平衡，取最弱 5%
        (u & pl.col("week_end") & (pl.col("rk_ret5") <= 0.05)).fill_null(False).alias("e_xsrev"),
        pl.lit(False).alias("x_xsrev"),
        (-pl.col("ret5")).fill_null(0).alias("s_xsrev"),
        # S07 截面低波动：月度再平衡，取最低 10%
        (u & pl.col("month_end") & (pl.col("rk_vol60") <= 0.10)).fill_null(False).alias("e_lowvol"),
        pl.lit(False).alias("x_lowvol"),
        (-pl.col("vol60")).fill_null(0).alias("s_lowvol"),
        # S08 52 周新高动量：月度再平衡，距 250 日高点 3% 以内
        (u & pl.col("month_end") & (pl.col("dist_52w_high") >= -0.03)
         & (pl.col("close") > pl.col("ma120"))).fill_null(False).alias("e_high52w"),
        pl.lit(False).alias("x_high52w"),
        pl.col("dist_52w_high").fill_null(-1).alias("s_high52w"),
        # S09 量能确认的趋势延续（公开：突破 + 放量）
        (u & (pl.col("close") > pl.col("prior_high55"))
         & (pl.col("volume") > 1.5 * pl.col("prior_vol20"))).fill_null(False).alias("e_volbreak"),
        (pl.col("close") < pl.col("ma20")).fill_null(False).alias("x_volbreak"),
        pl.col("ret60").fill_null(0).alias("s_volbreak"),
        # S10 截面 20 日反转：月度再平衡，取 20 日收益最弱 10%
        (u & pl.col("month_end") & (pl.col("rk_ret20") <= 0.10)).fill_null(False).alias("e_xsrev20"),
        pl.lit(False).alias("x_xsrev20"),
        (-pl.col("ret20")).fill_null(0).alias("s_xsrev20"),
        # S11 低波动 + 20 日反转复合：两者排名靠前 30% 内，按排名和排序
        (u & pl.col("month_end") & (pl.col("rk_vol60") <= 0.30)
         & (pl.col("rk_ret20") <= 0.30)).fill_null(False).alias("e_lowvol_rev"),
        pl.lit(False).alias("x_lowvol_rev"),
        (-(pl.col("rk_vol60") + pl.col("rk_ret20"))).fill_null(-9).alias("s_lowvol_rev"),
        # S12 低波动 + 市场宽度过滤（宽度<0.5 当月不建仓）
        (u & pl.col("month_end") & (pl.col("rk_vol60") <= 0.10)
         & (pl.col("market_breadth") >= 0.5)).fill_null(False).alias("e_lowvol_breadth"),
        pl.lit(False).alias("x_lowvol_breadth"),
        (-pl.col("vol60")).fill_null(0).alias("s_lowvol_breadth"),
    )
    return out


STRATEGIES: list[Strategy] = [
    Strategy("S01_ma_cross_20_60", "趋势", "双均线 20/60 金叉",
             "e_ma_cross", "x_ma_cross", "s_ma_cross", 60, "至死叉或最长 60 交易日"),
    Strategy("S02_donchian_20_10", "趋势", "唐奇安 20 日突破 / 10 日退出",
             "e_donchian", "x_donchian", "s_donchian", 60, "至跌破 10 日低或最长 60 交易日"),
    Strategy("S03_tsmom_60_m", "时序动量", "60 日时序动量 + 月末调仓",
             "e_tsmom", "x_tsmom", "s_tsmom", 60, "至动量转负或最长 60 交易日"),
    Strategy("S04_rsi14_reversion", "均值回归", "RSI(14) < 30 超卖反转",
             "e_rsi", "x_rsi", "s_rsi", 10, "至 RSI>55 或最长 10 交易日"),
    Strategy("S05_bollinger_20_2", "均值回归", "布林带(20,2) 下轨反转",
             "e_boll", "x_boll", "s_boll", 10, "至回到中轨或最长 10 交易日"),
    Strategy("S06_xs_reversal_5d", "截面反转", "5 日收益最弱 5% 周度反转",
             "e_xsrev", "x_xsrev", "s_xsrev", 5, "周度换仓，最长 5 交易日"),
    Strategy("S07_xs_lowvol_60d", "截面因子", "60 日波动最低 10% 月度持有",
             "e_lowvol", "x_lowvol", "s_lowvol", 20, "月度换仓，最长 20 交易日"),
    Strategy("S08_high_52w", "动量", "52 周新高附近月度持有",
             "e_high52w", "x_high52w", "s_high52w", 20, "月度换仓，最长 20 交易日"),
    Strategy("S09_volume_breakout_55", "趋势", "55 日新高 + 1.5 倍量能突破",
             "e_volbreak", "x_volbreak", "s_volbreak", 20, "至跌破 MA20 或最长 20 交易日"),
    Strategy("S10_xs_reversal_20d", "截面反转", "20 日收益最弱 10% 月度持有",
             "e_xsrev20", "x_xsrev20", "s_xsrev20", 20, "月度换仓，最长 20 交易日"),
    Strategy("S11_lowvol_reversal", "截面因子", "低波动 + 20 日反转复合月度持有",
             "e_lowvol_rev", "x_lowvol_rev", "s_lowvol_rev", 20, "月度换仓，最长 20 交易日"),
    Strategy("S12_lowvol_breadth", "截面因子+择时", "低波动月度 + 市场宽度≥0.5 才建仓",
             "e_lowvol_breadth", "x_lowvol_breadth", "s_lowvol_breadth", 20,
             "月度换仓，最长 20 交易日"),
]


# ------------------------------------------------------------------ 回测
def make_config(slippage_bps: float, max_hold_days: int | None, gross: bool = False) -> MatcherConfig:
    commission = 0.0 if gross else ACCOUNT["commission_pct"]
    stamp = 0.0 if gross else ACCOUNT["stamp_tax_pct"]
    return MatcherConfig(
        matching="open_t+1",
        initial_capital=ACCOUNT["initial_capital"],
        max_positions=ACCOUNT["max_positions"],
        max_exposure_pct=ACCOUNT["max_exposure_pct"],
        commission_pct=commission,
        stamp_tax_pct=stamp,
        slippage_bps=0.0 if gross else slippage_bps,
        max_hold_days=max_hold_days,
        entry_price_basis=ACCOUNT["entry_price_basis"],
        block_limit_open=ACCOUNT["block_limit_open"],
        finalize_open_at_end=ACCOUNT["finalize_open_at_end"],
        execution_costs=ExecutionCostPolicy(
            min_commission=0.0 if gross else ACCOUNT["min_commission"],
            transfer_fee_pct=0.0 if gross else ACCOUNT["transfer_fee_pct"],
        ),
    )


def year_segments(start: date = EVAL_START, end: date = EVAL_END) -> list[tuple[date, date]]:
    segs: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        seg_end = min(date(cur.year, 12, 31), end)
        segs.append((cur, seg_end))
        cur = date(cur.year + 1, 1, 1)
    return segs


def run_continuous(
    m: Market, prepared: pl.DataFrame, strat: Strategy, slippage_bps: float,
    gross: bool = False,
) -> dict:
    """按自然年分段、carry 结转的连续单账户回放；不按折重置。"""
    cfg = make_config(slippage_bps, strat.max_hold_days, gross=gross)
    carry = None
    equity: list[dict] = []
    trades: list[dict] = []
    seg_records: list[dict] = []
    for seg_start, seg_end in year_segments():
        seg = prepared.filter(
            (pl.col("date") >= seg_start) & (pl.col("date") <= seg_end)
        ).sort(["date", "symbol"])
        if seg.is_empty():
            continue
        matrix = build_market_matrix(
            seg, seg[strat.entry], seg[strat.exit],
            entry_delay_bars=1, exit_delay_bars=1,
        )
        res = m.engine.simulate_market_matrix(
            matrix, cfg,
            options=SimulationOptions(
                include_monte_carlo=False, carry_in=carry, carry_out=True,
            ),
        )
        carry = res.carry_state
        equity.extend(res.equity_curve)
        trades.extend(asdict(t) for t in res.trades)
        seg_records.append({
            "start": str(seg_start), "end": str(seg_end),
            "signals": int(seg[strat.entry].sum()),
            "stats": res.stats,
        })
    return {
        "strategy": strat.key, "slippage_bps": slippage_bps, "gross": gross,
        "segments": seg_records, "equity": equity, "trades": trades,
        "final_cash": None if carry is None else carry.cash,
        "final_positions": 0 if carry is None else len(carry.positions),
    }


def _daily_returns(equity: list[dict]) -> np.ndarray:
    vals = np.array([float(row["value"]) for row in equity], dtype=float)
    return np.diff(vals) / vals[:-1]


def summarize(result: dict, start: date, end: date, label: str) -> dict:
    eq = [(r["date"], float(r["value"])) for r in result["equity"]
          if str(start) <= str(r["date"]) <= str(end)]
    if len(eq) < 2:
        return {"label": label, "n_days": len(eq), "error": "insufficient equity points"}
    vals = np.array([v for _, v in eq], dtype=float)
    rets = np.diff(vals) / vals[:-1]
    n = len(rets)
    years = n / 252.0
    total = vals[-1] / vals[0] - 1
    cagr = (vals[-1] / vals[0]) ** (1 / years) - 1 if years > 0 and vals[0] > 0 else None
    vol = float(rets.std(ddof=1) * np.sqrt(252)) if n > 2 else None
    sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(252)) if n > 2 and rets.std(ddof=1) > 0 else None
    downside = rets[rets < 0]
    sortino = (float(rets.mean() / downside.std(ddof=1) * np.sqrt(252))
               if len(downside) > 2 and downside.std(ddof=1) > 0 else None)
    peak = np.maximum.accumulate(vals)
    dd = vals / peak - 1
    maxdd = float(dd.min())
    trades = [t for t in result["trades"]
              if str(start) <= str(t["exit_date"]) <= str(end)]
    closed = [t for t in trades if not t.get("open_at_end")]
    pnl = np.array([float(t["pnl_amount"]) for t in closed], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    period_trades = [t for t in result["trades"]
                     if str(start) <= str(t["entry_date"]) <= str(end)]
    traded = sum(float(t.get("entry_value") or 0)
                 + (0.0 if t.get("open_at_end") else float(t.get("exit_value") or 0))
                 for t in period_trades)
    exposure = [s["stats"].get("avg_exposure") for s in result["segments"]]
    exposure = [e for e in exposure if e is not None]
    return {
        "label": label, "n_days": n,
        "total_return": float(total), "cagr": cagr, "ann_vol": vol,
        "sharpe": sharpe, "sortino": sortino, "max_drawdown": maxdd,
        "calmar": (cagr / abs(maxdd)) if cagr is not None and maxdd < 0 else None,
        "n_closed_trades": int(len(closed)), "n_open_at_end": int(len(trades) - len(closed)),
        "win_rate": float(len(wins) / len(closed)) if closed else None,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else None,
        "avg_pnl_pct": float(np.mean([float(t["pnl_pct"]) for t in closed])) if closed else None,
        "median_pnl_pct": float(np.median([float(t["pnl_pct"]) for t in closed])) if closed else None,
        "avg_holding_days": float(np.mean([float(t["duration"]) for t in closed])) if closed else None,
        "pct_trades_gt_20pct": float(np.mean([float(t["pnl_pct"]) >= 0.2 for t in closed])) if closed else None,
        "gross_traded_over_initial": float(traded / ACCOUNT["initial_capital"]),
        "avg_exposure": float(np.mean(exposure)) if exposure else None,
        "final_equity": float(vals[-1]), "start_equity": float(vals[0]),
        "returns": rets,
    }


def deflated_sharpe(returns: np.ndarray, n_trials: int) -> dict:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio。

    使用未年化的逐日 Sharpe；V[SR] 用同一批试验的 Sharpe 方差（多变体近似）。
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 30 or n_trials < 2:
        return {"ok": False, "reason": "insufficient observations or trials"}
    sd = r.std(ddof=1)
    if sd <= 0:
        return {"ok": False, "reason": "zero variance"}
    sr = r.mean() / sd
    g3 = float(((r - r.mean()) ** 3).mean() / sd ** 3)
    g4 = float(((r - r.mean()) ** 4).mean() / sd ** 4)
    nd = statistics.NormalDist()
    euler = 0.5772156649015329
    return {"ok": True, "sr_daily": float(sr), "skew": g3, "kurtosis": g4,
            "n": n, "n_trials": n_trials,
            "sr_annual": float(sr * np.sqrt(252)),
            "_parts": (sr, g3, g4, n, nd, euler)}


def dsr_value(returns: np.ndarray, n_trials: int, sr_variance: float | None = None) -> dict:
    base = deflated_sharpe(returns, n_trials)
    if not base.get("ok"):
        return base
    sr, g3, g4, n, nd, euler = base.pop("_parts")
    var_sr = sr_variance if sr_variance and sr_variance > 0 else None
    if var_sr is None:
        # 只有一个试验序列时退化为 PSR（用自身方差近似上限的保守处理）
        var_sr = 0.0
    sr0 = (var_sr ** 0.5) * (
        (1 - euler) * nd.inv_cdf(1 - 1 / n_trials) + euler * nd.inv_cdf(1 - 1 / (n_trials * 2.718281828459045))
    ) if var_sr > 0 else 0.0
    denom = (1 - g3 * sr + ((g4 - 1) / 4) * sr ** 2) ** 0.5
    z = (sr - sr0) * ((n - 1) ** 0.5) / denom
    base.update({"sr0_daily": float(sr0), "z": float(z), "dsr": float(nd.cdf(z)),
                 "note": "SR 方差取本批试验的日频 Sharpe 方差" if var_sr > 0 else "单序列退化 PSR"})
    return base


def index_benchmark(m: Market, start: date, end: date, symbol: str = "000001.SH") -> dict:
    dates = m.market.dataset_partition_dates("kline_index_daily", start, end)
    if not dates:
        return {"symbol": symbol, "error": "no index partitions"}
    first, last = min(dates), max(dates)
    parts = [m.market.read_dataset_partition("kline_index_daily", d) for d in (first, last)]
    if any(p.is_empty() for p in parts):
        return {"symbol": symbol, "error": "empty index partition"}
    def close_at(part):
        row = part.filter(pl.col("symbol") == symbol)
        return float(row["close"][0]) if row.height else None
    c0, c1 = close_at(parts[0]), close_at(parts[1])
    if c0 is None or c1 is None:
        return {"symbol": symbol, "error": "symbol missing"}
    return {"symbol": symbol, "first": str(first), "last": str(last),
            "price_return": c1 / c0 - 1}


def json_ready(obj):
    if isinstance(obj, dict):
        return {k: json_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_ready(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return json_ready(obj.tolist())
    if isinstance(obj, date):
        return str(obj)
    return obj


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
