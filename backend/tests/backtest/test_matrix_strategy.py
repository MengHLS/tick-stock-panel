from __future__ import annotations

import gc
import logging
import threading
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl
import pytest

from app.backtest import matrix as matrix_module
from app.backtest.factor import FACTOR_COLUMNS, FactorBacktestService
from app.backtest.matrix import (
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    RealtimeMarketDataMatrix,
    apply_time_masks,
    build_market_data_matrix,
    build_matrix_score,
    make_signal_matrix,
    matrix_feature,
    slice_signal_matrix,
    validate_signal_matrix,
)
from app.backtest.matrix import (
    load_market_data_matrix_from_parquet as _load_matrix_real,
)
from app.backtest.strategy import build_matrix_cache_profile
from app.indicators.pipeline import (
    compute_indicators,
    compute_limit_signals,
)
from app.indicators.pipeline import (
    compute_signals as compute_indicator_signals,
)
from app.strategy.engine import StrategyDataContext, StrategyEngine

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _migrated_signal_definitions(monkeypatch):
    """注入迁移自内置的信号定义 (信号列定义驱动, 不依赖运行目录)。"""
    from tests.signal_seeds import install_pipeline_caches
    install_pipeline_caches(monkeypatch)




def _load_matrix(parquet_root, start, end, **kwargs):
    """测试包装: 显式给出来源根, 并按临时夹具声明合成来源令牌。"""
    kwargs.setdefault("data_dir", Path(parquet_root).parent)
    return _load_matrix_real(parquet_root, start, end, **kwargs)


def test_common_matrix_features_match_polars_indicator_pipeline():
    rows = []
    start = date(2024, 1, 1)
    for offset in range(100):
        close = 10.0 + offset * 0.03 + np.sin(offset / 4.0) * 0.8
        rows.append({
            "symbol": "000001.SZ",
            "date": start + timedelta(days=offset),
            "open": close - 0.1,
            "high": close + 0.3 + (offset % 3) * 0.02,
            "low": close - 0.25,
            "close": close,
            "volume": 1000.0 + (offset % 7) * 130.0,
        })
    panel = pl.DataFrame(rows)
    features = {
        "prev_close", "change_pct", "change_amount", "amplitude",
        "ma5", "ma20", "ma60", "boll_upper", "boll_lower",
        "high_60d", "low_60d", "momentum_60d", "vol_ratio_5d",
        "annual_vol_20d", "rsi_14",
    }
    enriched = compute_indicators(panel, needed=features)
    market = build_market_data_matrix(panel)

    for name in sorted(features):
        expected = enriched.sort(["date", "symbol"])[name].to_numpy()
        actual = matrix_feature(market, name)[:, 0]
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-5, equal_nan=True)

    expected_bias = (
        enriched.sort(["date", "symbol"])["close"].to_numpy()
        / enriched.sort(["date", "symbol"])["ma20"].to_numpy()
        - 1.0
    )
    np.testing.assert_allclose(
        matrix_feature(market, "ma20_bias")[:, 0],
        expected_bias,
        rtol=2e-5,
        atol=2e-5,
        equal_nan=True,
    )


def _matrix_catalog_panel() -> pl.DataFrame:
    """目录对比用例的合成面板 (两个标的、120 根、含 amount/turnover/连板列)。

    独立成函数: 目录对比、不支持项正向断言、in_universe 双路径登记三处共用同一夹具,
    免得各自造面板导致「支持数」在不同夹具下不可比。
    """
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


def _matrix_catalog_market(panel):
    """目录对比口径的市场矩阵: 同一条构造 + 财务字段挂载路径。"""
    from app.backtest.fundamentals import FUNDAMENTAL_FACTOR_NAMES, attach_matrix_fundamental_fields

    market = build_market_data_matrix(
        panel,
        field_columns={"amount", "turnover_rate", "consecutive_limit_ups"},
    )
    return attach_matrix_fundamental_fields(market, None, sorted(FUNDAMENTAL_FACTOR_NAMES))

#: 4 个「注册在 provider 包里、矩阵路径也有内置实现」的撞名因子（F-A44）。
_COLLIDING_MATRIX_FACTORS = ("ma20", "ma60", "boll_lower", "boll_upper")

#: 矩阵路径缺实现、真调必抛 `unsupported matrix feature` 的 12 名（实跑登记值）。
#: 拆成两组，两组都由机器断言（见 test_matrix_path_unsupported_ids_each_really_raise）：
#:   * 6 名非 alias、真缺能力 —— 矩阵侧既无内置分支，provider 也没给矩阵字段；
#:   * 6 名是 alias，pack 只登记了 alias 到 `uf_*` canonical 的映射，而 canonical 在
#:     矩阵侧没有实现（provider 有该 id，`materialize_matrix_factor_field` 却返回 None）。
#: `ma120` / `ma200` 同样是 alias，但矩阵侧有内置 `ma{period}` 分支，故**不**在此列。
_MATRIX_UNSUPPORTED_NO_ALIAS = (
    "in_universe",
    "market_breadth",
    "month_end",
    "prior_amount_20",
    "sd20",
    "week_end",
)
_MATRIX_UNSUPPORTED_ALIAS = (
    "prior_high_20",
    "prior_high_250",
    "prior_high_55",
    "prior_low_10",
    "prior_vol_20",
    "vol60",
)
EXPECTED_MATRIX_UNSUPPORTED = {
    name: f"unsupported matrix feature: {name}"
    for name in _MATRIX_UNSUPPORTED_NO_ALIAS + _MATRIX_UNSUPPORTED_ALIAS
}

#: 目录快照的实跑锚点：111 名目录 / 7 个联动因子 / 104 名参与 / 92 名矩阵支持。
EXPECTED_CATALOG_COUNT = 111
EXPECTED_LINKAGE_COUNT = 7
EXPECTED_MATRIX_SUPPORTED_COUNT = 92


def _matrix_path_unsupported(market, names):
    """**行为探测**：对每个 id 真调一次 `matrix_feature`，谁抛
    `unsupported matrix feature` 就记下原文消息。

    为什么不用「provider 有没有覆写 `materialize_matrix`」推断：
    B0 包 14 个因子都没覆写矩阵方法，但其中 `ma20` / `ma60` / `boll_lower` /
    `boll_upper` 在 `matrix_feature` 的 `_MATRIX_COMPUTED_FEATURES` 里**本来就有**
    内置实现，会正常算出数值 —— 按类型推断会把这 4 个（正好是 F-A44 的撞名因子）
    误剔出对比集。只有真调用能区分「没实现」与「实现了但不在 provider 里」。

    抛出**其它**异常不算「不支持」：直接往外抛，让用例红 —— 那是实现缺陷，不是缺能力。
    """
    unsupported = {}
    for name in names:
        try:
            matrix_feature(market, name)
        except ValueError as exc:
            message = str(exc)
            if not message.startswith("unsupported matrix feature"):
                raise
            unsupported[name] = message
    return unsupported

def test_research_factor_catalog_matches_matrix_features():
    """目录里每一个「矩阵路径有实现」的因子，逐值对齐 frame 路径。

    能力边界用**行为探测**（真调 `matrix_feature` 看抛不抛 unsupported），并把三个
    数字都写成实跑锚点：目录 111 名 / 扣除 7 个联动因子后 104 名参与判定 / 12 名抛
    unsupported（见 EXPECTED_MATRIX_UNSUPPORTED）/ 92 名进入逐值对比。
    """
    from app.custom.cross_sectional_linkage.compute import LINKAGE_FACTOR_IDS
    from app.extensions.factors import ensure_factor_providers

    # provider 装载的因子（B0 / E3 / E4）是进程级注册态；不先 ensure 就会把它们当
    # 未知 id 抛 unsupported，支持数会随用例顺序漂移。
    ensure_factor_providers()

    panel = _matrix_catalog_panel()
    # 联动因子由 linkage store 物化，不能从这段无外部状态的合成面板推导 —— 这是
    # **数据来源**不在夹具里，与「矩阵路径有没有实现」无关；两条路径都不比。
    catalog_ids = {item["id"] for item in FACTOR_COLUMNS}
    assert len(catalog_ids) == EXPECTED_CATALOG_COUNT, f"目录条数变了: {len(catalog_ids)}"

    considered = catalog_ids - LINKAGE_FACTOR_IDS
    assert len(considered) == EXPECTED_CATALOG_COUNT - EXPECTED_LINKAGE_COUNT, len(considered)

    market = _matrix_catalog_market(panel)
    unsupported = _matrix_path_unsupported(market, considered)
    factor_names = considered - set(unsupported)

    # --- 登记口径：支持数 + 不支持清单都必须是实跑值，缩水就红 ---
    assert set(unsupported) == set(EXPECTED_MATRIX_UNSUPPORTED), (
        "矩阵不支持集合与登记值不一致; "
        f"多出={sorted(set(unsupported) - set(EXPECTED_MATRIX_UNSUPPORTED))}, "
        f"少了={sorted(set(EXPECTED_MATRIX_UNSUPPORTED) - set(unsupported))}"
    )
    assert len(factor_names) == EXPECTED_MATRIX_SUPPORTED_COUNT, (
        f"矩阵支持数应为 {EXPECTED_MATRIX_SUPPORTED_COUNT}, 实为 {len(factor_names)}"
    )

    # 4 个撞名因子（F-A44）两条路径都有实现，必须留在对比集里 —— 之前按「provider
    # 没覆写 materialize_matrix」把它们踢出去，等于先摘掉最该被比对的对象。
    for name in _COLLIDING_MATRIX_FACTORS:
        assert name in factor_names, f"{name} 必须留在逐值对比集里"

    expected = FactorBacktestService._compute_missing_factors(panel, factor_names)
    from app.backtest.fundamentals import FUNDAMENTAL_FACTOR_NAMES

    fundamental_names = sorted(factor_names & FUNDAMENTAL_FACTOR_NAMES)
    if fundamental_names:
        # 夹具无财务数据：两条路径都应得到全 null/NaN 列，而不是报错。
        expected = expected.with_columns([
            pl.lit(None, dtype=pl.Float64).alias(name)
            for name in fundamental_names
            if name not in expected.columns
        ])

    max_abs_diff = {}
    for name in sorted(factor_names):
        expected_values = expected.sort(["date", "symbol"])[name].to_numpy().reshape(market.shape)
        actual_values = matrix_feature(market, name)
        diff = np.abs(actual_values.astype(np.float64) - expected_values.astype(np.float64))
        finite = diff[np.isfinite(diff)]
        if finite.size:
            max_abs_diff[name] = float(finite.max())
        np.testing.assert_allclose(
            actual_values,
            expected_values,
            rtol=2e-4,
            atol=2e-4,
            equal_nan=True,
            err_msg=name,
        )

    # 4 个撞名因子逐值对比的实测 max_abs_diff 必须真有数字且落在容差内，
    # 不能只靠 allclose 的隐式判定（审核要的显式判据）。
    for name in _COLLIDING_MATRIX_FACTORS:
        assert name in max_abs_diff, f"{name} 没算出 max_abs_diff（逐值对比没覆盖到）"
        assert max_abs_diff[name] <= 2e-4, f"{name} max_abs_diff={max_abs_diff[name]!r}"


def test_matrix_path_unsupported_ids_each_really_raise():
    """被排除项逐条给「喂给 `matrix_feature` 必抛 unsupported」的正向断言。

    这是排除集唯一的合法依据：不靠类型、不靠「没覆写」，每条都有抛错证据。
    """
    from app.extensions.factors import ensure_factor_providers

    ensure_factor_providers()
    market = _matrix_catalog_market(_matrix_catalog_panel())

    for name, expected_message in EXPECTED_MATRIX_UNSUPPORTED.items():
        with pytest.raises(ValueError) as excinfo:
            matrix_feature(market, name)
        assert str(excinfo.value) == expected_message, f"{name} 的抛错原文变了"

    # --- 排除集逐名的真实归因，必须与登记值对上，不能只靠注释说明 ---
    from app.backtest.matrix import _MATRIX_COMPUTED_FEATURES
    from app.custom.research_factor_pack.factor_specs import _ALIAS_OF
    from app.extensions.factors import (
        materialize_matrix_factor_field,
        provider_factor_ids,
    )

    # 11 名的共同机制（逐名断言，不靠推断）：因子已注册进 provider，但 provider 拿不出
    # 矩阵字段，且名字不命中矩阵侧任何内置分支 —— 三者同时成立才允许判「不支持」。
    for name in EXPECTED_MATRIX_UNSUPPORTED:
        assert provider_factor_ids([name]), f"{name} 没进 provider 注册表"
        assert materialize_matrix_factor_field(market, name) is None, (
            f"{name} 已能出矩阵字段，不该再算不支持"
        )
        assert name not in _MATRIX_COMPUTED_FEATURES, f"{name} 有内置矩阵分支，不该算不支持"

    # 两支的划分只是目录事实（谁在 alias 表里），不是能力归因；这里固定它防止漂移。
    assert {n for n in _MATRIX_UNSUPPORTED_ALIAS if n in _ALIAS_OF} == set(
        _MATRIX_UNSUPPORTED_ALIAS
    ), "6 名 alias 支里有人不在 _ALIAS_OF"
    assert not any(n in _ALIAS_OF for n in _MATRIX_UNSUPPORTED_NO_ALIAS), (
        "5 名非 alias 支里有人其实有 alias"
    )

    # 反例：同样是 alias 但矩阵侧有内置 `ma{period}` 分支的两名，必须能算出数值。
    for name in ("ma120", "ma200"):
        assert name in _ALIAS_OF
        assert matrix_feature(market, name).shape == market.shape


def test_in_universe_both_path_reds_are_registered():
    """`in_universe` 两条路径各自的红都固定下来，不再用「剔除」把它藏掉。

    * 矩阵路径：抛 `unsupported matrix feature: in_universe`（缺矩阵实现）。
    * frame 路径：本夹具没有 `raw_close` 列 → 抛 `in_universe 缺少必需列: ['raw_close']`
      （E3 包的数据列缺口，与矩阵支不支持是两件事）。
    """
    from app.extensions.factors import ensure_factor_providers

    ensure_factor_providers()
    panel = _matrix_catalog_panel()

    market = _matrix_catalog_market(panel)
    with pytest.raises(ValueError) as matrix_excinfo:
        matrix_feature(market, "in_universe")
    assert str(matrix_excinfo.value) == "unsupported matrix feature: in_universe"

    with pytest.raises(ValueError) as frame_excinfo:
        FactorBacktestService._compute_missing_factors(panel, {"in_universe"})
    assert "in_universe 缺少必需列" in str(frame_excinfo.value)
    assert "raw_close" in str(frame_excinfo.value)

def _panel_with_missing_asset_bar() -> pl.DataFrame:
    rows = []
    start = date(2024, 1, 1)
    for offset in range(110):
        for asset_id, symbol in enumerate(("000001.SZ", "600000.SH")):
            if symbol == "000001.SZ" and offset == 43:
                continue
            if asset_id == 0:
                close = (
                    20.0 - offset * 0.15
                    if offset < 35
                    else 14.75 + (offset - 35) * 0.25
                )
            else:
                close = 18.0 + offset * 0.025 + np.sin(offset / 5.0) * 0.7
            rows.append({
                "symbol": symbol,
                "date": start + timedelta(days=offset),
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.25,
                "close": close,
                "volume": 1000.0 + asset_id * 200.0 + (offset % 7) * 130.0,
            })
    return pl.DataFrame(rows)


def test_matrix_features_skip_missing_asset_bars_like_polars_groups():
    panel = _panel_with_missing_asset_bar()
    features = {
        "prev_close", "change_pct", "change_amount", "amplitude",
        "ma5", "ma20", "ma60", "boll_upper", "boll_lower",
        "high_60d", "low_60d", "momentum_60d", "vol_ratio_5d",
        "annual_vol_20d", "rsi_14",
    }
    enriched = compute_indicators(panel, needed=features)
    market = build_market_data_matrix(panel)
    time_id_by_date = {
        label[:10]: time_id
        for time_id, label in enumerate(market.timestamp_labels)
    }

    for symbol in market.symbols:
        expected_rows = enriched.filter(pl.col("symbol") == symbol).sort("date")
        time_ids = np.array(
            [time_id_by_date[str(value)] for value in expected_rows["date"]],
            dtype=np.intp,
        )
        asset_id = market.symbols.index(symbol)
        for name in sorted(features):
            expected = expected_rows[name].to_numpy()
            actual = matrix_feature(market, name)[time_ids, asset_id]
            np.testing.assert_allclose(
                actual,
                expected,
                rtol=2e-5,
                atol=2e-5,
                equal_nan=True,
                err_msg=f"{symbol} {name}",
            )

    missing_time_id = time_id_by_date["2024-02-13"]
    missing_asset_id = market.symbols.index("000001.SZ")
    for name in features:
        assert np.isnan(matrix_feature(market, name)[missing_time_id, missing_asset_id])


def test_matrix_pipeline_builds_and_reuses_one_compact_valid_bar_index():
    panel = _panel_with_missing_asset_bar()
    market = build_market_data_matrix(panel)
    base_bytes = market.nbytes
    strategy = StrategyEngine._load_file(
        REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies" / "ma_golden_cross.py"
    ).matrix_strategy

    with patch.object(
        matrix_module,
        "_build_valid_bar_index",
        wraps=matrix_module._build_valid_bar_index,
    ) as build_index:
        MatrixStrategyPipeline().run(
            strategy,
            market,
            {
                "require_ma_golden": True,
                "use_volume_filter": False,
                "require_above_ma60": False,
            },
            MatrixPipelineConfig(
                basic_filter={"enabled": False},
                scoring={},
                order_by=None,
                descending=True,
            ),
        )

    index = market.valid_bars
    assert build_index.call_count == 1
    assert index.rows.size == panel.height
    assert index.offsets.tolist() == [0, 109, 219]
    assert market.valid_bars is index
    assert market.nbytes == base_bytes + index.nbytes


@pytest.mark.parametrize(
    ("strategy_file", "entry_column", "exit_column", "params"),
    [
        (
            "ma_golden_cross.py",
            "signal_ma_golden_5_20",
            "signal_ma_dead_5_20",
            {
                "require_ma_golden": True,
                "use_volume_filter": False,
                "require_above_ma60": False,
            },
        ),
        (
            "macd_golden.py",
            "signal_macd_golden",
            "signal_macd_dead",
            {"require_macd_golden": True, "use_volume_filter": False},
        ),
    ],
)
def test_matrix_crossovers_skip_missing_asset_bars_like_polars_signals(
    strategy_file: str,
    entry_column: str,
    exit_column: str,
    params: dict,
):
    panel = _panel_with_missing_asset_bar()
    indicator_names = (
        {"ma5", "ma20"}
        if strategy_file == "ma_golden_cross.py"
        else {"macd_dif", "macd_dea"}
    )
    enriched = compute_indicators(panel, needed=indicator_names)
    expected = compute_indicator_signals(
        enriched,
        needed={entry_column, exit_column},
    )
    market = build_market_data_matrix(panel)
    strategy_def = StrategyEngine._load_file(
        REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies" / strategy_file
    )
    actual = strategy_def.matrix_strategy.compute_signals(market, params)
    time_id_by_date = {
        label[:10]: time_id
        for time_id, label in enumerate(market.timestamp_labels)
    }

    for symbol in market.symbols:
        expected_rows = expected.filter(pl.col("symbol") == symbol).sort("date")
        time_ids = np.array(
            [time_id_by_date[str(value)] for value in expected_rows["date"]],
            dtype=np.intp,
        )
        asset_id = market.symbols.index(symbol)
        expected_entry = (
            expected_rows[entry_column].fill_null(False).cast(pl.UInt8).to_numpy()
        )
        expected_exit = (
            expected_rows[exit_column].fill_null(False).cast(pl.UInt8).to_numpy()
        )
        np.testing.assert_array_equal(actual.entry[time_ids, asset_id], expected_entry)
        np.testing.assert_array_equal(actual.exit[time_ids, asset_id], expected_exit)

    missing_time_id = time_id_by_date["2024-02-13"]
    missing_asset_id = market.symbols.index("000001.SZ")
    assert actual.entry[missing_time_id, missing_asset_id] == 0
    assert actual.exit[missing_time_id, missing_asset_id] == 0
    assert actual.entry.any() or actual.exit.any()


def test_builtin_matrix_strategies_use_their_declared_formula_modules():
    strategy_dir = REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies"
    strategy_files = sorted(
        path for path in strategy_dir.glob("*.py") if path.name != "__init__.py"
    )

    # 夹具目录 = 25 个 matrix 策略 (分钟形态策略在 strategies_minute 子目录, 研究模板在 research 目录)
    assert len(strategy_files) == 25
    for strategy_path in strategy_files:
        strategy = StrategyEngine._load_file(strategy_path)
        assert strategy.execution_backend == "matrix_native"
        assert strategy.matrix_strategy is not None
        assert strategy.matrix_strategy.__class__.__module__ == strategy_path.stem
        assert strategy.filter_fn is None
        assert strategy.filter_history_fn is None


def test_market_matrix_derives_live_raw_close_when_requested():
    panel = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "date": [date(2024, 1, 1)] * 2,
        "open": [10.0, 20.0],
        "high": [10.2, 20.2],
        "low": [9.8, 19.8],
        "close": [10.1, 20.1],
        "volume": [1_000.0, 2_000.0],
    })
    market = build_market_data_matrix(panel, field_columns={"raw_close"})

    np.testing.assert_array_equal(market.field("raw_close"), market.close)

    live = RealtimeMarketDataMatrix(
        panel,
        field_columns={"raw_close"},
    )
    live.update(panel.with_columns(pl.lit(date(2024, 1, 2)).alias("date")))
    snapshot = live.snapshot()
    np.testing.assert_array_equal(snapshot.field("raw_close")[-1], snapshot.close[-1])


def test_direct_parquet_matrix_reports_actionable_error_when_enriched_is_empty(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    market_root.mkdir()

    with pytest.raises(ValueError, match="本地指标数据为空"):
        _load_matrix(
            market_root,
            date(2024, 1, 1),
            date(2024, 1, 31),
            field_columns=set(),
        )


def test_direct_parquet_matrix_matches_panel_builder_and_reuses_mmap(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    days = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    rows = []
    closes = {
        "000001.SZ": (10.0, 11.0, 12.0),
        "000002.SZ": (10.0, 10.5, None),
        "300001.SZ": (10.0, 12.0, 12.2),
    }
    for symbol, values in closes.items():
        for current, close in zip(days, values, strict=True):
            if close is None:
                continue
            rows.append({
                "symbol": symbol,
                "date": current,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1_000.0,
                "amount": close * 100_000.0,
                "raw_close": close,
                "raw_high": close,
                "raw_low": close,
                "turnover_rate": 1.5,
            })
    panel = pl.DataFrame(rows).sort(["symbol", "date"])
    for current in days:
        partition = market_root / f"date={current.isoformat()}"
        partition.mkdir(parents=True)
        panel.filter(pl.col("date") == current).write_parquet(partition / "part.parquet")

    instruments = pl.DataFrame({
        "symbol": ["000001.SZ", "000002.SZ", "300001.SZ"],
        "name": ["普通", "ST测试", "创业板"],
        "total_shares": [1_000_000.0, 2_000_000.0, 3_000_000.0],
        "float_shares": [800_000.0, 1_500_000.0, 2_000_000.0],
        "limit_up": [12.0, 11.0, 13.0],
        "limit_down": [10.0, 9.0, 10.0],
    })
    enriched = compute_limit_signals(
        panel,
        instruments,
        needed={"signal_limit_up", "signal_limit_down"},
    ).join(
        instruments.select("symbol", "name", "total_shares", "float_shares"),
        on="symbol",
        how="left",
    )
    field_columns = {
        "amount",
        "raw_close",
        "raw_high",
        "raw_low",
        "turnover_rate",
        "total_shares",
        "float_shares",
    }
    expected = build_market_data_matrix(enriched, field_columns=field_columns)
    cache_root = tmp_path / "matrix_cache"
    actual = _load_matrix(
        market_root,
        days[0],
        days[-1],
        field_columns=field_columns,
        instruments=instruments,
        cache_root=cache_root,
    )
    assert actual.cache_status == "built"

    assert actual.timestamp_labels == expected.timestamp_labels
    assert actual.symbols == expected.symbols
    assert actual.names == expected.names
    for name in (
        "timestamps",
        "session_ids",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "tradable",
        "limit_up_locked",
        "limit_down_locked",
    ):
        np.testing.assert_array_equal(getattr(actual, name), getattr(expected, name))
    for name in field_columns:
        np.testing.assert_array_equal(actual.field(name), expected.field(name))

    cached = _load_matrix(
        market_root,
        days[0],
        days[-1],
        field_columns=field_columns,
        instruments=instruments,
        cache_root=cache_root,
    )
    assert cached.cache_status == "exact"
    assert isinstance(cached.close, np.memmap)
    assert not cached.close.flags.writeable
    np.testing.assert_array_equal(cached.close, actual.close)

    latest_path = market_root / f"date={days[-1].isoformat()}" / "part.parquet"
    latest = pl.read_parquet(latest_path).with_columns(
        pl.when(pl.col("symbol") == "000001.SZ")
        .then(12.5)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    latest.write_parquet(latest_path)
    refreshed = _load_matrix(
        market_root,
        days[0],
        days[-1],
        field_columns=field_columns,
        instruments=instruments,
        cache_root=cache_root,
    )
    target_asset = refreshed.symbols.index("000001.SZ")
    assert refreshed.close[-1, target_asset] == pytest.approx(12.5)
    assert len(list(cache_root.glob("v*-*"))) == 2


def test_collect_parquet_axes_stringifies_numeric_symbols(tmp_path):
    import pyarrow as pa
    import pyarrow.dataset as pads

    day = date(2024, 2, 1)
    root = tmp_path / "date=2024-02-01"
    root.mkdir()
    pl.DataFrame({"symbol": [1, 2], "date": [day, day]}).write_parquet(root / "part.parquet")
    dataset = pads.dataset(
        str(tmp_path), format="parquet",
        partitioning=pads.partitioning(pa.schema([("date", pa.date32())]), flavor="hive"),
    )
    dates, symbols = matrix_module._collect_parquet_axes(
        dataset, matrix_module._matrix_filter_expression(day, day, None), batch_size=1,
    )
    assert dates == [day]
    assert symbols == ["1", "2"]


def test_collect_parquet_axes_deduplicates_bounded_groups(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.dataset as pads

    first = date(2024, 2, 1)
    for offset in range(9):
        day = first + timedelta(days=offset)
        part = tmp_path / f"date={day}" / "part.parquet"
        part.parent.mkdir()
        pl.DataFrame({"symbol": ["000001.SZ"], "date": [day]}).write_parquet(part)
    dataset = pads.dataset(
        str(tmp_path), format="parquet",
        partitioning=pads.partitioning(pa.schema([("date", pa.date32())]), flavor="hive"),
    )
    unique = matrix_module.pc.unique
    calls = []

    def counted_unique(values):
        calls.append(len(values))
        return unique(values)

    monkeypatch.setattr(matrix_module.pc, "unique", counted_unique)
    dates, symbols = matrix_module._collect_parquet_axes(
        dataset, matrix_module._matrix_filter_expression(first, first + timedelta(days=8), None),
        batch_size=1,
    )
    assert dates == [first + timedelta(days=offset) for offset in range(9)]
    assert symbols == ["000001.SZ"]
    assert calls == [8, 8, 1, 1]


def test_collect_parquet_axes_cancels_before_processing_partial_group(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.dataset as pads

    day = date(2024, 2, 1)
    part = tmp_path / f"date={day}" / "part.parquet"
    part.parent.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ"], "date": [day]}).write_parquet(part)
    dataset = pads.dataset(
        str(tmp_path), format="parquet",
        partitioning=pads.partitioning(pa.schema([("date", pa.date32())]), flavor="hive"),
    )
    cancelled = threading.Event()
    original = matrix_module._raise_if_matrix_cancelled
    calls = 0

    def cancel_after_first_batch(event):
        nonlocal calls
        calls += 1
        if calls == 2:
            cancelled.set()
        original(event)

    monkeypatch.setattr(matrix_module, "_raise_if_matrix_cancelled", cancel_after_first_batch)
    with pytest.raises(matrix_module.MatrixPrewarmCancelledError):
        matrix_module._collect_parquet_axes(
            dataset, matrix_module._matrix_filter_expression(day, day, None),
            batch_size=1, cancel_event=cancelled,
        )


def test_matrix_cold_build_reports_axis_scan_breakdown(tmp_path, caplog):
    root = tmp_path / "kline_daily_enriched"
    day = date(2024, 2, 1)
    partition = root / f"date={day}"
    partition.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"], "date": [day, day],
        "open": [10.0, 11.0], "high": [10.0, 11.0],
        "low": [10.0, 11.0], "close": [10.0, 11.0],
        "volume": [1000.0, 1000.0],
    }).write_parquet(partition / "part.parquet")

    with caplog.at_level(logging.INFO, logger=matrix_module.__name__):
        market = _load_matrix(
            root, day, day, field_columns=set(), cache_root=tmp_path / "cache",
        )

    assert market.symbols == ("000001.SZ", "600000.SH")
    assert market.timestamp_labels == ("2024-02-01",)
    assert any("matrix axes scan" in record.message and "read_ms=" in record.message
               and "unique_ms=" in record.message for record in caplog.records)


def test_covering_matrix_cache_reuses_wider_dates_and_fields(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    days = [date(2024, 1, 2) + timedelta(days=offset) for offset in range(4)]
    rows = []
    for current in days:
        partition = market_root / f"date={current.isoformat()}"
        partition.mkdir(parents=True)
        for asset_id, symbol in enumerate(("000001.SZ", "600000.SH")):
            close = 10.0 + asset_id + (current - days[0]).days
            rows.append({
                "symbol": symbol,
                "date": current,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1_000.0,
                "amount": close * 100_000.0,
                "raw_close": close,
            })
        pl.DataFrame([row for row in rows if row["date"] == current]).write_parquet(
            partition / "part.parquet"
        )
    instruments = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "name": ["A", "B"],
    })
    cache_root = tmp_path / "matrix_cache"
    broad = _load_matrix(
        market_root,
        days[0],
        days[-1],
        field_columns={"amount", "raw_close"},
        instruments=instruments,
        cache_root=cache_root,
    )
    narrow = _load_matrix(
        market_root,
        days[1],
        days[2],
        field_columns={"raw_close"},
        instruments=instruments,
        cache_root=cache_root,
    )

    assert broad.cache_status == "built"
    assert narrow.cache_status == "covering"
    assert narrow.cache_path == broad.cache_path
    assert narrow.timestamp_labels == tuple(value.isoformat() for value in days[1:3])
    assert set(narrow.fields) == {"raw_close"}
    assert isinstance(narrow.close, np.memmap)
    assert not narrow.close.flags.writeable
    assert len(list(cache_root.glob("v*-*"))) == 1


def test_covering_cache_ignores_outside_slice_change_but_invalidates_inside(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    days = [date(2024, 2, 1) + timedelta(days=offset) for offset in range(4)]
    for offset, current in enumerate(days):
        partition = market_root / f"date={current.isoformat()}"
        partition.mkdir(parents=True)
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [current],
            "open": [10.0 + offset],
            "high": [10.0 + offset],
            "low": [10.0 + offset],
            "close": [10.0 + offset],
            "volume": [1_000.0],
        }).write_parquet(partition / "part.parquet")
    instruments = pl.DataFrame({"symbol": ["000001.SZ"], "name": ["A"]})
    cache_root = tmp_path / "matrix_cache"
    _load_matrix(
        market_root,
        days[0],
        days[-1],
        field_columns=set(),
        instruments=instruments,
        cache_root=cache_root,
    )

    outside_path = market_root / f"date={days[-1].isoformat()}" / "part.parquet"
    pl.read_parquet(outside_path).with_columns(pl.lit(99.0).alias("close")).write_parquet(
        outside_path
    )
    outside = _load_matrix(
        market_root,
        days[1],
        days[2],
        field_columns=set(),
        instruments=instruments,
        cache_root=cache_root,
    )
    assert outside.cache_status == "covering"

    inside_path = market_root / f"date={days[2].isoformat()}" / "part.parquet"
    pl.read_parquet(inside_path).with_columns(pl.lit(77.0).alias("close")).write_parquet(
        inside_path
    )
    inside = _load_matrix(
        market_root,
        days[1],
        days[2],
        field_columns=set(),
        instruments=instruments,
        cache_root=cache_root,
    )
    assert inside.cache_status == "built"
    assert inside.close[-1, 0] == pytest.approx(77.0)


def test_matrix_cache_can_be_disabled(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    current = date(2024, 3, 1)
    partition = market_root / f"date={current.isoformat()}"
    partition.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [current],
        "open": [10.0],
        "high": [10.0],
        "low": [10.0],
        "close": [10.0],
        "volume": [1_000.0],
    }).write_parquet(partition / "part.parquet")

    market = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=None,
    )
    assert market.cache_status == "disabled"
    assert not isinstance(market.close, np.memmap)


def test_matrix_cache_cancellation_removes_staging_output(tmp_path, monkeypatch):
    market_root = tmp_path / "kline_daily_enriched"
    current = date(2024, 3, 2)
    partition = market_root / f"date={current.isoformat()}"
    partition.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [current],
        "open": [10.0],
        "high": [10.0],
        "low": [10.0],
        "close": [10.0],
        "volume": [1_000.0],
    }).write_parquet(partition / "part.parquet")
    cache_root = tmp_path / "matrix_cache"
    cancel_event = threading.Event()
    original_scan = matrix_module._scan_matrix_values

    def cancel_after_scan(*args, **kwargs):
        original_scan(*args, **kwargs)
        cancel_event.set()

    monkeypatch.setattr(matrix_module, "_scan_matrix_values", cancel_after_scan)

    with pytest.raises(
        matrix_module.MatrixPrewarmCancelledError,
        match="prewarm cancelled",
    ):
        _load_matrix(
            market_root,
            current,
            current,
            field_columns=set(),
            cache_root=cache_root,
            cancel_event=cancel_event,
        )

    assert list(cache_root.glob("v*-*")) == []
    assert list(cache_root.glob(".*.tmp")) == []


def test_matrix_cache_can_be_cancelled_before_scan(tmp_path):
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(matrix_module.MatrixPrewarmCancelledError):
        _load_matrix(
            tmp_path / "kline_daily_enriched",
            date(2024, 3, 1),
            date(2024, 3, 1),
            field_columns=set(),
            cancel_event=cancel_event,
        )


def test_matrix_cache_prunes_by_bytes_and_leaves_no_staging_directory(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    current = date(2024, 3, 4)
    partition = market_root / f"date={current.isoformat()}"
    partition.mkdir(parents=True)
    path = partition / "part.parquet"

    def write_close(value: float) -> None:
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [current],
            "open": [value],
            "high": [value],
            "low": [value],
            "close": [value],
            "volume": [1_000.0],
        }).write_parquet(path)

    cache_root = tmp_path / "matrix_cache"
    write_close(10.0)
    first = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=cache_root,
        cache_max_bytes=1,
    )
    write_close(11.0)
    second = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=cache_root,
        cache_max_bytes=1,
    )

    assert first.cache_path != second.cache_path
    del first
    gc.collect()
    assert second.close[0, 0] == pytest.approx(11.0)
    assert len(list(cache_root.glob("v*-*"))) == 1
    assert list(cache_root.glob(".*.tmp")) == []
    assert len(list(cache_root.glob(".axes-v1-*.json"))) == 1


def test_managed_source_generation_skips_file_walk_and_invalidates_explicitly(tmp_path):
    market_root = tmp_path / "kline_daily_enriched"
    current = date(2024, 3, 5)
    partition = market_root / f"date={current.isoformat()}"
    partition.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [current],
        "open": [10.0],
        "high": [10.0],
        "low": [10.0],
        "close": [10.0],
        "volume": [1_000.0],
    }).write_parquet(partition / "part.parquet")
    cache_root = tmp_path / "matrix_cache"

    first = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=cache_root,
        source_generation="generation-a",
    )
    repeated = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=cache_root,
        source_generation="generation-a",
    )
    changed = _load_matrix(
        market_root,
        current,
        current,
        field_columns=set(),
        cache_root=cache_root,
        source_generation="generation-b",
    )

    assert first.cache_status == "built"
    assert repeated.cache_status == "exact"
    assert repeated.cache_path == first.cache_path
    assert changed.cache_status == "built"
    assert changed.cache_path != first.cache_path
    del first, repeated
    gc.collect()
    assert len(list(cache_root.glob("v*-*"))) == 1


def test_registered_builtin_matrix_strategies_share_one_cache_profile():
    engine = StrategyEngine(
        strategy_dirs=[REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies"]
    )
    profile = build_matrix_cache_profile(engine, "stock")
    strategies = tuple(
        s for s in engine.strategy_definitions()
        if s.execution_backend != "minute_filter"
    )

    # 25 个 matrix 策略夹具 + 首板事件链 Provider 提供的 2 个研究策略
    assert len(strategies) == 27
    assert all(strategy.execution_backend == "matrix_native" for strategy in strategies)
    assert profile.warmup_bars > 0
    assert profile.forward_bars == max(int(strategy.max_hold_days or 0) for strategy in strategies)
    assert {"open", "high", "low", "close", "volume"}.issubset(profile.field_columns)


def test_chunked_matrix_score_matches_previous_full_matrix_formula():
    row_count = 4
    asset_count = 600
    symbols = [f"{asset_id:06d}.SZ" for asset_id in range(asset_count)]
    rows = []
    rng = np.random.default_rng(20260715)
    for time_id in range(row_count):
        for asset_id, symbol in enumerate(symbols):
            rows.append({
                "symbol": symbol,
                "date": date(2024, 1, 1) + timedelta(days=time_id),
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1_000.0,
                "feature_a": float(rng.normal()),
                "feature_b": float((asset_id % 7) - 3),
            })
    market = build_market_data_matrix(
        pl.DataFrame(rows),
        field_columns={"feature_a", "feature_b"},
    )
    universe = rng.random(market.shape) > 0.2
    weights = {"feature_a": 0.75, "feature_b": 0.25}

    expected = np.zeros(market.shape, dtype=np.float32)
    all_finite = universe.copy()
    total_weight = sum(weights.values())
    for name, weight in weights.items():
        values = market.field(name)
        finite = universe & np.isfinite(values)
        all_finite &= np.isfinite(values)
        row_min = np.min(np.where(finite, values, np.inf), axis=1)
        row_max = np.max(np.where(finite, values, -np.inf), axis=1)
        row_range = row_max - row_min
        normalized = np.zeros(market.shape, dtype=np.float32)
        varying = finite & np.isfinite(row_range[:, None]) & (row_range[:, None] > 0)
        equal = finite & ~varying
        np.divide(
            values - row_min[:, None],
            row_range[:, None],
            out=normalized,
            where=varying,
        )
        normalized[equal] = np.float32(0.5)
        expected += normalized * np.float32(weight / total_weight)
    expected *= np.float32(100.0)
    expected[~universe | ~all_finite] = 0.0

    actual = build_matrix_score(
        market,
        universe,
        weights,
        "score",
        True,
        fallback=np.zeros(market.shape, dtype=np.float32),
    )
    np.testing.assert_array_equal(actual, expected)

    inverted = build_matrix_score(
        market,
        universe,
        weights,
        "score",
        True,
        fallback=np.zeros(market.shape, dtype=np.float32),
        directions={"feature_a": "low", "feature_b": "low"},
    )
    np.testing.assert_allclose(
        inverted[universe],
        np.float32(100.0) - expected[universe],
        rtol=1e-6,
        atol=1e-6,
    )


def test_signal_slice_is_zero_copy_and_masking_only_allocates_final_flags():
    entry = np.ones((5, 2), dtype=np.uint8)
    codes = np.arange(10, dtype=np.int16).reshape(5, 2)
    score = np.arange(10, dtype=np.float32).reshape(5, 2)
    signals = make_signal_matrix(
        (5, 2),
        entry=entry,
        exit=entry,
        score=score,
        entry_signal_code=codes,
        exit_signal_code=codes,
    )
    sliced = slice_signal_matrix(signals, 1, 4)
    assert np.shares_memory(sliced.entry, signals.entry)
    assert np.shares_memory(sliced.score, signals.score)

    masked = apply_time_masks(
        sliced,
        np.array([True, False, True]),
        np.array([False, True, True]),
    )
    assert np.shares_memory(masked.score, signals.score)
    assert masked.entry.tolist() == [[1, 1], [0, 0], [1, 1]]
    assert masked.exit.tolist() == [[0, 0], [1, 1], [1, 1]]
    assert masked.entry_signal_code[1].tolist() == [-1, -1]
    assert masked.exit_signal_code[0].tolist() == [-1, -1]
    assert not masked.entry.flags.writeable
    assert signals.entry.tolist() == [[1, 1]] * 5


def test_matrix_pipeline_applies_basic_filter_and_candidate_scoring():
    panel = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "name": ["A", "B"],
        "date": [date(2024, 1, 1)] * 2,
        "open": [10.0, 20.0],
        "high": [10.0, 20.0],
        "low": [10.0, 20.0],
        "close": [10.0, 20.0],
        "volume": [100.0, 100.0],
        "amount": [50.0, 500.0],
    })
    market = build_market_data_matrix(panel, field_columns={"amount"})

    class AllEntries:
        def required_fields(self):
            return frozenset({"close"})

        def required_warmup_bars(self, params):
            return 1

        def compute_signals(self, market, params):
            return make_signal_matrix(market.shape, entry=np.ones(market.shape, dtype=np.uint8))

    signals = MatrixStrategyPipeline().run(
        AllEntries(),
        market,
        {},
        MatrixPipelineConfig(
            basic_filter={"enabled": True, "amount_min": 100.0},
            scoring={"close": 1.0},
            order_by="score",
            descending=True,
        ),
    )

    assert signals.entry.tolist() == [[0, 1]]
    assert signals.score.tolist() == [[0.0, 50.0]]


def test_signal_matrix_validation_rejects_mutable_strategy_output():
    signals = make_signal_matrix((2, 1))
    mutable_entry = signals.entry.copy()
    invalid = type(signals)(
        entry=mutable_entry,
        exit=signals.exit,
        score=signals.score,
        entry_signal_code=signals.entry_signal_code,
        exit_signal_code=signals.exit_signal_code,
    )
    with pytest.raises(ValueError, match="read-only"):
        validate_signal_matrix(invalid, (2, 1))


def test_matrix_pipeline_applies_asset_pool_before_cross_sectional_scoring():
    panel = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "name": ["A", "B"],
        "date": [date(2024, 1, 1)] * 2,
        "open": [10.0, 20.0],
        "high": [10.0, 20.0],
        "low": [10.0, 20.0],
        "close": [10.0, 20.0],
        "volume": [100.0, 100.0],
    })
    market = build_market_data_matrix(panel)

    class AllEntries:
        def required_fields(self):
            return frozenset({"close"})

        def required_warmup_bars(self, params):
            return 1

        def compute_signals(self, market, params):
            return make_signal_matrix(market.shape, entry=np.ones(market.shape, dtype=np.uint8))

    signals = MatrixStrategyPipeline().run(
        AllEntries(),
        market,
        {},
        MatrixPipelineConfig(
            basic_filter={"enabled": False},
            scoring={"close": 1.0},
            order_by="score",
            descending=True,
            asset_mask=np.array([False, True]),
        ),
    )

    assert signals.entry.tolist() == [[0, 1]]
    assert signals.score.tolist() == [[0.0, 50.0]]


def test_realtime_market_matrix_overwrites_last_row_and_appends_new_bar():
    panel = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"] * 2,
        "name": ["A", "B"] * 2,
        "date": [date(2024, 1, 1)] * 2 + [date(2024, 1, 2)] * 2,
        "open": [10.0, 20.0, 10.5, 20.5],
        "high": [10.2, 20.2, 10.7, 20.7],
        "low": [9.8, 19.8, 10.3, 20.3],
        "close": [10.1, 20.1, 10.6, 20.6],
        "volume": [1_000.0, 2_000.0, 1_100.0, 2_100.0],
        "amount": [10_100.0, 40_200.0, 11_660.0, 43_260.0],
    })
    buffer = RealtimeMarketDataMatrix(panel, field_columns={"amount"})

    same_bar = panel.filter(pl.col("date") == date(2024, 1, 2)).with_columns(
        (pl.col("close") + 5.0).alias("close")
    )
    buffer.update(same_bar)
    snapshot = buffer.snapshot()
    assert snapshot.shape == (2, 2)
    assert snapshot.close[-1].tolist() == pytest.approx(same_bar.sort("symbol")["close"].to_list())
    assert buffer.build_count == 1
    assert buffer.update_count == 1
    assert not snapshot.close.flags.writeable

    next_bar = same_bar.with_columns(pl.lit(date(2024, 1, 3)).alias("date"))
    buffer.update(next_bar)
    assert buffer.snapshot().shape == (3, 2)
    assert buffer.build_count == 1
    assert buffer.update_count == 2


def test_strategy_engine_runs_matrix_strategy_without_legacy_filter():
    start = date(2024, 1, 1)
    rows = []
    for offset in range(65):
        values = (
            ("000001.SZ", 10.0 + offset * 0.05),
            ("600000.SH", 20.0 + offset * 0.03),
        )
        for symbol, close in values:
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": start + timedelta(days=offset),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000.0,
                "amount": 100_000_000.0,
                "total_shares": 1_000_000_000.0,
                "float_shares": 800_000_000.0,
            })
    history = pl.DataFrame(rows)
    target = start + timedelta(days=64)
    engine = StrategyEngine(
        strategy_dirs=[REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies"],
    )
    strategy = engine.get("macd_golden")
    assert strategy.filter_fn is None

    result = engine.run(
        "macd_golden",
        StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=target,
            current=history.filter(pl.col("date") == target),
            history=history,
        ),
        pool=["600000.SH"],
        params={"require_macd_golden": False, "use_volume_filter": False},
        overrides={"basic_filter": {"enabled": False}},
    )

    assert [row["symbol"] for row in result.rows] == ["600000.SH"]
    assert result.total == 1


def test_strategy_engine_run_all_builds_one_shared_matrix():
    start = date(2024, 1, 1)
    rows = []
    for offset in range(65):
        close = 10.0 + offset * 0.05
        rows.append({
            "symbol": "000001.SZ",
            "name": "A",
            "date": start + timedelta(days=offset),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
            "amount": 100_000_000.0,
            "total_shares": 1_000_000_000.0,
            "float_shares": 800_000_000.0,
        })
    history = pl.DataFrame(rows)
    target = start + timedelta(days=64)
    engine = StrategyEngine(
        strategy_dirs=[REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies"],
    )
    original = engine.get("macd_golden")
    engine._strategies["macd_copy"] = replace(
        original,
        meta={**original.meta, "id": "macd_copy"},
    )
    params = {"require_macd_golden": False, "use_volume_filter": False}
    overrides = {"basic_filter": {"enabled": False}}

    with patch(
        "app.backtest.matrix.build_market_data_matrix",
        wraps=matrix_module.build_market_data_matrix,
    ) as build:
        results = engine.run_all(
            StrategyDataContext(
                asset_type="stock",
                timeframe="1d",
                as_of=target,
                current=history.filter(pl.col("date") == target),
                history=history,
            ),
            strategy_ids=["macd_golden", "macd_copy"],
            params_map={"macd_golden": params, "macd_copy": params},
            overrides_map={"macd_golden": overrides, "macd_copy": overrides},
        )

    assert build.call_count == 1
    assert results["macd_golden"].total == 1
    assert results["macd_copy"].total == 1
