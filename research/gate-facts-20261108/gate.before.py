"""因子准入闸门（FS01-FS06）—— 契约 §7.7 / §7.8 / §7.16 的单一实现。

位置与职责：§7.7.2 裁定「闸门放在消费入口，不放在求值层」，并要求「单一实现，禁止
各入口各写一遍」。本模块就是那个单一实现：判定逻辑只在这里写一次，任何入口都调
`assert_factors_usable`，不各自复制判定。

本单范围（B2 闸门核心）
--------------------
* 纯新增、不接线：§7.7.3 / §7.16.3 的 9 个调用点一个都没改，本模块目前没有生产
  调用方。
* 只判能从盘上事实判定的码：FS01 / FS02 / FS03 / FS05 / FS06。判不出来的分支一律
  抛 `GateError`（§7.17.4 C1/C3：出口唯一、FS06 fail-closed），不静默放行。
* 命名面（§7.17.2，v0.12）：`namespace` 由调用方声明 —— `"factor"`（缺省，等于今日
  行为）与 `"column"`（按 §7.8.3 第一行 base 处理）两面；域外取值 / Mapping 缺键
  → `FS09`（入参非法，§7.17.4 C4），不进 `blocked`。
* 事实只有两处盘上文件：registry 的 `FactorSpec` 与 `custom_factors/*.json`（只读）；
  allowlist 只读 `referenced_factor_inventory.json` 的 `summary.live_config` 分层。
  不读旁挂 `.sha256`（F-A36），不写任何产物。

CONTRACT-GAP（契约没写 / 派发书引入 / 契约自相矛盾，就地标记，等架构师裁定）
-----------------------------------------------------------------------
1. `mode="none"`：§7.7.2 / §7.8.4 只有 production / research / diagnostic 三值。
   本模块把它作「不判定」：`ok=True`、`blocked=()`、`mode="none"`，对应 §7.7.3
   表里 mode 为「—」的求值层。
2. `shadow=True`：契约没有这个参数。按派发书「只出报告、不抛异常、不改返回值」：
   返回值与非 shadow 完全相同，只是不抛 `GateError`。
3. `entry=...`：派发书写成 `assert_factors_usable(entry, factor_ids, mode)`，而
   §7.7.2 定的签名是 `(factor_ids, mode, *, ...)`，没有首位 `entry`。本模块保留
   契约的位置参数顺序，把 `entry` 作可选关键字（§7.7.3 的调用点名），只挂到
   `GateError.entry`，**不进** `detail`（§7.16.4 的 detail 键集合是固定的）。
4. `GateReport` 只有 §7.7.2 的六字段，而 §7.8.4 要求 research / diagnostic 报告
   「标 `deprecated_alias_used` / `reference_missing` / `dual_id` /
   `ambiguous_canonical`」——六字段里没有承载位置。本模块不自行扩字段，这四条标记
   的落点待裁定。
5. FS02「未登记」的口径：§7.7.2 只写「registry 与 custom store 都没有」，但活配置
   引用的 19 个 id 里有 14 个既不在 registry 也不在 store——它们是管线列 / 指标列
   （`close` / `raw_high` / `ma5` / `macd_dif` / `limit_up_price` …）。按字面判
   FS02，闸门一上线现有策略全停（§7.8.5 自己说的「一上线就停产」）。本模块把这批
   id 归为 `kind="base"`（§7.8.3 第一行：base 不 gate），口径与判据见
   `_column_universe`；这条归类要架构师确认。

硬规则（实现里逐条落到代码）
--------------------------
* 不得用 `stability` 反推 `active`（§7.8.4 末段）：status 只从定义 JSON 的 `status`
  字段取，本模块从不读 `spec.stability`。
* Provider 注册且无 status 的因子按 `draft` 处理（§7.8.4 末行），生产入口因此拒绝
  （FS01）——漏填必须失败，不许放行。
* FS06 优先于 FS03（§7.16.2 C2），FS03 只在 `mode="production"` 触发
  （§7.16.2 C4）。
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: §7.8.4 三值 + 派发书引入的 none（CONTRACT-GAP 1）。
MODES: tuple[str, ...] = ("production", "research", "diagnostic", "none")

#: `custom_factors/*.json` 的 status 取值（store.STATUSES 同源）。
STATUSES: tuple[str, ...] = ("draft", "active", "watch", "retired")

#: §7.7.2 / 开发经理 2026-11-08 裁定（`DELIVERY_SCHEDULE_202607…` §4 同精神）：
#: **同一 `submitted_id` 命中多码时只报优先级最高一码**，不写 `violations`。
#: `FS04` 不在此表内 —— 它由 `_guard_dual_id` 在聚合后单独判，且恒优先（§7.16.6）。
#: 数值越小越优先：FS04 > FS03 > FS06 > FS01 > FS05。
#: `FS05` 排在末位：`lang="python"` 只是「没有研究侧参考实现」，比 status / alias
#: 问题更适合作为兜底，与 `_judge` docstring 的既有次序一致。
_CODE_PRIORITY: dict[str, int] = {
    "FS04": 0,
    "FS03": 1,
    "FS06": 2,
    "FS01": 3,
    "FS05": 4,
}

#: §7.17.2 S5：命名面取值域（`column` 面按 §7.8.3 第一行 base 处理）。域外一律 FS09；
#: `base` / `virtual` 是 §7.8.3 的 **kind**，不是 namespace，传进来也按域外报错。
_NAMESPACES: tuple[str, ...] = ("factor", "column")

#: §7.8.3 裁定 B：闸门按「可复算性」分类，**不按 kind** —— 因此这里记的是
#: **豁免集**（不是白名单）：只有 base / virtual 不 gate（§7.7.2 末行：两者无 status、
#: 准入由台账 G1–G3 与代码审核承担）；其余一切（custom / composite / python / 以及
#: 任何未预期的新 kind）一律进闸门判定。旧实现用白名单 {custom, composite}，导致
#: 「同一个 id 换个 kind 就逃出闸门」（实测 vol60 作 custom 出 FS03、作 frame 出 []），
#: 178 个因子完全不受约束。改成黑名单语义后，新 kind 默认受约束（fail-closed）。
EXEMPT_KINDS: frozenset[str] = frozenset({"base", "virtual"})

#: §7.8.2 A-3：alias 传递解析上限，超过即 FS06。
MAX_ALIAS_HOPS = 4

#: 仓库内清单产物的默认位置（§7.10.2 唯一路径）。
DEFAULT_INVENTORY_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "evidence"
    / "referenced_factor_inventory.json"
)


@dataclass(frozen=True)
class GateReport:
    """§7.7.2 定死的六字段：名字、顺序、类型逐字照抄，多一个都算不合格。"""

    ok: bool
    blocked: tuple[tuple[str, str | None, str], ...]
    non_active: tuple[str, ...]
    unknown: tuple[str, ...]
    mode: str
    historical_only: bool

    def codes(self) -> tuple[str, ...]:
        """blocked 里的错误码（去重、保序），供入口拼 400 用。"""
        ordered: list[str] = []
        for _factor_id, _status, code in self.blocked:
            if code not in ordered:
                ordered.append(code)
        return tuple(ordered)


class GateError(Exception):
    """闸门拒绝。`detail` 形状照 §7.16.4（FS03 与 FS04 / FS06 共用）。"""

    def __init__(
        self,
        code: str,
        detail: dict,
        report: GateReport | None,
        entry: str | None = None,
    ) -> None:
        super().__init__(str(detail.get("message") or code))
        self.code = code
        self.detail = detail
        self.report = report
        self.entry = entry

    def to_detail(self) -> dict:
        """返回 detail 的副本（入口直接塞进 HTTP 400 的 `detail`）。"""
        return dict(self.detail)


class AliasResolutionError(Exception):
    """alias 解析不可判定（成环 / 超 MAX_ALIAS_HOPS / 目标未登记）→ FS06。"""

    code = "FS06"


@dataclass(frozen=True)
class FactorFacts:
    """单个因子 id 的盘上事实。`status=None` 表示「盘上没有 status」（Provider 注册）。"""

    factor_id: str
    registered: bool
    kind: str | None = None
    status: str | None = None
    alias_of: str | None = None
    lang: str | None = None
    strategy_usable: bool | None = None
    table_row: int | None = None


class FactsSource(Protocol):
    """事实来源（测试注入用同一个协议；生产默认 RegistryFacts）。"""

    def facts(self, factor_id: str) -> FactorFacts: ...


class MappingFacts:
    """内存事实源：未登记的 id 一律返回 `registered=False`（即可判 FS02）。"""

    def __init__(self, mapping: Mapping[str, FactorFacts]) -> None:
        self._mapping = dict(mapping)

    def facts(self, factor_id: str) -> FactorFacts:
        found = self._mapping.get(factor_id)
        if found is None:
            return FactorFacts(factor_id=factor_id, registered=False)
        return found


_COLUMN_UNIVERSE: frozenset[str] | None = None


def _column_universe() -> frozenset[str]:
    """管线列 / 指标列的 id 集合（惰性、只读一次）。

    CONTRACT-GAP 5：这些 id 在盘上是「裸列」而不是可登记因子——既没有 JSON 定义
    也没有 `FactorSpec`。它们等价于 §7.8.3 第一行的 base 列（不 gate）。集合来源
    逐个取自现有常量，不在这里写死任何 id。
    """
    global _COLUMN_UNIVERSE
    if _COLUMN_UNIVERSE is not None:
        return _COLUMN_UNIVERSE
    from app.factors.dsl import BASE_COLUMNS
    from app.indicators import pipeline

    names: set[str] = set(BASE_COLUMNS)
    for attribute in (
        "INDICATOR_COLUMNS",
        "ENRICHED_COLUMNS",
        "ENRICHED_STORAGE_COLS",
        "LIMIT_SIGNAL_OUTPUTS",
        "_ALL_INDICATOR_COLS",
        "_LIMIT_PRICE_COLUMNS",
    ):
        value = getattr(pipeline, attribute, None)
        if value is None:
            continue
        names |= set(value.keys() if isinstance(value, dict) else value)
    _COLUMN_UNIVERSE = frozenset(names)
    return _COLUMN_UNIVERSE


class RegistryFacts:
    """默认事实源：registry 的 FactorSpec + 可选 data_dir 下的 custom 定义（只读）。

    * status 只从定义 JSON 的 `status` 字段取（§7.7.1 #2：运行时对象没有 status，
      `to_spec` 把它单向投影成 stability 后丢弃）。**不读 stability。**
    * 管线列 / 指标列（无 spec 无定义但有该列）按 `kind="base"` 返回，见
      CONTRACT-GAP 5。
    * `alias_of` / `strategy_usable` 先看 spec 属性，缺了再看定义 JSON 同名字段；
      §7.16 的 F-A42-1 未落地时两处都取不到，此时 alias 判定面为 0（见交付说明）。
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._definitions: dict[str, dict] | None = None

    def _load_definitions(self) -> dict[str, dict]:
        if self._definitions is not None:
            return self._definitions
        definitions: dict[str, dict] = {}
        if self._data_dir is not None:
            from app.factors import store

            # `JsonDefinitionStore.dir()` 会 mkdir；闸门只读，目录不存在就不去碰它。
            subdir = getattr(getattr(store, "_STORE", None), "subdir", "user_data/custom_factors")
            if (self._data_dir / subdir).is_dir():
                for definition in store.load_all(self._data_dir):
                    factor_id = str(definition.get("id") or "")
                    if factor_id:
                        definitions[factor_id] = definition
        self._definitions = definitions
        return definitions

    def facts(self, factor_id: str) -> FactorFacts:
        from app.factors.registry import get_factor

        spec = get_factor(factor_id)
        definition = self._load_definitions().get(factor_id)
        if spec is None and definition is None:
            if factor_id in _column_universe():
                # CONTRACT-GAP 5：管线列 / 指标列按 base 处理（§7.8.3 第一行不 gate）。
                return FactorFacts(factor_id=factor_id, registered=True, kind="base")
            return FactorFacts(factor_id=factor_id, registered=False)

        kind = spec.kind if spec is not None else str(definition.get("kind") or "custom")
        lang = spec.lang if spec is not None else str(definition.get("lang") or "dsl")
        status = _definition_status(definition)
        # §7.16.5：spec 字段是权威投影（pack / store 定义写入），定义 JSON 只是兜底。
        alias_of = spec.alias_of if spec is not None else None
        if alias_of is None and definition is not None:
            alias_of = definition.get("alias_of") or None
        strategy_usable = spec.strategy_usable if spec is not None else None
        if strategy_usable is None and definition is not None:
            strategy_usable = definition.get("strategy_usable")
        return FactorFacts(
            factor_id=factor_id,
            registered=True,
            kind=kind,
            status=status,
            alias_of=str(alias_of) if alias_of else None,
            lang=lang,
            strategy_usable=bool(strategy_usable) if strategy_usable is not None else None,
            table_row=None,
        )


def _definition_status(definition: dict | None) -> str | None:
    """定义 JSON 的 status；没有定义或没有该字段时返回 None（= 盘上无状态）。"""
    if definition is None:
        return None
    if "status" not in definition:
        return None
    status = str(definition.get("status"))
    if status not in STATUSES:
        raise ValueError(f"定义 status 非法: {status!r}（应为 {list(STATUSES)} 之一）")
    return status


def resolve_alias(factor_id: str, facts: FactsSource) -> tuple[str, tuple[str, ...]]:
    """§7.8.2 A-3 的传递解析：上限 4 跳、环检测、目标必须已登记。

    返回 `(canonical_id, chain)`；非 alias 返回 `(factor_id, ())`。
    解析不可判定时抛 `AliasResolutionError`（→ FS06），绝不返回半截结果。
    """
    seen: list[str] = []
    current = factor_id
    for _hop in range(MAX_ALIAS_HOPS + 1):
        current_facts = facts.facts(current)
        if not current_facts.registered:
            if current == factor_id:
                return factor_id, ()
            raise AliasResolutionError(f"alias 解析目标未登记: {current}")
        if current_facts.alias_of is None:
            if current == factor_id:
                return factor_id, ()
            return current, tuple(seen)
        if current_facts.alias_of in seen or current_facts.alias_of == current:
            raise AliasResolutionError(f"alias 成环: {' -> '.join([*seen, current, current_facts.alias_of])}")
        seen.append(current)
        if len(seen) > MAX_ALIAS_HOPS:
            raise AliasResolutionError(f"alias 超过 {MAX_ALIAS_HOPS} 跳: {seen}")
        current = current_facts.alias_of
    raise AliasResolutionError(f"alias 超过 {MAX_ALIAS_HOPS} 跳: {seen}")


@dataclass(frozen=True)
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


def _judge(
    fact: FactorFacts,
    mode: str,
    *,
    allow_non_active: bool,
    allow_retired: bool,
    require_status: bool,
    facts: FactsSource,
) -> _Verdict:
    """单个 id 的判定。多个码同时成立时按 FS06 > FS03 > FS01 > FS05 排列。"""
    if not fact.registered:
        return _Verdict(("FS02",), False, False, None)

    if fact.kind in EXEMPT_KINDS:
        # §7.7.2 末行 + §7.8.3：base / virtual 不适用 status，也不按 alias 判。
        # 黑名单语义：不在这里「点名放行」，其余 kind 一律往下走判定。
        return _Verdict((), False, False, fact.factor_id)

    codes: list[str] = []
    resolved = fact.factor_id
    if fact.alias_of is not None:
        try:
            resolved, _chain = resolve_alias(fact.factor_id, facts)
        except AliasResolutionError:
            # §7.8.4 矩阵：FS06 在 production / research 都拒，diagnostic 放行（标
            # ambiguous_canonical；标记的落点见 CONTRACT-GAP 4）。
            if mode == "diagnostic":
                return _Verdict((), False, False, None)
            return _Verdict(("FS06",), False, False, None)
        if mode == "production":
            codes.append("FS03")
    elif fact.strategy_usable is False:
        # §7.16.5：strategy_usable 只有在 alias_of 非空时才为 False。
        # 「False 且 alias_of 为空」是定义自相矛盾，按 FS06（冲突）处理。
        if mode == "diagnostic":
            return _Verdict((), False, False, None)
        return _Verdict(("FS06",), False, False, None)

    non_active = False
    retired = False
    if require_status:
        # §7.8.4 末行：Provider 注册且无 status 的按 draft 处理。
        status = fact.status if fact.status is not None else "draft"
        if status not in STATUSES:
            # §7.17.4 C4：status 域外 → FS09（不得抛 ValueError，C1 出口唯一）。
            raise _invalid_argument(
                "status", mode, f"status 非法: {status!r}（应为 {list(STATUSES)} 之一）"
            )
        if mode == "production":
            if status != "active":
                codes.append("FS01")
        elif mode == "research":
            if status == "watch":
                non_active = True
            elif status == "draft":
                if allow_non_active:
                    non_active = True
                else:
                    codes.append("FS01")
            elif status == "retired":
                if allow_retired:
                    non_active = True
                    retired = True
                else:
                    codes.append("FS01")
        elif mode == "diagnostic":
            non_active = status != "active"

    if mode == "production" and fact.lang == "python":
        # §7.8.3：python 因子恒 reference_missing=true，没有研究侧参考实现。
        codes.append("FS05")

    # 只报优先级最高一码（本函数返回多码仅用于内部保留全貌；上报取 codes[0]）。
    if len(codes) > 1:
        codes = sorted(codes, key=lambda c: _CODE_PRIORITY.get(c, 99))
    return _Verdict(tuple(codes), non_active, retired, resolved)


def _normalise_ids(factor_ids: Iterable[str] | str) -> list[str]:
    raw = [factor_ids] if isinstance(factor_ids, str) else [str(item) for item in factor_ids]
    ordered: list[str] = []
    for item in raw:
        if item and item not in ordered:
            ordered.append(item)
    return ordered


def _guard_dual_id(
    resolved: Mapping[str, str],
    *,
    mode: str,
    report: GateReport,
    entry: str | None = None,
    shadow: bool = False,
) -> None:
    """§7.16.6 FS04：同一策略内 alias 与 canonical 并存 → 400 + `code="FS04"`。

    * 只在 production / research 判（diagnostic 放行并标 `dual_id`，§7.8.4）。
    * **FS04 优先于 FS03**（§7.16.6 末行）：本函数在 FS03 抛错之前调用。
    * `detail` 与 FS03/FS06 共用 §7.16.4 形状；`submitted_id` 取输入顺序的第一条，
      另给 `dual_ids` 列全部并存 id（§7.16.4 批量入口的 `violations` 同精神）。
    * `table_row` 仍为 None：§7.15.1 没有机器可读副本（见 check_ledger_consistency）。
    * `shadow=True` 时按 §7.7.2「shadow 不打断」返回、不抛 —— GateReport 六字段固定，
      没有 FS04 槽位，`dual_id` 标记的落点见 CONTRACT-GAP 4。
    """
    buckets: dict[str, list[str]] = {}
    for submitted, canonical in resolved.items():
        buckets.setdefault(canonical, []).append(submitted)
    for canonical, submitted in buckets.items():
        if len(submitted) < 2:
            continue
        if shadow:
            return
        detail = _detail(
            "FS04",
            mode,
            submitted[0],
            canonical,
            None,
            None,
            f"同一策略内混用同口径两个 id: {' / '.join(submitted)} 都指向 {canonical}",
        )
        detail["dual_ids"] = list(submitted)
        raise GateError("FS04", detail, report, entry=entry)


def _detail(
    code: str,
    mode: str,
    submitted_id: str,
    resolved_id: str | None,
    table_row: int | None,
    status: str | None,
    message: str,
) -> dict:
    """§7.16.4 的唯一形状（FS03 / FS06 共用）；FS01 另按 §7.7.5 带 status。"""
    detail: dict = {
        "code": code,
        "mode": mode,
        "submitted_id": submitted_id,
        "resolved_id": resolved_id,
        "canonical_id": resolved_id,
        "table_row": table_row,
        "message": message,
    }
    if code == "FS01":
        detail["status"] = status
    return detail


def _message(code: str, factor_id: str, status: str | None, mode: str, canonical: str | None) -> str:
    if code == "FS03":
        return f"生产入口不允许 alias，请改用 canonical id {canonical}"
    if code == "FS01":
        return f"因子 {factor_id} 的 status={status} 不允许在 {mode} 模式使用"
    if code == "FS02":
        return f"因子未登记: {factor_id}"
    if code == "FS05":
        return f"因子 {factor_id} 是 python 实现且没有研究侧参考实现（reference_missing）"
    if code == "FS06":
        return f"因子 {factor_id} 的 canonical 未裁定/解析不可判定"
    return code


def assert_factors_usable(
    factor_ids: Iterable[str] | str,
    mode: str,
    *,
    allow_non_active: bool = False,
    allow_retired: bool = False,
    require_status: bool = True,
    shadow: bool = False,
    entry: str | None = None,
    facts: FactsSource | None = None,
    namespace: str | Mapping[str, str] = "factor",
) -> GateReport:
    """§7.7.2 的闸门：判定矩阵照 4x2 表，`mode` 的第三值见 §7.8.4。

    参数（契约来源）：
      * `factor_ids`：被引用的因子 id 集合；单个 str 也接受（按一个 id 处理）。
      * `mode`：production / research / diagnostic；`none` 见 CONTRACT-GAP 1。
      * `allow_non_active` / `allow_retired`：§7.7.2 的 research 放行开关。
      * `require_status`：§7.16.3 签名里的开关；False 时整段 FS01 不判。
      * `shadow` / `entry`：CONTRACT-GAP 2 / 3。
      * `namespace`：§7.17.2 的命名面，keyword-only，缺省 `"factor"` 即今日行为；
        `"column"` 把该 id 按 §7.8.3 第一行 base 处理（面闭合判据 `_column_universe()`），
        也接受 `Mapping[str, str]` 逐 id 声明；域外取值 / Mapping 缺键 → `FS09`。

    返回 `GateReport`；有 blocked 且 `shadow=False` 时抛 `GateError`（fail-closed）。
    """
    if not isinstance(mode, str) or mode not in MODES:
        # §7.17.4 C4：入参非法一律 FS09（GateError），不抛 ValueError（C1 出口唯一）。
        raise _invalid_argument(
            "mode", str(mode), f"未知 mode: {mode!r}（只接受 {list(MODES)}）", entry
        )

    ordered_ids = _normalise_ids(factor_ids)
    faces = _namespace_faces(namespace, ordered_ids, mode, entry)
    source: FactsSource = facts if facts is not None else RegistryFacts()
    blocked: list[tuple[str, str | None, str]] = []
    non_active: list[str] = []
    unknown: list[str] = []
    historical = False
    resolved_by_id: dict[str, str] = {}
    gated_resolved: dict[str, str] = {}

    if mode != "none":  # CONTRACT-GAP 1：none = 不判定
        for factor_id in ordered_ids:
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
                )
            if verdict.resolved is not None:
                resolved_by_id[factor_id] = verdict.resolved
                gated_resolved[factor_id] = verdict.resolved
            if not fact.registered:
                unknown.append(factor_id)
            if verdict.codes:
                # 同一 submitted_id 命中多码 → 只报优先级最高一码（见 _CODE_PRIORITY）。
                # 单码时行为与旧实现逐位相同；多码时不再重复计数，也不会触发 violations。
                top_code = min(verdict.codes, key=lambda c: _CODE_PRIORITY.get(c, 99))
                blocked.append((factor_id, fact.status, top_code))
            else:
                if verdict.non_active:
                    non_active.append(factor_id)
                if verdict.retired:
                    historical = True
    report = GateReport(
        ok=not blocked,
        blocked=tuple(blocked),
        non_active=tuple(non_active),
        unknown=tuple(unknown),
        mode=mode,
        historical_only=historical,
    )

    if mode in ("production", "research"):
        # §7.16.6：FS04 在 production / research 都拒，diagnostic 允许（标 dual_id）；
        # 且 **FS04 优先于 FS03** —— 必须排在下面的 GateError(FS03) 之前。
        _guard_dual_id(gated_resolved, mode=mode, report=report, entry=entry, shadow=shadow)

    if report.blocked and not shadow:
        first_id, first_status, first_code = report.blocked[0]
        resolved = None if first_code == "FS02" else resolved_by_id.get(first_id, first_id)
        fact = source.facts(first_id)
        detail = _detail(
            first_code,
            mode,
            first_id,
            resolved,
            fact.table_row,
            first_status,
            _message(first_code, first_id, first_status, mode, resolved),
        )
        # `violations` 只在 `blocked` 含 >=2 个**不同 id** 时出现（批量入口语义）；
        # 单 id 多码已被聚合到一码（见 _CODE_PRIORITY），detail 恒为 §7.16.4 的 7 键
        # （FS01 另加 status）。
        if len({item_id for item_id, _s, _c in report.blocked}) > 1:
            detail["violations"] = [
                {"submitted_id": item_id, "code": item_code}
                for item_id, _item_status, item_code in report.blocked
            ]
        raise GateError(first_code, detail, report, entry=entry)

    return report


@dataclass(frozen=True)
class LiveConfigAllowlist:
    """§7.10.4 L2 的唯一读取面：清单产物里的 `summary.live_config` 分层。"""

    ids: tuple[str, ...]
    records: int
    sources: int
    primary: int
    companion: int
    source_path: str


def load_live_config_allowlist(path: str | Path | None = None) -> LiveConfigAllowlist:
    """只读清单产物的 `summary.live_config` 分层，返回 L2 allowlist。

    规则（§7.10.4 / F-A24 / F-A36）：
      * 分层只认 `summary.live_config`；`summary.all_records` 不参与放行。
      * 行 = `records[]` 中 `source_enabled is True` 的记录。
      * 计数逐项与 `summary.live_config` 对账：`records` / `sources` /
        `by_record_kind` 统计全部行，`by_verdict` 只统计 primary 行（§7.12.5 /
        F-A24：伴生记录的 exempt 不进 by_verdict）。任一项不等即 ValueError。
      * allowlist 的 id 只取 `record_kind == "primary"`：F-A24 规定伴生记录
        （`both_collision=true`）verdict 恒 exempt，不参与放行。
      * 只读这一个 JSON 文件；不读旁挂 `.sha256`（F-A36），不写任何产物。
    """
    target = Path(path) if path is not None else DEFAULT_INVENTORY_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    summary = payload["summary"]["live_config"]
    rows = [row for row in payload["records"] if row.get("source_enabled") is True]

    kinds = Counter(str(row.get("record_kind")) for row in rows)
    # §7.12.5 / F-A24：各层 by_verdict / by_code / by_namespace 只统计 primary，
    # 伴生记录（both_collision=true）verdict 恒 exempt、不参与放行。
    primary_rows = [row for row in rows if row.get("record_kind") == "primary"]
    verdicts = Counter(str(row.get("verdict")) for row in primary_rows)
    counts = {
        "records": len(rows),
        "sources": len({row.get("source_path") for row in rows}),
    }
    for key, actual in counts.items():
        if actual != summary[key]:
            raise ValueError(
                f"清单 live_config 分层与 summary 不一致: {key} summary={summary[key]} 实际={actual}"
            )
    for key, actual in (("by_record_kind", dict(kinds)), ("by_verdict", dict(verdicts))):
        expected = dict(summary[key])
        if actual != expected:
            raise ValueError(
                f"清单 live_config 分层与 summary 不一致: {key} summary={expected} 实际={actual}"
            )

    ids = sorted({str(row["ref_name"]) for row in primary_rows if row.get("ref_name")})
    return LiveConfigAllowlist(
        ids=tuple(ids),
        records=len(rows),
        sources=len({row.get("source_path") for row in rows}),
        primary=kinds.get("primary", 0),
        companion=kinds.get("companion", 0),
        source_path=str(target),
    )


def check_ledger_consistency(
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
    )
