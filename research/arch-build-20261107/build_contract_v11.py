"""v0.11 = v0.10 逐字节为底 + §10.3 停用 banner（标题下 3 行）+ 版本簿记（H1 / footer）。

只读 v0.10、只写 v0.11；不改 v0.7–v0.10、不改 backend/**、不提交、不部署。

DST 可重定向：只改 DST 一行就能在别的目录产出，产物必须逐字节相同
（v0.11 的正文与 footer 里不写任何绝对路径：footer 的路径是 v0.10 自带的历史字面量）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(r"C:/work/sourcecode/tick-stock-panel")
SRC = REPO / "docs" / "architecture" / "FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md"
DST = REPO / "docs" / "architecture" / "FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md"

# 底本守卫：v0.10 四元组（任何一个不符即停，不写文件）
BASE_SHA = "8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007"
BASE_LEN = 244093
BASE_NL = 2057
BASE_BODY_LEN = 242303
BASE_BODY_SHA = "e47703f2da50837627013d67abb8eebda094a2314490e35884de26af2cc4b870"

raw = SRC.read_bytes()
if hashlib.sha256(raw).hexdigest() != BASE_SHA:
    raise SystemExit("底本哈希变了")
if len(raw) != BASE_LEN:
    raise SystemExit(f"底本长度变了: {len(raw)}")
if raw.count(b"\n") != BASE_NL:
    raise SystemExit("底本行数变了")
if hashlib.sha256(raw[:BASE_BODY_LEN]).hexdigest() != BASE_BODY_SHA:
    raise SystemExit("底本正文前缀哈希不符")

BANNER_LINES = [
    "> ⛔ **本条裁定自 2026-11-07 起停用（已停用，R10）—— 判据、实现、评审均不得再按本节 recipe 2 下判。**",
    "> **现行唯一定义 = recipe 1 = §7.12.4 原文**（剔除 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键）；签认仍为**三元组** `(canonical_digest, schema_version, scanned_sources)`，`canonical_digest_recipe` 字段**不实现**；本节「本版起新产物必须用它」/「签认由三元组升为四元组」/「不可比不得判失败」/「L2 起产物必须 `\"2\"`」四句一并不生效；任何声称「recipe 2 合规」的产物按**不合规**处理。",
    "> 依据：`docs/architecture/CONTRACT_REVISION_R10_20261107.md` §7（独立审核四条 + 13 份产物 `canonical_digest_recipe` 全部 ABSENT、生成器 `grep` 为 0、审核 `A11 ok=false`）；本条只停用、不删除，正文历史保留以便复核。",
]
BANNER = ("\r\n" + "\r\n".join(BANNER_LINES) + "\r\n").encode("utf-8")

out = raw

# ── hunk 1：§10.3 标题下插 banner（1 个空行 + 3 行引用 = 插入 4 行）
HEAD_10_3 = "### 10.3 `notes` 是否进 canonical digest"
i = out.find(HEAD_10_3.encode("utf-8"))
if i < 0 or out.count(HEAD_10_3.encode("utf-8")) != 1:
    raise SystemExit("§10.3 标题锚点不唯一")
j = out.index(b"\r\n", i) + 2
if out[j:j + 2] != b"\r\n":
    raise SystemExit("§10.3 标题后不是空行")
out = out[:j] + BANNER + out[j:]

# ── hunk 2：H1 版本簿记（v0.10 → v0.11，1 字符）
H1_OLD = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.10（2026-11-07）"
H1_NEW = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.11（2026-11-07）"
if out.count(H1_OLD.encode("utf-8")) != 1:
    raise SystemExit("H1 锚点不唯一")
out = out.replace(H1_OLD.encode("utf-8"), H1_NEW.encode("utf-8"), 1)

# ── hunk 3a：footer 版本 token
FOOT_OLD = "版本 **v0.10（2026-11-07 R10："
FOOT_NEW = (
    "版本 **v0.11（2026-11-07 R11：§10.3 停用 banner 写入正文 + 版本簿记，判据零改动）**"
    "· v0.10（2026-11-07 R10："
)
if out.count(FOOT_OLD.encode("utf-8")) != 1:
    raise SystemExit("footer 版本锚点不唯一")
out = out.replace(FOOT_OLD.encode("utf-8"), FOOT_NEW.encode("utf-8"), 1)

# ── hunk 3b：footer 指针（接在 footer 最后一句之后）
TAIL_OLD = "逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
POINTER = (
    "· **§10.3 已停用（R10）**：停用 banner 在 §10.3 标题下三行；"
    "recipe 1 = §7.12.4 原文为唯一定义，签认三元组，`canonical_digest_recipe` 不实现；"
    "依据 `CONTRACT_REVISION_R10_20261107.md` §7 / `CONTRACT_REVISION_R11_20261107.md` §2"
)
if out.count(TAIL_OLD.encode("utf-8")) != 1:
    raise SystemExit("footer 尾锚点不唯一")
if out.rindex(TAIL_OLD.encode("utf-8")) < len(out) * 0.95:
    raise SystemExit("尾锚点不在 footer 区（不在文件末 5%）")
out = out.replace(TAIL_OLD.encode("utf-8"), (TAIL_OLD + POINTER).encode("utf-8"), 1)

DST.write_bytes(out)

print("size", len(out))
print("lines", out.count(b"\n"))
print("full", hashlib.sha256(out).hexdigest())
