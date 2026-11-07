#!/usr/bin/env python
"""生成 `referenced_factor_inventory` —— 契约 §7.10.2 / §7.10.3 的唯一产物生成器。

职责
  扫描六个扫描域（custom_signal / strategy_override / strategy_config /
  monitor_rule / custom_factor / research_strategy），把每一处**结构化的**
  字段/因子引用解析成一条记录，逐条给出 `ref_namespace` 与分级放行 `verdict`，
  写出 `docs/architecture/evidence/referenced_factor_inventory.json` 与同名
  `.sha256`。

不知道
  不判定因子口径、不改任何活配置、不写 `user_data`、不接闸门入口（L0 观测）。

三条硬规则（契约 §7.10.3）
  N1 命名空间先于分类：`field:X` **先**查 `ALLOWED_FIELDS`，命中即
     `ref_namespace=column` 且**不进入**因子闸门；未命中才回落 `factors.registry`。
     现实现 (`custom_signals.allowed_fields()`) 是两者的**并集**，集合语义不表达
     「先列后因子」，因此本脚本显式排序，不复用那个并集做分类。
  N2 `namespace=column` 的引用不因「名字恰好等于某因子 id」判 status。四个冲突名
     （`ma20`/`ma60`/`boll_lower`/`boll_upper`）另出一条 `both_collision=true`
     的伴生记录（F-A24），伴生记录只登记冲突，不参与放行。
  N3 同一引用在历史路径与盘中单日路径可能不同 → 按 `path_scope` 记录，两路径结论
     不一致标 `path_divergence=true` 且该条不得判 `allow`。

粒度（v2）
  一条记录 = 一个**结构化引用出现处**，不按 (源 × 名字) 合并：条件表达式的 `left` /
  `right`（裸白名单名或 `field:X`）、monitor 的 `field`、`scoring` 的每个键、公式的每个
  依赖名、composite 的每个 `members` 键、research 的 `fields.<名>` 各自成条，由 `side`
  标明出现处（`L` / `R` / `R:field` / `field` / `scoring` / `formula` / `members` /
  `fields.<名>`）。同名引用在同一源出现两次 → 两条记录，`evidence` 行号不同。
  F-A24 伴生记录同样**按出现处一条**，`verdict` 恒 `exempt` 且不参与放行判定。

结构化解析，不做全文 grep（F-A23）
  每个扫描域只读它自己的 schema 键：条件表达式的 `left` / `right`（`field:` 前缀）、
  `overlay_filter`、`scoring` 键、`ALLOWED_FIELDS` / `ENRICHED_COLUMNS` 集合成员、
  DSL 编译器的 `referenced_factors` / `dependencies`、composite 的 `members` 字典。
  `description` 一类散文与 `preferences.json` 的展示列**不在扫描面内**，因此不会被
  计为引用（本脚本从不解析自由文本）。

用法
  python scripts/build_referenced_factor_inventory.py                # 写到契约路径
  python scripts/build_referenced_factor_inventory.py --data-dir D:/TSP/data
  python scripts/build_referenced_factor_inventory.py --out <path> --quiet

退出码
  0 = 全部自检通过并已写出；1 = 有自检失败（产物仍写出，便于对照）；
  2 = 环境/参数错误（未写出）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCHEMA_VERSION = "2"   # v2: 逐出现粒度 + side + summary 分层 + canonical_sha256
CN_TZ = timezone(timedelta(hours=8))
OUT_REL = Path("docs/architecture/evidence/referenced_factor_inventory.json")
RESEARCH_STRATEGY_REL = Path("research/strategy-search-20261107/factor_map_v1.json")
SEEDS_REL = Path("backend/app/strategy/seeds")

# 记录字段顺序 = 契约 §7.10.2 表序 + F-A24 (`both_collision`) + N3 (`path_divergence`)
# + v2 (`side`)。`side` 是引用出现处，契约 §7.10.2 未列，随 v0.6 追认。
RECORD_FIELDS: tuple[str, ...] = (
    "source_kind", "source_path", "source_id", "source_sha256", "source_enabled",
    "path_scope", "ref_raw", "ref_namespace", "resolved_id", "class", "verifiable",
    "gate_mode", "verdict", "code", "evidence", "both_collision", "path_divergence",
    "side",
)

# FS 码（§7.7.4 / §7.8.4）；本清单只会产出 FS01 / FS02。
FS01 = "FS01"   # 因子状态不允许在该模式使用
FS02 = "FS02"   # 因子未登记

# 命名空间冲突名（N2 / F-A24）：同时存在于 ALLOWED_FIELDS 与注册表因子 id。
COLLISION_NAMES = ("ma20", "ma60", "boll_lower", "boll_upper")
SIGNAL_PREFIXES = ("signal_", "csg_", "csgi_")

# 活配置面口径（契约 §7.10.5）：enabled=true 的源 = custom_signals 21 + monitor_rules 1。
EXPECTED_ENABLED_SOURCES = 22
EXPECTED_COLLISION_SIGNALS = (
    "boll_breakdown_lower", "boll_breakout_upper", "ma20_breakdown", "ma20_breakout",
    "ma_dead_5_20", "ma_golden_20_60", "ma_golden_5_20",
)
EXPECTED_VIRTUAL_REFS = ("distance_to_high_60d", "limit_up_count_20d")

# v2 逐出现粒度下的期望计数（2026-11-07 实测基线；口径变化须同步本处与报告）。
EXPECTED_LIVE_RECORDS = 79        # 22 个活配置源的判定记录（不含伴生）
EXPECTED_LIVE_COMPANIONS = 14     # 4 个冲突名在 7 条冲突信号里的出现处
EXPECTED_TOTAL_RECORDS = 218      # 六类源全量记录（含伴生）


# ---------------------------------------------------------------- 小工具
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LineIndex:
    """证据行号定位器。仅用于产出 `file:line`，**不参与任何分类判定**。"""

    def __init__(self) -> None:
        self._cache: dict[Path, list[str]] = {}
        self._cursor: dict[tuple[Path, str], int] = {}

    def lines(self, path: Path) -> list[str]:
        if path not in self._cache:
            self._cache[path] = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return self._cache[path]

    def _search(self, path: Path, token: str, start: int) -> int | None:
        lines = self.lines(path)
        needle = f'"{token}"'
        begin = max(start, 1) - 1
        for i in range(begin, len(lines)):
            if needle in lines[i]:
                return i + 1
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
        for i in range(begin, len(lines)):
            if pattern.search(lines[i]):
                return i + 1
        return None

    def find_occ(self, path: Path, token: str) -> int:
        """按**出现顺序**定位：同一个 token 在本文件第 N 次调用返回第 N 个匹配行。

        JSON 本身没有行号信息，结构化解析因此拿不到位置；这里只做「第 N 次出现 → 第 N 个
        匹配行」，不做语义判断（F-A23：只用于产出 `evidence`）。同名两次落在同一行时，
        第二次从该行往后找不到会回退到整文件首匹配，两条记录给出同一行号（正确）。
        """
        key = (path, token)
        start = self._cursor.get(key, 1)
        found = self._search(path, token, start)
        if found is None:
            found = self._search(path, token, 1) or 1
        self._cursor[key] = found + 1
        return found


# ---------------------------------------------------------------- 解析器
class Resolver:
    """把一条原始引用解析成 (namespace, class, verifiable, verdict, code)。

    只做机械判定：集合成员、注册表 kind/lang/status、DSL 编译结果。
    """

    def __init__(self, specs: dict, defs: dict, allowed: frozenset, enriched: frozenset,
                 intraday_fields: frozenset) -> None:
        self.specs = specs
        self.defs = defs
        self.allowed = allowed
        self.enriched = enriched
        self.intraday_fields = intraday_fields
        self._dsl_cache: dict[str, bool] = {}
        self._py_cache: dict[str, bool] = {}
        self._verifiable_cache: dict[str, bool] = {}

    # -- 分类 ------------------------------------------------------
    @staticmethod
    def factor_class(spec) -> str:
        if spec.kind == "custom":
            return "custom_python" if getattr(spec, "lang", "dsl") == "python" else "custom_dsl"
        return spec.kind  # base / virtual / composite

    def status_of(self, fid: str) -> str:
        """§7.8.4：Provider 注册且无 status → 按 draft 处理（安全方向）。"""
        definition = self.defs.get(fid) or {}
        status = definition.get("status")
        return status if isinstance(status, str) and status else "draft"

    def verifiable(self, fid: str, depth: int = 0) -> bool:
        """§7.8.3 可复算性。base/virtual 为 n/a（调用方另给 None）。"""
        if fid in self._verifiable_cache:
            return self._verifiable_cache[fid]
        spec = self.specs.get(fid)
        if spec is None or depth > 4:
            return False
        cls = self.factor_class(spec)
        if cls == "custom_dsl":
            if fid not in self._dsl_cache:
                from app.factors.dsl import compile_formula

                self._dsl_cache[fid] = bool(compile_formula(spec.formula_text).ok)
            ok = self._dsl_cache[fid]
        elif cls == "custom_python":
            if fid not in self._py_cache:
                from app.factors.py_expr import compile_python_expression

                self._py_cache[fid] = bool(compile_python_expression(spec.formula_text).ok)
            ok = self._py_cache[fid]
        elif cls == "composite":
            members = [m for m, _w in spec.components]
            ok = bool(members) and all(
                self.specs.get(m) is not None
                and (
                    self.factor_class(self.specs[m]) in {"base", "virtual"}
                    or self.verifiable(m, depth + 1)
                )
                for m in members
            )
        else:
            ok = False
        self._verifiable_cache[fid] = ok
        return ok

    # -- 路径投影（N3）---------------------------------------------
    def path_namespace(self, raw: str, path: str) -> str:
        if path == "intraday":
            if raw in self.intraday_fields:
                return "column"
        elif raw in self.allowed:
            return "column"
        return "factor" if raw in self.specs else "unknown"

    # -- 主解析 ----------------------------------------------------
    def resolve(self, raw: str, *, gate_mode: str, path_scope: str,
                prefer: str = "column") -> dict:
        """返回 {namespace, resolved_id, cls, verifiable, verdict, code, divergence}。

        prefer="column" 用于条件表达式（N1：先列后因子）；
        prefer="factor" 用于 scoring 键（那是因子的消费位，见报告 §3.2）。
        """
        in_col = raw in (self.intraday_fields if path_scope == "intraday"
                         else self.allowed)
        in_reg = raw in self.specs
        if prefer == "factor" and in_reg:
            namespace = "factor"
        elif in_col:
            namespace = "column"
        elif in_reg:
            namespace = "factor"
        else:
            namespace = "unknown"

        resolved_id = raw if namespace == "factor" else None
        if namespace == "column":
            cls, verifiable = "base", None
        elif namespace == "factor":
            spec = self.specs[raw]
            cls = self.factor_class(spec)
            verifiable = None if cls in {"base", "virtual"} else self.verifiable(raw)
        else:
            cls, verifiable = "unregistered", None

        verdict, code = self._judge(namespace, cls, resolved_id, gate_mode)

        paths = ["history"] if path_scope == "history" else (
            ["intraday"] if path_scope == "intraday" else ["history", "intraday"]
        )
        views = {p: self.path_namespace(raw, p) for p in paths}
        divergence = len(set(views.values())) > 1
        if divergence:
            # N3：两路径结论不一致的条目不得判 allow（F-A25 只禁止 unknown）。
            verdict, code = "block", None
        return {
            "namespace": namespace, "resolved_id": resolved_id, "class": cls,
            "verifiable": verifiable, "verdict": verdict, "code": code,
            "divergence": divergence,
        }

    def _judge(self, namespace: str, cls: str, resolved_id: str | None,
               gate_mode: str) -> tuple[str, str | None]:
        if namespace == "unknown":
            return "block", FS02
        if namespace == "column":
            return "allow", None          # F-A29：column 必须判 allow
        if cls in {"base", "virtual"}:
            return "exempt", None         # §7.7.2：base/virtual 不适用 status 判定
        if gate_mode == "none":
            return "exempt", None         # §7.7.3：因子求值层不 gate
        status = self.status_of(resolved_id or "")
        if gate_mode == "production":
            return ("allow", None) if status == "active" else ("block", FS01)
        if gate_mode == "diagnostic":
            return "allow", None
        # research：active 放行；非 active 记 shadow（§7.7.2 需 allow_non_active）
        return ("allow", None) if status == "active" else ("shadow", None)


# ---------------------------------------------------------------- 组装一条记录
def emit(out: list, *, source_kind: str, source_path: str, source_id: str,
         source_sha: str, enabled, path_scope: str, occurrences: list[tuple[str, str]],
         gate_mode: str, evidence_for: Callable[[str, str], str], resolver: Resolver,
         prefer: str = "column") -> None:
    """按**出现处**逐条产出记录。

    `occurrences` 是 (side, 名称) 的有序列表：每个元素一条记录，不再按名字去重。
    调用方若给的是编译器输出的集合（本身已去重），集合语义即「每名一处」。
    """
    for side, raw in occurrences:
        if not isinstance(raw, str) or not raw:
            continue
        res = resolver.resolve(raw, gate_mode=gate_mode, path_scope=path_scope, prefer=prefer)
        # 只有「因子侧要过闸门」的同名才算冲突（base/virtual 本来就 exempt，撞名无风险）。
        spec = resolver.specs.get(raw)
        both = (raw in resolver.allowed) and spec is not None and resolver.factor_class(spec) in {
            "custom_dsl", "custom_python", "composite"}
        out.append({
            "source_kind": source_kind,
            "source_path": source_path,
            "source_id": source_id,
            "source_sha256": source_sha,
            "source_enabled": enabled,
            "path_scope": path_scope,
            "ref_raw": raw,
            "ref_namespace": res["namespace"],
            "resolved_id": res["resolved_id"],
            "class": res["class"],
            "verifiable": res["verifiable"],
            "gate_mode": gate_mode,
            "verdict": res["verdict"],
            "code": res["code"],
            "evidence": evidence_for(side, raw),
            "both_collision": False,
            "path_divergence": res["divergence"],
            "side": side,
        })
        if both:
            # F-A24：命名空间冲突的伴生记录 —— 同一出现处的另一侧视图，仅登记，不参与放行。
            companion = dict(out[-1])
            if companion["ref_namespace"] == "column":
                companion.update({
                    "ref_namespace": "factor",
                    "resolved_id": raw,
                    "class": resolver.factor_class(resolver.specs[raw]),
                    "verifiable": resolver.verifiable(raw),
                    "verdict": "exempt",
                })
            else:
                companion.update({
                    "ref_namespace": "column",
                    "resolved_id": None,
                    "class": "base",
                    "verifiable": None,
                    "verdict": "allow",
                })
            companion["code"] = None
            companion["both_collision"] = True
            companion["evidence"] = (out[-1]["evidence"]
                                     + "  # N2 伴生记录: 同名基础列优先, 不参与放行")
            out.append(companion)


def _dedup(seq) -> list[str]:
    out: list[str] = []
    for item in seq:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return out


def _condition_occurrences(cond: dict, allowed: frozenset) -> list[tuple[str, str]]:
    """条件表达式的**逐出现**结构化引用：(side, 名称)。

    `left` → `L`；`right` 写成 `field:X` → `R:field`（X）；`right` 直接写白名单列名 → `R`。
    与 `custom_signals._parse_right` 同口径：数字右值不是引用，不产记录。
    """
    occ: list[tuple[str, str]] = []
    left = cond.get("left")
    if isinstance(left, str) and left:
        occ.append(("L", left))
    right = cond.get("right")
    if isinstance(right, str) and right:
        if right.startswith("field:"):
            name = right[len("field:"):]
            if name:
                occ.append(("R:field", name))
        elif right in allowed:
            occ.append(("R", right))
    return occ

# ---------------------------------------------------------------- 六个扫描域

# ---------------------------------------------------------------- 六个扫描域
def scan_custom_signals(user_data: Path, resolver: Resolver, li: LineIndex, out: list) -> int:
    directory = user_data / "custom_signals"
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        enabled = data.get("enabled")
        enabled = None if enabled is None else bool(enabled)
        timeframe = data.get("timeframe") or "daily"
        # 只有 timeframe=intraday 的定义走分钟特征路径；build_intraday_expressions
        # 显式跳过 timeframe != intraday，日线信号只在历史帧上求值。
        path_scope = "intraday" if timeframe == "intraday" else "history"
        occurrences: list[tuple[str, str]] = []
        for cond in data.get("conditions") or []:
            if isinstance(cond, dict):
                occurrences.extend(_condition_occurrences(cond, resolver.allowed))
        rel = f"custom_signals/{path.name}"

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            # `field:X` 在文件里就是字面 `"field:X"`，按原样定位才落在正确行。
            token = f"field:{raw}" if side == "R:field" else raw
            return f"{_rel}:{li.find_occ(_p, token)}"

        emit(out, source_kind="custom_signal", source_path=rel,
             source_id=str(data.get("id") or path.stem), source_sha=sha256_file(path),
             enabled=enabled, path_scope=path_scope, occurrences=occurrences,
             gate_mode="production", evidence_for=evidence_for, resolver=resolver)
    return len(files)


def scan_monitor_rules(user_data: Path, resolver: Resolver, li: LineIndex, out: list) -> int:
    directory = user_data / "monitor_rules"
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        enabled = data.get("enabled")
        enabled = None if enabled is None else bool(enabled)
        occurrences: list[tuple[str, str]] = []
        for cond in data.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            field = cond.get("field")
            if not isinstance(field, str) or not field:
                continue
            # op=truth 时 field 是信号列（signal_/csg_），不是因子/列引用 → 不产记录。
            if cond.get("op") == "truth" or field.startswith(SIGNAL_PREFIXES):
                continue
            occurrences.append(("field", field))
        rel = f"monitor_rules/{path.name}"

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="monitor_rule", source_path=rel,
             source_id=str(data.get("id") or path.stem), source_sha=sha256_file(path),
             enabled=enabled, path_scope="intraday", occurrences=occurrences,
             gate_mode="production", evidence_for=evidence_for, resolver=resolver)
    return len(files)


def scan_strategy_overrides(user_data: Path, resolver: Resolver, li: LineIndex, out: list) -> int:
    directory = user_data / "strategy_overrides"
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        # strategy_overrides 无顶层 `enabled` 键 → source_enabled=null（未声明，
        # 既不是 true 也不是 false；是否生效由策略自身开关决定，见报告 §4.3）。
        enabled = data.get("enabled")
        enabled = None if enabled is None else bool(enabled)
        scoring = data.get("scoring")
        scoring_occ = [("scoring", str(k)) for k in scoring] if isinstance(scoring, dict) else []
        cond_occ: list[tuple[str, str]] = []
        for cond in data.get("overlay_filter") or []:
            if isinstance(cond, dict):
                cond_occ.extend(_condition_occurrences(cond, resolver.allowed))
        rel = f"strategy_overrides/{path.name}"
        sha = sha256_file(path)

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            token = f"field:{raw}" if side == "R:field" else raw
            return f"{_rel}:{li.find_occ(_p, token)}"

        for occurrences, prefer in ((scoring_occ, "factor"), (cond_occ, "column")):
            emit(out, source_kind="strategy_override", source_path=rel, source_id=path.stem,
                 source_sha=sha, enabled=enabled, path_scope="history",
                 occurrences=occurrences, gate_mode="production",
                 evidence_for=evidence_for, resolver=resolver, prefer=prefer)
    return len(files)


def _python_ctx_refs(source: str) -> list[str]:
    """`lang="python"` 分支：引用写在 `ctx["列名"]` 下标里，按 AST 取键。"""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        return []
    refs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            key = node.slice
            if node.value.id == "ctx" and isinstance(key, ast.Constant) and isinstance(key.value, str):
                refs.append(key.value)
    return sorted(set(refs))


def formula_occurrences(definition: dict) -> list[tuple[str, str]]:
    """一个因子定义引用到的列/因子，逐出现给出 (side, 名称)。

    composite → 每个 `members` 键一处；DSL → 编译器给出的 `referenced_factors` /
    `dependencies`（本身是集合，按「每名一处」处理）；`lang="python"` → `ctx["列名"]`。
    """
    kind = definition.get("kind") or "custom"
    if kind == "composite":
        members = definition.get("members")
        return [("members", str(m)) for m in members] if isinstance(members, dict) else []
    formula = definition.get("formula")
    if not isinstance(formula, str) or not formula.strip():
        return []
    lang = (definition.get("lang") or "dsl").strip() or "dsl"
    if lang != "dsl":
        return [("formula", name) for name in _python_ctx_refs(formula)]
    from app.factors.dsl import compile_formula

    compiled = compile_formula(formula)
    names = list(dict.fromkeys(list(compiled.referenced_factors) + list(compiled.dependencies)))
    return [("formula", name) for name in names]


def scan_custom_factors(user_data: Path, resolver: Resolver, li: LineIndex, out: list) -> int:
    directory = user_data / "custom_factors"
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        fid = str(data.get("id") or path.stem)
        rel = f"custom_factors/{path.name}"

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="custom_factor", source_path=rel, source_id=fid,
             source_sha=sha256_file(path), enabled=None, path_scope="history",
             occurrences=formula_occurrences(data), gate_mode="none",
             evidence_for=evidence_for, resolver=resolver, prefer="factor")
    return len(files)


def scan_strategy_configs(resolver: Resolver, out: list) -> int:
    directory = REPO_ROOT / SEEDS_REL
    files = sorted(directory.glob("*.py")) if directory.is_dir() else []
    scanned = 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        meta = None
        line_of: dict[str, int] = {}
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)):
                continue
            is_meta = any(isinstance(t, ast.Name) and t.id == "META" for t in node.targets)
            if not is_meta:
                continue
            for k, v in zip(node.value.keys, node.value.values, strict=False):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                line_of.setdefault(k.value, k.lineno)
                if k.value == "scoring" and isinstance(v, ast.Dict):
                    for sub in v.keys:
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            line_of.setdefault(sub.value, sub.lineno)
            try:
                meta = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                meta = None
        if not isinstance(meta, dict):
            continue
        scoring = meta.get("scoring")
        if not isinstance(scoring, dict) or not scoring:
            continue
        rel = f"{SEEDS_REL.as_posix()}/{path.name}"
        scanned += 1

        def evidence_for(side: str, raw: str, _rel: str = rel, _lo: dict = line_of) -> str:
            return f"{_rel}:{_lo.get(raw, 1)}"

        emit(out, source_kind="strategy_config", source_path=rel,
             source_id=str(meta.get("id") or path.stem), source_sha=sha256_file(path),
             enabled=None, path_scope="history",
             occurrences=[("scoring", str(k)) for k in scoring],
             gate_mode="production", evidence_for=evidence_for, resolver=resolver,
             prefer="factor")
    return scanned


def scan_research_strategies(resolver: Resolver, li: LineIndex, out: list) -> int:
    path = REPO_ROOT / RESEARCH_STRATEGY_REL
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    sha = sha256_file(path)
    rel = RESEARCH_STRATEGY_REL.as_posix()
    for strategy in data.get("strategies") or []:
        sid = str(strategy.get("id") or "?")
        occurrences: list[tuple[str, str]] = []
        for field_name, field in (strategy.get("fields") or {}).items():
            if not isinstance(field, dict):
                continue
            for name in _dedup(field.get("referenced_factors") or []):
                occurrences.append((f"fields.{field_name}", name))

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="research_strategy", source_path=rel, source_id=sid,
             source_sha=sha, enabled=None, path_scope="history",
             occurrences=occurrences, gate_mode="research",
             evidence_for=evidence_for, resolver=resolver, prefer="factor")
    return 1


# ---------------------------------------------------------------- 组装
def build_payload(*, data_dir: Path, generated_at: str) -> tuple[dict, dict]:
    """返回 (payload, meta)。meta 只供自检，不进 JSON。"""
    from app.factors.registry import all_factors
    from app.factors.store import load_into_registry
    from app.indicators.pipeline import ENRICHED_COLUMNS, ENRICHED_STORAGE_COLS
    from app.strategy.custom_signals import ALLOWED_FIELDS
    from app.strategy.intraday_features import INTRADAY_FEATURES

    user_data = Path(data_dir) / "user_data"
    # 与主程序同序（main.py:221）：自定义/复合因子载入注册表；该函数第一条调用就是
    # ensure_synced(data_dir)，扩展列因子因此先于公式解析注册（否则 ext_ 列判成未登记）。
    load_into_registry(Path(data_dir))
    specs = {spec.id: spec for spec in all_factors()}

    defs: dict = {}
    cf_dir = user_data / "custom_factors"
    cf_files = sorted(cf_dir.glob("*.json")) if cf_dir.is_dir() else []
    for cf in cf_files:
        try:
            definition = json.loads(cf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(definition, dict) and definition.get("id"):
            defs[str(definition["id"])] = definition

    allowed = frozenset(ALLOWED_FIELDS)
    enriched = frozenset(ENRICHED_COLUMNS)
    # 盘中路径的列集合：持久化列 + 当日单日行情即可算出的运行时列 + 分钟特征。
    # 指标列 (ma20/boll_*/rsi_*/...) 不落盘 —— ENRICHED_STORAGE_COLS 里没有它们，
    # 由 pipeline 在历史窗口上现算；单日快照自然没有 → 契约 §7.10.3 N3。
    intraday_cols = (frozenset(ENRICHED_STORAGE_COLS)
                     | {"limit_up_price", "limit_down_price"}
                     | frozenset(INTRADAY_FEATURES))
    resolver = Resolver(specs, defs, allowed, enriched, intraday_cols)
    li = LineIndex()
    records: list[dict] = []
    counts = {
        "custom_signal": scan_custom_signals(user_data, resolver, li, records),
        "monitor_rule": scan_monitor_rules(user_data, resolver, li, records),
        "strategy_override": scan_strategy_overrides(user_data, resolver, li, records),
        "custom_factor": scan_custom_factors(user_data, resolver, li, records),
        "strategy_config": scan_strategy_configs(resolver, records),
        "research_strategy": scan_research_strategies(resolver, li, records),
    }

    records.sort(key=_sort_key)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "canonical_sha256": "",          # 先占位，算完回填（不参与自身摘要）
        "repo_head": _git_head(),
        "data_root": str(user_data),
        "scanned_sources": sum(counts.values()),
        "records": records,
        "summary": _summary(records),
        "stale_count": 0,
        "notes": NOTES,
    }
    payload["canonical_sha256"] = canonical_digest(payload)
    meta = {"counts": counts, "data_dir": Path(data_dir), "user_data": user_data,
            "resolver": resolver}
    meta["defs"] = defs
    return payload, meta


def _count(records: list, key: str) -> dict:
    counts: dict[str, int] = {}
    for rec in records:
        value = rec[key]
        label = "null" if value is None else str(value)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _count_values(values: list) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        label = "null" if value is None else str(value)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))
def _sort_key(rec: dict) -> tuple:
    """稳定排序：按源 + 文件内行号 + 出现处，同源记录按文档顺序排。"""
    tail = rec["evidence"].rsplit(":", 1)[-1].split()[0] if rec["evidence"] else ""
    line = int(tail) if tail.isdigit() else 0
    return (rec["source_kind"], rec["source_path"], rec["source_id"], line,
            rec["side"], rec["ref_raw"], rec["ref_namespace"], rec["both_collision"])


def canonical_digest(payload: dict) -> str:
    """剔除 `generated_at` 与自身后的规范化 sha256 —— 签认用的稳定对象。

    F-A22 允许每次生成的 `generated_at` 不同，因此文件字节摘要（旁挂 `.sha256`）每次都变、
    无法绑定；本值对「除时间戳外的全部内容」按 `sort_keys=True` 序列化后取 sha256，
    同一输入两次生成必须相同。
    """
    core = {k: v for k, v in payload.items()
            if k not in {"generated_at", "canonical_sha256"}}
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


SOURCE_VERDICT_RANK = {"exempt": 0, "allow": 1, "shadow": 2, "block": 3, "unknown": 4}


def _source_verdicts(records: list[dict]) -> dict:
    """源级 verdict = 该源非伴生记录里最严的一条（block > shadow > allow > exempt）。"""
    worst: dict[tuple[str, str], str] = {}
    for rec in records:
        if rec["both_collision"]:
            continue
        key = (rec["source_kind"], rec["source_id"])
        cur = worst.get(key)
        if cur is None or SOURCE_VERDICT_RANK[rec["verdict"]] > SOURCE_VERDICT_RANK[cur]:
            worst[key] = rec["verdict"]
    return _count_values(list(worst.values()))


def _layer(records: list[dict], *, with_source_verdict: bool = False,
           with_source_kind: bool = False) -> dict:
    """一层计数：by_* 只覆盖非伴生记录（伴生记录不参与放行）。"""
    judged = [r for r in records if not r["both_collision"]]
    layer: dict = {
        "sources": len({(r["source_kind"], r["source_id"]) for r in records}),
        "records": len(records),
        "judged_records": len(judged),
        "companion_records": len(records) - len(judged),
        "by_verdict": _count(judged, "verdict"),
        "by_code": _count(judged, "code"),
        "by_namespace": _count(judged, "ref_namespace"),
        "by_class": _count(judged, "class"),
    }
    if with_source_verdict:
        layer["by_source_verdict"] = _source_verdicts(records)
    if with_source_kind:
        layer["by_source_kind"] = _count(records, "source_kind")
    return layer


def _summary(records: list[dict]) -> dict:
    """两层：`live_config` 是 L2 allowlist 的唯一读取面；`all_records` 只作观测。"""
    live = [r for r in records if r["source_enabled"] is True]
    return {
        "live_config": _layer(live, with_source_verdict=True),
        "all_records": _layer(records, with_source_kind=True),
    }


NOTES = [
    "记录粒度为一个结构化引用出现处（v2）：条件 left / right（裸名或 field:X）、"
    "monitor field、scoring 每个键、公式每个依赖名、composite 每个成员、"
    "research fields.<名> 各算一处，不按 (源 × 名字) 合并；同名出现两次 = 两条记录，"
    "由 side 与 evidence 区分。",
    "both_collision=true 是 F-A24 伴生记录（同一出现处的另一侧视图），verdict 恒为 exempt，"
    "不参与放行判定；summary 各层 by_* 计数只覆盖非伴生记录（judged_records）。",
    "summary.live_config = source_enabled=true 的活配置源，是 L2 allowlist 的唯一读取面；"
    "summary.all_records 只作全仓观测，不得用于放行。",
    "canonical_sha256 = 剔除 generated_at 与自身后按 sort_keys=True 规范化再取 sha256，"
    "用于签认；旁挂 .sha256 仍是本文件字节摘要，随 generated_at 变化（F-A22 允许）。",
]
def _git_head() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True, timeout=20)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _source_abs(rel: str, user_data: Path) -> Path:
    if rel.startswith(("backend/", "research/")):
        return REPO_ROOT / rel
    return user_data / rel


def recompute_stale(records: list, user_data: Path) -> int:
    """F-A26：按盘上字节重算 `source_sha256`，返回不符条数。"""
    digests: dict[str, str] = {}
    for rec in records:
        rel = rec["source_path"]
        if rel not in digests:
            try:
                digests[rel] = sha256_file(_source_abs(rel, user_data))
            except OSError:
                digests[rel] = ""
    return sum(1 for rec in records
               if digests.get(rec["source_path"]) != rec["source_sha256"])


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- 自检
def self_check(payload: dict, meta: dict) -> list[tuple[str, bool, str]]:
    records = payload["records"]
    summary = payload["summary"]
    live = summary["live_config"]
    allr = summary["all_records"]
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))

    # F-A22 清单幂等：同输入再生成一次，除 generated_at 外逐字节相同。
    second, _meta2 = build_payload(data_dir=meta["data_dir"],
                                   generated_at=payload["generated_at"])
    add("F-A22 幂等", dumps(second) == dumps(payload), "两次生成除 generated_at 外逐字节相同")
    add("canonical 稳定", second.get("canonical_sha256") == payload.get("canonical_sha256"),
        f"canonical_sha256={payload.get('canonical_sha256')}")

    # §7.10.2 记录字段固定且顺序固定（v2 追加 side）。
    bad = [r for r in records if tuple(r.keys()) != RECORD_FIELDS]
    add("§7.10.2 字段", not bad, f"{len(RECORD_FIELDS)} 字段 / {len(records)} 条，越界 {len(bad)} 条")

    # 逐出现粒度：同一 (源, side, 名字, 行) 不得重复（伴生记录算不同条）。
    keys = [(r["source_path"], r["side"], r["ref_raw"], r["evidence"], r["both_collision"])
            for r in records]
    add("逐出现唯一", len(keys) == len(set(keys)),
        f"{len(keys)} 条 / 去重后 {len(set(keys))} 条")

    # F-A25 无 unknown（非 0 时闸门拒绝启动）。
    unknown = [r for r in records if r["verdict"] == "unknown"]
    add("F-A25 无 unknown", not unknown, f"verdict=unknown {len(unknown)} 条")

    # F-A26 新鲜度。
    stale = recompute_stale(records, meta["user_data"])
    add("F-A26 新鲜度", stale == 0 and payload["stale_count"] == 0,
        f"stale_count 复算={stale} / 记录值={payload['stale_count']}")

    # 活配置层：22 源 / 79 条判定记录 / 14 条伴生 / 源级 22 allow。
    add("活配置源数", live["sources"] == EXPECTED_ENABLED_SOURCES,
        f"live sources={live['sources']}（期望 {EXPECTED_ENABLED_SOURCES}）")
    add("活配置 79 条判定", live["judged_records"] == EXPECTED_LIVE_RECORDS,
        f"judged={live['judged_records']}（期望 {EXPECTED_LIVE_RECORDS}）"
        f" by_verdict={live['by_verdict']}")
    add("活配置 14 条伴生", live["companion_records"] == EXPECTED_LIVE_COMPANIONS,
        f"companion={live['companion_records']}（期望 {EXPECTED_LIVE_COMPANIONS}）")
    sv = live["by_source_verdict"]
    add("源级 22 allow / 0 shadow / 0 block",
        sv.get("allow") == EXPECTED_ENABLED_SOURCES and not sv.get("shadow") and not sv.get("block"),
        f"by_source_verdict={sv}")

    # 全量层与 summary 自洽。
    add("全量记录数", allr["records"] == len(records) == EXPECTED_TOTAL_RECORDS,
        f"records={len(records)}（期望 {EXPECTED_TOTAL_RECORDS}）")
    add("summary 自洽",
        allr["judged_records"] + allr["companion_records"] == allr["records"]
        and live["records"] <= allr["records"]
        and set(summary) == {"live_config", "all_records"},
        f"live={live['records']} all={allr['records']} "
        f"（judged {allr['judged_records']} + companion {allr['companion_records']}）")

    # F-A24 命名空间冲突：4 个冲突名必须各有 column 侧记录，且伴生记录同步逐出现。
    coll_main = [r for r in records
                 if r["ref_raw"] in COLLISION_NAMES and r["ref_namespace"] == "column"
                 and not r["both_collision"]]
    companions = [r for r in records if r["both_collision"]]
    add("F-A24 冲突必报",
        {r["ref_raw"] for r in coll_main} == set(COLLISION_NAMES)
        and len(coll_main) == len(companions) == EXPECTED_LIVE_COMPANIONS,
        f"column 侧 {len(coll_main)} 条 / 伴生 {len(companions)} 条（期望各 "
        f"{EXPECTED_LIVE_COMPANIONS}）")

    # F-A23 结构化解析：散文/展示列不得计为引用。
    prose = [r for r in records
             if r["ref_raw"] in {"MA20", "MA5", "MA60"}
             or r["source_path"].endswith("preferences.json")
             or (r["source_id"] == "custom_mvoa5yy6"
                 and r["evidence"].startswith("strategy_overrides/custom_mvoa5yy6.json:3"))]
    add("F-A23 不 grep", not prose, f"散文/展示列误计 {len(prose)} 条")

    # 7 条冲突信号必须判 column（逐出现，全部）。
    wrong = []
    for sid in EXPECTED_COLLISION_SIGNALS:
        hits = [r for r in records if r["source_id"] == sid and not r["both_collision"]
                and r["ref_raw"] in COLLISION_NAMES]
        if not hits or any(r["ref_namespace"] != "column" for r in hits):
            wrong.append(sid)
    add("7 条冲突信号=column", not wrong, f"判错 {len(wrong)} 条 {wrong}")

    # 2 个 virtual 引用不判 block。
    virt = [r for r in records if r["ref_raw"] in EXPECTED_VIRTUAL_REFS]
    bad_virt = [r for r in virt if r["class"] != "virtual" or r["verdict"] == "block"]
    add("2 virtual 不拦", len({r["ref_raw"] for r in virt}) == 2 and not bad_virt,
        f"virtual 记录 {len(virt)} 条，判错 {len(bad_virt)} 条")

    # 分级放行的最终答案：按现在规则被 FS01 真拦几条。
    fs01 = [r for r in records if r["code"] == FS01]
    add("FS01 实拦", True, f"{len(fs01)} 条")

    # path_scope 取值：只记录真实求值路径；"both" 今天无来源（见报告 §4）。
    scopes = {r["path_scope"] for r in records}
    add("path_scope 无悬空 both", scopes <= {"history", "intraday"},
        f"取值集合 {sorted(scopes)}")

    # 反向对照（证明通道不是死代码，不是靠"永远不触发"得到 0）：
    # ① N3 分叉通道：ma20 在两条路径上确会分叉 → 必须判 block。
    reso = meta["resolver"]
    probe = reso.resolve("ma20", gate_mode="production", path_scope="both")
    add("N3 通道可触发", probe["divergence"] and probe["verdict"] == "block",
        "ma20 按 both 解析 → divergence="
        f"{probe['divergence']}, verdict={probe['verdict']}")

    # ② FS01 通道：活配置若真的把 draft 因子当因子用，必须拦。
    draft_ids = sorted(fid for fid, d in meta["defs"].items()
                       if (d.get("status") or "draft") == "draft")
    probes = [(fid, reso.resolve(fid, gate_mode="production", path_scope="history",
                                prefer="factor")) for fid in draft_ids]
    fired = [fid for fid, r in probes if r["verdict"] == "block" and r["code"] == FS01]
    add("FS01 通道可触发", bool(probes) and len(fired) == len(probes),
        f"试探 {len(probes)} 个 draft 定义，判 block+FS01 {len(fired)} 个")
    return results


# ---------------------------------------------------------------- 入口
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成 referenced_factor_inventory（契约 §7.10.2）")
    parser.add_argument("--data-dir", default=None,
                        help="应用数据根 (含 user_data/ 与 ext_data/)，缺省取应用设置")
    parser.add_argument("--out", default=None, help=f"输出路径，缺省 {OUT_REL.as_posix()}")
    parser.add_argument("--quiet", action="store_true", help="只打印自检结果")
    args = parser.parse_args(argv)

    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
    else:
        from app.config import settings

        data_dir = Path(settings.data_dir).resolve()
    out_path = Path(args.out).resolve() if args.out else (REPO_ROOT / OUT_REL)
    if not (data_dir / "user_data").is_dir():
        print(f"[error] data_dir 下没有 user_data: {data_dir}", file=sys.stderr)
        return 2

    generated_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
    payload, meta = build_payload(data_dir=data_dir, generated_at=generated_at)
    payload["stale_count"] = recompute_stale(payload["records"], meta["user_data"])

    results = self_check(payload, meta)
    text = dumps(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (out_path.parent / (out_path.name + ".sha256")).write_text(
        f"{digest}  {out_path.name}\n", encoding="utf-8", newline="\n")

    live = payload["summary"]["live_config"]
    allr = payload["summary"]["all_records"]
    if not args.quiet:
        print(f"data_root      : {payload['data_root']}")
        print(f"repo_head      : {payload['repo_head']}")
        print(f"scanned_sources: {payload['scanned_sources']}  {meta['counts']}")
        print(f"records        : {len(payload['records'])}")
        print(f"summary        : live={json.dumps(live, ensure_ascii=False)}")
        print(f"                 all={json.dumps(allr, ensure_ascii=False)}")
        print(f"stale_count    : {payload['stale_count']}")
        print(f"canonical      : {payload['canonical_sha256']}")
        print(f"out            : {out_path}")
        print(f"sha256         : {digest}")
    ok_all = True
    for name, ok, detail in results:
        ok_all = ok_all and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
