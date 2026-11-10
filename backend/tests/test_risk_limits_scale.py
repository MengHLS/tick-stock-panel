"""风控参数量级校验回归（S01b 第 3 改动集）。

覆盖：纯函数边界、策略装载层、请求层（三个 Pydantic 模型 + BacktestConfig），
以及内置种子策略的 STOP_LOSS / MAX_HOLD_DAYS 量级实测不受影响。
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.strategy.risk_limits import validate_max_hold_days, validate_stop_loss

SEEDS_DIR = Path(__file__).resolve().parents[1] / "app" / "strategy" / "seeds"
CONST_RE = re.compile(r"^(STOP_LOSS|MAX_HOLD_DAYS)\s*=\s*([^\s#]+)", re.MULTILINE)


# ── 纯函数边界 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value", [-0.08, -0.5, 0.5, 0.0, None])
def test_stop_loss_accepts_within_scale(value):
    assert validate_stop_loss(value) == value


@pytest.mark.parametrize("value", [-8, 8, -0.5001, 1.0])
def test_stop_loss_rejects_out_of_scale(value):
    with pytest.raises(ValueError):
        validate_stop_loss(value)


@pytest.mark.parametrize("value", [1, 45, 60, None])
def test_max_hold_days_accepts(value):
    assert validate_max_hold_days(value) == value


@pytest.mark.parametrize("value", [0, -1, -45])
def test_max_hold_days_rejects(value):
    with pytest.raises(ValueError):
        validate_max_hold_days(value)


# ── 策略装载层 ────────────────────────────────────────────────────────────
_GOOD = '''"""tmp strategy"""
META = {"id": "rl_good", "name": "RL good", "asset_types": ["stock"], "timeframes": ["1d"]}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 45
def filter(df, params):
    import polars as pl
    return pl.lit(True)
'''


def test_strategy_load_rejects_invalid_risk_scale(tmp_path):
    from app.strategy.engine import StrategyEngine

    (tmp_path / "rl_good.py").write_text(_GOOD, encoding="utf-8")
    (tmp_path / "rl_bad_stop.py").write_text(
        _GOOD.replace('"rl_good"', '"rl_bad_stop"').replace("STOP_LOSS = -0.08", "STOP_LOSS = -8"),
        encoding="utf-8",
    )
    (tmp_path / "rl_bad_hold.py").write_text(
        _GOOD.replace('"rl_good"', '"rl_bad_hold"').replace("MAX_HOLD_DAYS = 45", "MAX_HOLD_DAYS = 0"),
        encoding="utf-8",
    )
    engine = StrategyEngine(strategy_dirs=[tmp_path])
    ids = {s.meta["id"] for s in engine.strategy_definitions()}
    assert "rl_good" in ids
    assert "rl_bad_stop" not in ids
    assert "rl_bad_hold" not in ids
    errors = " ".join(str(item.get("error", "")) for item in engine.load_errors())
    assert "超出量级上限" in errors
    assert "必须 >= 1" in errors


# ── 请求层 ────────────────────────────────────────────────────────────────
def test_backtest_request_validators():
    from app.api.backtest import BacktestRequest

    ok = BacktestRequest(symbols=["600000.SH"], stop_loss_pct=-0.08, max_hold_days=5)
    assert ok.stop_loss_pct == -0.08 and ok.max_hold_days == 5
    with pytest.raises(Exception):
        BacktestRequest(symbols=["600000.SH"], stop_loss_pct=-8)
    with pytest.raises(Exception):
        BacktestRequest(symbols=["600000.SH"], max_hold_days=0)


def test_strategy_backtest_request_validates_overrides():
    from app.api.backtest import StrategyBacktestRequest

    ok = StrategyBacktestRequest(strategy_id="x", overrides={"stop_loss": -0.08, "max_hold_days": 45})
    assert ok.overrides["stop_loss"] == -0.08
    for bad in ({"stop_loss": -8}, {"max_hold_days": 0}):
        with pytest.raises(Exception):
            StrategyBacktestRequest(strategy_id="x", overrides=bad)


def test_save_config_request_validates_overrides():
    from app.api.strategy import SaveConfigRequest

    assert SaveConfigRequest(strategy_id="x", overrides={"stop_loss": -0.08}).overrides
    with pytest.raises(Exception):
        SaveConfigRequest(strategy_id="x", overrides={"stop_loss": -8})


def test_backtest_config_post_init_validates():
    from app.services.backtest import BacktestConfig

    cfg = BacktestConfig(symbols=["600000.SH"], start=date(2024, 1, 1), end=date(2024, 6, 1),
                         stop_loss_pct=-0.06, max_hold_days=5)
    assert cfg.max_hold_days == 5
    with pytest.raises(ValueError):
        BacktestConfig(symbols=["600000.SH"], start=date(2024, 1, 1), end=date(2024, 6, 1),
                       stop_loss_pct=-8)


# ── 种子策略量级（回归：现有种子不受新校验影响） ───────────────────────────
def test_seed_strategies_stay_within_risk_scale():
    files = sorted(SEEDS_DIR.glob("*.py"))
    assert files, "seeds 目录为空"
    checked = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        values = {name: raw for name, raw in CONST_RE.findall(text)}
        if "STOP_LOSS" in values:
            raw = values["STOP_LOSS"]
            if raw != "None":
                validate_stop_loss(float(raw), context=f"{path.name}.STOP_LOSS")
                checked += 1
        if "MAX_HOLD_DAYS" in values:
            raw = values["MAX_HOLD_DAYS"]
            if raw != "None":
                validate_max_hold_days(int(raw), context=f"{path.name}.MAX_HOLD_DAYS")
                checked += 1
    assert checked > 20, f"只检查到 {checked} 个常量，疑似正则失效"
