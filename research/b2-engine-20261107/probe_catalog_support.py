"""探针: 列出当前因子目录里, 矩阵路径 `matrix_feature` 不支持物化的 id。

用途: 归因 B2 给测试带来的影响 (与 B0 pack 分开记账)。

只读: 构造与 tests/backtest/test_matrix_strategy.py::test_research_factor_catalog_matches_matrix_features
相同的合成面板, 逐个 id 试 matrix_feature, 记录异常类型与消息。
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(ROOT))

from app.backtest.factor import FACTOR_COLUMNS  # noqa: E402
from app.backtest.matrix import build_market_data_matrix, matrix_feature  # noqa: E402
from app.custom.cross_sectional_linkage.compute import LINKAGE_FACTOR_IDS  # noqa: E402


def panel() -> pl.DataFrame:
    rows = []
    start = date(2024, 1, 1)
    for offset in range(120):
        for asset_id, symbol in enumerate(("000001.SZ", "600000.SH")):
            close = 10.0 + asset_id * 5.0 + offset * (0.02 + asset_id * 0.01) + np.sin(offset / 5.0)
            volume = 1000.0 + asset_id * 250.0 + (offset % 9) * 80.0
            rows.append({
                "symbol": symbol,
                "date": start + timedelta(days=offset),
                "open": close - 0.15 + (offset % 3) * 0.02,
                "high": close + 0.35 + asset_id * 0.03,
                "low": close - 0.3,
                "close": close,
                "volume": volume,
                "amount": volume * close,
                "turnover_rate": 1.0 + asset_id * 0.2 + (offset % 7) * 0.05,
                "consecutive_limit_ups": (
                    (offset % 17) + 1 if (asset_id == 0 and offset % 17 == 0)
                    else (2 if (asset_id == 1 and offset % 23 == 0) else 0)
                ),
            })
    return pl.DataFrame(rows)


def main() -> int:
    import os

    tag = os.environ.get("PROBE_TAG", "current")
    df = panel()
    market = build_market_data_matrix(
        df, field_columns={"amount", "turnover_rate", "consecutive_limit_ups"}
    )
    ids = sorted({item["id"] for item in FACTOR_COLUMNS})
    ok, bad = [], []
    for name in ids:
        try:
            matrix_feature(market, name)
            ok.append(name)
        except Exception as exc:  # noqa: BLE001
            bad.append({"id": name, "error": type(exc).__name__, "detail": str(exc)[:120]})
    out = {
        "tag": tag,
        "catalog_size": len(ids),
        "matrix_supported": len(ok),
        "matrix_unsupported": len(bad),
        "unsupported": bad,
        "linkage_excluded": sorted(LINKAGE_FACTOR_IDS),
        "has_b0_pack": (ROOT / "app/custom/research_factor_pack").is_dir(),
        "has_universe_pack": (ROOT / "app/custom/research_universe_pack").is_dir(),
    }
    logs = Path(__file__).resolve().parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    dest = logs / f"catalog_support_{tag}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "unsupported"}, ensure_ascii=False))
    for item in bad:
        print("  UNSUPPORTED", item["id"], "|", item["detail"][:80])
    print("written", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
