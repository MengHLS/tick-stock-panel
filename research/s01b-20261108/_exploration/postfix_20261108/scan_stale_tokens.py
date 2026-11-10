"""扫出「D 口径旧数字」在 research/s01b-20261108 下每份文档里的落点。

用途：给出「本批之后不可再引用的旧数字」的机器证据——哪些文档里写着 D 值，
以及这些文档是否同时写了 C 值（写了 = 对照记录，不算作废；只写 D = 作废）。

输出 stale_tokens_scan.json。
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PARENT = HERE.parent

# D 口径专有（修复后不再成立）
D_ONLY = {
    "485,293.78": "base_nodefaults_10bp / only_trailing_peak_price_close 末值（D）",
    "485,420.69": "only_execution_costs 末值（D）",
    "434,710.53": "only_entry_price_basis_raw 末值（D）",
    "527,074.75": "base_nodefaults_gross 末值（D）",
    "1,121,259.36": "only_block_limit_open 末值（D）",
    "-51.47": "基线总收益 −51.47%（D）",
    "−51.47": "基线总收益 −51.47%（D）",
    "-51.46": "only_execution_costs 总收益 −51.46%（D）",
    "−51.46": "only_execution_costs 总收益 −51.46%（D）",
    "-56.53": "only_entry_price_basis_raw 总收益 −56.53%（D）",
    "−56.53": "only_entry_price_basis_raw 总收益 −56.53%（D）",
    "+12.13": "only_block_limit_open 总收益 +12.13%（D）",
    "12.13%": "only_block_limit_open 总收益 +12.13%（D）",
    "-9.73": "基线年化 −9.73%（D）",
    "−9.73": "基线年化 −9.73%（D）",
    "-71.95": "基线 MDD −71.95%（D）",
    "−71.95": "基线 MDD −71.95%（D）",
    "1,722.56": "Σpnl 与权益变动缺口（该缺口已由修复消除）",
}
# C 口径标记（同一文档里出现这些 ⇒ 该文档是 D/C 对照记录）
C_MARK = ["483,571", "−51.64", "-51.64", "−56.70", "-56.70", "+11.78", "11.78%"]


def main() -> int:
    hits = {}
    for p in sorted(PARENT.rglob("*.md")):
        if HERE in p.parents and p.name.startswith(("METRICS_D_vs_C", "metrics_table_C")):
            rel = str(p.relative_to(PARENT))
            continue  # 本目录新产物由 report 单独说明
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            t = p.read_text(encoding="utf-8", errors="replace")
        d = {k: t.count(k) for k in D_ONLY if k in t}
        c = {k: t.count(k) for k in C_MARK if k in t}
        if d:
            rel = str(p.relative_to(PARENT))
            hits[rel] = {
                "bytes": p.stat().st_size,
                "d_only_tokens": d,
                "c_tokens": c,
                "classification": "D_C_COMPARE（同时有 C 值，属对照记录）" if c else "D_ONLY_STALE（只写 D 值 ⇒ 作废）",
            }
    out = {"root": str(PARENT), "d_only_token_glossary": D_ONLY,
           "c_markers": C_MARK, "files": hits}
    (HERE / "stale_tokens_scan.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for rel, v in hits.items():
        print(f"{v['classification']:<42} {rel}  ({v['bytes']}B, {len(v['d_only_tokens'])} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
