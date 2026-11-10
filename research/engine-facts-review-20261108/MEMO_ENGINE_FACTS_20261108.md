# 引擎事实核验备忘：trailing_take_profit / trailing_peak_price / STOP_LOSS=-8

- 审核角色：独立审核工程师（只读核验，不改被审代码、不跑回测、不给实现建议）
- 时间：2026-11-08 16:4x（Asia/Shanghai）
- 仓库：`C:\work\sourcecode\tick-stock-panel`（`D:\TSP` 只是 data_root，无 `backend/`）
- 版本锚：`git rev-parse --short HEAD` = `52ead74c`，`git rev-parse --abbrev-ref HEAD` = `dev`
- 机械证据：`research/engine-facts-review-20261108/verify_engine_facts.py`（220 行 / 12,113 B）+ 运行日志 `verify.log`
- 复现命令与退出码见 §6。**87 条锚点全部命中，MISS=0，退出码 0。**

## 结论速览（每条一句：确证 / 未确证）

1. **确证**：`TRAILING_TAKE_PROFIT_DRAWDOWN = 0.08` 是「相对峰值回撤 8%」（线价 = 峰值 × (1 − |dd|)），不是「涨幅回吐 8 个百分点」；符号取 `abs()`，正负等价，但入口处会被静默夹紧到 `[0.005, 0.5]`；`exit_reason` 字面值 `trailing_take_profit`；成交价 = 开盘已越线取当日开盘价、日内触及取线价，**没有「次日开盘」分支**；T+1 与停牌/跌停约束都在。
2. **确证**：策略模块**不能**固定 peak price——`strategy/engine.py:648-652` 的模块常量清单只有 5 个风控名，没有 peak price；`TRAILING_PEAK_PRICE = "close"` 会被**静默忽略**（既不读也不报错）；唯一来源是策略文件 `META.backtest_defaults.trailing_peak_price`（API 请求、overrides 里都没有这个字段），且 `mode="full"` 时该值会被当作"不支持的执行规则"直接拒跑。
3. **确证**：`STOP_LOSS = -8` 生成的线价 = `entry × (1 − 8) = −7 × entry < 0`，被 `_valid_price(v > 0 and isfinite)` 过滤，止损线根本不存在 → 静默等价于「不设止损」，无异常、无日志、无计数；整条入口链（策略常量 / API / services / 匹配层）**没有任何量级校验**，`_normalize_pct` 只覆盖 4 个键，明确不含 `stop_loss` 与 `max_hold_days`。

未确证的部分集中在"运行时观测"：本轮按派单要求未跑回测、未加载应用，因此"trades 里 stop_loss 计数为 0""写 `TRAILING_PEAK_PRICE` 时确实零报错"都是由代码路径推断，不是运行时实测（见 §5）。

## 0. 被审文件指纹（`verify.log` 第 0 节原样）

| 文件 | sha256(前16) | 字节 | LF | mtime |
|---|---|---|---|---|
| `backend/app/backtest/engine.py` | `ecc3d8261c5605ed` | 268,800 | 5,670 | 2026-11-07 00:01:33 |
| `backend/app/backtest/strategy.py` | `c3bfb254969efcc6` | 173,615 | 3,909 | 2026-11-07 00:01:33 |
| `backend/app/backtest/execution_policy.py` | `11644aca487afc63` | 18,462 | 497 | 2026-11-03 17:08:58 |
| `backend/app/strategy/engine.py` | `44ef5884a339790b` | 104,076 | 2,359 | 2026-11-05 01:57:44 |
| `backend/app/api/backtest.py` | `cebd2dbffdf4a4bf` | 64,729 | 1,598 | 2026-11-08 00:38:50 |
| `backend/app/services/backtest.py` | `9ef30140ee555e2e` | 16,947 | 440 | 2026-10-26 18:07:02 |

`git status --porcelain` 里这 6 个文件均未出现在修改列表（engine.py / strategy.py / execution_policy.py / strategy/engine.py / services/backtest.py 干净；api/backtest.py 显示 ` M`，mtime 00:38:50 早于本次核验）。

---

## 1. `trailing_take_profit` 真实语义

### 1.1 线的构造（唯一公式，四条路径同式）

```
engine.py:3019   line_pct = 1.0 - abs(float(drawdown))
engine.py:3021   return adjusted_peak * line_pct          # live 生效分支
engine.py:3054   return raw_peak * line_pct * adjusted_open / raw_open   # legacy raw 重标定分支
```

等价的直接写法散落在四条路径（数值一致）：

| 位置 | 代码原文 |
|---|---|
| `engine.py:1715-1719` | `activate = config.trailing_take_profit_activate_pct` / `if activate is not None and drawdown is not None and peak_price > entry_price:` / `if peak_price / entry_price - 1 >= abs(float(activate)):` / `lines.append((peak_price * (1 - abs(float(drawdown))), "trailing_take_profit"))` |
| `engine.py:2184-2190` | `activate_pct = getattr(config, "trailing_take_profit_activate_pct", None)` … `risk_lines.append((peak_price * (1 - abs(float(drawdown_pct))), "trailing_take_profit"))` |
| `engine.py:3088-3105` | `peak_price / entry_price - 1 >= abs(float(activate))` … `_trailing_risk_line(..., abs(float(drawdown)))` / `"trailing_take_profit",` |
| `engine.py:4040-4053` | 同 3088-3105 的门槛与字面值（日内阶段） |
| `engine.py:4841-4849` | `take_profit_line = peak_price * (1 - abs(float(drawdown_pct)))` / `risk_lines.append((take_profit_line, "trailing_take_profit"))` |

### 1.2 四个问句的答复

**(a) 语义与符号约定**

- 是**峰值回撤 8%**：触发线在「峰值的 92%」处，`peak × (1 − 0.08)`；不是「涨幅回吐 8 个百分点」（后者应为 `peak × (1 − (peak_profit − 0.08))` 或 `entry × (1 + peak_profit − 0.08)`）。
  判别算式（同参数两算法不同）：`entry = 10`、`peak = 12`（峰值涨幅 20% ≥ activate 10%）：
  - 峰值回撤 8%：线 = `12 × 0.92 = 11.04`
  - 涨幅回吐 8pp：线 = `12 × (1 − (0.20 − 0.08)) = 12 × 0.88 = 10.56`
  引擎取 11.04。
- 符号约定：**全程 `abs()`**（3084、3094、3102、4043、4050、4848 皆然），所以 `0.08` 与 `-0.08` 完全等价，正值也被接受。
- 但入口不是"原样接受"：`backend/app/backtest/strategy.py:1617-1621`
  ```python
  trailing_take_profit_drawdown = self._normalize_pct(
      self._override_value(overrides, "trailing_take_profit_drawdown", getattr(s, "trailing_take_profit_drawdown", None)),
      0.005,
      0.5,
  )
  ```
  `_normalize_pct`（`strategy.py:3556-3563`）= `abs()` 后 `min(max(pct, 0.005), 0.5)`，**静默夹紧**、无日志无异常。所以：`0.08` → 0.08（8%）；`8`（当成 8%）→ 被夹成 **0.5 = 50% 回撤线**；`0.001` → 0.005。activate 的区间是 `[0.01, 2.0]`（`:1612-1616`），`20` 会被夹成 `2.0`（200%，永不触发）。

**(b) 触发后 `exit_reason` 与成交价**

- `exit_reason` 字面值：**`"trailing_take_profit"`**（`engine.py:1719/2190/3104/4052/4849`），由 `_sell()` 原样落库：`engine.py:3217  exit_reason=reason,`。不加重前缀、不映射（同族还有 `stop_loss` / `take_profit` / `trailing_stop` / `max_hold` / `signal` / `end` / `time_exit`，见 `engine.py:420` 注释与 `:4235/:4244`）。
- 成交价分两个阶段，**都不是「次日开盘」**：
  1. 开盘阶段（仅 `exit_fill ∈ {open_t+1, signal_next_minute}`，`engine.py:3854-3855、3951`）：`if _valid_price(open_price) and open_price <= stop_price:` → 成交价 = **当日开盘价**（跳空按开盘价）；开盘未越线则该阶段不成交（`_open_risk_trigger_price` `:2998 open_price > risk_price → return None`）。`open_t+1` 分支直接 `return open_price`（`:3001`）。
  2. 日内阶段（`engine.py:4001-4097`，**无 exit_fill 门控**）：`elif _valid_price(low_price) and low_price <= stop_price: override = stop_price`（`:4066-4067`）→ 成交价 = **线价**。
  - 结论：风控线的成交是「当日日内触及、线价成交」，`close_t` 模式下同样如此（`close_t` 只是没有开盘阶段，不是"按收盘价止损"）。把 `close_t` 理解成"止损也按收盘价成交"是错的。
- T+1：**有**。建仓日不参与任何退出判决：`engine.py:4007 or pos["entry_date"] == date_text`（日内阶段）、`:3863`（开盘阶段）、`:3954`（open_t+1 卖出循环）。
- 涨跌停/停牌：**有**。`_can_sell`（`engine.py:3121-3146`）：停牌 `:3122`、价无效 `:3125`、`close_t` 收盘封死跌停 `:3136-3143`、一字跌停 `:3144 if _one_price_limit(time_id, asset_id, "down")`、legacy raw 价 ≤ 跌停价+0.005 `:3131`。被拦后走 `_mark_pending`（`:3288`）递延，`reason` 保留，`blocked_exit_days` 累加。

**(c) activate 与 drawdown 的先后**

不是时间先后，而是**门槛**：两个字段都非 `None`、且 `peak_price > entry_price`，并且 `peak_price / entry_price - 1 >= abs(activate)` 成立时，drawdown 线才会被加入线集合（`engine.py:3090-3105`；1717-1719、2186-2190、4042-4053、4843-4849 同式）。也就是「先达到 activate 涨幅，drawdown 才启用」，用同一个峰值定义判定。

多线共存时取**最高价**那条：`max(valid_risk, key=lambda item: item[0])`（`:3111`、`:4056`）——回撤 8% 的线通常高于移动止损线，所以先命中、报 `trailing_take_profit`。

**(d) 峰值口径：除「只用收盘价」之外的分支**

- `trailing_peak_price = "high"`（**默认**，`engine.py:253`）→ 峰值用 `pos["max_high"]`；`"close"` → `pos["max_close"]`（`:3067-3071`、`:4021-4025`）。
- 峰值**收盘后才并入**，当日决策只用昨日及更早的峰值（`engine.py:4270-4290`：`max_high = max(..., 当日 high)`、`max_close = max(..., 当日 close)`，且建仓日 `close_t` 的当日 high 不计入，`:4276-4285`）→ 不构成前视。
- 第三条分支：`entry_price_basis = "raw"` 且矩阵带 `raw_close`（`legacy_raw_risk`，`:2588-2590`）时，线价按原始价重标定：`raw_peak * line_pct * adjusted_open / raw_open`（`:3054`），条件为复权开盘/原始开盘的比值与峰值时的 scale 不一致（`:3042-3053`）。

### 1.3 四条路径归属（对派单"消费点"清单的必要更正）

| 路径 | 入口 | trailing_take_profit 消费点 | 何时会跑 |
|---|---|---|---|
| `_simulate_portfolio_matrix`（**生产主路径**） | `simulate_market_matrix`（`:2543`）← `backtest/strategy.py:2305/2691`（`config.mode != "full"`） | `:3019-3055`（线构造）、`:3088-3111`（开盘判定）、`:4040-4077`（日内判定） | `mode="position"`（`StrategyBacktestConfig` 默认 `:731`）——matrix_native 策略走这条 |
| `_simulate_independent_matrix` | `simulate_independent_market_matrix`（`:1923`）← `strategy.py:2296/2682`（`mode == "full"`） | `:1715-1719` | 仅 `mode="full"` |
| `simulate_independent_candidates_legacy` | 旧独立撮合 | `:2184-2190` | legacy 调用方 |
| `simulate_portfolio_legacy` | `:4484` | `:4841-4853` | legacy 调用方 |

派单把 `:1715`、`:2184-2190`、`:3026-3110`、`:4023-4052`、`:4841-4850` 平列为"消费点"——**行号全部命中**，但只有 `:3026/:3088/:4023` 三处在 matrix_native 的实际路径上；另外三处属于 full/legacy，**同一次回测只会跑到一路**。这一点会影响"改常量后为什么无效"的排查方向（见 §4(a)）。

---

## 2. `trailing_peak_price` 能否被策略模块固定

**不能。三个明确结论：**

**(a) 模块常量清单里没有 peak price。** `backend/app/strategy/engine.py:648-652` 全文：

```python
stop_loss=getattr(mod, "STOP_LOSS", None),
trailing_stop=getattr(mod, "TRAILING_STOP", None),
trailing_take_profit_activate=getattr(mod, "TRAILING_TAKE_PROFIT_ACTIVATE", None),
trailing_take_profit_drawdown=getattr(mod, "TRAILING_TAKE_PROFIT_DRAWDOWN", None),
max_hold_days=getattr(mod, "MAX_HOLD_DAYS", None),
```

清单共 5 个风控名，**没有 `TRAILING_PEAK_PRICE`**（也没有 `TAKE_PROFIT`）。`StrategyDef`（`:195-221`）也没有 peak 字段。

**(b) 策略文件里写 `TRAILING_PEAK_PRICE = "close"` 会被静默忽略，不报错。** 证据：`grep -r "TRAILING_PEAK" backend/app` → **0 命中**；加载器只 `getattr` 上面 5 个名字 + `ENTRY_SIGNALS/EXIT_SIGNALS/META/LOOKBACK_DAYS/REQUIRED_FEATURES/SCORING`，没有 `dir(mod)` 白名单、没有"未知模块常量"报错分支（全仓检索 `dir(mod)` / `unknown constant` → 0 命中）。因此这个常量既不生效也不被拒——属于"写了当没写"。

**(c) 完整来源链（与派单给的链路不同：没有 API 请求字段这一段）**

```
策略文件 META["backtest_defaults"]["trailing_peak_price"]      # 唯一来源, 声明式
  └─ backtest/strategy.py:3586-3589  _strategy_execution_policy()
        parse_backtest_defaults(s.meta.get("backtest_defaults"), ...).engine_options()
     └─ backtest/execution_policy.py:135-140
          trailing_peak = _choice(payload.get("trailing_peak_price", "high"), {"high", "close"}, ...)
        # 非 high/close → BacktestDefaultsError; META 里未知字段在 v1 schema 下 fail closed (:122-127)
     └─ ExecutionPolicy.trailing_peak_price (:72, 默认 "high")  → engine_options() (:89)
  └─ MatcherConfig(trailing_peak_price=execution_policy["trailing_peak_price"])
       backtest/strategy.py:1865（position 主路径）/ :1587（minute_filter）/ :2638（另一路径）
  └─ engine.py:3069 / :4023 / :3026 消费
```

- **API 请求没有任何对应字段**：`api/backtest.py` 全文检索 `trailing_peak_price` → 0 命中；`services/backtest.py` → 0 命中。`StrategyBacktestRequest.overrides`（`api/backtest.py:356`）是无类型 dict，但匹配层只认 6 个 override 键（脚本实测）：`stop_loss / take_profit / trailing_stop / trailing_take_profit_activate / trailing_take_profit_drawdown / max_hold_days`（`backtest/strategy.py:1601-1622`）——**不含 trailing_peak_price**，写进 overrides 也是死数据。
- 所以"一次正常回测能否把它设成 close"：**能，但只能改策略文件的 `META.backtest_defaults` 并让策略重载**。唯一在仓内这么做的策略是 `backend/app/custom/first_board_event_chain/first_limit_pullback_3f_runner_t74.py:80  "trailing_peak_price": "close",`。
- 追加限制：`mode="full"` 时 `"close"` 会被判为不支持的执行规则——`engine.py:344 ("trailing_peak_price", "收盘峰值回撤")` + `:380 config.trailing_peak_price == "close"` → `unsupported_full_execution_rules()` → `backtest/strategy.py:1599-1600 return _err(full_execution_unsupported_message(...))`，直接拒跑而不是降级。

---

## 3. `STOP_LOSS = -8` 静默失效

### 3.1 失效机理（算式，`verify.log` §3c 实测输出）

```
engine.py:4028  (entry_price * (1 - abs(config.stop_loss_pct)), "stop_loss")
engine.py:4676  return v > 0 and np.isfinite(v)          # _valid_price
engine.py:4054  valid_lines = [(line, reason) for line, reason in risk_lines if _valid_price(line)]
```

- `STOP_LOSS = -8` → `stop_loss = -8`（原值透传，见 3.2）→ 线价 = `entry × (1 − |−8|) = entry × (1 − 8) = −7 × entry`。
- 实测三组：`entry=9.8` → 线价 `−68.6000`，`_valid_price = False`；`entry=12.5` → `−87.5000`，`False`；对照 `-0.08`、`entry=9.8` → `9.0160`，`True`。
- 负线价在**四个过滤点**被丢弃：`:1720`、`:2192`、`:4054`、`:4850`。其中生产路径是 `:4054`。
- 另一处同源失效：建仓日收盘锁定止损也用同一线（`:4107-4111 stop_line = risk_entry_price * (1 - |stop_loss_pct|)`；`current_close <= stop_line`）——线为负时永不成立，连"次日开盘止损"的挂单都不会登记。
- 结果：`stop_loss` 在 trades/`exit_reason` 里永远不出现，**无异常、无日志、无 `execution_stats` 计数**（`execution_stats` 只有 `sell_suspended/sell_limit_down/sell_invalid_price/...` 类计数，没有"风控线无效"这一类）。同一笔交易会一直持有到 `max_hold`/信号/期末。
- 对照（同族常量不是失效而是**静默失真**）：`TRAILING_STOP = -8` → `_normalize_pct(abs=8, 0.005, 0.5)` → **0.5**，即 −50% 移动止损；`TRAILING_TAKE_PROFIT_DRAWDOWN = 8` → **0.5**（50% 回撤线）；`TRAILING_TAKE_PROFIT_ACTIVATE = 20` → **2.0**（200%，永不激活）。这三种写法都不会报错。

### 3.2 入口链（逐跳）与"无量级校验"的位置证据

1. **策略文件（模块常量）**：`STOP_LOSS` / `MAX_HOLD_DAYS` → `strategy/engine.py:648 / :652` → `StrategyDef.stop_loss: float | None`（`:201`）、`max_hold_days: int | None`（`:205`）——**声明处无范围**。
2. **API 层**：
   - 策略回测：`StrategyBacktestRequest`（`api/backtest.py:350-...`）**没有** risk 字段，风险参数只能走 `overrides: dict | None`（`:356`），原样透传（`:439 overrides=req.overrides,`）——**无 schema、无校验**。
   - 信号回测：`BacktestRequest` 有 `stop_loss_pct: float | None = None`（`:91`）、`max_hold_days: int | None = None`（`:92`）——**裸类型、无 `Field(ge=…)`/`Field(le=…)`**。对照同一模型 `:86 symbols: list[str] = Field(..., min_length=1)`，说明作者会用 `Field`，风险参数是刻意没加。
3. **services 层**：`BacktestConfig`（`services/backtest.py:79`）`stop_loss_pct: float | None = None  # 例 -0.05 = -5%`（`:88`）、`max_hold_days: int | None = None`（`:89`）——**只有注释，没有校验**；vectorbt 旧通路只取 `abs()`（`:313-314 pf_kwargs["sl_stop"] = abs(config.stop_loss_pct)`），`-8` 在那里同样变成"800% 止损"（对 vectorbt 而言等于不触发）。
4. **匹配层**：`backtest/strategy.py:1601 stop_loss = self._override_value(overrides, "stop_loss", s.stop_loss)`、`:1622 max_hold_days = ...` → 直接写入 `MatcherConfig`（`:1850 stop_loss_pct=stop_loss`、`:1855 max_hold_days=max_hold_days`）。**这两个键不过 `_normalize_pct`**：脚本实测 `_normalize_pct` 只覆盖 `['take_profit', 'trailing_stop', 'trailing_take_profit_activate', 'trailing_take_profit_drawdown']`。
5. **全局断言**：`backend/app` 下与 `stop_loss` 同现 `raise/ValueError/HTTPException/assert` 的行 = **0 处**；`backtest/strategy.py` 内没有任何 `stop_loss` 的夹紧表达式（脚本两条 `T()` 均 OK）。`max_hold_days` 也没有下限夹紧。
6. **`max_hold_days < 1` 的实际行为**：无拒绝。`engine.py:4243 elif config.max_hold_days is not None and pos["hold_days"] >= config.max_hold_days:`；`hold_days` 建仓日记 1（`_buy_planned`，`:3427`）或 0（`_process_entries`，`:3751`），此后每交易日 +1（`:3846`）。`max_hold_days = 0` 或负 → 等价于"最早可卖日收盘离场"，不报错。

### 3.3 仓内种子策略实测取值（回归基线）

扫描范围 `backend/app/**/*.py`（排除 `.tmp-review/`），共 **28 个策略文件**声明了这两个常量：25 个 `strategy/seeds/*`、2 个 `custom/first_board_event_chain/*`、1 个 `strategy/research/*`：

- `STOP_LOSS` 分布：`−0.06` × 11、`−0.05` × 11、`−0.08` × 4、`−0.07` × 2 → **|STOP_LOSS| ∈ [0.05, 0.08]**
- `MAX_HOLD_DAYS` 分布：`15` × 10、`20` × 6、`10` × 5、`5` × 3、`30` × 2、`25` × 1、`74` × 1 → **∈ {5, 10, 15, 20, 25, 30, 74}**

代表性锚点（file:line = 常量所在行）：

| 文件 | STOP_LOSS | MAX_HOLD_DAYS |
|---|---|---|
| `strategy/seeds/consecutive_limit_ups.py` | `-0.05` (`:36`) | `5` (`:37`) |
| `strategy/seeds/limit_up_momentum.py` | `-0.05` (`:45`) | `5` (`:46`) |
| `strategy/seeds/near_limit_up.py` | `-0.05` (`:58`) | `5` (`:59`) |
| `strategy/seeds/low_volatility_leader.py` | `-0.05` (`:55`) | `30` (`:56`) |
| `strategy/seeds/active_limit_gene.py` | `-0.08` (`:57`) | `25` (`:58`) |
| `strategy/seeds/trend_breakout.py` | `-0.08` (`:58`) | `20` (`:59`) |
| `strategy/seeds/breakout_new_high_60d.py` | `-0.07` (`:52`) | `20` (`:53`) |
| `strategy/research/factor_rank_research.py` | `-0.08` (`:62`) | `30` (`:63`) |
| `custom/first_board_event_chain/strategy_rebreak.py` | `-0.08` (`:77`) | `10` (`:78`) |
| `custom/first_board_event_chain/first_limit_pullback_3f_runner_t74.py` | `-0.06` (`:125`) | `74` (`:130`) |

对"`|stop_loss| > 0.5` 报错 / `max_hold_days < 1` 拒绝"这条回归基线：现网合法取值最大是 `|−0.08|` 与 `74`，阈值 0.5 / 1 有 6 倍以上余量，**不会误伤任何在册策略**——可作为该判据的基线事实。

### 3.4 本次施改对象的当下取值（只读快照，属于活跃变更，仅供对照）

`D:\TSP\data\strategies\custom\custom_mw7fvp17.py`，2026-11-08 16:26:07，4,751 B，`sha256:5879a6dfa200…`：

```
:74  STOP_LOSS = -0.08
:75  TRAILING_TAKE_PROFIT_ACTIVATE = 0.10
:76  TRAILING_TAKE_PROFIT_DRAWDOWN = 0.08
:79  TRAILING_STOP = None
:80  MAX_HOLD_DAYS = 45
```

按上文量级：`-0.08` 落在正常带内（不会被丢）、`0.10` 在 activate 的 `[0.01, 2.0]` 内、`0.08` 在 drawdown 的 `[0.005, 0.5]` 内、`45` 无上限约束。**即：若四臂结果仍"看起来没风控"，不能归因于 §3.1 的量级陷阱**（是否生效另需运行时验证，本轮未做）。此快照随时可能被改动，只能代表 16:26:07 那一刻。

---

## 4. 与派单句子的冲突（不迁就，逐条列）

**(a) "消费点（约 :1715、:2184-2190、:3026-3110、:4023-4052、:4841-4850）"——行号全对，归属错。** 这五处分属 4 条互斥路径（§1.3），matrix_native 生产路径（`mode="position"` → `simulate_market_matrix` → `_simulate_portfolio_matrix`）只用 `:3026/:3088/:4023`；`:1715` 属 `mode="full"`，`:2184` 属 candidates_legacy，`:4841` 属 `simulate_portfolio_legacy`。把五处当"同一套消费点"会得出"改一处影响全局"的错误预期。

**(b) "`execution_policy["trailing_peak_price"]` 的完整来源链（API 请求字段 → services → MatcherConfig）"——不存在 API 请求字段这一段。** `api/backtest.py`、`services/backtest.py` 全文无 `trailing_peak_price`；`overrides` 只认 6 个键，也不含它。链路只到 `META.backtest_defaults` 为止（§2c）。

**(c) "成交价取哪个价（触发日开盘价？线价？次日开盘？）"——三者中"次日开盘"不存在。** 触发日开盘价（开盘越线）与线价（日内触及）都会出现，取决于阶段；`open_t+1` 的"次日"性来自"信号/委托在开盘执行"，不是把触及日推后一天。另需注意 `close_t` 的止损也不是收盘价成交（§1.2b）。

**(d) "有没有「峰值只用收盘价」以外的分支"——有两条**：默认 `"high"`（`max_high`），以及 `entry_price_basis="raw"` 时的 legacy raw 重标定分支（`:3054`）。

**(e) 派单把 `:4850` 写作"用 `_valid_price` 过滤风险线"——准确**（`risk_lines = [(line, reason) ... if _valid_price(line)]`），但它属于 legacy 路径；生产路径的同一过滤在 `:4054`。

---

## 5. 未确证 / 取证边界

1. **未跑回测、未启动应用**（按派单要求）。因此下列为代码推断、非运行时实测：`stop_loss` 在 trades 中计数为 0；写 `TRAILING_PEAK_PRICE` 时加载零报错；`_normalize_pct` 夹紧后最终进入 `MatcherConfig` 的数值。
2. **未做动态加载实验**（导入策略模块观察 `StrategyDef`）。"未知模块常量被忽略"由"无读取点 + 无白名单/校验点"推出，不是黑盒观测。
3. **未评审/未运行任何测试**（`pytest` 未跑）。本备忘不对 `backend/tests/**` 的既有断言有效性表态。
4. 未评价 S01b 规格与四臂结果，也未给任何实现建议（越界项，属策略经理/开发经理）。
5. 顺带观察（不在本次三问内，**未判性质**，仅记录供后续单独取证）：`hold_days` 在两个建仓入口初值不同（`_buy_planned` `:3427 = 1`；`_process_entries` `:3751 = 0`），而 `max_hold` 判定用同一比较式（`:4243`）。若两条建仓路径（计划买入 vs 非计划开盘买入）都按 `open_t+1` 成交，`max_hold_days` 的实际持有会话数可能相差 1。本轮未构造用例验证，不下结论。

---

## 6. 复现命令与退出码

```bash
cd C:/work/sourcecode/tick-stock-panel

# 版本锚
git rev-parse --short HEAD          # → 52ead74c            exit 0
git rev-parse --abbrev-ref HEAD     # → dev                 exit 0

# 87 条锚点 + 纯算术演示（只读，不 import 应用代码，不跑回测）
PYTHONIOENCODING=utf-8 python -u research/engine-facts-review-20261108/verify_engine_facts.py \
  > research/engine-facts-review-20261108/verify.log 2>&1
echo $?                             # → 0                   （OK=87 MISS=0）
```

首次运行时因把 `abs(float(drawdown))` 的锚点写成 `:4049`（实际 `:4050`）出现 `MISS=1 / exit 1`，更正后 `OK=87 / MISS=0 / exit 0`；两次结果都在 `verify.log` 的可追溯历史里（脚本内每条锚点都打印 `file:line + 备注`）。

产物清单：
- `research/engine-facts-review-20261108/MEMO_ENGINE_FACTS_20261108.md`（本文件）
- `research/engine-facts-review-20261108/verify_engine_facts.py`（220 行 / 12,113 B / 锚点断言 + 算术演示）
- `research/engine-facts-review-20261108/verify.log`（运行输出，含指纹与逐条 OK）
