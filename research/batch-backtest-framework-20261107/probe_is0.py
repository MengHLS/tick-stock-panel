"""探针: 同一折 (fold0) IS, 批量共享矩阵 vs 生产 _prepare_shared_matrix, 差在哪。"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "research/batch-backtest-framework-20261107"))

import run_batch as rb
from app.backtest.optimizer import OptimizeConfig, default_direction
from app.backtest.walkforward import (
    WalkForwardConfig,
    WalkForwardService,
    generate_folds,
)

groups = json.loads(Path("groups_g2.json").read_text(encoding="utf-8"))["groups"]
group = groups[0]
rt = rb.build_runtime()
start, end = date(2024, 12, 2), date(2026, 10, 31)
sl = rb.prepare_slice(rt, groups=groups, symbols=None, start=start, end=end,
                      asset_type="stock", train_days=252, test_days=63, step_days=63)
fold = sl.folds[0]
print("mine matrix:", sl.market.nbytes, sl.market.timestamp_labels[0], sl.market.timestamp_labels[-1], len(sl.market.symbols))
print("mine warmup_bars:", sl.plan.warmup_bars)

def opt(matrix, label):
    cfg = OptimizeConfig(
        strategy_id=group["strategy_id"], symbols=None,
        start=fold.train_start, end=fold.train_end,
        param_grid=group["param_grid"], objective="sortino",
        direction=default_direction("sortino"), max_workers=1,
        base_params=group.get("base_params") or {}, overrides=None,
        backtest_kwargs={"mode": "position", "initial_capital": 1_000_000.0, "asset_type": "stock"},
    )
    res = rt.optimizer.optimize(cfg, prepared_market_data=matrix)
    st = (res.get("best_backtest") or {}).get("stats") or {}
    print(label, "best_score=", res.get("best_score"), "raw_best=", res.get("best_raw"),
          "n_trades=", st.get("n_trades"), "shape=", st.get("market_matrix_shape"),
          "shared_bytes=", st.get("shared_market_data_bytes"))
    return res

opt(sl.market, "A_mine:")

wf = WalkForwardService(rt.optimizer, rt.service, rt.strategy_engine)
wcfg = WalkForwardConfig(
    strategy_id=group["strategy_id"], symbols=None, start=start, end=end,
    param_grid=group["param_grid"], objective="sortino",
    train_days=252, test_days=63, step_days=63,
    base_params=group.get("base_params") or {},
    backtest_kwargs={"mode": "position", "initial_capital": 1_000_000.0, "asset_type": "stock"},
    trading_days=tuple(sl.trading_days), continuous_account=True,
)
folds = generate_folds(start, end, 252, 63, 63, trading_days=sl.trading_days)
sp = wf._prepare_shared_matrix(wcfg, folds, backtest_kwargs={"mode": "position", "initial_capital": 1_000_000.0, "asset_type": "stock"})
m2 = sp.market_data
print("prod matrix:", m2.nbytes, m2.timestamp_labels[0], m2.timestamp_labels[-1], len(m2.symbols))
opt(m2, "B_prod:")
