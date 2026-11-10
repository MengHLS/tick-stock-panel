"""⑤-a 追加报数的自检：两法拆分是否闭合、缺口机制是否对上、run 目录是否被动过。

只读 five_a/ 与 ../results/a0_10bp/，不写任何 run 目录。
退出码 0 = 全部断言通过。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
TOL = 0.02

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    acc = json.loads((HERE / "dual_accounting.json").read_text(encoding="utf-8"))
    split = pd.DataFrame(acc["split"])
    flags = pd.DataFrame(acc["gap_structure"])
    at = {r["arm"]: r for r in json.loads((HERE / "arms_table.json").read_text(encoding="utf-8"))}
    man = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))

    arm_tags = list(acc["arms"].keys())

    check("split 行数 = 8 臂 × 2 记法", len(split) == 16, "实际 %d" % len(split))
    check("每臂两记法齐备",
          all((split["arm"] == t).sum() == 2 for t in arm_tags),
          str({t: int((split["arm"] == t).sum()) for t in arm_tags}))
    check("记法集合 = {A_pnl_amount, B_value_diff}",
          set(split["method"]) == {"A_pnl_amount", "B_value_diff"}, str(set(split["method"])))

    # 1) 恒等式：总差 = 同键 Δ + 仅本臂 Σ − 仅基线 Σ
    worst = float(split["identity_resid"].abs().max())
    check("恒等式残差全 ≤ 0.005", worst <= 0.005, "max=%.6f" % worst)

    # 2) 分块笔数自洽
    ok = bool(((split["n_same_key"] + split["n_only_arm"]) == split["n_arm"]).all())
    check("同键 + 仅本臂 = 本臂笔数", ok)

    # 3) 同键笔数在两种记法下相同（键与记法无关）
    ok = True
    for t in arm_tags:
        a = split[(split["arm"] == t) & (split["method"] == "A_pnl_amount")].iloc[0]
        b = split[(split["arm"] == t) & (split["method"] == "B_value_diff")].iloc[0]
        ok &= int(a["n_same_key"]) == int(b["n_same_key"]) and int(a["n_only_arm"]) == int(b["n_only_arm"])
    check("同键/仅本臂笔数两法一致", ok)

    # 4) 基线自比：两法各自 0 差
    base_rows = split[split["arm"] == "base_nodefaults_10bp"]
    check("基线自比两法均 0 差",
          bool((base_rows["total_gap"].abs() < 1e-9).all()),
          str(base_rows[["method", "total_gap"]].to_dict("records")))

    # 5) 缺口闭合：Σ差 = 期末未平仓缺口 + 已平仓缺口 + 取整净额
    check("各臂缺口闭合 recon_ok", bool(flags["recon_ok"].all()))
    resid = (flags["gap_open_at_end"] + flags["gap_flagged_closed"] + flags["sum_rounding"] - flags["sum_gap"]).abs()
    check("缺口闭合残差 ≤ 0.005", float(resid.max()) <= 0.005, "max=%.4f" % float(resid.max()))

    # 6) 已平仓不等笔必须能被除权闭式解释（残差 ≤ 0.05）
    bad = flags[flags["n_gap_flagged_closed"] > 0]
    check("已平仓不等笔的除权闭式残差 ≤ 0.05",
          bool((bad["pred_resid"].abs() <= 0.05).all()) if len(bad) else True,
          str(bad[["arm", "gap_flagged_closed", "pred_div_closed_form", "pred_resid"]].to_dict("records")))

    # 7) 只有 raw 基和 finalize 两臂出现 > 0.02 的缺口（其余臂只允许 ±0.01 取整）
    nz = flags[flags["n_gap_gt_flag_tol"] > 0]["arm"].tolist()
    check("出现非取整缺口的臂 = {entry_price_basis_raw, finalize_open_at_end}",
          set(nz) == {"only_entry_price_basis_raw", "only_finalize_open_at_end"}, str(nz))
    check("finalize 臂的不等笔全是期末未平仓",
          int(flags.loc[flags["arm"] == "only_finalize_open_at_end", "n_gap_open_at_end"].iloc[0])
          == int(flags.loc[flags["arm"] == "only_finalize_open_at_end", "n_gap_gt_flag_tol"].iloc[0]))

    # 8) 与 arms_table.json 的 pnl 法数字一致（同一批 run）
    ok = True
    detail = []
    for t in arm_tags:
        a = split[(split["arm"] == t) & (split["method"] == "A_pnl_amount")].iloc[0]
        r = at[t]
        same = abs(float(a["same_key_delta"]) - float(r["same_key_pnl_delta"])) < 0.02
        onlyn = int(a["n_only_arm"]) == int(r["only_this_arm_n"])
        onlyv = abs(float(a["only_arm_sum"]) - float(r["only_this_arm_pnl"])) < 0.02
        n = int(a["n_arm"]) == int(r["n_trades"])
        ok &= same and onlyn and onlyv and n
        if not (same and onlyn and onlyv and n):
            detail.append((t, r["same_key_pnl_delta"], a["same_key_delta"]))
    check("pnl 法与既有 arms_table.json 逐值一致", ok, str(detail))

    # 9) run 目录未被改动：manifest 里的三张 parquet sha256 复算一致
    bad_sha = []
    for tag, blk in man.get("arms", {}).items():
        for name, sha in blk.get("artifacts_sha256", {}).items():
            p = HERE / tag / name
            if not p.exists() or sha256_file(p) != sha:
                bad_sha.append((tag, name))
    check("manifest 四张 parquet 复算一致（run 目录未被动过）", not bad_sha, str(bad_sha))
    n_sha = sum(len(b.get("three_parquet_sha256", {})) for b in man.get("arms", {}).values())
    check("manifest 三张 parquet × 8 臂 = 24 条", n_sha == 24, "实际 %d" % n_sha)

    # 10) 199 附录：与派单已知量逐值对齐
    ap = acc["appendix_199_inject"]
    s199 = ap["split"]
    tgt = {
        "n_same_key": 111, "n_only_arm": 88, "n_only_base": 97,
    }
    for k, v in tgt.items():
        check("199 分块 %s = %d" % (k, v), int(s199[k]) == v, "实际 %s" % s199[k])
    A = s199["methods"]["A_pnl_amount"]
    B = s199["methods"]["B_value_diff"]
    for label, got, want in (
        ("A 同键 Δ", A["same_key_delta"], 102681.20),
        ("A 仅199", A["only_arm_sum"], 472120.73),
        ("A 仅208", A["only_base_sum"], 268485.06),
        ("A 总差", A["total_gap"], 843286.99),
        ("B 同键 Δ", B["same_key_delta"], 19128.46),
        ("B 仅199", B["only_arm_sum"], 444928.01),
        ("B 仅208", B["only_base_sum"], 268485.11),
        ("B 总差", B["total_gap"], 732541.58),
    ):
        check("199 %s = %.2f" % (label, want), abs(float(got) - want) <= 0.02, "实际 %.2f" % float(got))
    check("199 两法同键占比 12.18% / 2.61%",
          abs(A["same_key_share_pct"] - 12.18) < 0.01 and abs(B["same_key_share_pct"] - 2.61) < 0.01,
          "实际 %.2f / %.2f" % (A["same_key_share_pct"], B["same_key_share_pct"]))

    # 11) 199 的 29 笔分块
    check("199 不等笔 = 29", ap["n_gap_gt_flag_tol"] == 29, str(ap["n_gap_gt_flag_tol"]))
    check("期末未平仓 5 笔 +84,132.95",
          ap["n_open_at_end"] == 5 and abs(ap["gap_open_at_end"] - 84132.95) <= 0.02,
          "%d / %.2f" % (ap["n_open_at_end"], ap["gap_open_at_end"]))
    check("已平仓 24 笔 +26,612.60",
          ap["n_closed"] == 24 and abs(ap["gap_closed"] - 26612.60) <= 0.02,
          "%d / %.2f" % (ap["n_closed"], ap["gap_closed"]))
    check("24 笔除权闭式残差 ≤ 0.05", abs(ap["pred_resid"]) <= 0.05, "%.2f" % ap["pred_resid"])
    check("199 权益 = 1,242,725.28", abs(ap["final_equity"] - 1242725.28) <= 0.02, "%.2f" % ap["final_equity"])
    check("199 Σpnl − 5 笔浮亏 = 权益变化（残差 ≤ 0.05）",
          abs(ap["bridge_pnl_minus_open"]) <= 0.05, "%.2f" % ap["bridge_pnl_minus_open"])
    check("199 Σ价差 + 24 笔分红 = 权益变化（残差 ≤ 0.05）",
          abs(ap["bridge_vdiff_plus_div"]) <= 0.05, "%.2f" % ap["bridge_vdiff_plus_div"])

    # 12) 29 笔明细文件行数
    rows29 = pd.read_csv(HERE / "appendix_199_29rows.csv")
    check("appendix_199_29rows.csv 行数 = 29", len(rows29) == 29, str(len(rows29)))

    # 13) 每臂逐笔明细覆盖率
    pt = pd.read_csv(HERE / "dual_per_trade.csv")
    check("dual_per_trade.csv 行数 = Σ 各臂笔数",
          len(pt) == sum(a["n_trades"] for a in acc["arms"].values()),
          "%d vs %d" % (len(pt), sum(a["n_trades"] for a in acc["arms"].values())))
    check("每臂逐笔 pnl/价差/差 三列自洽",
          bool(((pt["pnl_amount"] - pt["value_diff"] - pt["gap_pnl_minus_vdiff"]).abs() <= 0.02).all()))

    # 14) 产物 sha256 与 dual_accounting.json 自载一致
    bad = []
    for n, sha in acc["artifacts_sha256"].items():
        if sha256_file(HERE / n) != sha:
            bad.append(n)
    check("dual 产物 sha256 复算一致", not bad, str(bad))

    # ---- 输出 ----
    n_fail = sum(1 for _, ok, _ in CHECKS if not ok)
    lines = []
    for name, ok, detail in CHECKS:
        lines.append("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -> " + detail) if detail and not ok else ""))
    lines.append("")
    lines.append("checks=%d  fails=%d  VERDICT=%s" % (len(CHECKS), n_fail, "ALL_PASS" if n_fail == 0 else "HAS_FAIL"))
    text = "\n".join(lines)
    (HERE / "verify_dual_result.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
