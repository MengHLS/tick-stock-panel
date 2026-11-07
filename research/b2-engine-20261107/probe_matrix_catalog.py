"""列出因子目录里哪些 id 在矩阵路径不可物化 (用于给 test_research_factor_catalog 划排除表)。

只读探针: 用与测试相同的合成面板构造 market, 逐个 id 试 matrix_feature。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np
import polars as pl

from app.backtest.factor import FACTOR_COLUMNS
from app.backtest.matrix import build_market_data_matrix, matrix_feature
from app.custom.cross_sectional_linkage.compute import LINKAGE_FACTOR_IDS


def main() -> int:
    rows = []
    start = date(2024, 1, 1)
    for offset in range(120):
        for asset_id, symbol in enumerate(("000001.SZ", "600000.SH")):
            close = 10.0 + asset_id * 5.0 + offset * (0.02 + asset_id * 0.01) + np.sin(offset / 5.0)
            volume = 1000.0 + asset_id * 250.0 + (offset % 9) * 80.0
            rows.append({
                "symbol": symbol, "date": start + timedelta(days=offset),
                "open": close - 0.15 + (offset % 3) * 0.02,
                "high": close + 0.35 + asset_id * 0.03,
                "low": close - 0.3, "close": close, "volume": volume,
                "amount": volume * close,
                "turnover_rate": 1.0 + asset_id * 0.2 + (offset % 7) * 0.05,
                "consecutive_limit_ups": ((offset % 17) + 1 if (asset_id == 0 and offset % 17 == 0)
                                          else (2 if (asset_id == 1 and offset % 23 == 0) else 0)),
            })
    panel = pl.DataFrame(rows)
    market = build_market_data_matrix(
        panel, field_columns={"amount", "turnover_rate", "consecutive_limit_ups"}
    )
    ids = sorted({item["id"] for item in FACTOR_COLUMNS} - LINKAGE_FACTOR_IDS)
    unsupported = []
    for name in ids:
        try:
            matrix_feature(market, name)
        except ValueError:
            unsupported.append(name)
    print(f"catalog={len(ids)} unsupported={len(unsupported)}")
    for name in unsupported:
        print(" UNSUPPORTED", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
