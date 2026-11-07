"""test_matrix_strategy.py 第二版修法：把「frame 路径包 / alias」按能力探测排除。

第一版把 `in_universe` 写死成一个常量；实测目录里还有 B0 的单侧件与 alias（sd20、
prior_*、vol60、ma120、ma200）以及 E4 的 month_end / week_end 同样没有矩阵实现 ——
写死名单会随包增加继续红。改为询问 provider 是否覆写矩阵钩子（能力探测），
包一旦补上矩阵实现，这些 id 自动回到逐值对比集。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("tests/backtest/test_matrix_strategy.py")

EDITS: list[tuple[str, str, str]] = []

EDITS.append((
    "M1-helper",
    '''#: 需要外生状态（frame/provider 路径）的因子: 合成面板不可算, 不参与逐值对比。
STATEFUL_FACTOR_IDS = frozenset({"in_universe"})''',
    '''def _matrix_path_unsupported(names: set[str]) -> set[str]:
    """`matrix_feature` 没有实现的 id: alias 与「只有 frame 路径」的 provider 因子。

    * alias（§7.15.1 第 1–8 行）在矩阵侧没有分支，只有 canonical 有；DSL 因子路径会
      解析到 canonical —— 两条路径的口径本就不同，不参与逐值对比。
    * provider 未覆写 `FactorProvider.materialize_matrix` /
      `materialize_matrix_field` 时只有 frame 路径（B0 / E3 / E4 三包均如此），
      `matrix_feature` 走到 `_compute_matrix_feature` 末尾必抛 unsupported。

    这是**能力探测**而不是白名单：某个包补上矩阵实现后，这些 id 会自动回到对比集。
    """
    from app.extensions.factors import FactorProvider, factor_provider_for
    from app.factors.registry import get_factor

    unsupported: set[str] = set()
    for name in names:
        spec = get_factor(name)
        if spec is not None and spec.alias_of is not None:
            unsupported.add(name)
            continue
        provider = factor_provider_for(name)
        if provider is None:
            continue
        if (
            type(provider).materialize_matrix is FactorProvider.materialize_matrix
            and type(provider).materialize_matrix_field is FactorProvider.materialize_matrix_field
        ):
            unsupported.add(name)
    return unsupported''',
))

EDITS.append((
    "M2-names",
    '''    # 联动因子由 linkage store 物化, 不能从这段无外部状态的合成面板推导。
    # `in_universe`（E3, research_universe_pack）走 frame/provider 路径, 需要
    # `raw_close` 与 as-of 的 `st_history` 数据集; 该包明确「矩阵侧列为 B0b 另批,
    # 本批不动矩阵路径」, 两条路径在这段合成面板上都不可算 → 同样排除出逐值对比。
    factor_names = (
        {item["id"] for item in FACTOR_COLUMNS}
        - LINKAGE_FACTOR_IDS
        - STATEFUL_FACTOR_IDS
    )''',
    '''    # 联动因子由 linkage store 物化, 不能从这段无外部状态的合成面板推导; 其余
    # 「矩阵路径没有实现」的 id 由 _matrix_path_unsupported 按能力探测排除
    # （alias + 只有 frame 路径的 provider 包）。
    catalog_ids = {item["id"] for item in FACTOR_COLUMNS}
    factor_names = catalog_ids - LINKAGE_FACTOR_IDS - _matrix_path_unsupported(catalog_ids)''',
))


def main() -> int:
    raw = TARGET.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    for name, old, new in EDITS:
        count = text.count(old)
        if count != 1:
            print(f"[FAIL] {name}: matched {count}", flush=True)
            return 1
        text = text.replace(old, new)
        print(f"[ok] {name}", flush=True)
    TARGET.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    print(f"[done] {TARGET} {TARGET.stat().st_size} B", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
