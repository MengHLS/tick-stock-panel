"""任务 2 的三处最小修法（一次性脚本）。

1) tests/test_auction_factor_pack.py：`_clean_registry` 原来把 kind∈{custom,composite}
   的动态因子**清掉且不恢复**，provider 装载包（B0 14 + in_universe + 竞价包）同样是
   kind=custom → 全量跑时被吞掉，`_PROVIDERS_READY` 已是 True 不会重新发现，之后
   `all_factors()` 恒为 93（应为 110）。修法：fixture 入口快照整表，teardown 恢复快照。
2) tests/backtest/test_matrix_strategy.py：`in_universe`（E3）走 frame/provider 路径且
   需要 raw_close + as-of st_history 数据集，本段合成面板与矩阵路径都没有 → 与联动因子
   同样排除出「合成面板逐值对比」的作用域（注释写明理由）。
3) app/api/backtest.py：`FactorBatchRequest.factor_names.max_length=96` 是目录 86 时的
   常量；目录已 110 → 「整份目录可提交」这条既有断言被卡的其实是生产侧陈旧上限，
   不是测试过宽。改 96 → 200（保留兜底上限，留余量）。

跑法：在 backend/ 下 `python ../research/gate-fa43-20261108/patch_task2.py`（幂等性：每处
要求精确匹配 1 次）。
"""
from __future__ import annotations

import sys
from pathlib import Path

EDITS: list[tuple[str, Path, str, str]] = []

EDITS.append((
    "A-auction-fixture",
    Path("tests/test_auction_factor_pack.py"),
    '''@pytest.fixture(autouse=True)
def _clean_registry():
    from app.factors import registry

    def dynamic_ids():''',
    '''@pytest.fixture(autouse=True)
def _clean_registry():
    from app.factors import registry

    # 本文件只测竞价包自己的动态注册。**入口先快照整表**：provider 装载包的因子
    # （B0 14 个 + in_universe + 竞价包）同样是 kind=custom，属于进程级注册状态，
    # 而 `extensions.factors._PROVIDERS_READY` 在首次发现后即为 True，被清掉后
    # `all_factors()` 不会重新发现 —— 不恢复就会把 110 变成 93（全量跑 10 红）。
    saved_registry = dict(registry._REGISTRY)

    def dynamic_ids():''',
))

EDITS.append((
    "B-auction-restore",
    Path("tests/test_auction_factor_pack.py"),
    """    yield
    for key in dynamic_ids():
        registry._REGISTRY.pop(key, None)
    _load_all_cache.clear()""",
    """    yield
    for key in dynamic_ids():
        registry._REGISTRY.pop(key, None)
    # 恢复入口快照：只回滚本文件的增删，不把 provider 装载包留在被清空的状态。
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved_registry)
    _load_all_cache.clear()""",
))

EDITS.append((
    "C-matrix-in-universe",
    Path("tests/backtest/test_matrix_strategy.py"),
    '''    # 联动因子由 linkage store 物化, 不能从这段无外部状态的合成面板推导。
    factor_names = {item["id"] for item in FACTOR_COLUMNS} - LINKAGE_FACTOR_IDS''',
    '''    # 联动因子由 linkage store 物化, 不能从这段无外部状态的合成面板推导。
    # `in_universe`（E3, research_universe_pack）走 frame/provider 路径, 需要
    # `raw_close` 与 as-of 的 `st_history` 数据集; 该包明确「矩阵侧列为 B0b 另批,
    # 本批不动矩阵路径」, 两条路径在这段合成面板上都不可算 → 同样排除出逐值对比。
    factor_names = (
        {item["id"] for item in FACTOR_COLUMNS}
        - LINKAGE_FACTOR_IDS
        - STATEFUL_FACTOR_IDS
    )''',
))

EDITS.append((
    "D-matrix-constant",
    Path("tests/backtest/test_matrix_strategy.py"),
    """def _panel_with_missing_asset_bar() -> pl.DataFrame:""",
    '''#: 需要外生状态（frame/provider 路径）的因子: 合成面板不可算, 不参与逐值对比。
STATEFUL_FACTOR_IDS = frozenset({"in_universe"})


def _panel_with_missing_asset_bar() -> pl.DataFrame:''',
))

EDITS.append((
    "E-batch-cap",
    Path("app/api/backtest.py"),
    '''    factor_names: list[str] = Field(..., min_length=1, max_length=96)  # 目录 86 + 自定义余量''',
    '''    factor_names: list[str] = Field(..., min_length=1, max_length=200)  # 目录 110 + 自定义余量''',
))


def main() -> int:
    # 读入 → 统一 LF → 逐处替换 → 原 EOL 写回
    state: dict[Path, str] = {}
    crlf: dict[Path, bool] = {}
    for name, path, old, new in EDITS:
        if path not in state:
            raw = path.read_bytes().decode("utf-8")
            crlf[path] = "\r\n" in raw
            state[path] = raw.replace("\r\n", "\n")
        count = state[path].count(old)
        if count != 1:
            print(f"[FAIL] {name} ({path}): matched {count} times (want 1)", flush=True)
            return 1
        state[path] = state[path].replace(old, new)
        print(f"[ok] {name} ({path})", flush=True)
    for path, text in state.items():
        payload = text.replace("\n", "\r\n") if crlf[path] else text
        path.write_bytes(payload.encode("utf-8"))
        print(f"[done] {path} {path.stat().st_size} B", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
