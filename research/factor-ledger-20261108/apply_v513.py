# -*- coding: utf-8 -*-
"""v5.12 -> v5.13 精度订正（§17.4 归因细化 + 未提交实现状态）。

只改 docs/factors 下两文件；不碰 backend/**、不碰盘上定义、不提交。
每处替换断言「恰好命中 1 次」（fail-closed）；md 在 json 写后被第三方改动则中止。
注释里的 @@NL@@ 会被本脚本自己换成反斜杠+n 之前——见文件尾部 POST 段。
用法：cd <repo> && PYTHONUTF8=1 python research/factor-ledger-20261108/apply_v513.py
"""
from __future__ import annotations
import hashlib, io, json, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MD = REPO / "docs" / "factors" / "F_CLASS_REGISTRATION_20261107.md"
JS = REPO / "docs" / "factors" / "evidence" / "f_class_registry.json"
BACKUP = REPO / "research" / "factor-ledger-20261108" / "backup_v512"
PROBE_JSON = "research/factor-ledger-20261108/probe_collision_faces.json"

CN = timezone(timedelta(hours=8))
NOW = datetime.now(CN)
HHMM = NOW.strftime("%H:%M")
ISO = NOW.strftime("%Y-%m-%dT%H:%M+0800")
NL = chr(10)
CRLF = bytes([13, 10])

OLD_REG_ROW = ("| `docs/factors/evidence/f_class_registry.json` | 178,326 B | 3089 | LF（CRLF 0） "
               "| 2026-11-08T01:10 | `010a08f40f8c3e4f4cf4c5a833761f782ef099fd2d548742ee8eae598657b55e` "
               "| `010a08f40f8c3e4f4cf4c5a833761f782ef099fd2d548742ee8eae598657b55e` |")


def sub_once(text, old, new, tag):
    n = text.count(old)
    if n != 1:
        raise SystemExit("[FAIL] anchor %s: expected 1 hit, got %d" % (tag, n))
    return text.replace(old, new)


def lf_sha(raw):
    lf = raw.replace(CRLF, bytes([10]))
    return len(raw), lf.count(bytes([10])), hashlib.sha256(lf).hexdigest()


BANNER = (
    f"> **v5.13（2026-11-08 {HHMM}）：两处精度订正，公式与数值一律不动** —— "
    "①§17.4 把「这 4 个名字在活信号里」的写法写成一律带 `field:` 前缀，**以偏概全**：实测 7 条活信号共 **14 处引用**，"
    "其中 **12 处带 `field:`、2 处是裸名**（`ma_golden_20_60` 两个条件的 `left` 都写裸 `ma20`，`right` 是 `field:ma60`）；"
    "两种写法在本 DSL 里**都是列引用、都不是因子引用**，结论不变，但写法必须能对着盘面读 → 新增 §17.6。"
    "②「列面 0 码放行」是**工作树未提交**实现的实测：`git show HEAD:backend/app/factors/gate.py` 的 "
    "`assert_factors_usable` 签名（HEAD `:467`–`:477`）**没有** `namespace`，HEAD 全文 grep `namespace` 只有 `:592` 一处注释命中；"
    "故「今天这 7 条信号不会被打成 400」的真实理由是 **§17.5 那条「闸门生产调用点 = 0」**，**不是**「列面已上线所以安全」。"
    "**8 只公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列、`replaced_by` 四条、K1–K12、`signature` 三元组一律未动。**"
)

SEC176_LINES = [
    "## 17.6 v5.13 两处精度订正（只改写法，不改任何裁定）",
    "",
    "复核脚本：`research/factor-ledger-20261108/probe_collision_faces.py`；原始输出 `probe_collision_faces.json`"
    "（2,663 B / LF `dfa42a020a0fc0f9…`）。两处都由这一个脚本一次跑出。",
    "",
    "### 17.6.1 活信号的引用写法：12 处 `field:` + 2 处裸名",
    "",
    "| 信号（`enabled` 全 `true`、`kind` 全 `both`） | 引用写法 |",
    "| --- | --- |",
    "| `boll_breakdown_lower` | `right='field:boll_lower'` |",
    "| `boll_breakout_upper` | `right='field:boll_upper'` |",
    "| `ma20_breakdown` / `ma20_breakout` / `ma_dead_5_20` / `ma_golden_5_20` | `right='field:ma20'`（每条两条件的 `right`） |",
    "| `ma_golden_20_60` | **`left='ma20'`（裸名，两条件各一）** + `right='field:ma60'` |",
    "",
    "- 合计 **14 处**引用：**12 处带 `field:` 前缀、2 处裸名**；`field:` 前缀与裸名在本 DSL 里**都是列引用**，都不是因子引用 → 都走 column 面。",
    "- §17.4 那句「是列（`field:ma20` / `field:ma60` / `field:boll_lower` / `field:boll_upper`）」按此更正；"
    "**§17.4 的结论（当因子引用 → `FS01` → 400；当列引用 → 0 码）不变**。",
    "",
    "### 17.6.2 `namespace` 是工作树未提交实现，HEAD 上没有",
    "",
    "- HEAD：`git show HEAD:backend/app/factors/gate.py` 的 `assert_factors_usable` 签名（`:467`–`:477`）参数为 "
    "`factor_ids / mode / allow_non_active / allow_retired / require_status / shadow / entry / facts` —— **没有 `namespace`**；"
    "HEAD 全文 `grep -n namespace` → **仅 `:592` 一处注释**命中。",
    "- 工作树：`backend/app/factors/gate.py` 现有 `namespace` keyword-only 参数（`:570`）与 `_namespace_faces`（`:336`），"
    "但该文件 `git status` 为 ` M`（**未提交**）。",
    "- 实测（`probe_collision_faces.json`）：`gate.assert_factors_usable.__code__.co_varnames` 含 `namespace` = **True**；"
    "4 名 **factor 面 4/4 `FS01`**、**column 面 4/4 `[]`（0 码）**。",
    "- 读法：**HEAD 上按因子面引用这 4 个名字仍是 `FS01` → 400**（不是 `FS03`）；「列面 0 码」只在工作树成立。",
    "- **「今天 7 条信号不被打成 400」的真实理由是 §17.5：闸门的生产调用点 = 0。** 不许读成「列面已上线、所以安全」。",
    "",
    "### 17.6.3 本节没做的事",
    "",
    "未改任何公式 / `warmup_bars` / `dependencies` / `shift` / 双 id 三列 / `replaced_by` / K1–K12 / `signature`；"
    "未改 `market_breadth` 门票任何参数；未改 §17.1–§17.3 的裁定文本；未改 `backend/**`"
    "（`gate.py` 的未提交改动**不是我改的、我也没动它**）；未提交、未部署。",
    "",
    "---",
    "",
]
SEC176 = NL.join(SEC176_LINES)


def edit_json(doc):
    meta = doc["meta"]
    old_ver = meta["version"]
    meta["version"] = "5.13" if isinstance(old_ver, str) else 5.13
    meta["revised_at"] = ISO
    meta["freeze_declaration"]["status"] = "FROZEN at v5.13"
    meta["freeze_declaration"]["declared_at"] = ISO
    doc["self_check"]["generated_at"] = ISO
    doc["v5_13_changes"] = {
        "batch": "v5.13 精度订正（§17.4 归因细化），公式与数值一律不动",
        "date": "2026-11-08",
        "author": "因子工程师",
        "scope": "docs/factors 两文件（台账 md + evidence/f_class_registry.json）；未改 backend/**、未改盘上定义、未提交",
        "probe": {
            "script": PROBE_JSON.replace(".json", ".py"),
            "output": PROBE_JSON,
            "output_size_bytes": 2663,
            "output_lf_sha16": "dfa42a020a0fc0f9",
        },
        "changes": [
            {
                "id": 1,
                "what": "§17.4 把 4 个名字在活信号里的写法写成一律 `field:` 前缀",
                "fix": "实测 7 条活信号共 14 处引用：12 处带 field: 前缀、2 处裸名（ma_golden_20_60 两条件的 left='ma20'）；"
                       "field: 前缀与裸名都属列引用，都不是因子引用",
                "why": "写法要能对着盘面读；结论（factor 面 FS01→400 / column 面 0 码）不变",
            },
            {
                "id": 2,
                "what": "「列面 0 码放行」被写得仿佛已交付",
                "fix": "HEAD 的 assert_factors_usable 签名（HEAD :467-:477）无 namespace，HEAD 全文 grep namespace 仅 :592 一处注释；"
                       "工作树版才有 namespace（未提交，git status ' M'）。今天 7 条信号不被打成 400 的真实理由是闸门生产调用点 = 0（§17.5）",
                "why": "未提交实现不能当已交付行为引用，否则接线时会把「本来就有列面」当既成事实",
            },
        ],
        "not_changed": [
            "8 只 formula_text / warmup_bars / dependencies / shift",
            "双 id 三列 canonical_id / aliases[] / superseded_by",
            "replaced_by 四条 / K1–K12 / signature 三元组（aefdf528…2d1a / 2 / 67）",
            "market_breadth 门票参数（§16.4）与「已派、未交付」状态写法",
            "§17.1–§17.3 的 G4 裁定文本",
            "backend/**：gate.py 的未提交改动不是我改的，我也没动它",
        ],
    }
    return doc


def edit_md(text, reg_size, reg_lines, reg_sha):
    text = sub_once(
        text,
        "**台账 v5.12（2026-11-08 01:10 修订；v5.11 于 00:56、",
        f"**台账 v5.13（2026-11-08 {HHMM} 修订；v5.12 于 01:10、v5.11 于 00:56、",
        "A1 status line version",
    )
    text = sub_once(
        text,
        OLD_REG_ROW,
        "| `docs/factors/evidence/f_class_registry.json` | %s B | %d | LF（CRLF 0） "
        "| 2026-11-08T%s | `%s` | `%s` |" % (format(reg_size, ","), reg_lines, HHMM, reg_sha, reg_sha),
        "A2 registry row",
    )
    text = sub_once(
        text,
        "（v5.8 补；v5.12 数值同步为 178,326 B / 3089 个换行符）",
        "（v5.8 补；v5.13 数值同步为 %s B / %d 个换行符）" % (format(reg_size, ","), reg_lines),
        "A3 line-count note",
    )
    text = sub_once(
        text,
        NL + "- **唯一例外**：第三方直写造成的字节修复。",
        NL + BANNER + NL + "- **唯一例外**：第三方直写造成的字节修复。",
        "A4 banner insert",
    )
    text = sub_once(
        text,
        "---" + NL + NL + "## 18. 8 只 `active` 的生效留痕（v5.12）",
        SEC176 + "## 18. 8 只 `active` 的生效留痕（v5.12）",
        "A5 insert 17.6",
    )
    if CRLF in text.encode("utf-8"):
        raise SystemExit("[FAIL] md contains CRLF")
    return text


def main():
    mm_md = MD.stat().st_mtime
    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in (MD, JS):
        dst = BACKUP / p.name
        if not dst.exists():
            shutil.copy2(p, dst)
    print("[ok] backup -> %s" % BACKUP)

    doc = edit_json(json.loads(JS.read_bytes().decode("utf-8")))
    JS.write_bytes(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"))
    reg_size, reg_lines, reg_sha = lf_sha(JS.read_bytes())
    print("[ok] json: %d B / %d LF / %s" % (reg_size, reg_lines, reg_sha))

    if MD
