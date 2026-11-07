# -*- coding: utf-8 -*-
"""v5.11 -> v5.12 订正批（开发经理派单）。

只改 docs/factors 下三个文件；不碰 backend/**、不碰盘上因子定义、不提交。
每处替换都断言「恰好命中 1 次」，任何一处不符就整体不写盘（fail-closed）。

用法：cd <repo> && python research/factor-ledger-20261108/apply_v512.py
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MD = REPO / "docs" / "factors" / "F_CLASS_REGISTRATION_20261107.md"
JS = REPO / "docs" / "factors" / "evidence" / "f_class_registry.json"
GAP = REPO / "docs" / "factors" / "FACTOR_GAP_SPEC_20261107.md"
BACKUP = REPO / "research" / "factor-ledger-20261108" / "backup_v511"

CN = timezone(timedelta(hours=8))
NOW = datetime.now(CN)
HHMM = NOW.strftime("%H:%M")
ISO = NOW.strftime("%Y-%m-%dT%H:%M+0800")

LIMIT = 111
TESTS = "backend/tests/test_factor_registry.py"
CONST4 = [
    (":289", "assert len(specs) == 110"),
    (":290", "assert len({spec.id for spec in specs}) == 110  # id 唯一"),
    (":329", "assert len(stock) == 110"),
    (":377", "assert len(factors) == 110"),
]

PER_FACTOR = [
    ("uf_vol60", "vol60", "1.1102230246251565e-16（5,469,335）"),
    ("uf_ma120", "ma120", "0.0（5,428,988）"),
    ("uf_ma200", "ma200", "0.0（5,371,122）"),
    ("uf_prior_high_20", "prior_high_20", "0.0（5,496,401）"),
    ("uf_prior_high_55", "prior_high_55", "0.0（5,472,715）"),
    ("uf_prior_high_250", "prior_high_250", "0.0（5,332,523）"),
    ("uf_prior_low_10", "prior_low_10", "0.0（5,503,218）"),
    ("uf_prior_vol_20", "prior_vol_20", "0.0（5,496,401）"),
]
COLLIDE4 = ["ma20", "ma60", "boll_lower", "boll_upper"]
LIVE7 = [
    ("ma20_breakout", "field:ma20"),
    ("ma20_breakdown", "field:ma20"),
    ("ma_dead_5_20", "field:ma20"),
    ("ma_golden_5_20", "field:ma20"),
    ("ma_golden_20_60", "field:ma60"),
    ("boll_breakout_upper", "field:boll_upper"),
    ("boll_breakdown_lower", "field:boll_lower"),
]
NS_MATRIX = [
    ("ma20", "FS01", "0", "是"),
    ("ma60", "FS01", "0", "是"),
    ("sd20", "FS01", "FS02", "否"),
    ("boll_lower", "FS01", "0", "是"),
    ("boll_upper", "FS01", "0", "是"),
    ("prior_amount_20", "FS01", "FS02", "否"),
]


def sub_once(text: str, old: str, new: str, tag: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"[FAIL] anchor {tag}: expected 1 hit, got {n}")
    return text.replace(old, new)


def lf_sha(path: Path) -> tuple[int, int, str]:
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    return len(raw), lf.count(b"\n"), hashlib.sha256(lf).hexdigest()


# ---------------------------------------------------------------- markdown

def edit_md(text: str, reg_size: int, reg_lines: int, reg_sha: str) -> str:
    # A1 头部版本号
    text = sub_once(
        text,
        "**台账 v5.11（2026-11-08 00:56 修订；v5.10 于 00:52、",
        f"**台账 v5.12（2026-11-08 {HHMM} 修订；v5.11 于 00:56、v5.10 于 00:52、",
        "A1 header version",
    )

    # A2 §0.1 registry 指纹行
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines)
           if ln.startswith("| `docs/factors/evidence/f_class_registry.json` |")]
    if len(idx) != 1:
        raise SystemExit(f"[FAIL] A2: registry row hits {len(idx)}")
    i = idx[0]
    lines[i] = (
        f"| `docs/factors/evidence/f_class_registry.json` | {reg_size:,} B | {reg_lines} "
        f"| LF（CRLF 0） | {NOW.strftime('%Y-%m-%dT%H:%M')} "
        f"| `{reg_sha}` | `{reg_sha}` |"
    )
    text = "\n".join(lines)

    # A3 行数口径那句
    text = sub_once(
        text,
        "（v5.8 补；v5.11 数值同步为 163,451 B / 2758 个换行符）",
        f"（v5.8 补；v5.12 数值同步为 {reg_size:,} B / {reg_lines} 个换行符）",
        "A3 lines note",
    )

    # A4 v5.11 banner 就地订正标记
    text = sub_once(
        text,
        "③把「110 怎么数出来的、变 111 要动哪两行测试常量」落成整表"
        "（`backend/tests/test_factor_registry.py:289-290`）。",
        "③把「110 怎么数出来的、变 111 要动哪两行测试常量」落成整表"
        "（`backend/tests/test_factor_registry.py:289-290`）。"
        "**【v5.12 就地订正：不是两行，是 4 处 —— `:289` / `:290` / `:329` / `:377`；"
        "按两行改会留 2 条红，见 §16.5 第 4 条】**",
        "A4 banner correction",
    )

    # A5 §16.1 表后加登记状态
    text = sub_once(
        text,
        "\n### 16.2 110 这个数怎么来的",
        "\n**登记状态（v5.12）**：`market_breadth` = **已派、未交付**。开发经理 "
        f"2026-11-08 {HHMM} 已派系统开发工程师；本文写作时 "
        "`grep -rn \"market_breadth\" backend/app --include=*.py` 仍 **0 命中**、"
        "`all_factors()` 仍 110、`compile_formula(\"market_breadth\")` 仍 `E001`。"
        "交付判据见 §16.5 五条 —— 本格从「缺载体、待登记」改为「已派、未交付」，"
        "**不改**任何登记参数。\n\n### 16.2 110 这个数怎么来的",
        "A5 sec16.1 status",
    )

    # A6 §16.4 表加状态行
    text = sub_once(
        text,
        "| 强制约束 | **禁止对其再做任何截面算子或排名** | 否则按标的广播后重复计数，约 3,000 倍 |",
        "| 强制约束 | **禁止对其再做任何截面算子或排名** | 否则按标的广播后重复计数，约 3,000 倍 |\n"
        "| 状态（v5.12） | **已派、未交付** | 已派系统开发工程师；本文写作时 `backend/app` 仍 0 命中。"
        "门票本身不变，只改状态写法 |",
        "A6 sec16.4 status row",
    )

    # A7 §16.5 第 4 条：两处 -> 4 处
    old4 = (
        "4. `pytest tests/test_factor_registry.py::test_catalog_counts_and_kinds` → 111；"
        "**必须同步改** `backend/tests/test_factor_registry.py:289`（`len(specs) == 110`）"
        "与 `:290`（`len({spec.id for spec in specs}) == 110`）两个常量，否则测试红。"
        "若 `market_breadth` 进 provider，还要看 "
        "`factor_provider_status()[\"factor_count\"]` 从 33 变 34 会不会撞别的常量 —— "
        "实现时须**全量跑** `tests/`。"
    )
    rows = "\n".join(
        f"   - `{TESTS}{ln}` `{code}`" for ln, code in CONST4
    )
    new4 = (
        "4. `pytest tests/test_factor_registry.py::test_catalog_counts_and_kinds` → 111；"
        "**必须同步改 4 处，不是 2 处**（v5.12 订正：v5.11 只列了 `:289`–`:290`，"
        "按两处改会留 2 条红）：\n"
        f"{rows}\n"
        "   实测：`grep -n \"110\" backend/tests/test_factor_registry.py` → **恰 4 命中**"
        "（`:289` / `:290` / `:329` / `:377`；文件 403 行）。四条缺一条就红一条。"
        "若 `market_breadth` 进 provider，还要看 "
        "`factor_provider_status()[\"factor_count\"]` 从 33 变 34 会不会撞别的常量 —— "
        "实现时须**全量跑** `tests/`。"
    )
    text = sub_once(text, old4, new4, "A7 sec16.5 item4")

    return text


SEC17 = """---

## 17. G4 立 P0：6 个单侧件不补 status、不按 id 开豁免口（v5.12）

开发经理派单（2026-11-08 01:0x）要求把 G4 从「缺口编号」升为**裁定**。本节就是这条裁定，含三条不可绕过的约束，以及一张新测的 2 命名面 × 6 只实测表。**本节不改任何公式、不改任何因子定义。**

### 17.1 裁定

- **G4 = P0**（缺口原文与验收判据见 `docs/factors/FACTOR_GAP_SPEC_20261107.md` §9 G4；量级 S；路径「架构契约 → 开发实现 → 独立审核」）。
- 6 只：`ma20` / `ma60` / `sd20` / `boll_lower` / `boll_upper` / `prior_amount_20`。在 `mode="production"`、`namespace="factor"`（缺省面）下 **6/6 `FS01`**、`detail.status = None`。
- **这是设计行为，不是残留缺陷**：`status` 只从盘上定义 JSON 读，而盘上 id 必须匹配 `^uf_[a-z0-9_]{1,40}$`（`backend/app/factors/store.py:17`）；这 6 个 id 不带 `uf_` 前缀 → **没有任何合法载体承载它们的 `status`**。`FactorSpec` 数据类也没有 `status` 字段（`backend/app/factors/registry.py`）。
- 因此本裁定明确**不做**三件事：①不补 `status`（无载体）；②不建 `uf_*` 双胞胎（§7.15.1 第 14 行明令不得新建 `uf_prior_amount_20`；其余同理，双胞胎会触发 §7.16.6 的 `FS04`）；③**不按 id 开白名单放行**。

### 17.2 豁免口：不得开（硬约束）

- 豁免集是 `EXEMPT_KINDS = {base, virtual}`（`backend/app/factors/gate.py:74`）——**黑名单语义、按 `kind` 判、不按 id 判**。
- 若有任何一方（策略经理 / 开发经理 / 独立审核 / 研究侧）要求「把这 6 个名字加白名单放行」，**必须先回来改本节这条裁定**，并在台账留改判依据与实测；**不得在闸门里按 id 开小门**。
- 理由：闸门是「策略只经因子表达」的**唯一执行点**。按 id 白名单在这个执行点上开后门，同一份名单随后就会被用来放行 `draft` 因子；而按 id 的名单无法机械判定「这只该放、那只不该放」。
- 若真要解除，正确路径是 **G4 本身**：`FactorSpec` 增 `status`（或 provider 注册路径显式给 `status`），再逐只走 §7.11 的 V3 闸门升 `active`，**禁止批量写 `active`**（§7.5-5 / `F-A21` / `F-A30`）。

### 17.3 实测：2 个命名面 × 6 只（v5.12 新测）

脚本 `research/factor-ledger-20261108/probe_namespace_v511.py`（只读真盘：`store.load_into_registry(D:/TSP/data)` + `ensure_factor_providers()` + `gate.RegistryFacts(D:/TSP/data)`），原始输出 `probe_namespace_v511.json`：

| id | `namespace="factor"`（缺省） | `namespace="column"` | 在 `_column_universe()`（68 名）内 |
| --- | --- | --- | --- |
| `ma20` | **FS01** | 0 码 | 是 |
| `ma60` | **FS01** | 0 码 | 是 |
| `sd20` | **FS01** | **FS02** | **否** |
| `boll_lower` | **FS01** | 0 码 | 是 |
| `boll_upper` | **FS01** | 0 码 | 是 |
| `prior_amount_20` | **FS01** | **FS02** | **否** |

对照组（证明真盘 `status` 读取本身是通的、alias 判据也没坏）：`uf_vol60` → **0 码**、`fact_status=active`；`vol60` → **`FS03`**（`blocked_codes=[FS03, FS01]`，判据只认 `FS03`）。

### 17.4 4 个撞名名字的 400 归因（订正一处：只对 factor 面成立）

- 「4 个撞名名字」= `ma20` / `ma60` / `boll_lower` / `boll_upper` —— 恰是上表里在 `_column_universe()` 内的那 4 只（`sd20` / `prior_amount_20` 不在列宇宙，故 column 面是 `FS02` 而不是 0 码）。
- **当因子引用**（`namespace="factor"`，缺省）→ `FS01` → **400**。依据：契约 §7.7.5 错误码表「`FS01` … 400；`detail` 含 `factor_id` / `status` / `mode`」，`F-A47` 规定错误面唯一且是 400。**不是 `FS03`**：`FS03` 只在 alias→canonical 时出，而这 4 只 `alias_of=None`（不是 alias；对照实测 `vol60` → `FS03`）。
- **当列引用**（`namespace="column"`，§7.17.2 / `F-A43-2`「column 面直接 allow」）→ 这 4 只 **0 码放行**。
- **今日现状（别读成「今天这 7 条信号已经坏了」）**：这 4 个名字今天在活信号里是**列**（`field:ma20` / `field:ma60` / `field:boll_lower` / `field:boll_upper`），走 column 面 → **今天不会被打成 400**。400 只在「被当因子引用」时出现。
- 7 条活信号实测（`D:/TSP/data/user_data/custom_signals/*.json`，逐条核过 `enabled=true`，`kind` 全为 `"both"`）：`ma20_breakout`（`field:ma20`）、`ma20_breakdown`（`field:ma20`）、`ma_dead_5_20`（`field:ma20`）、`ma_golden_5_20`（`field:ma20`）、`ma_golden_20_60`（`field:ma60`）、`boll_breakout_upper`（`field:boll_upper`）、`boll_breakdown_lower`（`field:boll_lower`）。`grep -l "ma20\\|ma60\\|boll_lower\\|boll_upper" *.json` → **恰 7 个文件**（该目录共 21 个信号文件）。

### 17.5 今天闸门的生产调用点 = 0（400 是契约面，不是已接线行为）

- `grep -rn "assert_factors_usable" backend/app --include=*.py` → 只命中 `backend/app/factors/gate.py` 自身（定义与 docstring），**无任何生产调用点**；`GateError` 也没有 `exception_handler`（`backend/app/main.py` 的 6 个 handler 里没有它）。
- 所以「接线后 400」是 §7.7.5 / `F-A47` 的**既定行为**，不是今天已发生的事实。本批不接线（接线归实现批 + 独立审核）。

### 17.6 本节没做的事

没有改 `backend/**`、没有改盘上因子定义、没有为这 6 只造任何字段或 JSON、没有开任何豁免、没有提交、没有部署；`signature` 三元组未动。
"""

SEC18_HEAD = """---

## 18. 8 只 `active` 的生效留痕（v5.12）

本节只补**生效这件事的留痕**（时刻、迁移、逐只证据指针、生效后的闸门事实）。公式、窗口、依赖一律不在此节、也未动。

### 18.1 生效时刻与状态迁移

| 项 | 值 | 出处（可复算） |
| --- | --- | --- |
| 生效时刻 | **2026-11-07T23:33:57** | 8 只盘上 JSON 的 `updated_at`，逐只同一秒（8/8 实测） |
| 改前 | `status = "draft"` | 契约 v0.12 §7.15.3：17:4x 实测「15 个文件都是 `"status": "draft"`」 |
| 改后 | `status = "active"` | `D:/TSP/data/user_data/custom_factors/uf_*.json#status` |
| 盘上 `version` | 仍 **1**（未 +1） | 直写路径不经 upsert 的版本 +1 分支；**不回写、不伪造** |
| 改的键 | 仅 `status` 与 `updated_at` 两个 | 逐只对照 §7.1 块登记的 `formula_text` / `warmup_bars` / `dependencies`，一字未变 |

### 18.2 逐只证据指针（一 id 一行）

| # | canonical id | 研究名 | `status` | `updated_at` | `version` | V3 全量 `max_abs_diff`（n） | V3 截面 `rank_change_max` | B0 保真 `max_abs_diff` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""

SEC18_TAIL = """
三条指针的 JSON 路径（与 §15.1 末表同一对象，本文只引用不重算）：

| 列 | 文件 | JSON 路径 |
| --- | --- | --- |
| V3 全量 | `docs/factors/evidence/F_CLASS_PARITY_20261107.json` | `#factor_parity.<canonical id>`（`tol=1e-12`、`n_over_tol=0`，8/8） |
| V3 截面 | `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json` | `#pairs.<研究名>.rank_last_day_full_market.rank_change_max` |
| B0 保真 | `docs/factors/evidence/registration_b0_20261107.json` | `#fidelity.per_factor.<研究名>.max_abs_diff` |

**`vol60` 的单列说明**（照抄 §15.1，不许改口径）：V3 `max_abs_diff = 1.11e-16 < 1e-12`，记为「判过」，**不得**写成「逐位相同」；其余 7 只实测 `0.0`，可写「逐位相同」。

### 18.3 生效后的闸门事实（v5.12 实测）

| 侧 | 结果 | 证据 |
| --- | --- | --- |
| canonical（8 只 `uf_*`） | **8/8 0 码**、`fact_status=active` → **不再出 `FS01`** | `research/factor-ledger-20261108/probe_active8_v512.py` → `probe_active8_v512.json` |
| alias（8 个研究原名） | **8/8 `FS03`**（`blocked_codes` 另含 `FS01`，判据只认 `FS03`） | `research/b0b-20261107/verify_fs03_realdisk.py` → 9/9 PASS |

两行合起来的读法：**canonical 可进生产，alias 不可进生产** —— 这正是本批要做成的事。alias 那个 `FS01` 是 alias 自身 pack `FactorSpec` 无 `status` 载体（同 §17 的 G4 根因），不构成新缺口。

### 18.4 本节没做的事

未改任何公式 / `warmup_bars` / `dependencies` / `shift` / 双 id 三列 / `replaced_by`；未改盘上 `version`；未提交、未部署；闸门的生产调用点仍为 **0**（§17.5）。

---
"""

BANNER = """\n> **v5.12（2026-11-08 {hhmm}）：订正批（开发经理派单），公式与数值一律不动** —— 五件：①**门票订正**：v5.11 写「`market_breadth` 登记须同步改 `{tests}:289`–`:290` 两处常量」，实测是 **4 处**（`:289` / `:290` / `:329` `assert len(stock) == 110` / `:377` `assert len(factors) == 110`；`grep -n "110"` 恰 4 命中、文件 403 行），按两处改会留 2 条红；②`market_breadth` 状态由「缺载体、待研究侧登记」改为 **已派、未交付**（已派系统开发工程师；本文写作时 `grep -rn "market_breadth" backend/app --include=*.py` 仍 **0 命中**）；③**G4 立 P0 并写成裁定**（新增 §17）：6 个单侧件不补 `status`、不建 `uf_*` 双胞胎、**不按 id 开豁免口**，任何「加白名单放行」的要求必须先回来改这条裁定；④**4 个撞名名字的 400 归因按实际命名面分开写**（新增 §17.4）：当因子引用是 `FS01` → 400（§7.7.5 / `F-A47`，不是 `FS03`），当列引用是 0 码放行（§7.17.2 / `F-A43-2`），故今天 7 条活信号（走 column 面）**不会**被打成 400；⑤**8 只 `active` 的生效留痕**（新增 §18）：生效时刻 `2026-11-07T23:33:57`（8/8 同一秒）、改前 `draft` 改后 `active`、盘上 `version` 仍 1、逐只 V3/截面/B0 指针，并实测「canonical 侧不再出 `FS01`、alias 侧仍出 `FS03`」。**8 只公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列、`replaced_by` 四条、K1–K12、`signature` 三元组一律未动。**\n"""


def build_sec17() -> str:
    return SEC17


def build_sec18() -> str:
    rows = []
    for i, (cid, name, v3) in enumerate(PER_FACTOR, 1):
        rows.append(
            f"| {i} | `{cid}` | `{name}` | `active` | `2026-11-07T23:33:57` | `1` | "
            f"`{v3}` | `0.0` | `0.0` |"
        )
    return SEC18_HEAD + "\n".join(rows) + "\n" + SEC18_TAIL


# ---------------------------------------------------------------- json

def edit_json(doc: dict) -> dict:
    doc["meta"]["version"] = "5.12"
    doc["meta"]["revised_at"] = ISO
    fd = doc["meta"]["freeze_declaration"]
    fd["status"] = "FROZEN at v5.12"
    fd["declared_at"] = ISO
    fd["revised_at"] = ISO

    acr = doc.setdefault("admission_carrier_rulings", {})
    acr["g4_p0_ruling_v5_12"] = {
        "ruling": "G4 = P0（裁定，不只是缺口编号）",
        "ruled_at": ISO,
        "ids": ["ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"],
        "default_namespace_face_code": "FS01",
        "observed_detail_status": None,
        "do_not": [
            "补 status（盘上 id 必须匹配 ^uf_[a-z0-9_]{1,40}$，这 6 个无合法载体）",
            "建 uf_* 双胞胎（§7.15.1 第 14 行；双胞胎触发 §7.16.6 的 FS04）",
            "按 id 开白名单放行（EXEMPT_KINDS={base,virtual} 是黑名单语义、按 kind 不按 id）",
        ],
        "whitelist_forbidden": (
            "任何人要求把这 6 个名字加白名单放行，必须先回来改这条裁定并留改判依据与实测；"
            "不得在 gate.py 按 id 开小门。理由：闸门是「策略只经因子表达」的唯一执行点。"
        ),
        "correct_path": "G4 本身：FactorSpec 增 status 或 provider 注册路径显式给 status，再逐只走 §7.11 V3 闸门升 active，禁止批量写 active（§7.5-5 / F-A21 / F-A30）",
        "namespace_matrix": {
            "script": "research/factor-ledger-20261108/probe_namespace_v511.py",
            "output": "research/factor-ledger-20261108/probe_namespace_v511.json",
            "mode": "production",
            "facts": "RegistryFacts(D:/TSP/data)",
            "rows": [
                {"id": fid, "as_factor": fac, "as_column": col, "in_column_universe": uni}
                for fid, fac, col, uni in NS_MATRIX
            ],
            "controls": {
                "uf_vol60": {"code": None, "fact_status": "active"},
                "vol60": {"code": "FS03", "blocked_codes": ["FS03", "FS01"]},
            },
            "column_universe_size": 68,
        },
        "four_collide_ids": COLLIDE4,
        "four_collide_attribution": {
            "as_factor": "FS01 → 400（契约 §7.7.5 错误码表 / F-A47 错误面唯一且是 400）",
            "as_column": "0 码放行（§7.17.2 / F-A43-2 column 面直接 allow）",
            "not_FS03": "这 4 只 alias_of=None，不是 alias；FS03 只在 alias→canonical 时出（对照 vol60 → FS03）",
            "today_status": "这 4 个名字今天在活信号里是列（field:ma20 等），走 column 面 → 今天不会被打成 400；400 只在被当因子引用时出现",
        },
        "live_signals_today": {
            "dir": "D:/TSP/data/user_data/custom_signals",
            "files_in_dir": 21,
            "matching_files": len(LIVE7),
            "all_enabled": True,
            "all_kind": "both",
            "namespace_face": "column",
            "would_be_400_today": False,
            "files": [{"file": f + ".json", "ref": r} for f, r in LIVE7],
        },
        "gate_production_call_sites": {
            "count": 0,
            "evidence": "grep -rn assert_factors_usable backend/app --include=*.py → 只命中 gate.py 自身；GateError 无 exception_handler",
            "meaning": "「接线后 400」是 §7.7.5 / F-A47 的既定行为，不是今天已发生的事实",
        },
    }

    doc["active_take_effect_20261107"] = {
        "effective_at": "2026-11-07T23:33:57",
        "carrier": "D:/TSP/data/user_data/custom_factors/<canonical id>.json#status",
        "before": {
            "status": "draft",
            "basis": "契约 v0.12 §7.15.3：17:4x 实测 15 个盘上定义文件全为 \"status\": \"draft\"",
        },
        "after": {"status": "active"},
        "disk_version_after": 1,
        "disk_version_note": "直写路径不经 upsert 的版本 +1 分支；不回写、不伪造",
        "keys_changed": ["status", "updated_at"],
        "per_factor": [
            {
                "canonical_id": cid,
                "research_name": name,
                "status": "active",
                "updated_at": "2026-11-07T23:33:57",
                "version": 1,
                "v3_max_abs_diff_n": v3,
                "v3_rank_change_max": "0.0",
                "b0_max_abs_diff": "0.0",
                "evidence": {
                    "v3": "docs/factors/evidence/F_CLASS_PARITY_20261107.json#factor_parity." + cid,
                    "rank": "docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json#pairs." + name + ".rank_last_day_full_market.rank_change_max",
                    "b0": "docs/factors/evidence/registration_b0_20261107.json#fidelity.per_factor." + name + ".max_abs_diff",
                },
            }
            for cid, name, v3 in PER_FACTOR
        ],
        "gate_after": {
            "canonical_production": "8/8 0 码，fact_status=active → 不再出 FS01",
            "alias_production": "8/8 FS03（blocked_codes 另含 FS01，判据只认 FS03）",
            "canonical_script": "research/factor-ledger-20261108/probe_active8_v512.py",
            "canonical_output": "research/factor-ledger-20261108/probe_active8_v512.json",
            "alias_script": "research/b0b-20261107/verify_fs03_realdisk.py",
            "alias_result": "9/9 PASS",
        },
        "not_asserted": [
            "不写「逐位相同」给 vol60（1.11e-16 < 1e-12 判过，不是 0）",
            "不改盘上 version、不重跑 upsert、不伪造审批时间",
        ],
    }

    doc["v5_12_changes"] = {
        "batch": "v5.12 订正批（开发经理派单），公式与数值一律不动",
        "date": "2026-11-08",
        "author": "因子工程师",
        "scope": "docs/factors 台账三文件（F_CLASS_REGISTRATION_20261107.md + evidence/f_class_registry.json + FACTOR_GAP_SPEC_20261107.md）；未改 backend/**、未改盘上定义、未提交",
        "changes": [
            {
                "id": 1,
                "what": "market_breadth 登记要同步改的测试常量数写小了（v5.11 写「两处」）",
                "fix": "实测 4 处并列出行号：" + "；".join(
                    f"{TESTS}{ln} `{code}`" for ln, code in CONST4
                ) + "；grep -n \"110\" 恰 4 命中，文件 403 行",
                "why": "按两处改，测试会留 2 条红",
            },
            {
                "id": 2,
                "what": "market_breadth 登记状态写法停在「缺载体、待研究侧登记」",
                "fix": "改为「已派、未交付」：开发经理已派系统开发工程师；本文写作时 grep -rn \"market_breadth\" backend/app --include=*.py 仍 0 命中、all_factors() 仍 110",
                "why": "状态要能对着实测读",
            },
            {
                "id": 3,
                "what": "G4 只有缺口编号与验收判据，没有「不得开豁免口」的裁定文本",
                "fix": "立 G4 = P0 并写成裁定（台账 §17 / 本文 admission_carrier_rulings.g4_p0_ruling_v5_12）：6 个单侧件不补 status、不建 uf_* 双胞胎、不按 id 开白名单；任何「加白名单放行」要求必须先回来改裁定",
                "why": "闸门是「策略只经因子表达」的唯一执行点，按 id 开豁免等于在该点开后门",
            },
            {
                "id": 4,
                "what": "4 个撞名名字的 400 归因含混（会被读成「今天 7 条活信号已经坏了」）",
                "fix": "实测 2 命名面 × 6 只（probe_namespace_v511.json）：factor 面 6/6 FS01；column 面 ma20/ma60/boll_lower/boll_upper 0 码、sd20/prior_amount_20 FS02。400 只对「当因子引用」成立；今天 7 条活信号走 column 面不会被打成 400",
                "why": "把「今天已经坏了」和「接线后才坏」分开，避免误判成在跑坏信号",
            },
            {
                "id": 5,
                "what": "8 只 active 的生效时刻与逐只证据没有集中留痕（散在 §15.1）",
                "fix": "新增台账 §18 与本文 active_take_effect_20261107：生效时刻 2026-11-07T23:33:57（8/8 同一秒）、draft→active、盘上 version 仍 1、逐只 V3/截面/B0 指针；实测 canonical 侧 8/8 0 码、alias 侧 8/8 仍 FS03",
                "why": "生效是一个时间点的事实，散着写无法被单点复算",
            },
        ],
        "not_changed": [
            "8 只 formula_text / warmup_bars / dependencies / shift",
            "双 id 三列 canonical_id / aliases[] / superseded_by",
            "replaced_by 四条 / K1–K12 / signature 三元组（aefdf528…2d1a / \"2\" / 67）",
            "盘上 D:/TSP/data/user_data/custom_factors/*.json 的任何字节（不改 status、不改 version）",
            "market_breadth 的登记参数（§16.4 门票一字未改，只改状态写法与常量处数）",
        ],
    }
    return doc


# ---------------------------------------------------------------- gap spec

def edit_gap(text: str) -> str:
    text = sub_once(
        text,
        "# 因子缺口规格 v1.3（2026-11-07；v1.3 于 2026-11-08 00:40 追加 §9 准入载体缺口，§0–§8 一字未改）",
        "# 因子缺口规格 v1.4（2026-11-07；v1.3 于 2026-11-08 00:40 追加 §9 准入载体缺口；"
        f"v1.4 于 2026-11-08 {HHMM} 把 §9 G4 升为裁定并订正 G5 的常量处数，§0–§8 一字未改）",
        "P4 header",
    )

    anchor = (
        "- **影响面**：策略经理引用这 6 个 id 的策略在 `production` 全部被拒"
        "（当前实测：全部 `FS01`）。不解除则「策略只经因子表达」在这些策略上无法落地到可运行。"
    )
    add = (
        anchor
        + "\n- **裁定（v5.12 立 P0）**：本缺口升为**裁定**，锁定三条不做：①不补 `status`（无合法载体）；"
        "②不建 `uf_*` 双胞胎（§7.15.1 第 14 行；双胞胎会触发 §7.16.6 的 `FS04`）；"
        "③**不按 id 开白名单放行**（`EXEMPT_KINDS={base,virtual}` 是黑名单语义、按 `kind` 不按 id）。"
        "任何人要求「把这 6 个名字加白名单放行」，**必须先回来改本裁定**并留改判依据与实测，"
        "不得在闸门里按 id 开小门 —— 闸门是「策略只经因子表达」的唯一执行点。"
        "裁定全文见台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §17；"
        "机器可读版 `docs/factors/evidence/f_class_registry.json#admission_carrier_rulings.g4_p0_ruling_v5_12`。"
        "\n- **4 个撞名名字的 400 归因（v5.12 实测，2 命名面 × 6 只）**："
        "`ma20` / `ma60` / `boll_lower` / `boll_upper` 同时在 `_column_universe()`（68 名）内 —— "
        "**当因子引用**（`namespace=\"factor\"`，缺省）→ `FS01` → **400**（契约 §7.7.5 / `F-A47`；"
        "**不是** `FS03`，这 4 只 `alias_of=None`）；**当列引用**（`namespace=\"column\"`，"
        "§7.17.2 / `F-A43-2`）→ **0 码放行**；`sd20` / `prior_amount_20` 不在列宇宙 → column 面是 `FS02`。"
        "**今日这 4 个名字在 7 条活信号里是列**（`D:/TSP/data/user_data/custom_signals`："
        "`ma20_breakout` / `ma20_breakdown` / `ma_dead_5_20` / `ma_golden_5_20` / `ma_golden_20_60` / "
        "`boll_breakout_upper` / `boll_breakdown_lower`，逐条 `enabled=true`、`kind=\"both\"`）→ 走 column 面，"
        "**今天不会被打成 400**；400 只在被当因子引用时出现。实测脚本 "
        "`research/factor-ledger-20261108/probe_namespace_v511.py`（输出同名 `.json`）。"
    )
    text = sub_once(text, anchor, add, "P1 G4 ruling")

    old = (
        "**实现时必须同步改的两行（不改就红）**：`backend/tests/test_factor_registry.py:289` "
        "`assert len(specs) == 110` → `111`、`:290` "
        "`assert len({spec.id for spec in specs}) == 110` → `111`。"
    )
    lines = "；".join(f"`{TESTS}{ln}` `{code}` → `111`" for ln, code in CONST4)
    new = (
        "**实现时必须同步改的 4 处（v5.12 订正：v1.3 写「两行」会留 2 条红）**："
        f"{lines}（`grep -n \"110\"` 恰 4 命中，文件 403 行）。"
    )
    text = sub_once(text, old, new, "P2 four constants")

    perf = "**实现门票（v5.11 追加，2026-11-08 00:58）**"
    i = text.find(perf)
    if i < 0:
        raise SystemExit("[FAIL] P3: implementation ticket paragraph not found")
    j = text.find("\n", i)
    text = (
        text[:j]
        + f"\n\n- **状态（v5.12）**：**已派、未交付**。开发经理已于 2026-11-08 {HHMM} 派系统开发工程师；"
        "写作时实测 `grep -rn \"market_breadth\" backend/app --include=*.py` 仍 **0 命中**、"
        "`all_factors()` 仍 110。登记参数（`§16.4` 门票）一字未改，只改状态写法。"
        + text[j:]
    )
    return text


# ---------------------------------------------------------------- main

def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in (MD, JS, GAP):
        dst = BACKUP / p.name
        if dst.exists():
            print(f"[skip] backup exists, keeping the v5.11 copy: {dst.name}")
            continue
        shutil.copy2(p, dst)
    print(f"[ok] backup -> {BACKUP}")

    # 1) JSON first (md §0.1 must fingerprint the FINAL json bytes)
    raw = JS.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    doc = edit_json(doc)
    JS.write_bytes(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"))
    reg_size, reg_lines, reg_sha = lf_sha(JS)
    print(f"[ok] json: {reg_size} B / {reg_lines} LF / {reg_sha}")

    # 2) markdown
    md = io.open(MD, encoding="utf-8", newline="").read()
    before_len = len(md)
    md = edit_md(md, reg_size, reg_lines, reg_sha)
    md = sub_once(
        md,
        "\n- **唯一例外**：第三方直写造成的字节修复。",
        BANNER.format(hhmm=HHMM, tests=TESTS)
        + "\n- **唯一例外**：第三方直写造成的字节修复。",
        "A9 banner insert",
    )
    if not md.endswith("\n"):
        md += "\n"
    md = md + "\n" + build_sec17() + "\n" + build_sec18()
    if "\r\n" in md:
        raise SystemExit("[FAIL] md contains CRLF")
    io.open(MD, "w", encoding="utf-8", newline="").write(md)
    print(f"[ok] md: {before_len} -> {len(md)} chars, LF only")

    # 3) gap spec
    gap = io.open(GAP, encoding="utf-8", newline="").read()
    gap = edit_gap(gap)
    if "\r\n" in gap:
        raise SystemExit("[FAIL] gap contains CRLF")
    io.open(GAP, "w", encoding="utf-8", newline="").write(gap)
    print("[ok] gap spec edited")

    for p in (MD, JS, GAP):
        b = p.read_bytes()
        print(f"[out] {p.name}: {len(b)} B / CRLF {b.count(chr(13).encode() + chr(10).encode())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
