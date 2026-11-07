"""F-A43–F-A47 + FS09 的 gate.py 补丁脚本（一次性；跑完即归档为证据）。

用法：在 backend/ 下 `python ../research/gate-fa43-20261108/patch_gate.py`
每个 hunk 要求精确匹配 1 次，任何一处不匹配即中止且不写盘。
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path("app/factors/gate.py")

EDITS: list[tuple[str, str, str]] = []

# E1 模块 docstring
EDITS.append((
    "E1-docstring",
    """* 只判能从盘上事实判定的码：FS01 / FS02 / FS03 / FS05 / FS06。判不出来的分支一律
  `NotImplementedError`，不静默放行（见 `check_ledger_consistency` 与 FS04 守卫）。""",
    """* 只判能从盘上事实判定的码：FS01 / FS02 / FS03 / FS05 / FS06。判不出来的分支一律
  抛 `GateError`（§7.17.4 C1/C3：出口唯一、FS06 fail-closed），不静默放行。
* 命名面（§7.17.2，v0.12）：`namespace` 由调用方声明 —— `"factor"`（缺省，等于今日
  行为）与 `"column"`（按 §7.8.3 第一行 base 处理）两面；域外取值 / Mapping 缺键
  → `FS09`（入参非法，§7.17.4 C4），不进 `blocked`。""",
))

# E2 常量
EDITS.append((
    "E2-namespaces",
    """#: `custom_factors/*.json` 的 status 取值（store.STATUSES 同源）。
STATUSES: tuple[str, ...] = ("draft", "active", "watch", "retired")""",
    """#: `custom_factors/*.json` 的 status 取值（store.STATUSES 同源）。
STATUSES: tuple[str, ...] = ("draft", "active", "watch", "retired")

#: §7.17.2 S5：命名面取值域（`column` 面按 §7.8.3 第一行 base 处理）。域外一律 FS09；
#: `base` / `virtual` 是 §7.8.3 的 **kind**，不是 namespace，传进来也按域外报错。
_NAMESPACES: tuple[str, ...] = ("factor", "column")""",
))

# E3 GateError.report 允许 None（§7.17.6 ④）
EDITS.append((
    "E3-gateerror-report",
    """    def __init__(
        self,
        code: str,
        detail: dict,
        report: GateReport,
        entry: str | None = None,
    ) -> None:""",
    """    def __init__(
        self,
        code: str,
        detail: dict,
        report: GateReport | None,
        entry: str | None = None,
    ) -> None:""",
))

# E4 _judge 内 status 域外改 FS09
EDITS.append((
    "E4-judge-status",
    """        if status not in STATUSES:
            raise ValueError(f"status 非法: {status!r}（应为 {list(STATUSES)} 之一）")""",
    """        if status not in STATUSES:
            # §7.17.4 C4：status 域外 → FS09（不得抛 ValueError，C1 出口唯一）。
            raise _invalid_argument(
                "status", mode, f"status 非法: {status!r}（应为 {list(STATUSES)} 之一）"
            )""",
))

# E5 新增三个私有工具函数（插在 _judge 之前）
EDITS.append((
    "E5-helpers",
    '''@dataclass(frozen=True)
class _Verdict:
    codes: tuple[str, ...]
    non_active: bool
    retired: bool
    resolved: str | None
''',
    '''@dataclass(frozen=True)
class _Verdict:
    codes: tuple[str, ...]
    non_active: bool
    retired: bool
    resolved: str | None


def _invalid_argument(
    param: str,
    mode: str,
    message: str,
    entry: str | None = None,
) -> GateError:
    """§7.17.4 C4：入参非法 → `FS09`（`detail` 照 §7.16.4，**不加**附加键）。

    `submitted_id` 记违规**参数名**（`"namespace"` / `"mode"` / `"status"`）；
    `resolved_id` / `canonical_id` / `table_row` 为 `None`。返回异常对象而不是直接
    raise，便于调用处写 `raise ... from exc` 保留因果链。
    """
    return GateError(
        "FS09",
        _detail("FS09", mode, param, None, None, None, message),
        None,
        entry=entry,
    )


def _namespace_faces(
    namespace: str | Mapping[str, str],
    ordered_ids: list[str],
    mode: str,
    entry: str | None = None,
) -> dict[str, str]:
    """§7.17.2 S3/S5：把 `namespace` 摊成逐 id 的命名面，域外/缺键一律 FS09。

    * `str` 形态：整组同一面。
    * `Mapping` 形态：逐 id 取面，**缺键即报错**（漏一个「忘了声明的列」就等于继续
      误拦那 4 条）；多余键忽略（S3）。
    """
    if isinstance(namespace, str):
        if namespace not in _NAMESPACES:
            raise _invalid_argument(
                "namespace",
                mode,
                f"namespace 取值非法: {namespace!r}（只接受 {list(_NAMESPACES)}）",
                entry,
            )
        return dict.fromkeys(ordered_ids, namespace)
    if not isinstance(namespace, Mapping):
        raise _invalid_argument(
            "namespace",
            mode,
            f"namespace 必须是 {' / '.join(_NAMESPACES)} 之一或 Mapping[str, str]，"
            f"收到 {type(namespace).__name__}",
            entry,
        )
    faces: dict[str, str] = {}
    for factor_id in ordered_ids:
        if factor_id not in namespace:
            raise _invalid_argument(
                "namespace",
                mode,
                f"namespace Mapping 缺键（未声明该 id 的命名面）: {factor_id!r}",
                entry,
            )
        face = namespace[factor_id]
        if not isinstance(face, str) or face not in _NAMESPACES:
            raise _invalid_argument(
                "namespace",
                mode,
                f"namespace Mapping 的值非法（id={factor_id!r}）: {face!r}",
                entry,
            )
        faces[factor_id] = face
    return faces


def _column_verdict(fact: FactorFacts) -> _Verdict:
    """§7.17.2 S2/S4：列面 id 按 §7.8.3 第一行 base 处理；面外 id fail-closed 报 FS02。

    * S2：不判 status（无 FS01）、不判 alias（无 FS03/FS06）、不判 lang（无 FS05），
      `non_active` 不记，`resolved` 仍取 `fact.factor_id`。
    * S4：`namespace="column"` 且 id ∉ `_column_universe()` → **FS02**（不静默 allow、
      不退化成 FS01），堵住「把 draft 因子改名成列名来免检」。
    """
    if fact.factor_id not in _column_universe():
        return _Verdict(("FS02",), False, False, None)
    return _Verdict((), False, False, fact.factor_id)
''',
))

# E6 签名追加 keyword-only namespace（F-A43-1：既有 8 个参数名/次序/缺省值不动）
EDITS.append((
    "E6-signature",
    """    require_status: bool = True,
    shadow: bool = False,
    entry: str | None = None,
    facts: FactsSource | None = None,
) -> GateReport:""",
    """    require_status: bool = True,
    shadow: bool = False,
    entry: str | None = None,
    facts: FactsSource | None = None,
    namespace: str | Mapping[str, str] = "factor",
) -> GateReport:""",
))

# E6b 参数说明
EDITS.append((
    "E6b-paramdoc",
    """      * `shadow` / `entry`：CONTRACT-GAP 2 / 3。""",
    """      * `shadow` / `entry`：CONTRACT-GAP 2 / 3。
      * `namespace`：§7.17.2 的命名面，keyword-only，缺省 `"factor"` 即今日行为；
        `"column"` 把该 id 按 §7.8.3 第一行 base 处理（面闭合判据 `_column_universe()`），
        也接受 `Mapping[str, str]` 逐 id 声明；域外取值 / Mapping 缺键 → `FS09`。""",
))

# E7 mode 校验改 FS09
EDITS.append((
    "E7-mode",
    """    if mode not in MODES:
        raise ValueError(f"未知 mode: {mode!r}（只接受 {list(MODES)}）")

    ordered_ids = _normalise_ids(factor_ids)""",
    """    if not isinstance(mode, str) or mode not in MODES:
        # §7.17.4 C4：入参非法一律 FS09（GateError），不抛 ValueError（C1 出口唯一）。
        raise _invalid_argument(
            "mode", str(mode), f"未知 mode: {mode!r}（只接受 {list(MODES)}）", entry
        )

    ordered_ids = _normalise_ids(factor_ids)
    faces = _namespace_faces(namespace, ordered_ids, mode, entry)""",
))

# E8 循环体：列面短路 + 事实读取的 ValueError 兜底
EDITS.append((
    "E8-loop",
    """        for factor_id in ordered_ids:
            fact = source.facts(factor_id)
            verdict = _judge(
                fact,
                mode,
                allow_non_active=allow_non_active,
                allow_retired=allow_retired,
                require_status=require_status,
                facts=source,
            )""",
    """        for factor_id in ordered_ids:
            try:
                fact = source.facts(factor_id)
            except ValueError as exc:
                # 定义 JSON 的 status 域外（§7.17.4 C4）→ FS09，不让 ValueError 逃出去。
                raise _invalid_argument("status", mode, str(exc), entry) from exc
            if faces[factor_id] == "column":
                verdict = _column_verdict(fact)
            else:
                verdict = _judge(
                    fact,
                    mode,
                    allow_non_active=allow_non_active,
                    allow_retired=allow_retired,
                    require_status=require_status,
                    facts=source,
                )""",
))

# E9 check_ledger_consistency 改抛 GateError(FS06)（§7.17.4 C3 / C1）
EDITS.append((
    "E9-ledger",
    '''def check_ledger_consistency(*_args, **_kwargs) -> None:
    """§7.16.5：`alias_of` 必须与 §7.15.1 的 canonical 表一致，不一致报 FS06。

    这一支**判不出来**：§7.15.1 的 14 行表只存在于契约正文（markdown 表格），盘上
    没有机器可读的等价物，而 §7.16.5 明确「唯一权威、禁止二次登记」，本模块不能
    自己造一份副本当权威。按派发书「判不出来的必须 raise NotImplementedError」，
    这里显式抛出，绝不静默返回「一致」。
    """
    raise NotImplementedError(
        "FS06 的「台账未裁定 / 表与定义不一致」分支无法从盘上事实判定："
        "§7.15.1 的 14 行 canonical 表只存在于契约正文，盘上无机器可读副本，"
        "§7.16.5 又禁止二次登记；需架构师先裁定机器可读台账的路径与形状。"
    )''',
    '''def check_ledger_consistency(
    *_args,
    mode: str = "production",
    entry: str | None = None,
    **_kwargs,
) -> None:
    """§7.16.5：`alias_of` 必须与 §7.15.1 的 canonical 表一致，不一致报 FS06。

    这一支**判不出来**：§7.15.1 的 14 行表只存在于契约正文（markdown 表格），盘上
    没有机器可读的等价物，而 §7.16.5 明确「唯一权威、禁止二次登记」，本模块不能
    自己造一份副本当权威。按 §7.17.4 C3，判不出来就 `GateError(FS06)` fail-closed
    （HTTP 400）：既不静默返回「一致」，也不再让 `NotImplementedError` 逃出闸门
    （C1 出口唯一）。
    """
    raise GateError(
        "FS06",
        _detail(
            "FS06",
            mode,
            "ledger",
            None,
            None,
            None,
            "§7.15.1 的 canonical 台账没有机器可读副本，alias 台账一致性不可判定（FS06）",
        ),
        None,
        entry=entry,
    )''',
))


def main() -> int:
    raw = GATE.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    for name, old, new in EDITS:
        count = text.count(old)
        if count != 1:
            print(f"[FAIL] {name}: matched {count} times (want 1)", flush=True)
            return 1
        text = text.replace(old, new)
        print(f"[ok] {name}", flush=True)
    GATE.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    print(f"[done] wrote {GATE} {GATE.stat().st_size} B", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
