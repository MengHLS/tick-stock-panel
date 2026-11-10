# -*- coding: utf-8 -*-
"""Read-only mechanical anchors for three engine facts.

被审对象: backend/app/backtest/engine.py, backend/app/backtest/strategy.py,
backend/app/backtest/execution_policy.py, backend/app/strategy/engine.py,
backend/app/api/backtest.py, backend/app/services/backtest.py

不写任何被审文件, 不跑回测, 不 import 应用代码。只做 file:line 原文断言 + 纯算术演示。
用法: python research/engine-facts-review-20261108/verify_engine_facts.py
退出码: 0 = 全部锚点命中; 1 = 有未命中 (逐条打印 MISS)。
"""
import hashlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E = "backend/app/backtest/engine.py"
S = "backend/app/backtest/strategy.py"
P = "backend/app/backtest/execution_policy.py"
SE = "backend/app/strategy/engine.py"
AB = "backend/app/api/backtest.py"
SB = "backend/app/services/backtest.py"

FAILS = []
OK = 0


def lines(rel):
    return (ROOT / rel).read_text(encoding="utf-8").splitlines()


def A(rel, n, needle, note):
    """assert: 1-based line n of rel contains needle."""
    global OK
    src = lines(rel)
    if n < 1 or n > len(src):
        FAILS.append("MISS %s:%d out of range (%d lines) - %s" % (rel, n, len(src), note))
        return
    if needle in src[n - 1]:
        OK += 1
        print("OK   %s:%d  %s" % (rel, n, note))
    else:
        FAILS.append("MISS %s:%d want %r - %s | actual=%r"
                     % (rel, n, needle, note, src[n - 1].strip()))


def T(cond, note):
    global OK
    if cond:
        OK += 1
        print("OK   " + note)
    else:
        FAILS.append("MISS " + note)


print("== 0. 指纹 (只记录, 不判等) ==")
for rel in (E, S, P, SE, AB, SB):
    p = ROOT / rel
    b = p.read_bytes()
    print("   %-42s sha256:%s %7d B %5d LF mtime=%s"
          % (rel, hashlib.sha256(b).hexdigest()[:16], len(b), b.count(b"\n"),
             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))
print()

print("== 1. trailing_take_profit: 线的构造与峰值口径 ==")
A(E, 241, "trailing_take_profit_activate_pct: float | None = None", "MatcherConfig.activate 字段")
A(E, 242, "trailing_take_profit_drawdown_pct: float | None = None", "MatcherConfig.drawdown 字段")
A(E, 253, 'trailing_peak_price: Literal["high", "close"] = "high"', "峰值口径默认 high")
A(E, 3019, "line_pct = 1.0 - abs(float(drawdown))", "线价 = 峰值 * (1 - |drawdown|)")
A(E, 3021, "return adjusted_peak * line_pct", "live 生效分支: 复权峰值 * line_pct")
A(E, 3054, "return raw_peak * line_pct * adjusted_open / raw_open", "legacy raw 分支重标定线价")
A(E, 3069, 'if config.trailing_peak_price == "close"', "峰值取 max_close 或 max_high")
A(E, 3094, "peak_price / entry_price - 1 >= abs(float(activate))", "activate 门槛: 峰值涨幅 >= |activate|")
A(E, 3102, "abs(float(drawdown))", "drawdown 取绝对值后再乘")
A(E, 3104, '"trailing_take_profit",', "exit_reason 字面值 (open 阶段)")
A(E, 1719, '"trailing_take_profit"', "independent 路径同式 (mode=full)")
A(E, 2190, '"trailing_take_profit"', "candidates_legacy 路径同式")
A(E, 4043, "peak_price / entry_price - 1 >= abs(float(activate))", "日内阶段同一 activate 门槛")
A(E, 4050, "abs(float(drawdown))", "日内阶段 drawdown 取绝对值")
A(E, 4052, '"trailing_take_profit",', "exit_reason 字面值 (日内阶段)")
A(E, 4848, "take_profit_line = peak_price * (1 - abs(float(drawdown_pct)))", "legacy _risk_profile 同式")

print()
print("== 1b. 触发与成交价 ==")
A(E, 4054, "for line, reason in risk_lines if _valid_price(line)", "风险线先过 _valid_price")
A(E, 4056, "max(valid_lines, key=lambda item: item[0])", "多线取最高价者")
A(E, 4058, "open_price <= stop_price", "开盘已越线 -> 用开盘价")
A(E, 4066, "low_price <= stop_price", "最低价触及 -> 用线价")
A(E, 4067, "override = stop_price", "成交价 = 线价")
A(E, 2998, "open_price > risk_price", "_open_risk_trigger_price: 开盘未越线则无成交")
A(E, 3001, "return open_price", "open_t+1 开盘越线成交价 = 开盘价")
A(E, 3189, 'config.execution_costs.fill_price(', "override 仍过执行成本模型")
A(E, 3217, "exit_reason=reason", "TradeRecord.exit_reason 原样落库")
A(E, 4007, 'pos["entry_date"] == date_text', "建仓日不参与风控卖出 (T+1)")
A(E, 3122, "matrix.tradable[time_id, asset_id]", "_can_sell: 停牌不卖")
A(E, 3144, '_one_price_limit(time_id, asset_id, "down")', "一字跌停不卖")
A(E, 3131, "price) <= limit_down + 0.005", "legacy raw: 跌停价不卖")

print()
print("== 1c. activate / drawdown 次序与峰值时点 ==")
A(E, 3091, "activate is not None", "activate 必须非空才启用")
A(E, 3092, "drawdown is not None", "drawdown 必须非空才启用")
A(E, 3093, "peak_price > entry_price", "峰值须已高于成本")
A(E, 4270, "峰值在收盘后并入", "峰值在收盘后并入 (次日才用)")
A(E, 4287, 'pos["max_high"] = max(float(pos["max_high"]), high_price)', "max_high 用当日 high")
A(E, 4290, 'pos["max_close"] = max(float(pos["max_close"]), close_price)', "max_close 用当日 close")
A(E, 4003, "for position_id in list(positions)", "日内风控循环 (无条件执行, 不受 exit_fill 门控)")
A(E, 3951, 'if open_phase and config.exit_fill == "open_t+1"', "开盘阶段只在 open_t+1 存在")

print()
print("== 2. trailing_peak_price 来源链 ==")
A(P, 42, '"trailing_peak_price",', "仅属 backtest_defaults 已知字段")
A(P, 72, 'trailing_peak_price: Literal["high", "close"] = "high"', "ExecutionPolicy 默认 high")
A(P, 89, '"trailing_peak_price": self.trailing_peak_price,', "engine_options 透传")
A(P, 136, 'payload.get("trailing_peak_price", "high")', "取值来源 = payload (META.backtest_defaults)")
A(P, 137, '{"high", "close"}', "只接受 high/close, 其它值 fail closed")
A(S, 3586, "parse_backtest_defaults(", "_strategy_execution_policy 解析入口")
A(S, 3587, 's.meta.get("backtest_defaults")', "来源 = 策略 META.backtest_defaults")
A(S, 1865, 'trailing_peak_price=execution_policy["trailing_peak_price"]', "写入 MatcherConfig (position 主路径)")
A(S, 1587, 'trailing_peak_price=execution_policy["trailing_peak_price"]', "写入 MatcherConfig (minute_filter 路径)")
A(S, 2638, 'trailing_peak_price=execution_policy["trailing_peak_price"]', "写入 MatcherConfig (另一路径)")
A(E, 344, '("trailing_peak_price", "收盘峰值回撤")', "mode=full 把 close 列为不支持规则")
A(S, 1599, "if unsupported_rules:", "full 模式命中即报错返回")
T("trailing_peak_price" not in (ROOT / AB).read_text(encoding="utf-8"),
  "api/backtest.py 全文无 trailing_peak_price (无请求字段)")
T("trailing_peak_price" not in (ROOT / SB).read_text(encoding="utf-8"),
  "services/backtest.py 全文无 trailing_peak_price")
T("TRAILING_PEAK" not in (ROOT / SE).read_text(encoding="utf-8"),
  "strategy/engine.py 不读 TRAILING_PEAK* 模块常量")

print()
print("== 2b. 策略模块常量读取清单 (只有 5 个风控名) ==")
A(SE, 648, 'getattr(mod, "STOP_LOSS", None)', "读 STOP_LOSS")
A(SE, 649, 'getattr(mod, "TRAILING_STOP", None)', "读 TRAILING_STOP")
A(SE, 650, 'getattr(mod, "TRAILING_TAKE_PROFIT_ACTIVATE", None)', "读 TRAILING_TAKE_PROFIT_ACTIVATE")
A(SE, 651, 'getattr(mod, "TRAILING_TAKE_PROFIT_DRAWDOWN", None)', "读 TRAILING_TAKE_PROFIT_DRAWDOWN")
A(SE, 652, 'getattr(mod, "MAX_HOLD_DAYS", None)', "读 MAX_HOLD_DAYS")
A(SE, 201, "stop_loss: float | None", "StrategyDef.stop_loss 无默认无范围")
A(SE, 205, "max_hold_days: int | None", "StrategyDef.max_hold_days 无默认无范围")
T(not re.search(r'getattr\(mod, "(TAKE_PROFIT|TRAILING_PEAK_PRICE)"', (ROOT / SE).read_text(encoding="utf-8")),
  "清单内无 TAKE_PROFIT / TRAILING_PEAK_PRICE 模块常量")

print()
print("== 3. STOP_LOSS 静默失效 ==")
A(E, 4671, "def _valid_price(value) -> bool:", "_valid_price 定义")
A(E, 4676, "return v > 0 and np.isfinite(v)", "_valid_price 判据: 必须 > 0")
A(E, 4028, '(entry_price * (1 - abs(config.stop_loss_pct)), "stop_loss")', "止损线 = 成本 * (1 - |pct|)")
A(E, 4838, '(entry_price * (1 - abs(config.stop_loss_pct)), "stop_loss")', "legacy 同式")
A(E, 4850, "for line, reason in risk_lines if _valid_price(line)", "legacy 过滤点")
A(E, 4107, 'stop_line = float(pos["risk_entry_price"]) * (', "建仓日收盘锁止损也用同一线")
A(E, 4111, "current_close <= stop_line", "线为负则永不锁定")

print()
print("== 3b. stop_loss / max_hold_days 入口链与量级校验 ==")
A(AB, 91, "stop_loss_pct: float | None = None", "信号回测请求字段: 裸 float, 无 Field 约束")
A(AB, 92, "max_hold_days: int | None = None", "max_hold_days 裸 int, 无 Field 约束")
A(AB, 86, "symbols: list[str] = Field(..., min_length=1)", "对照: 同模型对 symbols 确实用了 Field")
A(AB, 356, "overrides: dict | None = None", "策略回测风险参数走无类型 overrides")
A(AB, 439, "overrides=req.overrides,", "overrides 原样透传")
A(SB, 88, "stop_loss_pct: float | None = None", "BacktestConfig 无校验 (注释仅写 -0.05 = -5%)")
A(SB, 89, "max_hold_days: int | None = None", "BacktestConfig.max_hold_days 无校验")
A(SB, 314, 'pf_kwargs["sl_stop"] = abs(config.stop_loss_pct)', "vectorbt 旧通路只取 abs")
A(S, 1601, 'stop_loss = self._override_value(overrides, "stop_loss", s.stop_loss)', "stop_loss 不过 _normalize_pct")
A(S, 1622, 'max_hold_days = self._override_value(overrides, "max_hold_days", s.max_hold_days)', "max_hold_days 不过 _normalize_pct")
A(S, 1850, "stop_loss_pct=stop_loss,", "原值写入 MatcherConfig")
A(S, 3560, "pct = abs(float(value))", "_normalize_pct 才做 abs")
A(S, 3563, "return min(max(pct, min_value), max_value)", "_normalize_pct 才做区间夹紧")

src_s = (ROOT / S).read_text(encoding="utf-8").splitlines()
norm_targets = []
for i, l in enumerate(src_s, 1):
    if "_normalize_pct(" in l:
        for j in range(i, min(i + 3, len(src_s) + 1)):
            m = re.search(r'_override_value\(overrides,\s*"([a-z_]+)"', src_s[j - 1])
            if m:
                norm_targets.append((i, m.group(1)))
                break
print("   _normalize_pct 覆盖的 override 键: %s" % sorted({k for _, k in norm_targets}))
T({k for _, k in norm_targets} == {"take_profit", "trailing_stop",
                                   "trailing_take_profit_activate",
                                   "trailing_take_profit_drawdown"},
  "_normalize_pct 只覆盖 4 个键, 不含 stop_loss / max_hold_days")

full_src = "\n".join(src_s)
T(not re.search(r'stop_loss[^\n]*(_normalize_pct|min\(max\(|max\(min\()', full_src),
  "backtest/strategy.py 无任何 stop_loss 量级夹紧")
T(not re.search(r'max_hold_days[^\n]*(max\(|min\()', full_src),
  "backtest/strategy.py 无任何 max_hold_days 下限夹紧")

app_py = []
for p in (ROOT / "backend/app").rglob("*.py"):
    if ".tmp-review" in str(p):
        continue
    for i, l in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if re.search(r"stop_loss", l) and re.search(r"(ValueError|HTTPException|assert |raise )", l):
            app_py.append("%s:%d %s" % (p.relative_to(ROOT), i, l.strip()[:90]))
print("   backend/app 内 stop_loss 相关 raise: %d 处" % len(app_py))
for x in app_py:
    print("      " + x)
T(not app_py, "backend/app 内没有任何 stop_loss 的量级校验分支")

print()
print("== 3c. -8 的纯算术 (不跑回测) ==")
for sl, entry in ((-8, 9.8), (-8.0, 12.5), (-0.08, 9.8)):
    raw = entry * (1 - abs(sl))
    valid = raw > 0
    print("   STOP_LOSS=%-6s entry=%-5s -> 线价 %10.4f  _valid_price=%s"
          % (sl, entry, raw, "True" if valid else "False (线被丢弃)"))
T(abs(9.8 * (1 - abs(-8)) - (-68.6)) < 1e-9, "-8 的线价算式 = entry*(1-8) = -7*entry")
T(not (9.8 * (1 - abs(-8)) > 0), "-8 的线价 < 0, 被 _valid_price 判 False")
T(abs(9.8 * (1 - abs(-0.08)) - 9.016) < 1e-9, "-0.08 的线价 = 9.016 (正常)")

print()
print("== 结果 ==")
print("OK=%d MISS=%d" % (OK, len(FAILS)))
for f in FAILS:
    print(f)
sys.exit(0 if not FAILS else 1)
