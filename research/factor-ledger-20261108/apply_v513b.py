# -*- coding: utf-8 -*-
"""v5.12 -> v5.13（§17.4 精度订正 + 未提交实现状态）。只改 docs/factors 两文件。"""
import hashlib, io, json, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

R = Path(__file__).resolve().parents[2]
MD = R / "docs/factors/F_CLASS_REGISTRATION_20261107.md"
JS = R / "docs/factors/evidence/f_class_registry.json"
P = R / "research/factor-ledger-20261108"
BACK = P / "backup_v512"
NL = chr(10)
CRLF = bytes([13, 10])
CN = timezone(timedelta(hours=8))
NOW = datetime.now(CN)
HHMM = NOW.strftime("%H:%M")
ISO = NOW.strftime("%Y-%m-%dT%H:%M+0800")

BANNER = (P / "v513_parts/banner.txt").read_text(encoding="utf-8").strip().replace("@HHMM@", HHMM)
SEC = (P / "v513_parts/sec176.md").read_text(encoding="utf-8").strip()
OLD_ROW = ("| `docs/factors/evidence/f_class_registry.json` | 178,326 B | 3089 | LF（CRLF 0） "
           "| 2026-11-08T01:10 | `010a08f40f8c3e4f4cf4c5a833761f782ef099fd2d548742ee8eae598657b55e` "
           "| `010a08f40f8c3e4f4cf4c5a833761f782ef099fd2d548742ee8eae598657b55e` |")


def sub(t, old, new, tag):
    n = t.count(old)
    if n != 1:
        raise SystemExit("[FAIL] %s: %d hits" % (tag, n))
    return t.replace(old, new)


def jdiff(doc):
    m = doc["meta"]
    m["version"] = "5.13" if isinstance(m["version"], str) else 5.13
    m["revised_at"] = ISO
    m["freeze_declaration"]["status"] = "FROZEN at v5.13"
    m["freeze_declaration"]["declared_at"] = ISO
    doc["self_check"]["generated_at"] = ISO
    doc["v5_13_changes"] = {
        "batch": "v5.13 精度订正（§17.4 归因细化），公式与数值一律不动",
        "date": "2026-11-08", "author": "因子工程师",
        "scope": "docs/factors 两文件（台账 md + evidence/f_class_registry.json）；未改 backend/**、未改盘上定义、未提交",
        "probe": {"script": "research/factor-ledger-20261108/probe_collision_faces.py",
                  "output": "research/factor-ledger-20261108/probe_collision_faces.json",
                  "output_size_bytes": 2663, "output_lf_sha16": "dfa42a020a0fc0f9"},
        "changes": [
            {"id": 1, "what": "§17.4 把 4 个名字在活信号里的写法写成一律 field: 前缀",
             "fix": "实测 7 条活信号 14 处引用：12 处 field: 前缀、2 处裸名（ma_golden_20_60 两条件 left='ma20'）；两者都属列引用，都不是因子引用",
             "why": "写法要能对着盘面读；结论（factor 面 FS01→400 / column 面 0 码）不变"},
            {"id": 2, "what": "「列面 0 码放行」写得仿佛已交付",
             "fix": "HEAD 的 assert_factors_usable 签名（HEAD :467-:477）无 namespace，HEAD 全文 grep namespace 仅 :592 一处注释；工作树版才有（未提交，git status ' M'）。今天 7 条信号不被打成 400 的真实理由是闸门生产调用点 = 0（§17.5）",
             "why": "未提交实现不能当已交付行为引用，否则接线时会把「本来就有列面」当既成事实"}],
        "not_changed": ["8 只 formula_text / warmup_bars / dependencies / shift",
                        "双 id 三列 canonical_id / aliases[] / superseded_by",
                        "replaced_by 四条 / K1–K12 / signature 三元组（aefdf528…2d1a / 2 / 67）",
                        "market_breadth 门票参数（§16.4）与「已派、未交付」状态写法",
                        "§17.1–§17.3 的 G4 裁定文本",
                        "backend/**：gate.py 的未提交改动不是我改的，我也没动它"],
    }
    return doc


def mdiff(t, size, lines, sha):
    t = sub(t, "**台账 v5.12（2026-11-08 01:10 修订；v5.11 于 00:56、",
            "**台账 v5.13（2026-11-08 %s 修订；v5.12 于 01:10、v5.11 于 00:56、" % HHMM, "A1")
    t = sub(t, OLD_ROW, "| `docs/factors/evidence/f_class_registry.json` | %s B | %d | LF（CRLF 0） | 2026-11-08T%s | `%s` | `%s` |"
            % (format(size, ","), lines, HHMM, sha, sha), "A2")
    t = sub(t, "（v5.8 补；v5.12 数值同步为 178,326 B / 3089 个换行符）",
            "（v5.8 补；v5.13 数值同步为 %s B / %d 个换行符）" % (format(size, ","), lines), "A3")
    t = sub(t, NL + "- **唯一例外**：第三方直写造成的字节修复。",
            NL + BANNER + NL + "- **唯一例外**：第三方直写造成的字节修复。", "A4")
    t = sub(t, "---" + NL + NL + "## 18. 8 只 `active` 的生效留痕（v5.12）",
            SEC + NL + NL + "## 18. 8 只 `active` 的生效留痕（v5.12）", "A5")
    return t


def main():
    mm = MD.stat().st_mtime
    BACK.mkdir(parents=True, exist_ok=True)
    for p in (MD, JS):
        if not (BACK / p.name).exists():
            shutil.copy2(p, BACK / p.name)
    doc = jdiff(json.loads(JS.read_bytes().decode("utf-8")))
    JS.write_bytes(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"))
    raw = JS.read_bytes()
    lf = raw.replace(CRLF, bytes([10]))
    size, lines, sha = len(raw), lf.count(bytes([10])), hashlib.sha256(lf).hexdigest()
    print("[ok] json %d B / %d LF / %s" % (size, lines, sha))
    if MD.stat().st_mtime != mm:
        raise SystemExit("[FAIL] md touched meanwhile — stopped before md write")
    t = io.open(MD, encoding="utf-8", newline="").read()
    n0 = len(t)
    t = mdiff(t, size, lines, sha)
    if not t.endswith(NL):
        t += NL
    if CRLF in t.encode("utf-8"):
        raise SystemExit("[FAIL] CRLF in md")
    io.open(MD, "w", encoding="utf-8", newline="").write(t)
    print("[ok] md %d -> %d chars" % (n0, len(t)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
