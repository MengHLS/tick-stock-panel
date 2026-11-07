"""dsl.py 的 B2 改动: 新增 xs_rank_pool / xs_rank_market / xs_rank_pct / xs_mean + E017."""


def main(apply) -> None:
    apply(
        "backend/app/factors/dsl.py",
        [
            (
                "→ 依赖/预热推导 → Polars Expr。编译失败返回结构化错误 (E001-E016), 不抛裸异常。",
                "→ 依赖/预热推导 → Polars Expr。编译失败返回结构化错误 (E001-E017), 不抛裸异常。\n\n"
                "E017 (B2 新增, 契约 §3.2.1): 掩码参数不是布尔值。只有 xs_rank_pool /\n"
                "xs_rank_pct / xs_mean 的第 2 参数会返回它; 合法掩码 = 比较/逻辑表达式, 或\n"
                "带 \"mask\" 标签的已注册 0/1/null 掩码因子 (如 in_universe)。",
            ),
            (
                '    "rank": (1, ()),\n'
                '    "zscore": (1, ()),\n'
                '    "winsorize": (1, ("k",)),  # k 可省略, 默认 3',
                '    "rank": (1, ()),\n'
                '    "zscore": (1, ()),\n'
                '    "winsorize": (1, ("k",)),  # k 可省略, 默认 3\n'
                '    # 截面排名族 / 截面均值 (契约 §3 / §4): 第 2 参数恒为 mask (必填, 无默认值)\n'
                '    "xs_rank_pool": (2, ()),\n'
                '    "xs_rank_market": (1, ()),\n'
                '    "xs_rank_pct": (2, ()),\n'
                '    "xs_mean": (2, ()),',
            ),
            (
                'CROSS_OPERATORS = frozenset({"rank", "zscore", "winsorize"})',
                'CROSS_OPERATORS = frozenset({"rank", "zscore", "winsorize"})\n'
                "# 截面排名族 / 截面均值: 第 2 参数是掩码 (契约 §3.2.1 / §4.2);\n"
                "# 三者与 CROSS_OPERATORS 同属截面族 (cross_sectional=True, 不得嵌进时序窗口)。\n"
                'XS_OPERATORS = frozenset({"xs_rank_pool", "xs_rank_pct", "xs_mean"})\n'
                'XS_ALL_OPERATORS = frozenset({"rank", "zscore", "winsorize", "xs_rank_market", *XS_OPERATORS})\n'
                '# 掩码参数下标 (0-based); 只有这些算子做 E017 类型检查\n'
                'XS_MASK_ARG_INDEX = {"xs_rank_pool": 1, "xs_rank_pct": 1, "xs_mean": 1}\n'
                "# 掩码因子标记: 值域 {0.0, 1.0, null}, 需布尔视图 (契约 §2.2 输出表末行)。\n"
                "# 复用 FactorSpec.tags, 不新增注册表字段。\n"
                'MASK_FACTOR_TAG = "mask"',
            ),
        ],
    )
