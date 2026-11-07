"""dsl.py B2 改动 2/2: E017 语义检查 + 截面算子 codegen + 截面族扩展。"""

NEW_HELPER = '''

def _is_mask_node(node: dict) -> bool:
    """静态判定一个 AST 节点是否是合法掩码 (契约 §3.2.1)。

    合法: 比较/逻辑表达式; 或带 MASK_FACTOR_TAG 的已注册因子 (如 in_universe)。
    非法: 裸数值列 / 数字字面量 / 其它函数 (保守拒绝, 不做类型推断)。
    """
    kind = node["kind"]
    if kind == "col":
        spec = get_factor(node["value"])
        return spec is not None and MASK_FACTOR_TAG in tuple(spec.tags)
    if kind == "unary":
        return _is_mask_node(node["children"][0])
    if kind == "bin":
        return node["value"] in _CMP_METHOD or node["value"] in ("and", "or")
    return False

'''

E017_CHECK = '''    if "lo" in constants and "hi" in constants and constants["lo"] > constants["hi"]:
        errors.append(DslError("E003", "clamp 的 lo 不能大于 hi", offset=node["offset"]))
    mask_index = XS_MASK_ARG_INDEX.get(name)
    if mask_index is not None and mask_index < len(args) and not _is_mask_node(args[mask_index]):
        errors.append(DslError(
            "E017",
            f"{name} 的第 {mask_index + 1} 参数必须是布尔掩码: 传比较/逻辑表达式,"
            f" 或带 '{MASK_FACTOR_TAG}' 标签的已注册掩码因子 (如 in_universe)",
            offset=args[mask_index]["offset"],
            detail={"operator": name, "arg_index": mask_index},
        ))
    return constants'''

XS_BRANCH = '''    if name in XS_OPERATORS or name == "xs_rank_market":
        inner, inner_window, inner_bool = _compile_node(children[0])
        if inner is None:
            return None, False, False
        if inner_window:
            inner = inner.over("symbol")
        if inner_bool:
            inner = inner.cast(pl.Float64)
        if name == "xs_rank_market":
            # 全样本平均名次 / 全样本非空家数; 与现有 rank 同式 (XS-B1 逐位相同)
            market_count = inner.count().over("date")
            return inner.rank(method="average").over("date") / market_count, False, False
        mask_expr, mask_window, mask_bool = _compile_node(children[1])
        if mask_expr is None:
            return None, False, False
        if mask_window:
            mask_expr = mask_expr.over("symbol")
        if not mask_bool:
            # 掩码因子值域 {1.0, 0.0, null} -> Boolean; null 保持 null (G3 三态)
            mask_expr = mask_expr.cast(pl.Boolean)
        if name == "xs_rank_pool":
            # 分子分母同一批样本: 池内非空 (契约 §3.2.1)
            member = pl.when(mask_expr).then(inner).otherwise(None)
            pool_count = member.count().over("date")
            return _safe_div(
                member.rank(method="average").over("date"),
                pool_count.cast(pl.Float64),
            ), False, False
        if name == "xs_rank_pct":
            # 缺陷形态 (仅差异证明): 分子全样本名次, 分母池内家数 (含 x 为空者)
            global_rank = inner.rank(method="average").over("date")
            pool_size = (
                pl.when(mask_expr)
                .then(pl.lit(1, dtype=pl.Int32))
                .otherwise(pl.lit(0, dtype=pl.Int32))
                .sum()
                .over("date")
            )
            return pl.when(mask_expr & inner.is_not_null()).then(
                _safe_div(global_rank, pool_size.cast(pl.Float64))
            ).otherwise(None), False, False
        # xs_mean: 当日所有行同值 (含池外行); 池内无有效样本 -> null
        return pl.when(mask_expr).then(inner).otherwise(None).mean().over("date"), False, False

    if name == "if_else":'''

OLD_CROSS_FIND = '''        if node["kind"] == "call" and node["value"] in CROSS_OPERATORS:
            cross_sectional = True'''
NEW_CROSS_FIND = '''        if node["kind"] == "call" and node["value"] in XS_ALL_OPERATORS:
            cross_sectional = True'''

OLD_CONTAINS = '''        if node["kind"] == "call" and node["value"] in CROSS_OPERATORS:
            return True
        return any(_contains_cross(child) for child in node["children"])'''
NEW_CONTAINS = '''        if node["kind"] == "call" and node["value"] in XS_ALL_OPERATORS:
            return True
        return any(_contains_cross(child) for child in node["children"])'''

OLD_REJECT_MSG = '''                        f"截面算子不能嵌在时序窗口内: {node['value']}(...) 的参数含 rank/zscore/winsorize",'''
NEW_REJECT_MSG = '''                        f"截面算子不能嵌在时序窗口内: {node['value']}(...) 的参数含 rank/zscore/winsorize/xs_*",'''

OLD_TEMP = '''        if current.get("kind") == "call" and current.get("value") in CROSS_OPERATORS:
            operand = current["children"][0]
            if _has_any_over(operand):
                alias = f"__tsfx_{len(temp_roots)}__"
                current["children"][0] = {"kind": "col", "value": alias, "children": [], "offset": operand["offset"]}
                temp_roots.append({"alias": alias, "root": copy.deepcopy(operand)})
                pending.append(temp_roots[-1]["root"])
                continue  # 操作数已替换为临时列, 不再下钻原子树
        pending.extend(current.get("children", []))'''
NEW_TEMP = '''        if current.get("kind") == "call" and current.get("value") in XS_ALL_OPERATORS:
            # 数据参数恒为 children[0]; xs_* 家族的掩码参数 (children[1]) 同样可能含窗口
            indexes = [0]
            if current["value"] in XS_MASK_ARG_INDEX:
                indexes.append(XS_MASK_ARG_INDEX[current["value"]])
            replaced = False
            for index in indexes:
                operand = current["children"][index]
                if _has_any_over(operand):
                    alias = f"__tsfx_{len(temp_roots)}__"
                    current["children"][index] = {"kind": "col", "value": alias, "children": [], "offset": operand["offset"]}
                    temp_roots.append({"alias": alias, "root": copy.deepcopy(operand)})
                    pending.append(temp_roots[-1]["root"])
                    replaced = True
            if replaced:
                continue  # 相关操作数已替换为临时列, 不再下钻该子树
        pending.extend(current.get("children", []))'''


def main(apply) -> None:
    apply(
        "backend/app/factors/dsl.py",
        [
            # 1) 新增 _is_mask_node 助手 (放在 _safe_div 之后、codegen 段落内)
            (
                "def _safe_div(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:",
                NEW_HELPER.lstrip("\n") + "\ndef _safe_div(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:",
            ),
            # 2) E017 语义检查
            (
                '''    if "lo" in constants and "hi" in constants and constants["lo"] > constants["hi"]:
        errors.append(DslError("E003", "clamp 的 lo 不能大于 hi", offset=node["offset"]))
    return constants''',
                E017_CHECK,
            ),
            # 3) xs_* codegen 分支
            ('    if name == "if_else":', XS_BRANCH),
            # 4) 截面族扩展 (4 处)
            (OLD_CROSS_FIND, NEW_CROSS_FIND),
            (OLD_CONTAINS, NEW_CONTAINS),
            (OLD_REJECT_MSG, NEW_REJECT_MSG),
            (OLD_TEMP, NEW_TEMP),
        ],
    )
