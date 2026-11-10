"""v0.16 独立校验：不复用构建脚本的任何自报值，全部重算。

A1 四元组 / A2 footer 自洽 / B1-B3 §7.1 块 / A4 正文反向还原
E1-E2 判据号与阈值 / A6 错误码集 / A7 组合行与唯一算法
A8 §10.3 banner / A9 numstat 净增 / A10 口径一致

用法：cd C:/work/sourcecode/tick-stock-panel
      PYTHONIOENCODING=utf-8 python research/arch-build-20261108/verify_v016.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md"
NEW = REPO / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md"

SEC71_LF = (2514, "6d3db013")
SEC71_CRLF = (2541, "a8e88134")
CRLF_B = bytes([13, 10])
CRLF = "\r\n"

results: list[dict] = []


def check(cid: str, ok: bool, detail: str) -> None:
    results.append({"id": cid, "ok": bool(ok), "detail": detail})


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sec71(text: str) -> dict:
    lines = text.split(CRLF)
    start = [i for i, ln in enumerate(lines) if ln.startswith("### 7.1 ")][0]
    stop = [i for i, ln in enumerate(lines) if ln.startswith("### 7.2 ")][0]
    lf_block = "\n".join(lines[start:stop]) + "\n"
    crlf_block = CRLF.join(lines[start:stop]) + CRLF
    return {
        "lf": (len(lf_block), sha(lf_block.encode())[:8]),
        "crlf": (len(crlf_block), sha(crlf_block.encode())[:8]),
        "crlf_bytes": crlf_block,
    }


def clean_lines(text: str) -> list[str]:
    out = text.split(CRLF)
    if out and out[-1] == "":
        out.pop()
    return out


def numstat(old: str, new: str) -> dict:
    a, b = clean_lines(old), clean_lines(new)
    added = deleted = 0
    hunks = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        hunks += 1
        deleted += i2 - i1
        added += j2 - j1
    return {"hunks": hunks, "added": added, "deleted": deleted, "net": added - deleted}


# 判据行：表行首列恰为反引号包住的单个判据号（不含区间 `F-A1`–`F-A47`）
FA_ROW = re.compile(r"^\|\s*`(F-A\d+(?:-[0-9]+[a-z]?)?)`\s*\|")


def fa_rows(text: str) -> dict[str, str]:
    out = {}
    for ln in text.split(CRLF):
        m = FA_ROW.match(ln)
        if m:
            out[m.group(1)] = ln
    return out


def old_num(k: str):
    m = re.match(r"^F-A(\d+)", k)
    return int(m.group(1)) if m else None


def section_slice(text: str, start_pat: str, stop_pat: str) -> str:
    lines = text.split(CRLF)
    s = [i for i, ln in enumerate(lines) if re.search(start_pat, ln)]
    e = [i for i, ln in enumerate(lines) if re.search(stop_pat, ln)]
    if not s or not e:
        return ""
    return CRLF.join(lines[s[0]:e[0]])


def main() -> int:
    base_b = BASE.read_bytes()
    new_b = NEW.read_bytes()
    base_t = base_b.decode("utf-8")
    new_t = new_b.decode("utf-8")

    fmark = "本文件正文 sha256".encode("utf-8")
    f_off = new_b.rfind(fmark)
    body_len = new_b.rfind(CRLF_B, 0, f_off) + 2
    footer_line = new_b[body_len:].decode("utf-8").rstrip("\r\n")
    body_sha = sha(new_b[:body_len])
    body_lines = new_b[:body_len].count(CRLF_B)
    total_lines = new_b.count(CRLF_B)

    # ---- A1 四元组 ----
    check("A1", True,
          f"size={len(new_b)} lines={total_lines} sha={sha(new_b)} "
          f"body_len={body_len} body_lines={body_lines} body_sha={body_sha}")

    # ---- A2 footer 自洽 ----
    def g(pat):
        m = re.search(pat, footer_line)
        return m.group(1) if m else None

    d_len = int(g(r"正文 `(\d+) B`") or -1)
    d_sha = g(r"sha256：`([0-9a-f]{64})`") or ""
    d_headc = int(g(r"head -c (\d+)") or -1)
    d_total = int(g(r"全文 `(\d+)` 行") or -1)
    d_body = int(g(r"正文 `(\d+)` \+ footer 1") or -1)
    ok2 = (d_len == body_len and d_sha == body_sha and d_headc == body_len
           and d_total == total_lines and d_body == body_lines)
    check("A2", ok2,
          f"len {d_len}=={body_len} | sha_match={d_sha == body_sha} | "
          f"head-c {d_headc}=={body_len} | total {d_total}=={total_lines} | "
          f"body {d_body}=={body_lines}")

    # ---- B1/B2/B3 §7.1 块 ----
    s_new = sec71(new_t)
    s_base = sec71(base_t)
    check("B1", s_new["lf"] == SEC71_LF, f"LF={s_new['lf']} expect={SEC71_LF}")
    check("B2", s_new["crlf"] == SEC71_CRLF, f"CRLF={s_new['crlf']} expect={SEC71_CRLF}")
    check("B3", s_new["crlf_bytes"] == s_base["crlf_bytes"],
          f"byte_equal_to_v015={s_new['crlf_bytes'] == s_base['crlf_bytes']} "
          f"len={len(s_new['crlf_bytes'])}")

    # ---- A4 正文反向还原 ----
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "b16", REPO / "research/arch-build-20261108/build_contract_v016.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    def crlf(s: str) -> str:
        return s.replace(CRLF, "\n").replace("\n", CRLF)

    reverted = new_t
    pairs = [
        (mod.NEW_H1, mod.OLD_H1),
        (mod.NEW_TABLE_INTRO, mod.OLD_TABLE_INTRO),
        (mod.NEW_TABLE, mod.OLD_TABLE),
        (mod.COMBO_EVIDENCE, ""),
        (mod.NEW_SIG_LINE_TAIL, mod.OLD_SIG_LINE_TAIL),
        (mod.FA48_BLOCK, ""),
        (crlf(mod.V016_ROW) + CRLF, ""),
        (crlf(mod.SECTION15).rstrip(CRLF) + CRLF, ""),
    ]
    counts = []
    for new_s, old_s in pairs:
        nc, oc = crlf(new_s), crlf(old_s)
        counts.append(reverted.count(nc))
        reverted = reverted.replace(nc, oc, 1)
    rev_lines = reverted.split(CRLF)
    idx_f = [i for i, ln in enumerate(rev_lines) if ln.startswith("本文件正文 sha256")][0]
    rev_body = CRLF.join(rev_lines[:idx_f]) + CRLF
    b_lines = base_t.split(CRLF)
    idx_bf = [i for i, ln in enumerate(b_lines) if ln.startswith("本文件正文 sha256")][0]
    base_body = CRLF.join(b_lines[:idx_bf]) + CRLF
    ok4 = rev_body == base_body
    check("A4", ok4,
          f"revert_hit_counts={counts}; bodies_equal={ok4}; "
          f"rev={len(rev_body.encode())}B base={len(base_body.encode())}B")

    # ---- E1/E2 判据号 ----
    b_rows, n_rows = fa_rows(base_t), fa_rows(new_t)
    b_old = {k: v for k, v in b_rows.items() if (old_num(k) or 999) <= 47}
    n_old = {k: v for k, v in n_rows.items() if (old_num(k) or 999) <= 47}
    n_new = {k: v for k, v in n_rows.items() if (old_num(k) or 0) > 47}
    missing = sorted(set(b_old) - set(n_old))
    changed = sorted(k for k in b_old if k in n_old and b_old[k] != n_old[k])
    added = sorted(set(n_new) - set(b_rows))
    check("E1", not missing and not changed,
          f"base_old={len(b_old)} new_old={len(n_old)} missing={missing} changed={changed}")
    allow = {"F-A48", "F-A48-1", "F-A48-2", "F-A48-3", "F-A48-4",
             "F-A49", "F-A49-1", "F-A49-2"}
    check("E2", set(added) <= allow and not (set(b_rows) & set(added)),
          f"added={added} allowed={sorted(allow)} "
          f"new_old_ids_reused={sorted(set(b_rows) & set(added))}")

    # ---- A6 错误码集 ----
    cb = set(re.findall(r"FS\d\d", base_t))
    cn = set(re.findall(r"FS\d\d", new_t))
    beyond = sorted(cn - cb)
    fs11_bad = []
    for m in re.finditer(r"FS11", new_t):
        w = new_t[max(0, m.start() - 40):m.start() + 60]
        if not re.search(r"(新开\s*`?FS11|无\s*`?FS11|不复用\s*`?FS11)", w):
            fs11_bad.append(w.replace(CRLF, " "))
    ok6 = set(beyond) <= {"FS11"} and not fs11_bad
    check("A6", ok6, f"base={sorted(cb)} beyond={beyond} fs11_bad={fs11_bad}")

    # ---- A7 §7.16.4：组合行 + 唯一算法 ----
    s7164 = section_slice(new_t, r"^\*\*7\.16\.4 ", r"^\*\*7\.16\.5 ")
    has_algo = "键数 |detail| = 7 + |{ k 的成立条件为真 }|" in s7164
    combos = sorted(set(re.findall(r"\*\*组合行([①②③④])\*\*", s7164)))
    has_fs04 = ("`FS04` 恒优先" in s7164) and ("绝不追加 `violations`" in s7164)
    nine = re.search(r"组合行②[^\r\n]*\*\*9\*\*", s7164) is not None
    keydom = "{7, 8, 9}" in s7164
    fs09_reg = "逐键等于 7 键" in s7164
    ok7 = has_algo and combos == ["①", "②", "③", "④"] and has_fs04 and nine and keydom
    check("A7", ok7,
          f"algo={has_algo} combos={combos} fs04_priority={has_fs04} "
          f"nine_row={nine} keydomain_789={keydom} fs09_7keys={fs09_reg}")

    # ---- A8 §10.3 banner ----
    ok8 = bool(re.search(r"^### 10\.3.*（已停用，R10）", new_t, re.M))
    check("A8", ok8, f"sec_10_3_banner={ok8}")

    # ---- A9 numstat 净增一致 ----
    d = numstat(base_t, new_t)
    git_added = git_deleted = None
    try:
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--numstat", "--", str(BASE), str(NEW)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        parts = proc.stdout.strip().split("\t")
        if len(parts) >= 2 and parts[0].isdigit():
            git_added, git_deleted = int(parts[0]), int(parts[1])
    except Exception as e:  # noqa: BLE001
        check("A9", False, f"git failed: {e}")
    else:
        net_d = d["added"] - d["deleted"]
        net_g = (git_added - git_deleted) if git_added is not None else None
        ok9 = net_g is not None and net_d == net_g
        check("A9", ok9,
              f"difflib +{d['added']}/-{d['deleted']} net={net_d} | "
              f"git +{git_added}/-{git_deleted} net={net_g} | "
              f"hunks={d['hunks']} net_match={net_d == net_g}")

    # ---- A10 口径一致（42 次调用 / 31 带 detail / 无 32 组残留）----
    n42 = len(re.findall(r"42 次调用", new_t))
    n32 = len(re.findall(r"32 组", new_t))
    n31 = len(re.findall(r"31 次抛错带 `detail`", new_t))
    n3131 = len(re.findall(r"31/31", new_t))
    stale4242 = len(re.findall(r"42/42", new_t))
    ok10 = n42 >= 1 and n32 == 0 and n31 >= 1 and n3131 >= 1 and stale4242 == 0
    check("A10", ok10,
          f"42次调用={n42} 32组残留={n32} 31次带detail={n31} 31/31={n3131} 旧42/42残留={stale4242}")

    # ---- A11 组合实测表逐格对证据（文档 vs EVIDENCE_v016.json）----
    ev_path = REPO / "research/arch-build-20261108/EVIDENCE_v016.json"
    bad11: list = []
    if ev_path.exists():
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        matrix = ev["gap1_matrix"]
        start11 = next((i for i, ln in enumerate(clean_lines(new_t))
                        if ln.startswith("| 输入（`registry = D:/TSP/data`）")), None)
        rows11: list = []
        if start11 is not None:
            i = start11 + 2
            cl = clean_lines(new_t)
            while i < len(cl) and cl[i].startswith("|"):
                rows11.append([c.strip() for c in cl[i].strip().strip("|").split("|")])
                i += 1

        def parse11(cell: str):
            mm = re.search(r"`(FS\d\d)`\s*→\s*\*\*(\d)\*\*", cell)
            if mm:
                return (mm.group(1), int(mm.group(2)))
            return ("PASS", None)

        # 证据：每 3 条一组（production / research / diagnostic）
        trips = [matrix[k:k + 3] for k in range(0, len(matrix), 3)]
        if len(trips) == 14 and len(rows11) == 13:
            # 文档第 2 行合并了 single-alias-alias2 / alias3 两组（同一组输入的不同 alias）
            for idx, row in enumerate(rows11):
                base_idx = idx if idx <= 1 else idx + 1
                if base_idx >= len(trips):
                    break
                t = trips[base_idx]
                for j in range(3):
                    if j + 1 >= len(row):
                        bad11.append((idx + 1, "SHORT"))
                        break
                    got = parse11(row[j + 1])
                    exp_code = t[j].get("code", "PASS")
                    exp_n = t[j].get("n_keys")
                    if got[0] != exp_code:
                        bad11.append((idx + 1, j, got[0], exp_code))
                    if exp_number_ok := (exp_n is None or got[1] == exp_n):
                        pass
                    else:
                        bad11.append((idx + 1, j, got[1], exp_n))
        else:
            bad11.append(("shape", len(trips), len(rows11)))
    else:
        bad11.append(("evidence_missing",))
    check("A11", not bad11,
          "table_cells_vs_evidence=" + ("ALL MATCH" if not bad11 else str(bad11[:6])))

    # ---- 汇总 ----
    print("=" * 78)
    print("v0.16 独立校验")
    print("=" * 78)
    allok = True
    for r in results:
        flag = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            allok = False
        print(f"[{flag}] {r['id']:>4}  {r['detail']}")
    print("-" * 78)
    print("SUMMARY", "ALL PASS" if allok else "HAS FAIL")
    print()

    out = REPO / "research/arch-build-20261108/_v16_verify.json"
    out.write_text(json.dumps({"results": results, "all_pass": allok},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
