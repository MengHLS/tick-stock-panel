"""验证第 3 改动集：风控参数量级校验在「请求层 / 装载层」都生效，且现有策略不受影响。

四段：
A. 纯函数边界（-0.5 / 0.5 / -8 / 0 / 1）
B. 策略装载层：临时目录里放三条策略（好 / STOP_LOSS=-8 / MAX_HOLD_DAYS=0），
   好策略进注册表，坏策略进 _load_errors 且不注册。
C. 生产策略目录（D:\TSP\data\strategies\{custom,ai,composite} + 内置 research）
   全量装载：条数、以及每条 STOP_LOSS / MAX_HOLD_DAYS 的量级实测表。
D. 请求层：BacktestRequest / StrategyBacktestRequest / SaveConfigRequest /
   BacktestConfig 的正例与反例。
运行：backend\.venv\Scripts\python.exe research\s01b-20261108\verify_risk_limits.py
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

GOOD = '''"""good"""
META = {"id": "rl_good", "name": "RL good", "asset_types": ["stock"], "timeframes": ["1d"]}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 45
REQUIRED_FEATURES = ["close", "ma20"]
def filter(df, params):
    import polars as pl
    return pl.lit(True)
'''

BAD_STOP = GOOD.replace('"rl_good"', '"rl_bad_stop"').replace("STOP_LOSS = -0.08", "STOP_LOSS = -8")
BAD_HOLD = GOOD.replace('"rl_good"', '"rl_bad_hold"').replace("MAX_HOLD_DAYS = 45", "MAX_HOLD_DAYS = 0")

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{(' :: ' + detail) if detail else ''}")
    if not cond:
        failures.append(name)


def part_a() -> None:
    from app.strategy.risk_limits import validate_max_hold_days, validate_stop_loss
    for v in (-0.08, -0.5, 0.5, 0.0):
        check(f"A stop_loss 接受 {v}", validate_stop_loss(v) == v)
    for v in (-8, 8, -0.5001, 1.0):
        try:
            validate_stop_loss(v)
            check(f"A stop_loss 应拒绝 {v}", False)
        except ValueError:
            check(f"A stop_loss 拒绝 {v}", True)
    for v in (1, 45, 60):
        check(f"A max_hold_days 接受 {v}", validate_max_hold_days(v) == v)
    for v in (0, -1, -45):
        try:
            validate_max_hold_days(v)
            check(f"A max_hold_days 应拒绝 {v}", False)
        except ValueError:
            check(f"A max_hold_days 拒绝 {v}", True)
    check("A None 直通", validate_stop_loss(None) is None and validate_max_hold_days(None) is None)


def part_b() -> None:
    from app.strategy.engine import StrategyEngine
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "rl_good.py").write_text(GOOD, encoding="utf-8")
        (d / "rl_bad_stop.py").write_text(BAD_STOP, encoding="utf-8")
        (d / "rl_bad_hold.py").write_text(BAD_HOLD, encoding="utf-8")
        engine = StrategyEngine(strategy_dirs=[d])
        ids = sorted(s.meta["id"] for s in engine.strategy_definitions())
        errors = getattr(engine, "_load_errors", [])
        check("B 好策略装载成功", "rl_good" in ids, str(ids))
        check("B STOP_LOSS=-8 策略未注册", "rl_bad_stop" not in ids, str(ids))
        check("B MAX_HOLD_DAYS=0 策略未注册", "rl_bad_hold" not in ids, str(ids))
        blob = json.dumps(errors, ensure_ascii=False, default=str)
        check("B -8 报错文案含量级上限", "超出量级上限" in blob, blob[:300])
        check("B max_hold 报错文案含量级下限", "必须 >= 1" in blob, blob[:300])
        print("  load_errors =", json.dumps(errors, ensure_ascii=False, default=str))


def part_c() -> None:
    from app.strategy.engine import StrategyEngine
    from app.config import settings
    dirs = [
        PROJECT / "backend" / "app" / "strategy" / "research",
        Path(settings.data_dir) / "data" / "strategies" / "custom",
        Path(settings.data_dir) / "data" / "strategies" / "ai",
        Path(settings.data_dir) / "data" / "strategies" / "composite",
    ]
    engine = StrategyEngine(strategy_dirs=dirs)
    defs = engine.strategy_definitions()
    errors = getattr(engine, "_load_errors", [])
    print(f"  装载策略数 = {len(defs)}, load_errors = {len(errors)}")
    rows = []
    for s in sorted(defs, key=lambda x: x.meta.get("id", "")):
        sl, mh = s.stop_loss, s.max_hold_days
        ok = (sl is None or abs(float(sl)) <= 0.5) and (mh is None or int(mh) >= 1)
        rows.append({"id": s.meta.get("id"), "STOP_LOSS": sl, "MAX_HOLD_DAYS": mh, "within_bounds": ok})
    for r in rows:
        print(f"  {r['id']:<48} STOP_LOSS={r['STOP_LOSS']!s:<6} MAX_HOLD_DAYS={r['MAX_HOLD_DAYS']!s:<5} ok={r['within_bounds']}")
    (HERE / "risk_limits_production_table.json").write_text(
        json.dumps({"n_strategies": len(defs), "load_errors": errors, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    check("C 生产装载无 load_errors", not errors, str(errors)[:300])
    check("C 全部策略量级合规", all(r["within_bounds"] for r in rows))
    check("C S01b 变体在册", any(r["id"] == "custom_mw7fvp17" for r in rows))


def part_d() -> None:
    from app.api.backtest import BacktestRequest, StrategyBacktestRequest
    from app.api.strategy import SaveConfigRequest
    from app.services.backtest import BacktestConfig
    ok = BacktestRequest(symbols=["600000.SH"], stop_loss_pct=-0.08, max_hold_days=5)
    check("D BacktestRequest 正例", ok.stop_loss_pct == -0.08 and ok.max_hold_days == 5)
    for kw, label in ((dict(stop_loss_pct=-8), "stop_loss_pct=-8"),
                      (dict(max_hold_days=0), "max_hold_days=0")):
        try:
            BacktestRequest(symbols=["600000.SH"], **kw)
            check(f"D BacktestRequest 应拒绝 {label}", False)
        except Exception:
            check(f"D BacktestRequest 拒绝 {label}", True)
    ok = StrategyBacktestRequest(strategy_id="custom_mw7fvp17",
                                 overrides={"stop_loss": -0.08, "max_hold_days": 45})
    check("D StrategyBacktestRequest 正例", ok.overrides["max_hold_days"] == 45)
    for ov in ({"stop_loss": -8}, {"max_hold_days": 0}):
        try:
            StrategyBacktestRequest(strategy_id="x", overrides=ov)
            check(f"D StrategyBacktestRequest 应拒绝 {ov}", False)
        except Exception:
            check(f"D StrategyBacktestRequest 拒绝 {ov}", True)
    try:
        SaveConfigRequest(strategy_id="x", overrides={"stop_loss": -8})
        check("D SaveConfigRequest 应拒绝 stop_loss=-8", False)
    except Exception:
        check("D SaveConfigRequest 拒绝 stop_loss=-8", True)
    check("D SaveConfigRequest 正例",
          SaveConfigRequest(strategy_id="x", overrides={"stop_loss": -0.08}).overrides["stop_loss"] == -0.08)
    cfg = BacktestConfig(symbols=["600000.SH"], start=date(2024, 1, 1), end=date(2024, 6, 1),
                         stop_loss_pct=-0.06, max_hold_days=5)
    check("D BacktestConfig 正例", cfg.max_hold_days == 5)
    try:
        BacktestConfig(symbols=["600000.SH"], start=date(2024, 1, 1), end=date(2024, 6, 1),
                       stop_loss_pct=-8)
        check("D BacktestConfig 应拒绝 stop_loss_pct=-8", False)
    except ValueError:
        check("D BacktestConfig 拒绝 stop_loss_pct=-8", True)


def main() -> int:
    os.environ.setdefault("DATA_DIR", r"D:\TSP")
    part_a()
    part_b()
    part_c()
    part_d()
    print(f"\nfailures = {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
