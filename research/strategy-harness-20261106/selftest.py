"""批量底座自检 — 不碰行情数据，纯函数与契约校验。

跑法：backend/.venv/Scripts/python.exe research/strategy-harness-20261106/selftest.py
退出码 0 = 全部通过。
"""

from __future__ import annotations

import itertools
import math
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.backtest.stats_v2 import (
    bh_fdr_qvalues,
    deflated_sharpe_psr,
    expected_max_sharpe,
)
from app.backtest.strategy import BacktestResultPolicy
from app.backtest.walkforward import generate_folds
from batch_harness import LIGHT_POLICY, load_spec, psr_and_p

CASES: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    CASES.append(name)
    print(f"ok   {name}")


def t_psr_matches_stats_v2() -> None:
    for sharpe in (-3.0, -0.5, 0.0, 0.3, 1.2, 4.0):
        for n_obs in (5, 60, 250, 1200):
            for skew, kurt in ((0.0, 3.0), (-0.8, 5.5), (1.4, 9.0)):
                for em in (0.0, 0.5, 1.5):
                    z, psr, p_one = psr_and_p(sharpe, n_obs, skew, kurt, em)
                    ref = deflated_sharpe_psr(sharpe, n_obs, skew, kurt, em)
                    assert ref is not None, (sharpe, n_obs)
                    assert abs(psr - ref) < 1e-9, (psr, ref)
                    assert abs(psr + p_one - 1.0) < 1e-12, (psr, p_one)
                    expected_z_sign = math.copysign(1.0, sharpe - em)
                    assert math.copysign(1.0, z) == expected_z_sign


def t_psr_degenerate() -> None:
    assert psr_and_p(0.5, 3, 0.0, 3.0, 0.0) == (None, None, None)
    assert psr_and_p(float("nan"), 250, 0.0, 3.0, 0.0) == (None, None, None)


def t_em_monotonic() -> None:
    ratios = [expected_max_sharpe(n, 0.25) for n in (2, 5, 20, 100, 1000)]
    assert all(b > a for a, b in itertools.pairwise(ratios)), ratios
    assert expected_max_sharpe(1, 0.25) == 0.0
    assert expected_max_sharpe(10, 0.0) == 0.0


def t_bh_fdr() -> None:
    q = bh_fdr_qvalues([0.001, 0.02, 0.9, None])
    assert q[3] is None
    assert q[0] <= q[1] <= q[2] <= 1.0
    assert q[0] == 0.003  # m=3, rank1: 0.001*3/1
    assert bh_fdr_qvalues([None, None]) == [None, None]


def t_folds_on_trading_days() -> None:
    days: list[date] = []
    cursor = date(2024, 1, 1)
    while len(days) < 400:
        if cursor.weekday() < 5:  # 只保留工作日，制造"缺失日"效果
            days.append(cursor)
        cursor += timedelta(days=1)
    folds = generate_folds(days[0], days[-1], 120, 40, 40, trading_days=days)
    day_set = set(days)
    for fold in folds:
        assert fold.test_start > fold.train_end, "训练/测试区间必须严格错开"
        for edge in (fold.train_start, fold.train_end, fold.test_start, fold.test_end):
            assert edge in day_set, f"折边界 {edge} 不是交易日"
        assert fold.train_end - fold.train_start == timedelta(days=fold.train_end.toordinal() - fold.train_start.toordinal())
    # 自然日口径会落在周末之外的日子上：同一区间不给 trading_days 时边界不同
    natural = generate_folds(days[0], days[-1], 120, 40, 40)
    assert natural[0].train_end != folds[0].train_end, "两种口径不应产生相同边界"


def t_light_policy_trims() -> None:
    options = LIGHT_POLICY.simulation_options()
    assert options.include_curves is False
    assert options.include_trades is False
    assert options.include_per_symbol_stats is False
    assert options.include_monte_carlo is False
    assert options.include_return_distribution is False
    # 诊断字段必须留在 stats 里，否则 registry 无法证明共享装载生效
    selected = LIGHT_POLICY.select_stats({
        "sharpe": 1.0,
        "matrix_data_cache_hit": True,
        "matrix_data_cache_status": "covering",
        "shared_market_data": True,
        "return_distribution": [1, 2, 3],
        "mc_maxdd_p50": 0.1,
    })
    assert selected["matrix_data_cache_hit"] is True
    assert "return_distribution" in selected  # required_stats=None 时透传全部标量


def t_policy_required_stats() -> None:
    policy = BacktestResultPolicy.optimizer_trial("sharpe")
    assert "n_trades" in policy.required_stats
    assert policy.simulation_options().include_curves is False


def t_spec_validation(tmp_dir: Path) -> None:
    bad = tmp_dir / "bad.json"
    bad.write_text(
        '{"strategies":[{"id":"x"}],"cost_tiers":[{"id":"a"}],"start":"2025-01-01",'
        '"end":"2025-06-30","walkforward":{"train_days":10,"test_days":20,"step_days":10}}',
        encoding="utf-8",
    )
    try:
        load_spec(bad)
    except ValueError as exc:
        assert "step_days" in str(exc)
    else:
        raise AssertionError("非法 step_days 未被拒绝")


def main() -> int:
    print("批量底座自检")
    check("PSR 与 stats_v2 逐点一致，单侧 p 与 PSR 互补", t_psr_matches_stats_v2)
    check("PSR 退化输入返回 None", t_psr_degenerate)
    check("EM 随 n_trials 单调上升", t_em_monotonic)
    check("BH-FDR q 值单调、None 透传", t_bh_fdr)
    check("折边界只落在交易日且 IS/OOS 不重叠", t_folds_on_trading_days)
    check("轻量结果契约裁掉曲线/逐笔/分布", t_light_policy_trims)
    check("optimizer_trial 保留 n_trades", t_policy_required_stats)
    tmp_dir = Path(__file__).resolve().parent / ".selftest_tmp"
    tmp_dir.mkdir(exist_ok=True)
    try:
        check("规格校验拒绝 step_days < test_days", lambda: t_spec_validation(tmp_dir))
    finally:
        for item in tmp_dir.glob("*"):
            item.unlink()
        tmp_dir.rmdir()
    print(f"\n{len(CASES)} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
