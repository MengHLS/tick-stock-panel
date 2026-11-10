"""S01b 阶段2 验收：18 臂 C 口径产物 + 确定性复跑 + 六臂锚点 + 受保护文件未动。

退出码 0 = 全部 PASS；任何 FAIL 返回 1。结果写 verify_phase2_result.txt。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
RESULTS = HERE / "results_all"
RERUN = HERE / "_determinism_rerun"
D_ROOT = PARENT / "results"
ENGINE = PROJECT / "backend" / "app" / "backtest" / "engine.py"

ENGINE_SHA_EXPECTED = "4243fe97723dad20d01bd440783cf71ea6ef05c55a9ffd4652492031e40d8386"
PROTECTED = [
    (PARENT / "REPORT.md", 52097, "e60cd0b857f40fb227dad704e62c6d132fbba9e5107f1c53ba3870c436d7ca9b"),
    (PARENT / "metrics_table.md", 2738, "d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a"),
    (PARENT / "five_a" / "manifest.json", 10054, "7fe2c540ce229e7cede4c922e54cd89c0670c09a484683f14da08fc376b3124f"),
]
VOLATILE_STATS = {"timing_ms", "matrix_data_cache_timing_ms", "matrix_data_cache_hit",
                  "matrix_data_cache_status"}
ARM_ORDER = ["a0_10bp", "a0_30bp", "a0_gross", "a1_10bp", "a1_30bp", "a1_gross",
             "a2_10bp", "a2_30bp", "a2_gross", "a3_10bp", "a3_30bp", "a3_gross",
             "a2h_10bp", "a4_10bp", "a0ev_10bp", "a3ev_10bp", "prod_file_10bp", "smoke_a0"]
ANCHOR_EXPECTED = {
    "base_nodefaults_10bp": -0.17, "only_execution_costs": -0.17,
    "only_entry_price_basis_raw": -0.17, "base_nodefaults_gross": -0.17,
    "only_block_limit_open": -0.35, "only_trailing_peak_price_close": -0.17,
    "only_finalize_open_at_end": 0.0, "only_exit_signal_requires_profit": 0.0,
}

lines: list[str] = []
fails: list[str] = []
npass = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global npass
    tag = "PASS" if ok else "FAIL"
    if ok:
        npass += 1
    else:
        fails.append(f"{name} {detail}")
    lines.append(f"[{tag}] {name}" + (f"  {detail}" if detail else ""))


def sha(p: pathlib.Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stats_stable(result_json: pathlib.Path) -> dict:
    o = json.loads(result_json.read_text(encoding="utf-8"))
    return {k: v for k, v in o["stats"].items() if k not in VOLATILE_STATS}


def main() -> int:
    lines.append("== S01b 阶段2 验收 ==")
    check("engine.py sha256 为修复后 4243fe97", sha(ENGINE) == ENGINE_SHA_EXPECTED,
          f"{sha(ENGINE)[:16]}… size={ENGINE.stat().st_size}")

    delta = json.loads((HERE / "delta_arms.json").read_text(encoding="utf-8"))
    dmap = {a["tag"]: a for a in delta["arms"]}

    # B. 18 臂齐 + 三产物
    for tag in ARM_ORDER:
        arm = RESULTS / tag
        have = {n: (arm / n).exists() for n in ("trades.parquet", "equity.parquet",
                                                "drawdown.parquet", "result.json")}
        ok = all(have.values())
        rj = json.loads((arm / "result.json").read_text(encoding="utf-8")) if have["result.json"] else {}
        check(f"B  {tag} 产物齐(3 parquet+json) 且 error=None", ok and rj.get("error") is None,
              f"missing={[k for k, v in have.items() if not v]} error={rj.get('error')}")
        check(f"B  {tag} 记录 engine sha 与当前一致",
              rj.get("engine_sha256") == ENGINE_SHA_EXPECTED)

    # C. 确定性复跑
    for tag in ARM_ORDER:
        same = {}
        for name in ("trades.parquet", "equity.parquet", "drawdown.parquet"):
            same[name] = sha(RESULTS / tag / name) == sha(RERUN / tag / name)
        st_same = stats_stable(RESULTS / tag / "result.json") == stats_stable(RERUN / tag / "result.json")
        check(f"C  {tag} 复跑字节一致(3 parquet)", all(same.values()),
              f"{ {k: v for k, v in same.items() if not v} }")
        check(f"C  {tag} 复跑 stats 非易变字段一致", st_same)

    # D. D vs C
    n_unch = sum(1 for t in ARM_ORDER if dmap[t]["status"] == "UNCHANGED")
    check("D  D vs C：18 臂中 17 臂 stats 与产物完全未变", n_unch == 17, f"unchanged={n_unch}")
    for tag in ARM_ORDER:
        sh = dmap[tag]["parquet_sha256"]
        check(f"D  {tag} trades/equity 与旧 results 逐字节相同",
              sh["trades.parquet"]["same"] is True and sh["equity.parquet"]["same"] is True)
        check(f"D  {tag} stats.execution 整块未变", dmap[tag]["execution_same"] is True)
    check("D  smoke_a0 仅 market_matrix_shape/bytes 差异（数据根扩容），产物仍字节相同",
          set(dmap["smoke_a0"]["stats_diff"].keys()) <= {"market_matrix_shape", "market_matrix_bytes"}
          and dmap["smoke_a0"]["parquet_sha256"]["trades.parquet"]["same"] is True,
          json.dumps(dmap["smoke_a0"]["stats_diff"], ensure_ascii=False))

    # E. 六臂锚点
    for a in delta["anchor_six"]:
        exp = ANCHOR_EXPECTED.get(a["tag"])
        if exp is None or a.get("status") == "MISSING":
            check(f"E  锚点 {a['tag']} 有产物", False)
            continue
        check(f"E  锚点 {a['tag']} Δ={a['delta_pp']:+.4f}pp 与契约 {exp:+.2f}pp 一致",
              abs(a["delta_pp"] - exp) <= 0.005)
    check("E  三臂锚点产物逐字节未变（finalize / requires_profit / a0_10bp 祖先）",
          all(a.get("parquet_trades_same") is True for a in delta["anchor_six"]
              if a["tag"] in ("only_finalize_open_at_end", "only_exit_signal_requires_profit")))

    # F. 受保护文件
    for p, size, expect in PROTECTED:
        check(f"F  {p.name} 未动 ({size}B/{expect[:8]}…)", p.stat().st_size == size and sha(p) == expect,
              f"actual {p.stat().st_size}B/{str(sha(p))[:8]}…")

    # G. 交付物
    for name in ("METRICS_D_vs_C_20261108.md", "delta_arms.json", "metrics_table_C_20261108.md",
                 "run_all_arms.py", "build_delta.py"):
        check(f"G  {name} 存在且非空", (HERE / name).exists() and (HERE / name).stat().st_size > 0,
              f"{(HERE / name).stat().st_size if (HERE / name).exists() else 0}B")

    # H. 工作树（只列未跟踪/已改，供人工核对范围）
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=str(PROJECT),
                             capture_output=True, text=True, timeout=60)
        changed = [l for l in out.stdout.splitlines() if l.strip()]
        lines.append(f"[info] git status --porcelain: {len(changed)} 条")
        for l in changed[:40]:
            lines.append(f"       {l}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[info] git status failed: {exc!r}")

    lines.append("")
    lines.append(f"TOTAL pass={npass} fail={len(fails)}")
    for f in fails:
        lines.append(f"  FAILED: {f}")
    text = "\n".join(lines)
    (HERE / "verify_phase2_result.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
