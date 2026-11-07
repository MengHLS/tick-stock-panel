# 系统核心因子台账（93 个）

状态：**只读盘点，v1**。生成日期 2026-11-07。作者：因子工程师。
本文件是台账，不是规格变更单；任何口径修订见 `docs/factors/FACTOR_GAP_SPEC_20261107.md`。

## 0. 这份清单覆盖什么、不覆盖什么

| 项 | 值 | 依据 |
| --- | --- | --- |
| 运行中注册表总数 | **178**（base 117 / virtual 61，15 组） | `app.factors.registry.all_factors()` 实测 |
| 本清单覆盖 | **93** = 178 − 85 个 `ext_*` 扩展数据因子 | 见 §5 |
| 其中 base / virtual | 32 / 61 | `kind` 字段 |
| 财务 PIT 因子 | **7** 个（均为 `*_latest`，走 `app/backtest/fundamentals.py`） | `is_financial_pit` |
| 另有 PIT 依赖（非财务） | 1 个：`turnover_rate` | `price_basis` 含「历史时点流通股本」 |
| warmup 声明值**低于**实需（真治理项） | **18** 个 | `warmup_bars_declared` < `warmup_bars_derived` |
| warmup 声明值高于实需（安全冗余） | 28 个 | 同上，方向相反 |

**与任务书「93 个（含 8 个财务 PIT）」的两处核对结论（确证）：**

1. 93 这个数字对得上，但它等于「178 − 85 个扩展数据因子」，不是注册表总数：`ext_*` 全部来自扩展数据包（`app/custom/*`、扩展数据列），未纳入本次盘点。
2. 财务 PIT 严格是 **7 个**，不是 8 个。凑出「8」的可能是 `turnover_rate`——它用历史时点流通股本（PIT），但不是财务科目因子。

## 1. 口径公约（本清单的判定标准）

| 公约 | 内容 | 检查方式 |
| --- | --- | --- |
| 价格口径 | base/量价类一律用**前复权** `close`/`high`/`low`；`raw_*`（不复权）只用于涨跌停与股票池价格门槛 | 读 `pipeline.py` 的 `compute_indicators` 表达式 |
| 含当日 | 除显式 `ts_delay`/`shift(1)` 的「此前」语义外，全部**含当日**（当日收盘可知） | `includes_today` / `shift` 字段 |
| 窗口 | 窗口按**交易日 bar 数**（非自然日）；`min_samples` 不足即 null（不填充） | `window` 字段 |
| 空值策略 | 全表统一 `keep`：任一输入为空则输出为空，**不填 0、不前向填充**，策略侧自行 `fill_null(False)` | `null_policy_effective`（逐条读实现确认） |
| warmup | 声明值 vs 实需值分别记录；实需 = 使首个输出非空所需前置 bar 数（含窗口与嵌套因子） | `warmup_bars_derived` |

两层实现位置不同会导致同名口径分叉，读表时以「实现在」为准：

| 实现位置 | 因子数 | 含义 |
| --- | --- | --- |
| `backend/app/strategy/scoring.py` | 52 | |
| `backend/app/indicators/pipeline.py` | 18 | |
| `backend/app/custom/first_board_chain` | 9 | |
| `backend/app/backtest/fundamentals.py` | 7 | |
| `backend/app/custom/cross_sectional_linkage/compute.py` | 7 | |

## 2. 逐因子台账

列说明：`口径` = 价格基准 / 含当日 / shift / 窗口；`warmup` = 声明 / 实需（✗ = 不一致）；`空值` 全为 keep。

### 2.1 动量（8 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `momentum_5d` | 5日动量 | base | `close / close.shift(5) - 1` | 前复权收盘(close)；含当日=True；shift(5)；窗口=5 | 1 / 5 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `momentum_10d` | 10日动量 | base | `close / close.shift(10) - 1` | 前复权收盘(close)；含当日=True；shift(10)；窗口=10 | 1 / 10 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `momentum_20d` | 20日动量 | base | `close / close.shift(20) - 1` | 前复权收盘(close)；含当日=True；shift(20)；窗口=20 | 1 / 20 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `momentum_30d` | 30日动量 | base | `close / close.shift(30) - 1` | 前复权收盘(close)；含当日=True；shift(30)；窗口=30 | 1 / 30 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `momentum_60d` | 60日动量 | base | `close / close.shift(60) - 1` | 前复权收盘(close)；含当日=True；shift(60)；窗口=60 | 1 / 60 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `change_pct` | 日涨跌幅 | base | `close / close.shift(1) - 1` | 前复权收盘(close)；含当日=True；shift(1)；窗口=1 | 1 / 1 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `momentum_120d` | 120日动量 | virtual | `close / close.shift(120) - 1` | 前复权收盘(close)；含当日=True；shift(120)；窗口=120 | 121 / 120 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `mom_accel_20_60` | 动量加速度 | virtual | `momentum_20d - momentum_60d` | 前复权收盘(close)；含当日=True；无；窗口=60 | 1 / 60 ✗低估 | momentum_20d;momentum_60d | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.2 趋势（9 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `macd_hist` | MACD柱(原值) | base | `dif=ema12-ema26; dea=ema9(dif); hist=(dif-dea)*2` | 前复权收盘(close)；含当日=True；无；窗口=26 | 1 /  | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass1-2` |
| `macd_dif_pct` | MACD DIF强度 | virtual | `macd_dif / close` | 前复权收盘(close)；含当日=True；无；窗口=26 | 1 /  | macd_dif;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `macd_dea_pct` | MACD DEA强度 | virtual | `macd_dea / close` | 前复权收盘(close)；含当日=True；无；窗口=26 | 1 /  | macd_dea;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `macd_hist_pct` | MACD柱强度 | virtual | `macd_hist / close` | 前复权收盘(close)；含当日=True；无；窗口=26 | 1 /  | macd_hist;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `kdj_k` | KDJ-K | base | `RSV=100*(close-min(low,9))/(max(high,9)-min(low,9)); K=ewm_mean(RSV, alpha=1/3, adjust=False, ignore_nulls)` | 前复权 open/high/low/close；含当日=True；无；窗口=9 | 1 /  | high;low;close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass3` |
| `kdj_d` | KDJ-D | base | `D = ewm_mean(K, alpha=1/3, adjust=False, ignore_nulls)` | 前复权 open/high/low/close；含当日=True；无；窗口=9 | 1 /  | kdj_k | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass3` |
| `kdj_j` | KDJ-J | base | `J = 3*K - 2*D` | 前复权 open/high/low/close；含当日=True；无；窗口=9 | 1 /  | kdj_k;kdj_d | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass3` |
| `boll_position` | 布林位置 | virtual | `(close - boll_lower) / (boll_upper - boll_lower)，boll = ma20 ± 2*rolling_std(close,20)` | 前复权 open/high/low/close；含当日=True；无；窗口=20 | 1 / 20 ✗低估 | close;boll_upper;boll_lower | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `kdj_kd_diff` | KDJ K-D差 | virtual | `kdj_k - kdj_d` | 前复权 open/high/low/close；含当日=True；无；窗口=9 | 1 /  | kdj_k;kdj_d | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.3 均线偏离（10 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ma5_bias` | MA5乖离 | virtual | `close / ma5 - 1` | 前复权收盘(close)；含当日=True；无；窗口=5 | 1 / 5 ✗低估 | close;ma5 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ma10_bias` | MA10乖离 | virtual | `close / ma10 - 1` | 前复权收盘(close)；含当日=True；无；窗口=10 | 1 / 10 ✗低估 | close;ma10 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ma20_bias` | MA20乖离 | virtual | `close / ma20 - 1` | 前复权收盘(close)；含当日=True；无；窗口=20 | 1 / 20 ✗低估 | close;ma20 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ma30_bias` | MA30乖离 | virtual | `close / ma30 - 1` | 前复权收盘(close)；含当日=True；无；窗口=30 | 1 / 30 ✗低估 | close;ma30 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ma60_bias` | MA60乖离 | virtual | `close / ma60 - 1` | 前复权收盘(close)；含当日=True；无；窗口=60 | 1 / 60 ✗低估 | close;ma60 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ema5_bias` | EMA5乖离 | virtual | `close / ema5 - 1` | 前复权收盘(close)；含当日=True；无；窗口=5 | 1 /  | close;ema5 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ema10_bias` | EMA10乖离 | virtual | `close / ema10 - 1` | 前复权收盘(close)；含当日=True；无；窗口=10 | 1 /  | close;ema10 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ema20_bias` | EMA20乖离 | virtual | `close / ema20 - 1` | 前复权收盘(close)；含当日=True；无；窗口=20 | 1 /  | close;ema20 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ema30_bias` | EMA30乖离 | virtual | `close / ema30 - 1` | 前复权收盘(close)；含当日=True；无；窗口=30 | 1 /  | close;ema30 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ema60_bias` | EMA60乖离 | virtual | `close / ema60 - 1` | 前复权收盘(close)；含当日=True；无；窗口=60 | 1 /  | close;ema60 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.4 波动率（8 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `annual_vol_20d` | 20日波动率 | base | `pct_change(close).rolling_std(20) * sqrt(252)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 1 / 20 ✗低估 | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `atr_14` | ATR(14)原值 | base | `TR=max(h-l, \|h-prev_close\|, \|l-prev_close\|); ATR=ewm_mean(TR, alpha=1/14, adjust=False)` | 前复权 high/low/close；含当日=True；无；窗口=14 | 1 /  | high;low;close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `atr_pct` | ATR相对波动 | virtual | `atr_14 / close` | 前复权 high/low/close；含当日=True；无；窗口=14 | 1 /  | atr_14;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `amplitude` | 日振幅 | base | `(high - low) / prev_close，prev_close>0 否则为空` | 前复权 high/low/收盘；含当日=True；shift(1)（仅用于分母 prev_close）；窗口=1 | 1 / 1 | high;low;close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `boll_width` | 布林带宽 | virtual | `(boll_upper - boll_lower) / ma20` | 前复权收盘(close)；含当日=True；无；窗口=20 | 1 / 20 ✗低估 | ma20;boll_upper;boll_lower | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `downside_vol_20d` | 20日下行波动 | virtual | `sqrt(rolling_mean(clip(change, upper=0)^2, 20, min_samples=20))` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `vol_regime_5_60` | 波动率状态(5/60) | virtual | `rolling_std(change,5) / rolling_std(change,60)，std<=0 为空` | 前复权收盘(close)；含当日=True；无；窗口=60 | 61 / 60 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `amplitude_trend_20_60` | 振幅趋势(20/60) | virtual | `rolling_mean(amplitude,20) / rolling_mean(amplitude,60) - 1` | 前复权收盘(close)；含当日=True；无；窗口=60 | 61 / 60 ↑高估 | amplitude | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.5 价格位置（8 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gap_return` | 开盘跳空 | virtual | `open / prev_close - 1` | 前复权收盘(close)；含当日=True；无；窗口=1 | 1 / 1 | open;prev_close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `intraday_return` | 日内收益 | virtual | `close / open - 1` | 前复权收盘(close)；含当日=True；无；窗口=0 | 1 / 0 ↑高估 | open;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `close_position` | 收盘位置 | virtual | `(close - low) / (high - low)` | 前复权 open/high/low/close；含当日=True；无；窗口=0 | 1 / 0 ↑高估 | high;low;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `distance_to_high_60d` | 距60日高点 | virtual | `close / high_60d - 1；high_60d = close.rolling_max(60)（收盘价、含当日）` | 前复权收盘(close)；含当日=True；无；窗口=60 | 1 / 60 ✗低估 | close;high_60d | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr + backend/app/indicators/pipeline.py#compute_indicators/Pass1(high_60d)` |
| `distance_from_low_60d` | 距60日低点 | virtual | `close / low_60d - 1，low_60d = close.rolling_min(60)（收盘价、含当日）` | 前复权收盘(close)；含当日=True；无；窗口=60 | 1 / 60 ✗低估 | close;low_60d | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr + backend/app/indicators/pipeline.py#compute_indicators/Pass1(low_60d)` |
| `vwap_bias` | VWAP乖离 | virtual | `close / (amount / (volume*100)) - 1` | 前复权收盘(close)；含当日=True；无；窗口=0 | 1 / 0 ↑高估 | close;volume;amount | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `position_240d` | 一年价格位置 | virtual | `(close - min_240(close)) / (max_240(close) - min_240(close))，min_samples=240` | 前复权收盘(close)；含当日=True；无；窗口=240 | 241 / 240 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `distance_to_high_240d` | 距一年高点 | virtual | `close / rolling_max(close,240,min_samples=240) - 1` | 前复权收盘(close)；含当日=True；无；窗口=240 | 241 / 240 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.6 超买超卖（4 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rsi_6` | RSI(6) | base | `gain=max(diff(close),0), loss=max(-diff(close),0); avg=ewm_mean(alpha=1/6, adjust=False); RSI=100-100/(1+avg_gain/max(avg_loss,1e-12))` | 前复权收盘(close)；含当日=True；无；窗口=6 | 1 /  | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass5` |
| `rsi_14` | RSI(14) | base | `gain=max(diff(close),0), loss=max(-diff(close),0); avg=ewm_mean(alpha=1/14, adjust=False); RSI=100-100/(1+avg_gain/max(avg_loss,1e-12))` | 前复权收盘(close)；含当日=True；无；窗口=14 | 1 /  | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass5` |
| `rsi_24` | RSI(24) | base | `gain=max(diff(close),0), loss=max(-diff(close),0); avg=ewm_mean(alpha=1/24, adjust=False); RSI=100-100/(1+avg_gain/max(avg_loss,1e-12))` | 前复权收盘(close)；含当日=True；无；窗口=24 | 1 /  | close | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass5` |
| `rsi_14_delta_5d` | RSI五日变化 | virtual | `rsi_14 - rsi_14.shift(5)` | 前复权收盘(close)；含当日=True；rsi_14.shift(5)；窗口=14 | 6 /  | rsi_14 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.7 量价（11 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `vol_ratio_5d` | 5日量比 | base | `volume / volume.shift(1).rolling_mean(5)；盘中按 240/elapsed 折算当日量` | 前复权收盘(close)；含当日=True；shift(1).rolling_mean(5)（分母不含当日）；窗口=5 | 1 / 5 ✗低估 | volume | keep | — | `backend/app/indicators/pipeline.py#compute_indicators/Pass4` |
| `vol_ratio_10d` | 10日量比 | virtual | `volume / volume.shift(1).rolling_mean(10)` | 前复权收盘(close)；含当日=True；shift(1).rolling_mean(10)（分母不含当日）；窗口=10 | 11 / 10 ↑高估 | volume | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `vol_trend_5_10` | 成交量趋势 | virtual | `vol_ma5 / vol_ma10 - 1，vol_maN=volume.rolling_mean(N)（含当日）` | 前复权收盘(close)；含当日=True；无；窗口=10 | 1 / 10 ✗低估 | vol_ma5;vol_ma10 | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `turnover_rate` | 换手率 | base | `volume(手) * 10000 / float_shares(股)；float_shares<=0 时为空` | 成交量 + 历史时点流通股本；含当日=True；无；窗口=1 | 1 / 1 | volume;float_shares(按公告日生效) | keep | — | `backend/app/indicators/pipeline.py#compute_indicators#compute_all/Pass6` |
| `turnover_ratio_5d` | 换手率放大 | virtual | `turnover_rate / turnover_rate.shift(1).rolling_mean(5) - 1` | 前复权收盘(close)；含当日=True；shift(1).rolling_mean(5)；窗口=5 | 6 / 5 ↑高估 | turnover_rate | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `log_amount` | 成交额对数 | virtual | `ln(amount + 1)，amount>=0 否则为空` | 前复权收盘(close)；含当日=True；无；窗口=1 | 1 / 0 ↑高估 | amount | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `amount_ratio_5d` | 成交额放大 | virtual | `amount / amount.shift(1).rolling_mean(5) - 1` | 前复权收盘(close)；含当日=True；shift(1).rolling_mean(5)；窗口=5 | 6 / 5 ↑高估 | amount | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `vol_price_corr_20d` | 20日量价相关 | virtual | `Pearson corr(change, volume) over 20（min_samples=20，方差<=0 为空）` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close;volume | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `vol_trend_5_60` | 量能趋势(5/60) | virtual | `volume.rolling_mean(5) / volume.rolling_mean(60) - 1（均含当日）` | 前复权收盘(close)；含当日=True；无；窗口=60 | 60 / 60 | volume | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `obv_trend_20d` | 20日量能潮 | virtual | `rolling_sum(sign(change)*volume,20) / (rolling_mean(volume,20)*20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close;volume | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `amount_mean_20d` | 20日均成交额(亿) | virtual | `rolling_mean(amount/1e8, 20, min_samples=20) 单位=亿元` | 成交额；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | amount | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.8 流动性（4 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `amihud_20d` | 20日Amihud非流动性 | virtual | `rolling_mean(\|change\| / (amount/1e8), 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close;amount | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `turnover_z_60d` | 换手率60日z分 | virtual | `(turnover_rate - mean_60(t.shift(1))) / std_60(t.shift(1))，std<=0 为空` | 前复权收盘(close)；含当日=True；基线用 shift(1)；窗口=60 | 61 / 60 ↑高估 | turnover_rate | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `turnover_mean_20d` | 20日均换手 | virtual | `rolling_mean(turnover_rate, 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | turnover_rate | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `turnover_std_20d` | 20日换手波动 | virtual | `rolling_std(turnover_rate,20) / rolling_mean(turnover_rate,20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | turnover_rate | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.9 规模（1 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `log_float_mv` | 流通市值对数 | virtual | `ln(close * volume / turnover_rate)，turnover_rate>0 且 volume>0 否则为空` | 前复权收盘(close)；含当日=True；无；窗口=0 | 1 / 0 ↑高估 | close;volume;turnover_rate | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.10 财务（7 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pb_latest` | 市净率(最新公告) | base | `close / bps（bps=每股净资产；close 用当日收盘）` | 当日收盘（仅 pb_latest 参与）；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: pb | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `roe_latest` | ROE(最新公告) | base | `roe（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: roe | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `gross_margin_latest` | 毛利率(最新公告) | base | `gross_margin（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: gross_margin | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `net_margin_latest` | 净利率(最新公告) | base | `net_margin（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: net_margin | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `revenue_yoy_latest` | 营收增速(最新公告) | base | `revenue_yoy（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: revenue_yoy | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `net_income_yoy_latest` | 净利增速(最新公告) | base | `net_income_yoy（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: net_income_yoy | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |
| `debt_ratio_latest` | 资产负债率(最新公告) | base | `debt_to_asset_ratio（%）` | 不涉及价格；含当日=True；按公告日 join_asof：只在严格晚于 announce_date 的交易日生效（T+1）；窗口=— | 1 / 1 | financials/metrics/part.parquet: debt_ratio | keep | 是 | `backend/app/backtest/fundamentals.py#attach_fundamental_factors` |

### 2.11 截面联动（7 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `deviate_3d` | 3日基准偏离 | base | `个股 3 日收益 - 所属板块基准 3 日收益` | 前复权收盘 + 板块指数收盘；含当日=True；无；窗口=3 | 4 /  | close;板块基准收益(交易所板块指数) | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `deviate_10d` | 10日基准偏离 | base | `个股 10 日收益 - 所属板块基准 10 日收益` | 前复权收盘 + 板块指数收盘；含当日=True；无；窗口=10 | 11 /  | close;板块基准收益(交易所板块指数) | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `deviate_30d` | 30日基准偏离 | base | `个股 30 日收益 - 所属板块基准 30 日收益` | 前复权收盘 + 板块指数收盘；含当日=True；无；窗口=30 | 31 /  | close;板块基准收益(交易所板块指数) | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `industry_relative_momentum_20d` | 行业相对动量(20日) | base | `个股 20 日动量 - 同业等权均值` | 前复权收盘 + 行业成员；含当日=True；无；窗口=20 | 21 /  | close;industry(二级行业) | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `industry_rank_momentum_20d` | 行业内动量排名(20日) | base | `个股 20 日动量在所属行业内的平均排名百分位（1=最强）` | 前复权收盘 + 行业成员；含当日=True；无；窗口=20 | 21 /  | close;industry(二级行业) | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `industry_corr_60d` | 行业收益相关(60日) | base | `corr(个股日收益, 同业等权组合日收益) over 60，方差<=1e-18 为空` | 前复权收盘 + 行业成员；含当日=True；无；窗口=60 | 61 /  | close;industry | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |
| `industry_beta_60d` | 行业Beta(60日) | base | `cov(个股日收益, 同业等权组合日收益) / var(同业) over 60` | 前复权收盘 + 行业成员；含当日=True；无；窗口=60 | 61 /  | close;industry | keep | — | `backend/app/custom/cross_sectional_linkage/compute.py` |

### 2.12 收益形态（5 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `max_ret_20d` | 20日最大单日涨幅 | virtual | `change = close/close.shift(1)-1; rolling_max(change, 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `ret_skew_20d` | 20日收益偏度 | virtual | `rolling_skew(change, 20, bias=True)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `up_days_20d` | 20日上涨天数 | virtual | `(change>0).cast(f64).rolling_sum(20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `overnight_ret_20d` | 20日隔夜收益 | virtual | `rolling_sum(open/prev_close - 1, 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | open;prev_close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `intraday_ret_20d` | 20日日内收益 | virtual | `rolling_sum(close/open - 1, 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | open;close | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.13 涨停基因（2 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `limit_up_count_20d` | 涨停基因(20日) | virtual | `rolling_sum((consecutive_limit_ups.fill_null(0)>0).cast(f64), 20, min_samples=20)` | 前复权收盘(close)；含当日=True；无；窗口=20 | 21 / 20 ↑高估 | consecutive_limit_ups | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |
| `limit_up_count_60d` | 涨停基因(60日) | virtual | `同 limit_up_count_20d，窗口 60` | 前复权收盘(close)；含当日=True；无；窗口=60 | 61 / 60 ↑高估 | consecutive_limit_ups | keep | — | `backend/app/strategy/scoring.py#scoring_value_expr` |

### 2.14 首板事件链（9 个）

| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `first_board_chain_stage` | 首板事件链阶段 | virtual | `0 无锚/1 结构不完整/2 回调太浅/3 回攻未过前高/4 目标前已突破/5 首次收盘突破` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_anchor_distance` | 事件链锚点距离 | virtual | `锚点首板到目标首板的交易日数；未选锚为空` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_pullback_pct` | 事件链回调幅度 | virtual | `1 - L/P（前高 P、回调低点 L）` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_target_above_reference_pct` | 目标收盘距前高 | virtual | `目标首板收盘 / P - 1` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_strict_rebreak` | 事件链首次收盘突破 | virtual | `目标首板收盘首次突破 P 且此前无收盘突破` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_early_breakout` | 事件链目标前已突破 | virtual | `回调后、目标首板前已收盘突破 P` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_recovered_not_breakout` | 事件链回攻未过前高 | virtual | `结构有效且目标首板收盘未突破 P` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_seed_close_preserved` | 事件链锚点收盘守住 | virtual | `L >= 锚点首板收盘` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |
| `first_board_chain_seed_low_preserved` | 事件链锚点低点守住 | virtual | `L >= 锚点首板最低` | 前复权 open/high/low/close；含当日=True；事件内只用当日及以前 bar（递归回看，不 shift 未来）；窗口=250 | 251 /  | close;high;low;open;consecutive_limit_ups | keep | — | `backend/app/custom/first_board_chain` |

## 3. warmup 声明低于实际需求的 18 个（治理项）

这些因子的 `warmup_bars` 在注册表里声明得比实际所需短，后果是策略在因子尚未产出有效值的区间就认为「已预热」，早期信号可能是 null 或短窗口噪声。另有 28 个因子声明值偏保守（声明 > 实需），不构成风险，仅在表中标 `↑高估`。

| id | 声明 | 实需 | 说明 |
| --- | --- | --- | --- |
| `momentum_5d` | 1 | 5 | 需 5 根前置 bar；registry 声明 1（见 mismatch 标记） |
| `momentum_10d` | 1 | 10 | 需 10 根前置 bar；registry 声明 1（见 mismatch 标记） |
| `momentum_20d` | 1 | 20 | 需 20 根前置 bar；registry 声明 1（见 mismatch 标记） |
| `momentum_30d` | 1 | 30 | 需 30 根前置 bar；registry 声明 1（见 mismatch 标记） |
| `momentum_60d` | 1 | 60 | 需 60 根前置 bar；registry 声明 1（见 mismatch 标记） |
| `ma5_bias` | 1 | 5 | MA5 需 5 根 bar；registry 声明 1 |
| `ma10_bias` | 1 | 10 | MA10 需 10 根 bar；registry 声明 1 |
| `ma20_bias` | 1 | 20 | MA20 需 20 根 bar；registry 声明 1 |
| `ma30_bias` | 1 | 30 | MA30 需 30 根 bar；registry 声明 1 |
| `ma60_bias` | 1 | 60 | MA60 需 60 根 bar；registry 声明 1 |
| `boll_position` | 1 | 20 | rolling_std(20) 需 19 根；registry 声明 1 |
| `annual_vol_20d` | 1 | 20 | 需 19 根；registry 声明 1 |
| `boll_width` | 1 | 20 | 依赖 rolling_std(20)；registry 声明 1 |
| `vol_ratio_5d` | 1 | 5 | 需 5 根前置 bar |
| `vol_trend_5_10` | 1 | 10 | 需 9 根；registry 声明 1 |
| `distance_to_high_60d` | 1 | 60 | 需 59 根；registry 声明 1 |
| `distance_from_low_60d` | 1 | 60 | 需 59 根；registry 声明 1 |
| `mom_accel_20_60` | 1 | 60 | 继承 momentum_60d（60 根） |

## 4. 财务 PIT 因子（7 个）

| id | 名称 | PIT 来源 | 公式 | 空值 |
| --- | --- | --- | --- | --- |
| `pb_latest` | 市净率(最新公告) | `financial_announce` | `close / bps（bps=每股净资产；close 用当日收盘）` | keep |
| `roe_latest` | ROE(最新公告) | `financial_announce` | `roe（%）` | keep |
| `gross_margin_latest` | 毛利率(最新公告) | `financial_announce` | `gross_margin（%）` | keep |
| `net_margin_latest` | 净利率(最新公告) | `financial_announce` | `net_margin（%）` | keep |
| `revenue_yoy_latest` | 营收增速(最新公告) | `financial_announce` | `revenue_yoy（%）` | keep |
| `net_income_yoy_latest` | 净利增速(最新公告) | `financial_announce` | `net_income_yoy（%）` | keep |
| `debt_ratio_latest` | 资产负债率(最新公告) | `financial_announce` | `debt_to_asset_ratio（%）` | keep |

## 5. 未纳入本清单的 85 个 `ext_*`（扩展数据）

`all_factors()` 里 85 个 `ext_` 前缀因子由扩展数据包注册（集合竞价、龙虎榜等），其口径由各自 provider 定义、数据源不在本项目行情库内。本清单**不判定**其口径，只在策略引用时要求单独出证据。核验命令：

```bash
cd C:\work\sourcecode\tick-stock-panel\backend
.\\.venv\\Scripts\\python.exe -c "from app.factors import registry as R; fs=R.all_factors(); print(len(fs)); print([f.id for f in fs if f.id.startswith('ext_')][:5])"
```

## 6. 复现

```bash
cd C:\work\sourcecode\tick-stock-panel\backend
.\\.venv\\Scripts\\python.exe ..\docs\\research\\factor-audit-20261107\\scripts\\build_inventory.py   # 生成 csv/json
.\\.venv\\Scripts\\python.exe ..\docs\\research\\factor-audit-20261107\\scripts\\render_inventory_md.py     # 生成本文件
```

机器可读证据：`docs/factors/evidence/factors_inventory_core93_20261107.csv`（同 `docs/research/factor-audit-20261107/factors_inventory.csv`）、`factors_inventory.json`（含 dependencies / stability / asset_types）。
