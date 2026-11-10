"""v0.16 构建脚本：v0.15 逐字节为底，只做派单两项（缺口 1 / 缺口 2）的条款填充。

硬约束：
  * 底本 = FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md（297,167 B / 2,372 行 / 146b96b2a3426853）
  * 除下列 6 处正文改动 + footer 外，正文逐字节不变
  * §7.1 块仍须 LF 2514/6d3db013、CRLF 2541/a8e88134
  * F-A1–F-A47 判据号与阈值一字不动；只新增 F-A48 / F-A49

改动清单：
  M1  H1 标题 v0.15 → v0.16
  M2  修订记录表追加 v0.16 行
  M3  §7.16.4 追加键穷举表：替换表头 + 4 行单一变体 → 给出「键数唯一算法 + 组合行」
  M4  §7.16.4 追加键表后插入算法条与组合实测表（新增 12 行）
  M5  §7.7.2 闸门层签名行追加缺省事实源的硬约束（缺口 2 的条款位置）
  M6  §7.17.5 判据表后追加 F-A48 / F-A49 小节
  M7  §14 之后追加 §15（本版改动说明）
  F   footer 由本版正文字节重算

用法：
  cd C:/work/sourcecode/tick-stock-panel
  PYTHONIOENCODING=utf-8 python research/arch-build-20261108/build_contract_v016.py [--dst PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md"
DEFAULT_DST = REPO / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md"

# ---- 底本守卫：任一条不符即拒绝写入 ----
BASE_SHA = "146b96b2a3426853bc349fabcd7049cf63d17e200e63aaaa01ae72a9d8453b36"
BASE_LEN = 297167
BASE_NL = 2372
BASE_BODY_LEN = 294814
BASE_BODY_SHA = "c06815e5f31103e1679412244d965636fe555dcca6341aa93bc53d4a5b43fb20"

# ---- 7.1 块的三重锚（改前改后都必须成立）----
SEC71_LF_CHARS = 2514
SEC71_LF_SHA8 = "6d3db013"
SEC71_CRLF_CHARS = 2541
SEC71_CRLF_SHA8 = "a8e88134"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def section_7_1(text: str) -> dict:
    lines = text.split("\r\n")
    start = [i for i, line in enumerate(lines) if line.startswith("### 7.1 ")][0]
    stop = [i for i, line in enumerate(lines) if line.startswith("### 7.2 ")][0]
    lf_block = "\n".join(lines[start:stop]) + "\n"
    crlf_block = "\r\n".join(lines[start:stop]) + "\r\n"
    return {
        "start": start + 1,
        "stop": stop,
        "lf_chars": len(lf_block),
        "lf_sha8": sha256_hex(lf_block.encode())[:8],
        "crlf_chars": len(crlf_block),
        "crlf_sha8": sha256_hex(crlf_block.encode())[:8],
    }


# --------------------------------------------------------------------------
# M1：标题
# --------------------------------------------------------------------------
OLD_H1 = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.15（2026-11-08）"
NEW_H1 = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.16（2026-11-08）"

# --------------------------------------------------------------------------
# M2：修订记录追加一行（插在 v0.9 行之后，保留原有两行空行）
# --------------------------------------------------------------------------
V016_ROW = (
    "| v0.16（裁定） | 2026-11-08 | **R16（v0.15 逐字节为底，只填两处派单缺口；`F-A1`–`F-A47` 号与阈值一字不动）**："
    "① **§7.16.4（P1，条款自相矛盾）** 追加键表原只给单一变体的键数（7/8/8/8/7），**没有组合行**，"
    "按字面读 9 键不在表内；改为 **键数唯一算法 `|detail| = 7 + |{status, violations, dual_ids} ∩ 实产键|`**，"
    "并把 `status`/`violations`/`dual_ids` 三键的成立条件写成互不重叠的三条判式，表内补 **4 行组合行**"
    "（`FS01`+`violations`=9、`FS03`/`FS06`+`violations`=8、`FS04`+`violations` 不并存=8、`FS02`+`violations`=8）；"
    "写明 **`FS04` 恒优先、出现 `dual_ids` 时永不追加 `violations`**；`F-A47-4` 的「逐键等于 7 键」对 `FS09` 仍成立，"
    "同处加一句「其余变体按追加键集合判定，不按固定键数」。实测 **42 次调用（14 组输入 × 3 模式）**，"
    "其中 **31 次抛错带 `detail`、算法在这 31 次上 31/31 成立**（另 11 次 `diagnostic` 放行、不产 `detail`）；"
    "键数实际取值 **{7,8,9}**。"
    "② **§7.7.2 + §7.17.5（P0，接线陷阱）** 缺省事实源必须绑定 `data_dir`：`RegistryFacts(None)` 不读盘 → `_load_definitions()` 返回 `{}` → "
    "盘上 8 只 `active` 全被读成 `status=None` → `FS01`，任何调用点忘传 `facts` 即全站静默停产。"
    "写死「缺省事实源解析不到 `data_dir` 即 fail-closed 抛 `FS09`，不得静默按 `draft` 判」，新增 **`F-A48`**（4 条）与 **`F-A49`**（2 条）。"
    "**不新增错误码**：`FS01`–`FS10` 已全占，`F-A48` 复用 `FS09`（与 §7.17.4 `C4` 同一出口）。 "
    "| 开发经理 v0.16 派单两缺口 + 架构师本机复跑（`research/arch-build-20261108/probe_v016_gaps.py`、`EVIDENCE_v016.json`）+ "
    "盘面 `gate.py`（2026-11-08 03:46:31 / 36,334 B）实读 |"
)

# --------------------------------------------------------------------------
# M3：§7.16.4 追加键表（旧 5 行 → 新表头 + 算法前置段 + 组合行）
# --------------------------------------------------------------------------
OLD_TABLE_INTRO = "- **7 键之上的追加键只有三处（穷举；别处不得追加）**："
NEW_TABLE_INTRO = (
    "- **7 键之上的追加键只有三处（穷举；别处不得追加），且键数由唯一算法给出、不逐行数数**：\n\n"
    "  **唯一算法（本节唯一口径，替代任何逐行数数的读法）**：\n\n"
    "  ```\n"
    "  detail = 固定 7 键 ∪ { k ∈ {status, violations, dual_ids} | k 的成立条件为真 }\n"
    "  键数 |detail| = 7 + |{ k 的成立条件为真 }|\n"
    "  ```\n\n"
    "  三键的成立条件**互不重叠、可机械判**（`code` = 本条最终上报码，见下方「去重先于 `detail`」条）：\n\n"
    "  | 追加键 | 成立的充要条件 | 与另外两键的关系 |\n"
    "  | --- | --- | --- |\n"
    "  | `status` | **`code == \"FS01\"`** | 与 `violations` **可同时成立**（9 键）；与 `dual_ids` **永不共存**（`FS04` 恒优先，见下） |\n"
    "  | `violations` | **`code != \"FS04\"`** 且 `blocked` 含 **≥2 个不同 `submitted_id`** | 与 `status` **可同时成立**（9 键）；**`code == \"FS04\"` 时恒不成立** |\n"
    "  | `dual_ids` | **`code == \"FS04\"`** | 与另外两键 **互斥**（`FS04` 优先于 `FS01`/`FS03`/`FS06`，故 `status` 不追加；又因 `code == \"FS04\"` 使 `violations` 条件恒假） |\n\n"
    "  **`FS04` 恒优先（写死，不许有第二种读法）**：`_guard_dual_id` 在 `FS01`/`FS03`/`FS06` 上报之前抛出，故 `code == \"FS04\"` 时"
    "**即使 `blocked` 含 ≥2 个不同 `submitted_id` 也绝不追加 `violations`**——实测 `[\"vol60\",\"uf_vol60\",\"uf_dist_prior_high_250\"]` 三个 id、"
    "`blocked` 含 2 个不同 id，`detail` 仍为 **8 键**（7 + `dual_ids`，无 `violations`）。\n\n"
    "  由此推出的键数取值域是 **{7, 8, 9}** 三值，不是 {7, 8}；下表把**单一变体**与**组合行**并列，"
    "「键数」列只是算法的取值示例，**判定仍以算法为准**。\n\n"
    "  **`F-A47-4` 的「`detail` 逐键等于 7 键」对 `FS09` 仍成立**（`FS09` 的追加键集合恒为 `{}`，故键数恒 7）；"
    "但**其余变体一律按追加键集合判定，不按固定键数**——表里出现的 7 / 8 / 9 是取值的样例，"
    "不是可枚举的封闭清单；凡与本算法冲突的逐行数数读法，一律以算法为准。"
)

OLD_TABLE = """| 变体 | 追加键 | 键数 | 依据 |
| --- | --- | --- | --- |
| 单条 `FS03` / `FS06` | — | **7** | 本节 |
| `FS01` | `status` | 8 | §7.7.5 既有（本节不改；§7.7.5 正文的 `factor_id` 与本节 `submitted_id` 同值异名，实现只有 `submitted_id` 一键） |
| `FS04` | `dual_ids`（数组，按输入顺序） | 8 | §7.17.4 C2 / C7 —— 本节新增的**唯一**授权附加键 |
| 批量入口（`/run-all`、`/factor/batch`），**或** `blocked` 含 ≥2 个**不同** `submitted_id` | `violations`（数组；每项只列该 id 去重后的一码） | 8 | 本节下一条 + 本节「去重先于 `detail`」条（v0.15 落定） |
| `FS09` | **无** | **7** | §7.17.4 C4 / C7、`F-A47-4`：靠 `code` 与 `message` 区分，不靠键的存在性 |"""

NEW_TABLE = """| 变体 | 追加键集合 | 键数 = 7 + \\|集合\\| | 依据 |
| --- | --- | --- | --- |
| 单条 `FS03` / `FS06` / `FS09` / `FS02` / `FS05` / `FS10`，且 `blocked` 只有 1 个 `submitted_id` | `{}` | **7** | 本节；`FS09` 同见 §7.17.4 C4 / C7、`F-A47-4` |
| `FS01`，且 `blocked` 只有 1 个 `submitted_id` | `{status}` | **8** | §7.7.5 既有（本节不改；§7.7.5 正文的 `factor_id` 与本节 `submitted_id` 同值异名，实现只有 `submitted_id` 一键） |
| `FS04`（恒优先；`blocked` 不同 id 数**不影响**本行） | `{dual_ids}` | **8** | §7.17.4 C2 / C7 —— 本节新增的**唯一**授权附加键 |
| 批量入口（`/run-all`、`/factor/batch`），**或** `blocked` 含 ≥2 个**不同** `submitted_id`，且 `code != "FS04"`、`code != "FS01"` | `{violations}` | **8** | 本节下一条 + 本节「去重先于 `detail`」条（v0.15 落定）；**组合行①** |
| **组合行②**：`code == "FS01"` **且** `blocked` 含 ≥2 个不同 `submitted_id` | `{status, violations}` | **9** | 算法直接推出；**v0.16 补**（v0.15 表缺此行，按字面读 9 键不在表内） |
| **组合行③**：`code == "FS04"` **且** `blocked` 含 ≥2 个不同 `submitted_id` | `{dual_ids}` | **8** | 算法直接推出（`FS04` 优先 ⇒ 不追加 `violations`）；**v0.16 补** |
| **组合行④**：`code` ∈ {`FS03`,`FS06`,`FS02`,`FS05`,`FS10`} **且** `blocked` 含 ≥2 个不同 `submitted_id` | `{violations}` | **8** | 与组合行①同集合，单列一行以便与②③对照；**v0.16 补** |
| `FS09`（入参非法，单个参数名作 `submitted_id`，`blocked` 恒不进） | **无**（恒 `{}`） | **7** | §7.17.4 C4 / C7、`F-A47-4`：靠 `code` 与 `message` 区分，不靠键的存在性 |"""

# --------------------------------------------------------------------------
# M4：表后追加「组合实测」条（插在 `dual_ids` 载体条之前）
# --------------------------------------------------------------------------
ANCHOR_AFTER_TABLE = (
    "- **`dual_ids` 只在 `GateError.detail` 上（v0.14 裁定 (a)）**"
)

COMBO_EVIDENCE = """- **组合实测（v0.16 新增；`production` / `research` / `diagnostic` × 14 组输入 = 42 次调用，可复跑 `research/arch-build-20261108/probe_v016_gaps.py`，产物 `EVIDENCE_v016.json`；独立复算 `verify_v016.py`）**：下表是算法的取值样例，不是判定依据；判定一律按上面的算法。**同一组输入换 `mode` 会换 `code`，因而换键数** —— 这一列必须逐格读，不能只记 id 组合。**口径须分清**：42 次调用中 **31 次抛 `GateError` 带 `detail`**（算法在这 31 次上 **31/31 成立**，键数实际取值 {7,8,9}），**另 11 次是 `diagnostic` 放行、根本不产 `detail`**，键数判据不适用（不是「42 次都得 7/8/9」）：

| 输入（`registry = D:/TSP/data`） | `production` | `research` | `diagnostic` |
| --- | --- | --- | --- |
| `["vol60"]`（alias，单 id） | `FS03` → **7** | `FS01` → **8** | 通过 |
| `["ma120"]` / `["prior_high_20"]`（alias，单 id） | `FS03` → **7** | `FS01` → **8** | 通过 |
| `["ma20"]`（撞名，`kind=custom`、无 `status`） | `FS01` → **8** | `FS01` → **8** | 通过 |
| `["vol60","uf_vol60"]`（双 id，同一 canonical） | `FS04` → **8** | `FS04` → **8** | 通过 |
| `["uf_dist_prior_high_250","cf_auction_resonance"]`（2 不同 id，都 `FS01`） | `FS01` → **9** | `FS01` → **9** | 通过 |
| `["uf_dist_prior_high_250","vol60"]`（2 不同 id，首码 `FS01`、次码 `FS03`） | `FS01` → **9** | `FS01` → **9** | 通过 |
| `["vol60","uf_dist_prior_high_250"]`（**同一对、输入顺序相反**） | `FS03` → **8** | `FS01` → **9** | 通过 |
| `["uf_dist_prior_high_250","cf_auction_resonance","vol60"]`（3 不同 id） | `FS01` → **9** | `FS01` → **9** | 通过 |
| `["vol60","uf_vol60","ma20"]`（`FS04` + 第 3 个 id） | `FS04` → **8** | `FS04` → **8** | 通过 |
| `["vol60","uf_vol60","uf_dist_prior_high_250"]`（`FS04` + 另一个 `FS01` id） | `FS04` → **8** | `FS04` → **8** | 通过 |
| `["no_such_xyz"]`（未登记，单 id） | `FS02` → **7** | `FS02` → **7** | `FS02` → **7** |
| `["no_such_xyz","uf_dist_prior_high_250"]`（`FS02` + `FS01`） | `FS02` → **8** | `FS02` → **8** | `FS02` → **7**（`diagnostic` 放行 `FS01`，只剩 `FS02` 一码、`blocked` 只 1 个 id ⇒ 不追加 `violations`） |
| `["no_such_a","no_such_b"]`（2 个未登记） | `FS02` → **8** | `FS02` → **8** | `FS02` → **8** |

- **`violations` 里每项只有一码、且按 `blocked` 顺序**：每项 = `{"submitted_id": <id>, "code": <该 id 去重后的一码>}`。`blocked` 的顺序 = 输入顺序（`_normalise_ids` 去重保序），故 `violations` 顺序 = 输入顺序，不是优先级顺序 —— 实测 `["uf_dist_prior_high_250","cf_auction_resonance","vol60"]` 得 `[FS01, FS01, FS03]`（第三个是 `FS03` 而非别的），与 `_CODE_PRIORITY` 只作用于**同一 id 内部**一致。
"""

# --------------------------------------------------------------------------
# M5：§7.7.2 闸门层签名行后追加缺省事实源硬约束（缺口 2 的条款位置）
# --------------------------------------------------------------------------
OLD_SIG_LINE_TAIL = (
    "（**v0.12 追加**在尾部追加一个 keyword-only 参数 `namespace: str | Mapping[str, str] = \"factor\"`，"
    "缺省即今日行为，见 §7.17.2；既有参数名、顺序、缺省值一个不改。）"
)
NEW_SIG_LINE_TAIL = (
    "（**v0.12 追加**在尾部追加一个 keyword-only 参数 `namespace: str | Mapping[str, str] = \"factor\"`，"
    "缺省即今日行为，见 §7.17.2；既有参数名、顺序、缺省值一个不改。）\n"
    "- **缺省事实源必须绑定 `data_dir`（v0.16 新增，P0；判据 `F-A48`）**：`facts` 缺省时，实现只能经 `default_facts_source()` 取源，"
    "该函数把 `settings.data_dir`（= `.env` 的 `DATA_DIR`）绑进 `RegistryFacts(data_dir)`。**不得**用 `RegistryFacts()`（`data_dir=None`）当缺省："
    "它不读盘，`_load_definitions()` 直接返回 `{}`，`_definition_status(None)` → `None` → 按 `draft` 判 `FS01`，"
    "盘上 8 只 `active` 会被全判 `draft`、**全站静默停产**，且 `detail.status=None` 会被排障误读成「盘上没有 status」。"
    "**解析不到 `data_dir` 时 fail-closed**：抛 `GateError(code=\"FS09\")`、`detail.submitted_id=\"data_dir\"`、`detail` 恰 7 键、"
    "**不返回 `GateReport`**、**不退化成空事实源**。注意区分两种「没有 status」（不许混成同一种报错）："
    "①**压根没看到盘**（`data_dir` 解析不到）→ `FS09` 抛错；②**看到了盘、盘上确实没有该 id 的 status** → 按 §7.8.4 末行以 `draft` 判 `FS01`。"
    "调用方**显式**传 `facts=RegistryFacts()`（`data_dir=None`）不在本条范围内 —— 那是调用方自选空源，行为仍是 `FS01`，但它不是缺省。"
)

# --------------------------------------------------------------------------
# M6：§7.17.5 判据表后（`F-A47-4` 行之后、`#### 7.17.6` 之前）追加 F-A48 / F-A49
# --------------------------------------------------------------------------
ANCHOR_7176 = "#### 7.17.6 实现与接线约束（给系统开发工程师；本节只出条款，不写实现）"

FA48_BLOCK = """**`F-A48` 缺省事实源绑定 `data_dir` 且缺失即 fail-closed（v0.16 新增；P0；不新增错误码，复用 `FS09`）**

背景（2026-11-08 03:4x 盘面实测）：`RegistryFacts(None)` 的 `_load_definitions()` 直接返回 `{}`，故 `status` 恒为 `None`；`D:/TSP/data` 上 15 个定义 = **8 `active` + 7 `draft`**，缺省源若不绑定 `data_dir` 就把这 8 只全判 `FS01`。本条只定条款，实现归系统开发。

| # | 判据 | 度量（可机械判） |
| --- | --- | --- |
| `F-A48-1` | 缺省源**已绑定** | 存在 `gate.default_facts_source()`；`gate.default_facts_source()._data_dir is not None`，且 `Path(_data_dir) == Path(app.config.settings.data_dir)`。**反例**：`_data_dir is None` 即失败 |
| `F-A48-2` | 不传 `facts` 时**读到盘上 status** | 盘上 8 只 `active`（`uf_vol60` / `uf_ma120` / `uf_ma200` / `uf_prior_high_20` / `uf_prior_high_250` / `uf_prior_high_55` / `uf_prior_low_10` / `uf_prior_vol_20`）在 `production` / `research` / `diagnostic` 三模式下**各调一次** `assert_factors_usable(8 只, mode)`（**不传 `facts`**）→ 三次均 `ok=True`、`blocked=()`、`non_active=()`、`unknown=()`。任一模式出现 `FS01` 即失败（= 把 active 判成 draft） |
| `F-A48-3` | `data_dir` 解析不到 → **抛错，不返回 `GateReport`** | 令 `app.config.settings.data_dir = None`，调 `assert_factors_usable(["close"], mode)`（不传 `facts`）→ **抛 `GateError`**、`code == "FS09"`、`detail` **逐键等于 §7.16.4 固定 7 键**（不多不少）、`detail["submitted_id"] == "data_dir"`、`"data_dir" in detail["message"]`；**不得**返回 `GateReport`、**不得**抛 `ValueError` / `KeyError` / `AttributeError`。`app.config` 导入失败的分支同判（`code == "FS09"`） |
| `F-A48-4` | 两种「没有 status」不混判 | ①`settings.data_dir = None`（没看到盘）→ `FS09`（见 `F-A48-3`）；②`settings.data_dir` 指向**存在但无该 id JSON**的目录 → **`FS01`**（不是 `FS09`），且 `detail["status"] is None`、`detail` 恰 **8 键**（7 + `status`）。两次 `code` **必须不同** |

**`F-A49` 缺省源错误的 `mode` 保真（v0.16 新增；P1，随 `F-A48` 一并判）**

背景（同一批实测发现的真实缺陷）：`default_facts_source()` 内部调 `_invalid_argument("data_dir", "production", …)`，`mode` 被**写死**成 `"production"`。于是 `research` / `diagnostic` 调用在 `data_dir` 缺失时，`detail.mode` 报 `"production"`，违反 §7.16.4「`mode` = 本次请求的模式（`production` / `research` / `diagnostic` 取一）」。本节只出条款，实现归系统开发。

| # | 判据 | 度量（可机械判） |
| --- | --- | --- |
| `F-A49-1` | `detail.mode` = 调用方传的 `mode` | 令 `app.config.settings.data_dir = None`，对 `mode ∈ {production, research, diagnostic}` **各调一次**（不传 `facts`）→ 三次均抛 `GateError`、`code == "FS09"`，且 **`detail["mode"] == 传入的 mode`**（逐模式断言，三次不容许同为 `"production"`）。实测缺陷形态：三次都报 `"production"` |
| `F-A49-2` | 不因此改七键形状与 `submitted_id` | 三次的 `detail` 键集合**逐键等于 §7.16.4 固定 7 键**（不追加 `status`/`violations`/`dual_ids`）、`detail["submitted_id"] == "data_dir"`、`resolved_id` / `canonical_id` / `table_row` 均为 `None` |

**与既有判据的关系（不许重号、不许改阈值）**：`F-A1`–`F-A47` 一字不动；`F-A43`–`F-A47` 仍按原样判 `namespace` / `EXEMPT_KINDS` / `GateError` 出口；`F-A48` / `F-A49` 只判「缺省事实源」这一新面，**不改任何既有判据的度量**。**不新增错误码**：`FS01`–`FS10` 已全占（`FS09` 已是 `C4` 的入参非法码），本条复用 `FS09`，理由是「`data_dir` 解析不到」本质上就是「闸门拿不到判定所需的事实源」，与「入参非法」同属**调用前提不成立**，不同码会把同一类失败拆成两个出口。

**今天的状态（2026-11-08 03:5x 实测，供验收对锚）**：`default_facts_source()` **已存在**且 `_data_dir == D:/TSP/data`（`F-A48-1` 已过）；8 只 active 三模式不传 `facts` 全 `ok=True`（`F-A48-2` 已过）；`data_dir=None` 时三模式均抛 `FS09`、七键、`submitted_id="data_dir"`（`F-A48-3` 已过）；`F-A48-4` ②（空目录 → `FS01`、8 键）已过。**`F-A49-1` 未过**：`research` / `diagnostic` 下 `detail.mode` 仍为 `"production"`（`mode` 保真 1/3），这是本节新增条款指向的**唯一未过项**，执行归系统开发。

"""

# --------------------------------------------------------------------------
# M7：§15 本版改动说明（追加在 footer 之前）
# --------------------------------------------------------------------------
SECTION15 = """## 15. 本版改动说明（v0.16 / R16：两处派单缺口的条款填充）

**本版只做两件事，不含任何新准入裁定、不改任何判据阈值、不动 `F-A1`–`F-A47` 的号与字面。**

| # | 位置 | 旧（v0.15） | 新（v0.16） | 性质 |
| --- | --- | --- | --- | --- |
| R16-1 | `# 因子化引擎… v0.15` 标题（`:1`） | `v0.15` | `v0.16` | 版本身份 |
| R16-2 | 修订记录表（`v0.9` 行之后） | — | 新增 `v0.16（裁定）` 行 | 版本簿记 |
| R16-3 | §7.16.4 `- **7 键之上的追加键只有三处（穷举；别处不得追加）**：` | 一句引导语，紧接 5 行单变体表 | 该句 + **键数唯一算法**（`|detail| = 7 + |{status,violations,dual_ids} ∩ 实产键|`）+ **三键成立条件表**（互不重叠的三条判式）+ **`FS04` 恒优先**写死 + **「`F-A47-4` 的逐键等于 7 键对 `FS09` 仍成立；其余变体按追加键集合判定、不按固定键数」** | **P1 收口**：把「逐行数数」换成唯一算法 |
| R16-4 | §7.16.4 追加键表（5 行） | 单一变体 7/8/8/8/7，**无组合行** | 8 行 = 3 行单变体 + **4 行组合行**（9/8/8 各一）+ `FS09` 行；表头加 `键数 = 7 + |集合|` | **P1 收口**：9 键入表 |
| R16-5 | §7.16.4 表后（`dual_ids` 载体条之前） | — | 新增**组合实测表**（14 组输入 × 3 模式）+ `violations` 顺序条 + **口径句（31 次带 `detail` / 11 次 `diagnostic` 放行）** | 取证：算法 31/31 成立 |
| R16-6 | §7.7.2 闸门层签名句之后 | — | 新增**缺省事实源必须绑定 `data_dir`** 条（fail-closed 抛 `FS09`，区分两种「没有 status」） | **P0 收口**：接线陷阱 |
| R16-7 | §7.17.5 判据表后（`## 8.` 前） | — | 新增 **`F-A48`**（4 条）/ **`F-A49`**（2 条）+ 与既有判据的关系 + 今日实测锚 | 新增判据号，不改旧号 |
| R16-8 | 本 §15 | — | 本节 | 版本簿记 |
| R16-9 | footer（最后一行） | v0.15 的 footer | 由**本版正文字节**重算 | 自洽 |

**为什么键数必须是算法而不是枚举（三条理由）**

1. **追加键彼此不互斥，枚举必然漏格**：`status`（跟 `code == "FS01"` 走）与 `violations`（跟「`blocked` 含 ≥2 个不同 id」走）是**两个正交维度**，两者可同时为真 → 9 键。v0.15 的表把「`FS01`」与「批量/≥2 个不同 id」写成两行、各给 8，**读者按字面把两行取并集就会得出「不可能同时成立」或「同时成立时键数未定义」两种错误结论**。这不是措辞问题，是两条书面判据不能同时成立（与 P0-X 同型）。
2. **`FS04` 是唯一的例外，必须显式写死**：`_guard_dual_id` 在 `FS01`/`FS03`/`FS06` 上报**之前**抛出，所以 `code == "FS04"` 时 `violations` 永不出现（即使 `blocked` 含 ≥2 个不同 id）。若只用「7 + 追加键数」而不写 `FS04` 优先，实现方会按「≥2 个不同 id 就加 `violations`」写出 10 键，与实现（8 键）冲突。
3. **`mode` 会改 `code`，`code` 会改键数**：同一组输入在 `production` 与 `research` 下可分别得 `FS03` 与 `FS01`（`7` vs `8`），**甚至同一对 id 只因输入顺序不同就得 `FS03`→8 与 `FS01`→9**（实测 `["vol60","uf_dist_prior_high_250"]` vs `["uf_dist_prior_high_250","vol60"]`）。任何「按 id 组合查表」的写法都会在这里错。

**为什么 `F-A48` 复用 `FS09` 而不新开码**：`FS01`–`FS10` 十个码已全部占用（`FS07` = V3 未过、`FS08` = G2 成交口径、`FS09` = 入参非法、`FS10` = 矩阵能力缺口）。新开 `FS11` 会与 §7.10.2 的 `code` 枚举（`FS01`–`FS07`）及 §7.17.4 `C4` 的「`FS09` 是 `FS01`–`FS10` 之间唯一空位」直接冲突。`data_dir` 解析不到 = 调用前提不成立，与「入参非法」同类，复用 `FS09` 成本最低且不产生第二种出口。

**未动项（硬约束，逐项实测）**

| 项 | 断言 | 实测 |
| --- | --- | --- |
| `§7.1` 块 | LF 归一 `2,514` 字符 / `6d3db013…`；CRLF 保留 `2,541` 字符 / `a8e88134…` | 与 v0.15 **逐字节相等**（`verify_v016.py` B1–B3） |
| `F-A1`–`F-A47` | 判据行逐行未动 | 逐行相等（E1）；未新增 `F-A1`–`F-A47` 号（E2） |
| 判据阈值 | 零改动 | 同上 |
| 错误码集 | `FS01`–`FS10` 不变 | `FS09` 复用，无 `FS11` |
| `backend/**`、`docs/factors/**` | 一个字节不改 | 未写入、未提交 |

**版本关系**：v0.15 保持原字节、不删不改（**现行版身份移交本版**）；v0.14 / v0.13（被退回稿）、v0.12（更早的被退回稿）、v0.11（未签发）、v0.10 及更早**逐字节保留**。

"""


CR = chr(13)
LF = chr(10)


def build(dst: Path) -> dict:
    base = BASE.read_bytes()
    # 底本守卫
    if len(base) != BASE_LEN:
        raise SystemExit(f"底本长度变了: {len(base)} != {BASE_LEN}")
    if sha256_hex(base) != BASE_SHA:
        raise SystemExit("底本哈希变了")
    if base.count(b"\n") != BASE_NL:
        raise SystemExit(f"底本行数变了: {base.count(chr(10).encode())}")
    if sha256_hex(base[:BASE_BODY_LEN]) != BASE_BODY_SHA:
        raise SystemExit("底本正文字节变了")

    text = base.decode("utf-8")
    assert "\r\n" in text

    # 改前 7.1 锚
    pre71 = section_7_1(text)
    if (pre71["lf_chars"], pre71["lf_sha8"], pre71["crlf_chars"], pre71["crlf_sha8"]) != (
        SEC71_LF_CHARS, SEC71_LF_SHA8, SEC71_CRLF_CHARS, SEC71_CRLF_SHA8
    ):
        raise SystemExit(f"底本 §7.1 锚不符: {pre71}")

    changes: list[dict] = []

    def crlf(s: str) -> str:
        """把以 \\n 书写的常量按文档行尾（CRLF）展开；已含 CRLF 的原样返回。"""
        return s.replace("\r\n", "\n").replace("\n", "\r\n")

    def replace_once(hay: str, old: str, new: str, tag: str) -> str:
        old_c, new_c = crlf(old), crlf(new)
        n = hay.count(old_c)
        if n != 1:
            raise SystemExit(f"[{tag}] 期望唯一匹配，实际 {n} 次")
        changes.append({"tag": tag, "old_chars": len(old_c), "new_chars": len(new_c)})
        return hay.replace(old_c, new_c, 1)

    out = text
    out = replace_once(out, OLD_H1, NEW_H1, "M1-H1")
    out = replace_once(out, OLD_TABLE_INTRO, NEW_TABLE_INTRO, "M3-table-intro")
    out = replace_once(out, OLD_TABLE, NEW_TABLE, "M4-table-rows")
    out = replace_once(out, ANCHOR_AFTER_TABLE, COMBO_EVIDENCE + ANCHOR_AFTER_TABLE, "M5-combo-evidence")
    out = replace_once(out, OLD_SIG_LINE_TAIL, NEW_SIG_LINE_TAIL, "M6-default-source")
    out = replace_once(out, ANCHOR_7176, FA48_BLOCK + ANCHOR_7176, "M7-FA48-FA49")

    # M2：修订记录行（插在 v0.9 行之后）
    lines = out.split("\r\n")
    idx_v09 = [i for i, ln in enumerate(lines) if ln.startswith("| v0.9（裁定） |")][0]
    lines.insert(idx_v09 + 1, V016_ROW)
    changes.append({"tag": "M2-revision-row", "old_chars": 0, "new_chars": len(V016_ROW)})
    out = "\r\n".join(lines)

    # M7：§15 插在 footer 之前（footer = 最后一行非空后的那一行）
    lines = out.split("\r\n")
    # footer 是最后一条以「本文件正文 sha256」开头的行
    idx_footer = [i for i, ln in enumerate(lines) if ln.startswith("本文件正文 sha256")][0]
    # 在 footer 之前插入 §15：先找到 footer 前的 "---" 分隔
    insert_at = idx_footer
    lines[insert_at:insert_at] = SECTION15.rstrip("\n").split("\n") if "\r" not in SECTION15 else SECTION15.rstrip("\r\n").split("\r\n")
    changes.append({"tag": "M8-section15", "old_chars": 0, "new_chars": len(SECTION15)})
    out = "\r\n".join(lines)

    # 改后 7.1 锚（§7.1 在 §15 之前，插入不影响它，但仍要复算）
    post71 = section_7_1(out)
    if (post71["lf_chars"], post71["lf_sha8"], post71["crlf_chars"], post71["crlf_sha8"]) != (
        SEC71_LF_CHARS, SEC71_LF_SHA8, SEC71_CRLF_CHARS, SEC71_CRLF_SHA8
    ):
        raise SystemExit(f"改后 §7.1 锚不符: {post71}")

    # 去掉旧 footer，重算新 footer
    lines = out.split("\r\n")
    idx_footer = [i for i, ln in enumerate(lines) if ln.startswith("本文件正文 sha256")][0]
    # 正文 = footer 行起点之前的全部字节（含末尾空行），与 v0.15 footer 的 head -c 口径逐字节一致
    out_bytes = out.encode("utf-8")
    foot_off = out_bytes.rfind("本文件正文 sha256".encode("utf-8"))
    CRLF = bytes([13, 10])
    line_start = out_bytes.rfind(CRLF, 0, foot_off) + 2
    body_bytes = out_bytes[:line_start]
    body = body_bytes.decode("utf-8")
    body_sha = sha256_hex(body_bytes)
    body_len = len(body_bytes)
    n_body_lines = body_bytes.count(CRLF)

    footer = (
        f"本文件正文 sha256：`{body_sha}`（校验：`head -c {body_len} "
        f"\"docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md\" | sha256sum`；"
        f"正文 = 全文去掉最后一行 footer，以换行结尾）· 正文 `{body_len} B` · 全文 `{n_body_lines + 1}` 行"
        f"（正文 `{n_body_lines}` + footer 1）· 版本 **v0.16（2026-11-08 R16：派单两缺口一次并入 v0.15 现状；"
        f"判据阈值与 `F-A1`–`F-A47` 判据号零改动）** —— ① **§7.16.4（P1，条款自相矛盾）**：追加键表原只给单一变体键数、"
        f"**无组合行**，按字面读 9 键不在表内；改为**键数唯一算法** `|detail| = 7 + |{{status, violations, dual_ids}} ∩ 实产键|`，"
        f"三键成立条件写成互不重叠的三条判式（`status` ⇔ `code==FS01`；`violations` ⇔ `code!=FS04` 且 `blocked` 含 ≥2 个不同 "
        f"`submitted_id`；`dual_ids` ⇔ `code==FS04`），表内补 **4 行组合行**（9/8/8），"
        f"并**写死 `FS04` 恒优先、出现 `dual_ids` 时永不追加 `violations`**；键数取值域 **{{7,8,9}}**（不再是 {{7,8}}）；"
        f"`F-A47-4` 的「逐键等于 7 键」对 `FS09` 仍成立，同处写明「其余变体按追加键集合判定，不按固定键数」。"
        f"实测 **42 次调用（14 组输入 × 3 模式）**，其中 **31 次抛错带 `detail`、算法 31/31 成立**"
        f"（另 11 次 `diagnostic` 放行、不产 `detail`）（`probe_v016_gaps.py` / `EVIDENCE_v016.json`）。"
        f"② **§7.7.2 + §7.17.5（P0，接线陷阱）**：缺省事实源必须绑定 `data_dir`，解析不到即 **fail-closed 抛 `FS09`**、"
        f"**不返回 `GateReport`**、不退化成空事实源；`RegistryFacts(None)` 会把盘上 8 只 `active` 全判 `draft` → `FS01` → 全站静默停产；"
        f"新增 **`F-A48`**（4 条）与 **`F-A49`**（2 条，`detail.mode` 保真：盘面 `default_facts_source()` 把 `mode` 写死成 "
        f"`\"production\"`，`research`/`diagnostic` 下 `detail.mode` 报错 → `F-A49-1` 今日 1/3 未过）。**不新增错误码**："
        f"`FS01`–`FS10` 已全占，`F-A48` 复用 `FS09`（与 §7.17.4 `C4` 同一出口） · "
        f"生成：**v0.15 逐字节为底**（297,167 B / 2,372 行 / 全文 `146b96b2a3426853` / 正文 `c06815e5f31103e1`） + "
        f"**6 处正文改动 + 2 处插入**（H1 / 修订记录行 / §7.16.4 表引导语+算法 / §7.16.4 表 8 行 / §7.16.4 组合实测表 / "
        f"§7.7.2 缺省源条 / §7.17.5 `F-A48`+`F-A49` / 新增 §15） + 本 footer 由**本版正文字节**重算 · "
        f"**v0.16 为现行版**；v0.15（R15：P0-X 去重 / `E4-A4` 可判定五条 / `D6`→`D10`）、"
        f"v0.14 / v0.13（被退回稿）、v0.12、v0.11（未签发）、v0.10 及更早逐字节保留不删 · "
        f"`§7.1` 八行公式**十四份全同（v0.3–v0.16，含本版）**：LF `2,514` / `6d3db0139a45f54c`、"
        f"CRLF `2,541` / `a8e88134f60b504c`（台账 v5.11 `[4]` 绑块哈希，版本号不参与判定） · "
        f"`F-A1`–`F-A47` 判据号与阈值一字未动；本版新增且仅新增 `F-A48` / `F-A49`；错误码集不变（`FS01`–`FS10`）"
    )

    # body 已以 CRLF 结尾，直接接 footer，不得再插换行
    final_text = body + footer + CR + LF
    final = final_text.encode("utf-8")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(final)

    result = {
        "dst": str(dst),
        "size": len(final),
        "lines": final.count(b"\n"),
        "sha256": sha256_hex(final),
        "body_len": body_len,
        "body_sha256": body_sha,
        "footer_len": len(footer.encode("utf-8")),
        "changes": changes,
        "sec71_pre": pre71,
        "sec71_post": post71,
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=str(DEFAULT_DST))
    args = ap.parse_args()
    res = build(Path(args.dst))
    import json

    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
