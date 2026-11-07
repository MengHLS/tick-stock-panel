"""自定义/复合因子存储 (P3) — data/user_data/custom_factors/*.json。

持久化收口到统一契约 Store (app/definitions.py); 单文件损坏只禁用该因子并
告警, 不影响启动 (对齐 CONTRIBUTING 第 4 节插件隔离要求)。生命周期状态:
draft → active → watch → retired (P4 状态机, 存储字段就绪, 迁移逻辑见巡检设计)。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.definitions import DefinitionKind, JsonDefinitionStore, register_kind
from app.factors.dsl import compile_formula
from app.factors.py_expr import compile_python_expression
from app.factors.registry import FactorSpec, factor_dependencies, get_factor, register_factor

logger = logging.getLogger(__name__)

CUSTOM_ID_PATTERN = re.compile(r"^uf_[a-z0-9_]{1,40}$")
COMPOSITE_ID_PATTERN = re.compile(r"^cf_[a-z0-9_]{1,40}$")
MAX_COMPOSITE_MEMBERS = 8
STATUSES = frozenset({"draft", "active", "watch", "retired"})

_STORE = JsonDefinitionStore("user_data/custom_factors", label="custom factor")


def load_all(data_dir: Path) -> list[dict]:
    """读取全部自定义/复合因子定义; 损坏文件跳过。"""
    return _STORE.load_all(data_dir)


def save_one(data_dir: Path, definition: dict) -> None:
    _STORE.save_one(data_dir, definition)


def load_one(data_dir: Path, factor_id: str) -> dict | None:
    """按 id 读取单个定义; 不存在或损坏返回 None (与 load_all 同隔离口径)。"""
    return _STORE.load_one(data_dir, factor_id)


def delete_one(data_dir: Path, factor_id: str) -> bool:
    return _STORE.delete_one(data_dir, factor_id)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_spec(definition: dict) -> FactorSpec:
    """定义 → FactorSpec; 校验失败抛 ValueError (调用方 fail-closed)。

    custom: 依赖/预热由 DSL 编译推导 (编译失败即拒绝注册)。
    composite: 依赖 = 成员递归展开; 预热 = 成员最大值; 循环引用拒绝。
    """
    kind = str(definition.get("kind", "custom"))
    factor_id = str(definition.get("id", ""))
    label = str(definition.get("label", "")).strip()
    if not label:
        raise ValueError("label 不能为空")
    pattern = COMPOSITE_ID_PATTERN if kind == "composite" else CUSTOM_ID_PATTERN
    if not pattern.match(factor_id):
        raise ValueError(f"id 必须匹配 {pattern.pattern}")
    status = str(definition.get("status", "draft"))
    if status not in STATUSES:
        raise ValueError(f"status 必须是 {sorted(STATUSES)} 之一")

    if kind == "custom":
        formula = str(definition.get("formula", ""))
        lang = str(definition.get("lang", "dsl")).strip().lower()
        if lang not in ("dsl", "python"):
            raise ValueError(f"未知 lang: {lang} (可选 dsl / python)")
        if lang == "python":
            # T2 表达式级 Python (P3): 依赖由 ctx 构造期登记; 显式 warmup
            # 只允许增大 (推断值是安全下限, 少算会失真)。
            compiled = compile_python_expression(formula)
            if not compiled.ok:
                first = compiled.errors[0]
                raise ValueError(f"表达式无效 [{first.code}]: {first.message}")
            declared_warmup = int(definition.get("warmup_bars", 0) or 0)
            return FactorSpec(
                id=factor_id,
                label=label,
                group=str(definition.get("group", "自定义")),
                formula_text=formula,
                kind="custom",
                lang="python",
                version=int(definition.get("version", 1)),
                dependencies=compiled.dependencies,
                warmup_bars=max(declared_warmup, compiled.warmup_bars),
                direction=str(definition.get("direction", "none")),  # type: ignore[arg-type]
                stability="stable" if status == "active" else "experimental",
            )
        compiled = compile_formula(formula)
        if not compiled.ok:
            first = compiled.errors[0]
            raise ValueError(f"公式无效 [{first.code}]: {first.message}")
        return FactorSpec(
            id=factor_id,
            label=label,
            group=str(definition.get("group", "自定义")),
            formula_text=formula,
            kind="custom",
            version=int(definition.get("version", 1)),
            dependencies=frozenset(compiled.dependencies),
            warmup_bars=compiled.warmup_bars,
            direction=str(definition.get("direction", "none")),  # type: ignore[arg-type]
            stability="stable" if status == "active" else "experimental",
        )

    if kind != "composite":
        raise ValueError(f"未知 kind: {kind}")
    members_raw = definition.get("members")
    if not isinstance(members_raw, dict) or not (2 <= len(members_raw) <= MAX_COMPOSITE_MEMBERS):
        raise ValueError(f"composite 成员必须是 {2}~{MAX_COMPOSITE_MEMBERS} 个")
    from app.factors.dsl import BASE_COLUMNS

    components: list[tuple[str, float]] = []
    for member_id, weight in members_raw.items():
        member_id = str(member_id)
        if member_id == factor_id:
            raise ValueError("composite 不能引用自身")
        try:
            weight = float(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"成员 {member_id} 权重必须是数字") from exc
        if not weight:
            raise ValueError(f"成员 {member_id} 权重不能为 0")
        # 成员 = 注册表因子 或 enriched 基准列 (已物化, 可直接参与组合)
        if get_factor(member_id) is None and member_id not in BASE_COLUMNS:
            raise ValueError(f"未知成员因子: {member_id}")
        components.append((member_id, weight))
    # 环检测沿 components 链走 (依赖已展开, 看不到链路成员)
    seen = {factor_id}
    frontier = [member_id for member_id, _ in components]
    while frontier:
        current = frontier.pop()
        if current in seen:
            raise ValueError("composite 成员存在循环引用")
        seen.add(current)
        current_spec = get_factor(current)
        if current_spec is not None and current_spec.kind == "composite":
            frontier.extend(member_id for member_id, _ in current_spec.components)
    dependencies = factor_dependencies([member_id for member_id, _ in components])
    warmup = max(
        ((get_factor(member_id).warmup_bars if get_factor(member_id) else 1) for member_id, _ in components),
        default=1,
    )
    formula_text = " + ".join(
        f"{weight:g}*zscore({member_id})" for member_id, weight in components
    )
    return FactorSpec(
        id=factor_id,
        label=label,
        group=str(definition.get("group", "组合")),
        formula_text=formula_text,
        kind="composite",
        version=int(definition.get("version", 1)),
        dependencies=dependencies,
        warmup_bars=warmup,
        direction=str(definition.get("direction", "none")),  # type: ignore[arg-type]
        components=tuple(components),
        stability="stable" if status == "active" else "experimental",
    )


def register_definition(definition: dict) -> FactorSpec:
    """定义 → spec → 注册 (重复 id 版本未升时由注册表拒绝)。

    同一个 spec 已注册时按幂等跳过 (F-A5): 重复加载同一份盘上定义
    (启动期二次 load_into_registry / worker 复用) 不再告警, 也不抬版本;
    内容不同才会走到注册表的「版本未提升」拒绝。
    """
    spec = to_spec(definition)
    if get_factor(spec.id) == spec:
        return spec
    register_factor(spec)
    return spec


# ── 注册幂等 (F-A5) ─────────────────────────────────────────────────
# 「同内容二次注册」的判等口径 = to_spec() 的语义投影 (注册表与计算真正消费的
# 东西) + description + status。用投影而不是原始键集, 因为同一个定义有两种合法
# 形状: 盘上形状 (含 lang 等非 API 字段) 与 API 形状 (create_custom_factor 构造,
# 没有 lang 键)。缺省值按 to_spec 的口径补齐 (kind→custom, lang→dsl,
# status→draft, direction→none, group→按 kind 默认), 两种形状的同内容判等成立。
#
# 参与判等: id / kind / label / group / lang / formula / direction / status /
#   stability / warmup_bars(生效值) / dependencies(编译推导) / components(成员与
#   权重) / description。
# 不参与: version / created_at / updated_at (版本与时间戳); 以及 to_spec 不消费、
#   API 也不可写的附加存储字段 (tags / unit / scale_free 等) —— 它们不改变因子
#   行为, 写盘时按「以盘上定义为底」原样保留 (见 _merge_for_write), 不会被抹掉。
# 失效方向: 一旦某个字段被 to_spec 消费, 它会自动进入投影, 不必手工维护白名单
#   (旧实现的黑名单方向相反: 盘上多一个 lang 就必然误判成「变了」, 正是 F-A5 的
#   返工根因)。mtime / 文件大小 / 目录指纹一律不参与判等, 只看语义。
_NON_CONTENT_FIELDS = frozenset({"version", "created_at", "updated_at"})
_GROUP_DEFAULT = {"custom": "自定义", "composite": "组合"}


def _canonical(value):
    """JSON 值 → 可逐字比对的规范化结构 (数值走 float repr: 1 与 1.0 等价)。"""
    if isinstance(value, dict):
        return {f"k:{key}": _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "n:" + repr(float(value))
    if value is None:
        return "~null"
    return "s:" + str(value)


def content_signature(definition: dict) -> str:
    """定义的内容签名 (F-A5 判等的唯一口径); 不含版本号与时间戳, 不看 mtime。

    签名 = to_spec() 语义投影: 由编译器/校验器补齐缺省值并推导依赖与预热, 因此
    「盘上形状」与「API 形状」只要语义相同就得到同一签名。非法定义 (label 为空 /
    id 不匹配 / 公式编译不过) 抛 ValueError, 由调用方 fail-closed。
    """
    spec = to_spec(definition)
    projection = {
        "id": spec.id,
        "kind": spec.kind,
        "label": spec.label,
        "group": spec.group or _GROUP_DEFAULT.get(spec.kind, ""),
        "lang": spec.lang or "dsl",
        "direction": spec.direction,
        "status": str(definition.get("status", "draft")),
        "stability": spec.stability,
        "warmup_bars": int(spec.warmup_bars),
        "dependencies": sorted(spec.dependencies),
        # custom: 公式原文 (改一个字符即内容变化); composite 无公式, 看成员
        "formula": spec.formula_text if spec.kind == "custom" else "",
        "components": [[member, float(weight)] for member, weight in sorted(spec.components)],
        "description": str(definition.get("description") or ""),
    }
    return json.dumps(
        _canonical(projection), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def is_same_content(stored: dict, incoming: dict) -> bool:
    """盘上定义与待注册定义内容是否等价 (F-A5)。

    只有「两侧都能投影且投影相等」才算等价; 任一侧投影失败 (非法/编译不过) 一律
    返回 False, 让调用方继续走校验路径 —— 判等永远不会替校验放行 (fail-closed)。
    """
    try:
        expected = content_signature(stored)
        actual = content_signature(incoming)
    except ValueError:
        return False
    return expected == actual


def _merge_for_write(stored: dict | None, definition: dict) -> dict:
    """写盘基底: 以盘上定义为底, 只覆盖调用方显式给出的字段。

    API 只能写 label / group / formula / description / direction / status; 盘上的
    lang / warmup_bars / unit / scale_free / tags 等非 API 字段在调用方未给出时
    原样保留 (旧实现以入参整份覆盖, 会把盘上的 lang 抹掉)。
    """
    merged = dict(stored or {})
    for key, value in definition.items():
        if key in _NON_CONTENT_FIELDS:
            continue
        merged[key] = value
    return merged


def resolve_status(stored: dict | None, definition: dict) -> str:
    """upsert 的 status 裁决 —— create 不是生命周期操作。

    status 的唯一写入口是 POST /custom/{id}/status 与「编辑即回 draft」语义。
    因此盘上已存在该 id 时:
      - 调用方显式给出 status: 以调用方为准;
      - 未给出且除 status 外内容无变化 → 沿用盘上 status (一次 create 形状的
        重提交不得把 active 打回 draft);
      - 未给出但内容有变化 → draft (编辑即回 draft);
    尚无定义 (首次创建) 时: 调用方给出的 status, 否则 draft。
    """
    explicit = definition.get("status")
    if stored is None:
        return str(explicit or "draft")
    if explicit not in (None, ""):
        return str(explicit)
    on_disk = str(stored.get("status") or "draft")
    # 用盘上 status 探一次「除 status 外是否同内容」(is_same_content 内部已 fail-closed)
    probe = {**definition, "status": on_disk}
    return on_disk if is_same_content(stored, probe) else "draft"


def is_unchanged_definition(stored: dict | None, definition: dict) -> bool:
    """这次提交是否会走 upsert_definition 的幂等空操作 (同一口径, 供路由预判)。

    路由用它决定「不重跑试算」——必须与 upsert_definition 的归一化完全一致, 否则
    会出现「判等说变了、upsert 说没变」两套结论 (旧路由硬编码 status=draft 就是
    这样把 active 定义判成内容变化)。
    """
    if stored is None:
        return False
    return is_same_content(stored, {**definition, "status": resolve_status(stored, definition)})


def upsert_definition(data_dir: Path, definition: dict) -> dict:
    """按内容幂等落库 (F-A5) —— 注册 + 保存的唯一入口。

    内容与盘上定义等价 (见 content_signature): 版本不变、文件不写 (字节与 mtime
    都不动 → 目录指纹不变 → 依赖指纹的缓存不被全表失效), 返回 unchanged=True;
    注册表里缺这个版本时按盘上版本补注册, 同样不抬版本。
    内容有差异 (或尚无定义): 以盘上定义为底合并入参 (保留非 API 字段), 版本 =
    盘上版本 + 1 (注册表里的版本更高时取更高者 + 1, 避免「版本未提升」), 校验 →
    注册 → 原子覆盖写, 返回 unchanged=False。
    版本号一律以盘上/注册表为准; 调用方传入的 version 只在首次创建时生效。
    status 不由此入口「重置」: 归一化见 resolve_status (盘上已有定义沿用盘上状态,
    除真改内容回 draft 外), 否则一次 create 形状的重提交就会把线上因子打回不可用。
    """
    factor_id = str(definition.get("id", ""))
    stored = _STORE.load_one(data_dir, factor_id) if factor_id else None
    # status 归一化必须排在判等之前: 否则 API 形状 (无 status) 与盘上 active 会因
    # status 参与签名而被判成内容变化 (v+1 且状态回 draft)
    definition = {**definition, "status": resolve_status(stored, definition)}
    if stored is not None and is_same_content(stored, definition):
        spec = to_spec(stored)  # 盘上定义为权威: 版本号与时间戳都以它为准
        current = get_factor(factor_id)
        if current is None or current.version < spec.version:
            register_factor(spec)
        return {"ok": True, "id": factor_id, "version": spec.version, "unchanged": True}

    updated = _merge_for_write(stored, definition)
    if stored is None:
        updated["version"] = int(definition.get("version", 1) or 1)
        if not updated.get("created_at"):
            updated["created_at"] = _now()
    else:
        base = int(stored.get("version", 1))
        current = get_factor(factor_id)
        if current is not None and current.version > base:
            base = current.version
        updated["version"] = base + 1
        updated["created_at"] = (
            stored.get("created_at") or definition.get("created_at") or _now()
        )
    updated["updated_at"] = _now()
    spec = to_spec(updated)  # 与 register_definition 同一门禁: 非法即 ValueError
    register_factor(spec)
    _STORE.save_one(data_dir, updated)
    return {"ok": True, "id": factor_id, "version": updated["version"], "unchanged": False}


def load_into_registry(data_dir: Path) -> list[str]:
    """启动期把存储中的因子注册进注册表; 单个失败只跳过并告警。

    多轮加载: composite 成员可能引用尚未加载的 custom/其他 composite (文件按
    字母序加载, cf_* 先于 uf_*), 失败的 composite 延后重试, 覆盖链式引用;
    重试用尽仍失败的只告警不阻塞启动。
    """
    # 自定义公式可以引用 ext_ 扩展字段. 扩展因子必须先注册, 否则这些公式
    # 会在启动时被判为未知标识符, 之后虽然完成了惰性同步也不会自动重试.
    from app.factors.ext_factors import ensure_synced

    ensure_synced(data_dir)
    loaded: list[str] = []
    pending = list(load_all(data_dir))
    for round_index in range(3):
        deferred: list[dict] = []
        for definition in pending:
            try:
                register_definition(definition)
                loaded.append(str(definition["id"]))
            except ValueError as exc:
                if round_index < 2 and str(definition.get("kind")) == "composite":
                    deferred.append(definition)
                else:
                    logger.warning("custom factor 注册失败 %s: %s", definition.get("id"), exc)
            except Exception as exc:
                logger.warning("custom factor 注册失败 %s: %s", definition.get("id"), exc)
        if not deferred:
            break
        pending = deferred
    return loaded


# ── 统一定义契约注册 (P1b) ───────────────────────────────
_FACTOR_ID_PATTERN = re.compile(r"^(uf|cf)_[a-z0-9_]{1,40}$")


def _validate_definition(definition: dict) -> None:
    """统一契约校验器 = to_spec (id/label/DSL/复合成员全量校验, 非法抛 ValueError)。"""
    to_spec(definition)


def _definition_dependencies(definition: dict) -> frozenset[str]:
    """因子定义 → 输入列 (统一契约的依赖提取器) = DSL/复合成员编译依赖, 与 to_spec 同源。"""
    return to_spec(definition).dependencies


register_kind(DefinitionKind(
    kind="factor",
    store=_STORE,
    id_pattern=_FACTOR_ID_PATTERN,
    validate=_validate_definition,
    dependencies=_definition_dependencies,
))
