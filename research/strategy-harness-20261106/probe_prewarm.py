"""探测 prewarm_matrix_cache 的耗时与产物。"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import (
    build_matrix_cache_profile,
    prewarm_matrix_cache,
)
from app.config import settings
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

repo = KlineRepository(DataStore(settings.data_dir))
engine = BacktestEngine(repo)
sengine = StrategyEngine(strategy_dirs=[])

years = int(sys.argv[1]) if len(sys.argv) > 1 else 1
latest = date(2026, 11, 6)

profile = build_matrix_cache_profile(
    sengine, "stock", max_disk_bytes=settings.backtest_matrix_cache_max_mb * 1024 * 1024
)
print("profile:", profile)
t0 = time.perf_counter()
out = prewarm_matrix_cache(
    engine, sengine, asset_type="stock", latest_date=latest, years=years
)
dt_s = time.perf_counter() - t0
print(f"prewarm years={years} in {dt_s:.1f}s")
print(json.dumps({k: str(v)[:120] for k, v in out.items()}, ensure_ascii=False, indent=2))
