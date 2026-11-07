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

粒度（v2 / v0.6 §7.12.2）
  一条记录 = 一个**结构化引用出现处**，不按 (源 × 名字) 合并：条件表达式的 `left` /
  `right`、monitor 的 `conditions[].field`、`scoring` 的每个键、公式的每个依赖名、
  composite 的每个 `members` 键、research 的 `fields.<名>` 各自成条。同名引用在同一源
  出现两次 → 两条记录，`evidence` 行号不同。
  F-A24 伴生记录同样**按出现处一条**，`verdict` 恒 `exempt` 且不参与放行判定。

五个字面量字段（v0.6 §7.12.3，最易写错的地方）
  `ref_raw`   = 配置里的**字面量**，保留 `field:` 前缀（`field:ma60`），不剥不改；
  `ref_name`  = `ref_raw` 去前缀 + trim（`ma60`）—— 分类、解析、allowlist 比对只用它；
  `side`      = 表达式槽位，只允许 `L` / `R` / `F`（左值 / 右值 / monitor 条件字段）；
  `side_key`  = 结构键路径（`scoring` / `formula` / `members` / `fields.<名>`），可选，
                只做人读定位，**不参与任何判据、不进 allowlist、不进唯一键**；
  `path_base` = `repo`（仓库根）或 `data`（`data_root` 相对路径，不带 `user_data/` 前缀）。
  结构键引用没有表达式槽位、契约又只给三个取值：本脚本统一记 `side=L`（被引用的值槽），
  结构路径进 `side_key`。这是契约留白处，已在报告里登记为待架构师追认。

canonical digest（§7.12.4，唯一签认对象，可复算）
  剔除 `generated_at` / `repo_head` / `data_root` / `canonical_digest` 四键 → `records`
  按每条记录自身的规范化 JSON 排成与输入顺序无关的全序 → 整体
  `ensure_ascii=False, sort_keys=True, separators=(',',':')` → sha256。旁挂 `.sha256`
  取全文哈希、含 `generated_at`，只证明「本次运行字节完整」，不作签认对象、不作比对基准。

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

SCHEMA_VERSION = "2"   # v0.6 §7.10.2：逐出现粒度 + 五字面量字段 + 分层 summary
CN_TZ = timezone(timedelta(hours=8))
OUT_REL = Path("docs/architecture/evidence/referenced_factor_inventory.json")
RESEARCH_STRATEGY_REL = Path("research/strategy-search-20261107/factor_map_v1.json")
SEEDS_REL = Path("backend/app/strategy/seeds")

# 记录字段顺序 = 契约 §7.10.2 v0.6 表序（`path_divergence` / `both_collision` / `side` /
# `ref_name` / `record_kind` / `side_key` / `path_base` 都在表内）+ `note`。
# `note` 是表外唯一附录字段：把伴生记录的注释从 `evidence` 搬出来（§7.12.2 不许夹注释），
# 主记录恒 null。
RECORD_FIELDS: tuple[str, ...] = (
    "source_kind", "source_path", "source_id", "source_sha256", "source_enabled",
    "path_scope", "ref_raw", "ref_name", "ref_namespace", "resolved_id", "class",
    "verifiable", "gate_mode", "verdict", "code", "evidence", "both_collision",
    "path_divergence", "side", "side_key", "record_kind", "path_base", "note",
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

# §7.12.3：字面量前缀（`ref_raw` 保留、`ref_name` 去掉）与 `side` 的合法取值域。
REF_PREFIXES = ("field", "column", "signal")
SIDE_VALUES = ("L", "R", "F")
# §7.12.4：canonical digest 的剔除键（自指 + 与机器/时刻相关的三个）。
CANONICAL_DROP = ("generated_at", "repo_head", "data_root", "canonical_digest")
# §7.12.2：`evidence` 必须是 `path:line` 或 `path:start-end`，不得夹注释。
EVIDENCE_RE = re.compile(r"^.+?:\d+(?:-\d+)?$")


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
def split_prefix(literal: str) -> tuple[str, str | None]:
    """`field:X` / `column:X` / `signal:X` → `(X, 'field')`；无前缀 → `(literal, None)`。

    §7.12.3：字面量原样留在 `ref_raw`，归一化名只进 `ref_name`；分类与解析一律用后者。
    """
    text = literal.strip()
    for prefix in REF_PREFIXES:
        head = f"{prefix}:"
        if text.startswith(head):
            return text[len(head):].strip(), prefix
    return text, None


def emit(out: list, *, source_kind: str, source_path: str, source_id: str,
         source_sha: str, enabled, path_scope: str,
         occurrences: list[tuple[str, str, str | None]], gate_mode: str,
         evidence_for: Callable[[str, str], str], resolver: Resolver,
         path_base: str, prefer: str = "column") -> None:
    """按**出现处**逐条产出记录。

    `occurrences` 是 `(side, ref_raw, side_key)` 的有序列表，每个元素一条主记录，
    不再按名字去重：
      * `side` ∈ {L,R,F}（§7.10.2 v0.6：左值 / 右值 / monitor 条件字段）；
      * `ref_raw` 是配置里的字面量（保留 `field:` 前缀）；
      * `side_key` 是结构键路径（`scoring` / `formula` / `members` / `fields.<名>`），
        不参与判定、不进 allowlist、不进唯一键。
    伴生记录（F-A24）与主记录成对产出，`record_kind=companion` + `both_collision=true`
    双重标记，唯一键靠 `record_kind` 与主记录区分。
    """
    for side, literal, side_key in occurrences:
        if not isinstance(literal, str) or not literal.strip():
            continue
        name, _prefix = split_prefix(literal)
        if not name:
            continue
        res = resolver.resolve(name, gate_mode=gate_mode, path_scope=path_scope, prefer=prefer)
        # 只有「因子侧要过闸门」的同名才算冲突（base/virtual 本来就 exempt，撞名无风险）。
        spec = resolver.specs.get(name)
        both = (name in resolver.allowed) and spec is not None and resolver.factor_class(spec) in {
            "custom_dsl", "custom_python", "composite"}
        out.append({
            "source_kind": source_kind,
            "source_path": source_path,
            "source_id": source_id,
            "source_sha256": source_sha,
            "source_enabled": enabled,
            "path_scope": path_scope,
            "ref_raw": literal.strip(),
            "ref_name": name,
            "ref_namespace": res["namespace"],
            "resolved_id": res["resolved_id"],
            "class": res["class"],
            "verifiable": res["verifiable"],
            "gate_mode": gate_mode,
            "verdict": res["verdict"],
            "code": res["code"],
            "evidence": evidence_for(side, literal.strip()),
            "both_collision": False,
            "path_divergence": res["divergence"],
            "side": side,
            "side_key": side_key,
            "record_kind": "primary",
            "path_base": path_base,
            "note": None,
        })
        if both:
            # F-A24：命名空间冲突的伴生记录 —— 同一出现处的**因子侧视图**，仅登记，
            # 不参与放行；注释走 `note`，`evidence` 只留 `path:line`（§7.12.2）。
            companion = dict(out[-1])
            if companion["ref_namespace"] == "column":
                companion.update({
                    "ref_namespace": "factor",
                    "resolved_id": name,
                    "class": resolver.factor_class(resolver.specs[name]),
                    "verifiable": resolver.verifiable(name),
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
            companion["record_kind"] = "companion"
            companion["note"] = ("N2 伴生记录: 同名字面量同时命中 ALLOWED_FIELDS 与因子注册表, "
                                 "按 N1 基础列优先, 伴生仅登记冲突, 不参与放行")
            out.append(companion)


def _dedup(seq) -> list[str]:
    out: list[str] = []
    for item in seq:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return out


def _condition_occurrences(cond: dict, allowed: frozenset) -> list[tuple[str, str, str | None]]:
    """条件表达式的**逐出现**结构化引用：`(side, ref_raw, side_key)`。

    `left` → `side=L`，字面量原样；`right` 写成 `field:X` → `side=R` 且 `ref_raw="field:X"`
    （前缀保留，`ref_name` 去前缀）；`right` 直接写白名单列名 → `side=R`；数字右值不是
    引用，不产记录（与 `custom_signals._parse_right` 同口径）。条件里没有结构键，
    故 `side_key` 恒 None。
    """
    occ: list[tuple[str, str, str | None]] = []
    left = cond.get("left")
    if isinstance(left, str) and left.strip():
        occ.append(("L", left.strip(), None))
    right = cond.get("right")
    if isinstance(right, str) and right.strip():
        text = right.strip()
        name, prefix = split_prefix(text)
        if prefix is not None or name in allowed:
            occ.append(("R", text, None))
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
        # 显式跳过 timeframe != intraday，日线信号只在历史帧上求值（N4 / F-A38）。
        path_scope = "intraday" if timeframe == "intraday" else "history"
        occurrences: list[tuple[str, str, str | None]] = []
        for cond in data.get("conditions") or []:
            if isinstance(cond, dict):
                occurrences.extend(_condition_occurrences(cond, resolver.allowed))
        rel = f"custom_signals/{path.name}"

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            # `raw` 就是文件里的字面量（含 `field:` 前缀），按字面量定位即落在正确行。
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="custom_signal", source_path=rel,
             source_id=str(data.get("id") or path.stem), source_sha=sha256_file(path),
             enabled=enabled, path_scope=path_scope, occurrences=occurrences,
             gate_mode="production", evidence_for=evidence_for, resolver=resolver,
             path_base="data")
    return len(files)


def scan_monitor_rules(user_data: Path, resolver: Resolver, li: LineIndex, out: list) -> int:
    directory = user_data / "monitor_rules"
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        enabled = data.get("enabled")
        enabled = None if enabled is None else bool(enabled)
        occurrences: list[tuple[str, str, str | None]] = []
        for cond in data.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            field = cond.get("field")
            if not isinstance(field, str) or not field:
                continue
            # op=truth 时 field 是信号列（signal_/csg_），不是因子/列引用 → 不产记录。
            if cond.get("op") == "truth" or field.startswith(SIGNAL_PREFIXES):
                continue
            # monitor 规则的引用槽位固定是 `conditions[].field` → `side=F`（§7.12.3）。
            occurrences.append(("F", field.strip(), None))
        rel = f"monitor_rules/{path.name}"

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="monitor_rule", source_path=rel,
             source_id=str(data.get("id") or path.stem), source_sha=sha256_file(path),
             enabled=enabled, path_scope="intraday", occurrences=occurrences,
             gate_mode="production", evidence_for=evidence_for, resolver=resolver,
             path_base="data")
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
        scoring_occ = ([("L", str(k), "scoring") for k in scoring]
                       if isinstance(scoring, dict) else [])
        cond_occ: list[tuple[str, str, str | None]] = []
        for cond in data.get("overlay_filter") or []:
            if isinstance(cond, dict):
                cond_occ.extend(_condition_occurrences(cond, resolver.allowed))
        rel = f"strategy_overrides/{path.name}"
        sha = sha256_file(path)

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        for occurrences, prefer in ((scoring_occ, "factor"), (cond_occ, "column")):
            emit(out, source_kind="strategy_override", source_path=rel, source_id=path.stem,
                 source_sha=sha, enabled=enabled, path_scope="history",
                 occurrences=occurrences, gate_mode="production",
                 evidence_for=evidence_for, resolver=resolver, path_base="data",
                 prefer=prefer)
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


def formula_occurrences(definition: dict) -> list[tuple[str, str, str | None]]:
    """一个因子定义引用到的列/因子，按出现处给出 `(side, ref_raw, side_key)`。

    composite → 每个 `members` 键一处；DSL → 编译器给出的 `referenced_factors` /
    `dependencies`（本身是集合，按「每名一处」处理）；`lang="python"` → `ctx["列名"]`。
    三者都不是表达式槽位：`side` 记 `L`（值槽），结构路径进 `side_key`。
    """
    kind = definition.get("kind") or "custom"
    if kind == "composite":
        members = definition.get("members")
        return [("L", str(m), "members") for m in members] if isinstance(members, dict) else []
    formula = definition.get("formula")
    if not isinstance(formula, str) or not formula.strip():
        return []
    lang = (definition.get("lang") or "dsl").strip() or "dsl"
    if lang != "dsl":
        return [("L", name, "formula") for name in _python_ctx_refs(formula)]
    from app.factors.dsl import compile_formula
    compiled = compile_formula(formula)
    names = list(dict.fromkeys(list(compiled.referenced_factors) + list(compiled.dependencies)))
    return [("L", name, "formula") for name in names]


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
             evidence_for=evidence_for, resolver=resolver, path_base="data",
             prefer="factor")
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
             occurrences=[("L", str(k), "scoring") for k in scoring],
             gate_mode="production", evidence_for=evidence_for, resolver=resolver,
             path_base="repo", prefer="factor")
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
        occurrences: list[tuple[str, str, str | None]] = []
        for field_name, field in (strategy.get("fields") or {}).items():
            if not isinstance(field, dict):
                continue
            for name in _dedup(field.get("referenced_factors") or []):
                occurrences.append(("L", name, f"fields.{field_name}"))

        def evidence_for(side: str, raw: str, _p: Path = path, _rel: str = rel) -> str:
            return f"{_rel}:{li.find_occ(_p, raw)}"

        emit(out, source_kind="research_strategy", source_path=rel, source_id=sid,
             source_sha=sha, enabled=None, path_scope="history",
             occurrences=occurrences, gate_mode="research",
             evidence_for=evidence_for, resolver=resolver, path_base="repo",
             prefer="factor")
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
        "canonical_digest": "",          # 先占位，算完回填（计算时剔除自身）
        "repo_head": _git_head(),
        "data_root": str(user_data),
        "scanned_sources": sum(counts.values()),
        "records": records,
        "summary": _summary(records),
        "stale_count": 0,
        "notes": NOTES,
    }
    # stale 必须在算 digest 之前落定：digest 覆盖除四键外的全部内容，事后改 stale
    # 会让「外部按 §7.12.4 复算」与落盘值不等（F-A36）。
    payload["stale_count"] = recompute_stale(records, user_data)
    payload["canonical_digest"] = canonical_digest(payload)
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
    """稳定排序：按源 + 行号 + 槽位 + 结构键，同源记录按文档顺序排。"""
    tail = rec["evidence"].rsplit(":", 1)[-1].split("-")[0]
    line = int(tail) if tail.isdigit() else 0
    return (rec["source_kind"], rec["source_path"], rec["source_id"], line,
            rec["side"], rec["side_key"] or "", rec["ref_name"],
            0 if rec["record_kind"] == "primary" else 1)


def _rk(obj) -> str:
    """§7.12.4 的规范化序列化：`ensure_ascii=False` + `sort_keys` + 紧凑分隔符。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_digest(payload: dict) -> str:
    """§7.12.4 原样实现：剔除四键 → `records` 按 `rk` 全序 → 整体 `rk` → sha256。

    与旁挂 `.sha256` 的分工：本值不含 `generated_at` / `repo_head` / `data_root`，
    与机器和运行时刻无关，是签认对象；旁挂只证明「本次运行字节完整」（F-A22）。
    """
    core = {k: v for k, v in payload.items() if k not in CANONICAL_DROP}
    core["records"] = sorted(core.get("records", []), key=_rk)
    return hashlib.sha256(_rk(core).encode("utf-8")).hexdigest()


SOURCE_VERDICT_RANK = {"exempt": 0, "allow": 1, "shadow": 2, "block": 3, "unknown": 4}


def _source_verdicts(records: list[dict]) -> dict:
    """源级 verdict = 该源 primary 记录里最严的一条（block > shadow > allow > exempt）。"""
    worst: dict[tuple[str, str], str] = {}
    for rec in records:
        if rec["record_kind"] != "primary":
            continue
        key = (rec["source_kind"], rec["source_id"])
        cur = worst.get(key)
        if cur is None or SOURCE_VERDICT_RANK[rec["verdict"]] > SOURCE_VERDICT_RANK[cur]:
            worst[key] = rec["verdict"]
    return _count_values(list(worst.values()))


def _layer(records: list[dict], *, live: bool) -> dict:
    """一层计数。**任何层的 `by_*` 只覆盖 primary 记录**（§7.12.5 / F-A35）。

    伴生只出现在 `by_record_kind.companion`，因此机械上无法混进 `by_verdict`：
    两条记录靠 `record_kind` 分流，不靠 `both_collision` 的语义解释。
    """
    primary = [r for r in records if r["record_kind"] == "primary"]
    layer: dict = {
        "sources": len({(r["source_kind"], r["source_id"]) for r in records}),
        "records": len(records),
        "by_record_kind": _count(records, "record_kind"),
        "by_verdict": _count(primary, "verdict"),
        "by_code": _count(primary, "code"),
        "by_namespace": _count(primary, "ref_namespace"),
        "by_class": _count(primary, "class"),
        "by_path_scope": _count(primary, "path_scope"),
        "by_verdict_sources": _source_verdicts(records),
    }
    if not live:
        layer["by_source_kind"] = _count(records, "source_kind")
    return layer


def _summary(records: list[dict]) -> dict:
    """两层 + v1 兼容别名。

    `live_config`（`source_enabled=true` 的源）是 L2 allowlist 的**唯一**读取面；
    `all_records` 只作全仓观测；`by_verdict` / `by_code` / `by_namespace` 三个顶层键
    是 v1 读取方的别名，值必须等于 `all_records`（F-A35 断言）。
    """
    live = [r for r in records if r["source_enabled"] is True]
    all_records = _layer(records, live=False)
    summary: dict = {
        "live_config": _layer(live, live=True),
        "all_records": all_records,
    }
    summary["by_verdict"] = dict(all_records["by_verdict"])
    summary["by_code"] = dict(all_records["by_code"])
    summary["by_namespace"] = dict(all_records["by_namespace"])
    return summary


NOTES = [
    "记录粒度 = 一个结构化引用出现处（契约 §7.12.2）：条件 left / right、monitor "
    "conditions[].field、scoring 每个键、公式每个依赖名、composite 每个成员、research "
    "fields.<名> 各算一处，不按 (源 × 名字) 合并；同名两处 = 两条记录，由 evidence 行号区分。",
    "ref_raw 保留配置里的字面量（含 field: 前缀），ref_name = 去前缀 + trim 后的名字，"
    "分类/解析/allowlist 比对只用 ref_name（§7.12.3）；side ∈ {L,R,F} 是表达式槽位，"
    "结构键路径（scoring/formula/members/fields.<名>）只进 side_key，不参与判定、不进唯一键。",
    "both_collision=true 且 record_kind=companion 的是 F-A24 伴生记录（同一出现处的因子侧"
    "视图），verdict 恒 exempt，注释在 note 字段、evidence 只含 path:line；伴生不参与放行，"
    "不进入任何层的 by_verdict，只在 by_record_kind.companion 计数（§7.12.5 / F-A35）。",
    "summary.live_config = source_enabled=true 的活配置源，是 L2 allowlist 的唯一读取面；"
    "summary.all_records 只作全仓观测；summary.by_verdict / by_code / by_namespace 是 v1 "
    "兼容别名，值与 all_records 对应项相等。",
    "canonical_digest = §7.12.4：剔除 generated_at / repo_head / data_root / canonical_digest "
    "四键，records 按每条记录的规范化 JSON 全序，整体 ensure_ascii=False + sort_keys + "
    "separators=(',',':') 后取 sha256；签认、产物比对、闸门读取一律用它。旁挂 .sha256 取全文"
    "哈希、含 generated_at，每次重跑必变，只证明本次运行字节完整（F-A22 不作比对基准）。",
    "结构键引用没有表达式槽位、契约 side 只有三值：本产物统一记 side=L（被引用的值槽）并把"
    "结构路径写进 side_key；此处为契约留白，待架构师追认（改动面为 emit 调用处的常量）。",
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


# ---------------------------------------------------------------- v1 / v2 读取规则
class InventoryError(RuntimeError):
    """清单不可用（F-A39 / F-A25 / F-A26 的 fail-closed 出口）。"""


def normalize_inventory(payload: dict, *, level: str = "L0") -> dict:
    """按 §7.12.6 / F-A39 的降级读取规则校验并归一化，返回可用视图。

    `"1"`：可读，`ref_name := ref_raw`、`side := None`、`record_kind := "primary"`；
           只许 L0/L1，要求 L2/L3 一律拒绝启动。
    `"2"`：缺任一新增字段、或 `side` 越界 → 拒绝加载（fail-closed）。
    """
    version = payload.get("schema_version")
    if version == "1":
        if level in {"L2", "L3"}:
            raise InventoryError(f'schema_version=1 只允许 L0/L1，不许在 {level} 使用')
        records = []
        for rec in payload.get("records") or []:
            item = dict(rec)
            item.setdefault("ref_name", item.get("ref_raw"))
            item.setdefault("side", None)
            item.setdefault("record_kind", "primary")
            item.setdefault("path_base", None)
            records.append(item)
        return {"schema_version": "1", "records": records}
    if version != "2":
        raise InventoryError(f"未知 schema_version={version!r}")
    missing_top = [k for k in ("canonical_digest", "summary", "records") if k not in payload]
    if missing_top:
        raise InventoryError(f"schema_version=2 缺顶层字段 {missing_top}")
    need = ("ref_name", "record_kind", "path_base", "side")
    bad = [i for i, rec in enumerate(payload["records"])
           if any(f not in rec for f in need)]
    if bad:
        raise InventoryError(f"schema_version=2 的记录缺新增字段，索引 {bad[:5]}")
    out_of_range = [i for i, rec in enumerate(payload["records"])
                    if rec["side"] not in SIDE_VALUES]
    if out_of_range:
        raise InventoryError(f"side 越界（只允许 {SIDE_VALUES}），索引 {out_of_range[:5]}")
    return {"schema_version": "2", "records": payload["records"]}


# ---------------------------------------------------------------- 自检
def _independent_digest(payload: dict) -> str:
    """§7.12.4 的**第二份**实现（逐字照抄契约代码），用于交叉验证落盘值。

    与 `canonical_digest()` 分开写：哪一份写错都会在这里对不上，避免「自己验自己」。
    """
    drop = {"generated_at", "repo_head", "data_root", "canonical_digest"}

    def rk(x) -> str:
        return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    q = {k: v for k, v in payload.items() if k not in drop}
    q["records"] = sorted(q.get("records", []), key=rk)
    blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def self_check(payload: dict, meta: dict) -> list[tuple[str, bool, str]]:
    records = payload["records"]
    summary = payload["summary"]
    live = summary["live_config"]
    allr = summary["all_records"]
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))

    # ---- F-A22 幂等：同一 generated_at 再生成一次，逐字节相同 + digest 相同。
    second, _meta2 = build_payload(data_dir=meta["data_dir"],
                                   generated_at=payload["generated_at"])
    add("F-A22 幂等(字节)", dumps(second) == dumps(payload), "两次生成除 generated_at 外逐字节相同")
    add("F-A22 幂等(digest)", second["canonical_digest"] == payload["canonical_digest"],
        f"canonical_digest={payload['canonical_digest']}")

    # ---- F-A36 digest 可复算 + 对无关扰动稳定 + 对内容敏感。
    add("F-A36 外部复算", _independent_digest(payload) == payload["canonical_digest"],
        f"§7.12.4 复算={_independent_digest(payload)}")
    perturbed = json.loads(json.dumps(payload))
    perturbed["generated_at"] = "1999-01-01T00:00:00+08:00"
    perturbed["repo_head"] = "0" * 40
    perturbed["data_root"] = "X:/elsewhere/user_data"
    perturbed["records"] = list(reversed(perturbed["records"]))
    add("F-A36 扰动不变", _independent_digest(perturbed) == payload["canonical_digest"],
        "改 generated_at/repo_head/data_root + records 倒序 → digest 不变")
    flipped = json.loads(json.dumps(payload))
    for rec in flipped["records"]:
        if rec["record_kind"] == "primary":
            rec["verdict"] = "block" if rec["verdict"] != "block" else "allow"
            break
    add("F-A36 改 verdict 必变", _independent_digest(flipped) != payload["canonical_digest"],
        "改 1 条 primary 的 verdict → digest 变化")

    # ---- §7.10.2 字段固定且顺序固定。
    bad_fields = [r for r in records if tuple(r.keys()) != RECORD_FIELDS]
    add("§7.10.2 字段", not bad_fields,
        f"{len(RECORD_FIELDS)} 字段 / {len(records)} 条，越界 {len(bad_fields)} 条")

    # ---- F-A34 粒度与唯一键。
    keys = [(r["source_path"], r["evidence"], r["side"], r["ref_name"], r["record_kind"])
            for r in records]
    add("F-A34 唯一键", len(keys) == len(set(keys)),
        f"{len(keys)} 条 / 去重 {len(set(keys))} 条（键 = path+evidence+side+ref_name+record_kind）")
    add("F-A34 活配置 93=79+14",
        live["records"] == EXPECTED_LIVE_RECORDS + EXPECTED_LIVE_COMPANIONS
        and live["by_record_kind"].get("primary") == EXPECTED_LIVE_RECORDS
        and live["by_record_kind"].get("companion") == EXPECTED_LIVE_COMPANIONS,
        f"live records={live['records']} by_record_kind={live['by_record_kind']}")
    mg = [r for r in records if r["source_id"] == "ma_golden_20_60"]
    mg_prim = sorted((int(r["evidence"].rsplit(":", 1)[-1]), r["side"], r["ref_raw"])
                     for r in mg if r["record_kind"] == "primary")
    mg_comp = [r for r in mg if r["record_kind"] == "companion"]
    want = [(9, "L", "ma20"), (11, "R", "field:ma60"),
            (16, "L", "ma20"), (18, "R", "field:ma60")]
    add("F-A34 ma_golden_20_60 4 主 + 4 伴生",
        mg_prim == want and len(mg_comp) == 4,
        f"主={mg_prim} / 伴生={len(mg_comp)}")

    # ---- F-A35 summary 分层自洽（含反例证明有区分力）。
    add("F-A35 层内求和=primary",
        sum(allr["by_verdict"].values()) == allr["by_record_kind"].get("primary", -1)
        and sum(live["by_verdict"].values()) == live["by_record_kind"].get("primary", -1),
        f"all {sum(allr['by_verdict'].values())}=={allr['by_record_kind'].get('primary')}"
        f" / live {sum(live['by_verdict'].values())}=={live['by_record_kind'].get('primary')}")
    add("F-A35 v1 别名等值",
        summary["by_verdict"] == allr["by_verdict"]
        and summary["by_code"] == allr["by_code"]
        and summary["by_namespace"] == allr["by_namespace"],
        f"summary.by_verdict={summary['by_verdict']} == all_records.by_verdict")
    add("F-A35 live 22 源", live["sources"] == EXPECTED_ENABLED_SOURCES,
        f"live sources={live['sources']}（期望 {EXPECTED_ENABLED_SOURCES}）")
    poisoned = dict(allr["by_verdict"])
    poisoned["exempt"] = poisoned.get("exempt", 0) + allr["by_record_kind"].get("companion", 0)
    add("F-A35 反例可失败", sum(poisoned.values()) != allr["by_record_kind"].get("primary", -1),
        f"把伴生 {allr['by_record_kind'].get('companion')} 条计入 → 求和 "
        f"{sum(poisoned.values())} ≠ primary {allr['by_record_kind'].get('primary')}")

    # ---- F-A37 字面量与定位符。
    prefixed = [r for r in records if r["ref_raw"] != r["ref_name"]]
    bad_name = [r for r in records if r["ref_name"] != split_prefix(r["ref_raw"])[0]]
    sides = sorted({r["side"] for r in records})
    bad_ev = [r for r in records if "#" in r["evidence"] or not EVIDENCE_RE.match(r["evidence"])]
    bad_side_key = [r for r in records if r["side_key"] is not None
                    and not (r["side_key"] in {"scoring", "formula", "members"}
                             or r["side_key"].startswith("fields."))]
    add("F-A37 ref_raw 保留前缀",
        len(prefixed) >= 36 and not bad_name,
        f"带前缀 {len(prefixed)} 条（field:），ref_name 去前缀错 {len(bad_name)} 条")
    add("F-A37 side 三值", set(sides) <= set(SIDE_VALUES) and all(r["side"] for r in records),
        f"取值集合 {sides}")
    add("F-A37 evidence 可解析", not bad_ev,
        f"含 # 或不可解析 {len(bad_ev)} 条（正则 `path:line` / `path:start-end`）")
    add("F-A37 结构键只进 side_key", not bad_side_key,
        f"side_key 取值 {sorted({r['side_key'] for r in records if r['side_key']})}")

    # ---- F-A38 path_scope 与 both。
    scopes = sorted({r["path_scope"] for r in records})
    daily = [r for r in records if r["source_kind"] == "custom_signal"]
    mon = [r for r in records if r["source_kind"] == "monitor_rule"]
    div = [r for r in records if r["path_divergence"]]
    coll_src = [r for r in records if r["source_id"] in EXPECTED_COLLISION_SIGNALS
                and r["record_kind"] == "primary"]
    add("F-A38 path_scope ⊆ {history,intraday}",
        set(scopes) <= {"history", "intraday"},
        f"取值集合 {scopes}，both 计数 0")
    add("F-A38 21 日线 history + 1 monitor intraday",
        len({r["source_id"] for r in daily}) == 21
        and all(r["path_scope"] == "history" for r in daily)
        and bool(mon) and all(r["path_scope"] == "intraday" for r in mon),
        f"日线源 {len({r['source_id'] for r in daily})} / monitor 记录 {len(mon)}")
    add("F-A38 path_divergence 0", not div, f"{len(div)} 条")
    add("F-A38 7 条冲突源 allow",
        {r["source_id"] for r in coll_src} == set(EXPECTED_COLLISION_SIGNALS)
        and all(r["verdict"] == "allow" for r in coll_src),
        f"{len({r['source_id'] for r in coll_src})} 源 / verdict "
        f"{sorted({r['verdict'] for r in coll_src})}")

    # ---- F-A39 v1 兼容与降级边界（读取规则在 normalize_inventory，用合成对象测）。
    v1 = {"schema_version": "1",
          "records": [{"ref_raw": "ma20", "ref_namespace": "column", "verdict": "allow"}]}
    try:
        view1 = normalize_inventory(v1, level="L1")
        first = view1["records"][0]
        v1_ok = (first["ref_name"] == "ma20" and first["side"] is None
                 and first["record_kind"] == "primary")
    except InventoryError:
        v1_ok = False
    add("F-A39 v1 降级可读", v1_ok, 'ref_name:=ref_raw / side:=null / record_kind:="primary"')
    try:
        normalize_inventory(v1, level="L2")
        v1_refused = False
    except InventoryError:
        v1_refused = True
    add("F-A39 v1 不许 L2/L3", v1_refused, '读 "1" 却要求 L2 → 拒绝启动')
    broken = json.loads(json.dumps(payload))
    broken["records"][0].pop("path_base")
    broken["records"][0].pop("ref_name")
    try:
        normalize_inventory(broken, level="L0")
        v2_refused = False
    except InventoryError:
        v2_refused = True
    add("F-A39 v2 缺字段拒绝加载", v2_refused, '"2" 且缺新增字段 → 拒绝加载')

    # ---- F-A25 / F-A26。
    unknown = [r for r in records if r["verdict"] == "unknown"]
    add("F-A25 无 unknown", not unknown, f"verdict=unknown {len(unknown)} 条")
    stale = recompute_stale(records, meta["user_data"])
    add("F-A26 新鲜度", stale == 0 and payload["stale_count"] == 0,
        f"stale_count 复算={stale} / 记录值={payload['stale_count']}")

    # ---- 活配置面：22 源 / 79 条判定 / 14 条伴生 / 源级 22 allow。
    sv = live["by_verdict_sources"]
    add("源级 22 allow / 0 shadow / 0 block",
        sv.get("allow") == EXPECTED_ENABLED_SOURCES and not sv.get("shadow") and not sv.get("block"),
        f"by_verdict_sources={sv}")
    add("活配置 by_verdict 全 allow",
        live["by_verdict"] == {"allow": EXPECTED_LIVE_RECORDS},
        f"live.by_verdict={live['by_verdict']}")
    add("全量记录数", allr["records"] == len(records) == EXPECTED_TOTAL_RECORDS,
        f"records={len(records)}（期望 {EXPECTED_TOTAL_RECORDS}）")
    add("summary 结构",
        set(summary) == {"live_config", "all_records", "by_verdict", "by_code", "by_namespace"},
        f"summary 键={sorted(summary)}")

    # ---- F-A24 命名空间冲突必须报：4 个冲突名各有 column 主记录 + 伴生同步逐出现。
    coll_main = [r for r in records
                 if r["ref_name"] in COLLISION_NAMES and r["ref_namespace"] == "column"
                 and r["record_kind"] == "primary"]
    companions = [r for r in records if r["record_kind"] == "companion"]
    add("F-A24 冲突必报",
        {r["ref_name"] for r in coll_main} == set(COLLISION_NAMES)
        and len(coll_main) == len(companions) == EXPECTED_LIVE_COMPANIONS
        and all(r["both_collision"] and r["verdict"] == "exempt" and r["note"]
                for r in companions)
        and all(r["class"] == "custom_dsl" and r["resolved_id"] for r in companions),
        f"column 主 {len(coll_main)} / 伴生 {len(companions)}（期望各 "
        f"{EXPECTED_LIVE_COMPANIONS}），伴生形态=factor 视图(class=custom_dsl)")

    # ---- F-A23 结构化解析：散文/展示列不得计为引用。
    prose = [r for r in records
             if r["ref_name"] in {"MA20", "MA5", "MA60"}
             or r["source_path"].endswith("preferences.json")
             or (r["source_id"] == "custom_mvoa5yy6"
                 and r["evidence"].startswith("strategy_overrides/custom_mvoa5yy6.json:3"))]
    add("F-A23 不 grep", not prose, f"散文/展示列误计 {len(prose)} 条")

    # ---- 7 条冲突信号必须判 column（逐出现，全部）。
    wrong = []
    for sid in EXPECTED_COLLISION_SIGNALS:
        hits = [r for r in records if r["source_id"] == sid and r["record_kind"] == "primary"
                and r["ref_name"] in COLLISION_NAMES]
        if not hits or any(r["ref_namespace"] != "column" for r in hits):
            wrong.append(sid)
    add("7 条冲突信号=column", not wrong, f"判错 {len(wrong)} 条 {wrong}")

    # ---- 2 个 virtual 引用不判 block。
    virt = [r for r in records if r["ref_name"] in EXPECTED_VIRTUAL_REFS]
    bad_virt = [r for r in virt if r["class"] != "virtual" or r["verdict"] == "block"]
    add("2 virtual 不拦", len({r["ref_name"] for r in virt}) == 2 and not bad_virt,
        f"virtual 记录 {len(virt)} 条，判错 {len(bad_virt)} 条")

    # ---- 分级放行的最终答案：按现在规则被 FS01 真拦几条。
    fs01 = [r for r in records if r["code"] == FS01]
    add("FS01 实拦", not fs01, f"{len(fs01)} 条")

    # ---- 反向对照（证明通道不是死代码，不是靠「永远不触发」得到 0）。
    reso = meta["resolver"]
    probe = reso.resolve("ma20", gate_mode="production", path_scope="both")
    add("N3 通道可触发", probe["divergence"] and probe["verdict"] == "block",
        f"ma20 按 both 解析 → divergence={probe['divergence']}, verdict={probe['verdict']}")
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
        description="生成 referenced_factor_inventory（契约 §7.10.2 / §7.12）")
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
        print(f"summary.live   : {json.dumps(live, ensure_ascii=False)}")
        print(f"summary.all    : {json.dumps(allr, ensure_ascii=False)}")
        print(f"stale_count    : {payload['stale_count']}")
        print(f"canonical      : {payload['canonical_digest']}")
        print(f"out            : {out_path}")
        print(f"sha256(file)   : {digest}")
    ok_all = True
    for name, ok, detail in results:
        ok_all = ok_all and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
