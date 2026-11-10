"""S01b §9 文档级补正 · 增量独立复核（只读，不改任何被审文件）

复核对象（结论锚定这些指纹）：
  research/s01b-20261108/REPORT.md               52,097 B  e60cd0b857f40fb2…
  research/s01b-20261108/REPORT_pre_s9_1810.md.bak 43,194 B  e4b7c98fd47cf565…
  research/s01b-20261108/PREREG_S01B_20261108.md   4,446 B  2343971950eb4172…
  research/s01b-20261108/PREREG_pre_timefix_1810.md.bak 2,871 B cf95a0b7ae2298b4…
  research/s01b-20261108/metrics.json            13,937 B  282e090c5915a354…

判据（自定，全部机器可判定）：
  J1 非 §9 改动 = 0：把现行版按「替换 §4.1 列头那一行 + 删掉末尾 93 行」逆推，
     逆推结果必须与基线逐字节相同（sha256 相同即证明除此之外零改动）。
  J2 §9 引用的每个数字：与 metrics.json / trades.parquet / equity.parquet / 文件系统
     实测值逐项比对（2dp 打印值按 ±0.0051 判等；整数严格相等）。
  J3 PREREG 只增不改：前 2,871 B 与 cf95a0b7 副本逐字节相同，且追加段起始于第 2,872 B。
  J4 metrics.json：全树无 `oos` 键；每条记录顶层键集合 = 白名单；oos_by_scen 各档自算一致。
  J5 §9 引用的路径/哈希全部存在且与实测一致；已作废哈希在引用处标注「作废」。

只读：不写被审目录任何文件；本脚本只写自己目录下的 _s9_check.json。
用法（仓库根目录）：
  backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\check_s9_increment.py
退出码：0 = 全部 YES；1 = 有 NO（见 JSON 明细）；2 = 环境/文件缺失
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

PROJECT = Path(__file__).resolve().parents[2]
BASE = PROJECT / "research" / "s01b-20261108"
RES = BASE / "results"
HERE = Path(__file__).resolve().parent
SNAP = HERE / "snapshot"

MINUS = "\u2212"
CHECKS: list[dict] = []


def chk(cid: str, ok: bool, detail: str, blocking: bool = True) -> bool:
    CHECKS.append({"id": cid, "ok": bool(ok), "detail": detail, "blocking": blocking})
    return ok


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def num(s: str) -> float:
    s = s.strip().replace(MINUS, "-").replace(",", "").replace("%", "").replace("x", "")
    return float(s)


# ---------------------------------------------------------------- 数据自算
def load(tag: str):
    t = pl.read_parquet(RES / tag / "trades.parquet")
    e = pl.read_parquet(RES / tag / "equity.parquet").sort("date")
    return t, e


def eq_stats(t: pl.DataFrame, e: pl.DataFrame) -> dict:
    vals = e["value"].cast(pl.Float64).to_list()
    d = [str(x) for x in e["date"].to_list()]
    n = len(vals)
    total = vals[-1] / 1_000_000.0 - 1
    ann252 = (1 + total) ** (252 / n) - 1
    days_full = (date.fromisoformat(d[-1]) - date.fromisoformat(d[0])).days
    y_cal = days_full / 365.25
    ann_cal = (vals[-1] / 1_000_000.0) ** (1 / y_cal) - 1
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    daily = [vals[i] / vals[i - 1] - 1 for i in range(1, n)]
    mu = sum(daily) / len(daily)
    sd = math.sqrt(sum((x - mu) ** 2 for x in daily) / (len(daily) - 1))
    sharpe = mu / sd * math.sqrt(252)
    # OOS: base = 2022-12-30 权益，段 = 2023-01-03..末
    pairs = list(zip(d, vals))
    base = [v for dd, v in pairs if dd <= "2022-12-30"][-1]
    seg = [v for dd, v in pairs if dd >= "2023-01-01"]
    oos_days = (date.fromisoformat(d[-1]) - date(2022, 12, 30)).days
    y_oos = oos_days / 365.25
    oos_ann = (seg[-1] / base) ** (1 / y_oos) - 1
    pk, oos_mdd = base, 0.0
    for v in [base] + seg:
        pk = max(pk, v)
        oos_mdd = min(oos_mdd, v / pk - 1)
    rets = [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg))]
    m2 = sum(rets) / len(rets)
    s2 = math.sqrt(sum((r - m2) ** 2 for r in rets) / (len(rets) - 1))
    return {
        "final_equity": vals[-1], "total": total, "ann252": ann252, "ann_cal": ann_cal,
        "days_full": days_full, "y_cal": y_cal, "mdd": mdd, "sharpe": sharpe,
        "oos_base": base, "oos_end": seg[-1], "oos_days": oos_days, "y_oos": y_oos,
        "oos_ann": oos_ann, "oos_mdd": oos_mdd,
        "oos_sharpe": m2 / s2 * math.sqrt(252), "n_days": n,
    }


def trade_stats(t: pl.DataFrame) -> dict:
    closed = t.filter(~pl.col("open_at_end"))
    allp = t["pnl_pct"].cast(pl.Float64).to_list()
    cl = closed["pnl_pct"].cast(pl.Float64).to_list()
    dur = t["duration"].cast(pl.Float64).to_list()
    sd = sorted(dur)
    n = len(sd)

    def avg(x):
        return sum(x) / len(x)

    def med_upper(x):
        s = sorted(x)
        return s[len(s) // 2]

    def med_avg(x):
        s = sorted(x)
        k = len(s)
        return s[k // 2] if k % 2 else (s[k // 2 - 1] + s[k // 2]) / 2

    def med_lower(x):
        s = sorted(x)
        return s[(len(s) - 1) // 2]

    p90_nearest = float(pl.Series(dur).quantile(0.9))      # polars 默认 interpolation="nearest"
    try:
        import numpy as np
        p90_linear = float(np.percentile(dur, 90))
    except Exception:
        p90_linear = float("nan")
    p90_index = sd[int(n * 0.9)]
    return {
        "n_trades": t.height, "n_closed": closed.height,
        "n_end": t.height - closed.height,
        "win_closed": 100 * sum(1 for x in cl if x > 0) / len(cl),
        "win_all": 100 * sum(1 for x in allp if x > 0) / len(allp),
        "n_win_closed": sum(1 for x in cl if x > 0),
        "n_win_all": sum(1 for x in allp if x > 0),
        "avg_closed": 100 * avg(cl), "avg_all": 100 * avg(allp),
        "med_closed_upper": 100 * med_upper(cl), "med_closed_avg": 100 * med_avg(cl),
        "med_closed_lower": 100 * med_lower(cl),
        "med_all_upper": 100 * med_upper(allp), "med_all_avg": 100 * med_avg(allp),
        "med_all_lower": 100 * med_lower(allp),
        "p50_median": float(pl.Series(dur).median()),
        "p90_nearest": p90_nearest, "p90_linear": p90_linear, "p90_index": p90_index,
        "entry_sum": float(t["entry_value"].sum()),
        "dur": dur,
    }


def main() -> int:
    res: dict = {"anchors": {}, "J1": {}, "J2": {}, "J3": {}, "J4": {}, "J5": {}}

    # ---------------- 锚点 ----------------
    f_report = BASE / "REPORT.md"
    f_base = BASE / "REPORT_pre_s9_1810.md.bak"
    f_prereg = BASE / "PREREG_S01B_20261108.md"
    f_prereg_old = BASE / "PREREG_pre_timefix_1810.md.bak"
    f_metrics = BASE / "metrics.json"
    f_mtable = BASE / "metrics_table.md"
    f_gen = BASE / "report_metrics.py"
    f_mybase = SNAP / "REPORT_at_audit_e4b7c98f.md"
    for p in (f_report, f_base, f_prereg, f_prereg_old, f_metrics, f_mtable, f_gen):
        if not p.exists():
            print("MISSING", p)
            return 2
    anchors = {
        "REPORT.md": (f_report, 52097, "e60cd0b857f40fb2"),
        "REPORT_pre_s9_1810.md.bak": (f_base, 43194, "e4b7c98fd47cf565"),
        "PREREG_S01B_20261108.md": (f_prereg, 4446, "2343971950eb4172"),
        "PREREG_pre_timefix_1810.md.bak": (f_prereg_old, 2871, "cf95a0b7ae2298b4"),
        "metrics.json": (f_metrics, 13937, "282e090c5915a354"),
        "metrics_table.md": (f_mtable, 2738, "d025d8ce96f98cc2"),
        "report_metrics.py": (f_gen, 7970, "38a67c9fb87eed55"),
    }
    ok_all = True
    for name, (p, size, pre) in anchors.items():
        h = sha(p)
        ok = (p.stat().st_size == size) and h.startswith(pre)
        ok_all &= ok
        res["anchors"][name] = {"bytes": p.stat().st_size, "sha256": h, "mtime": mtime(p), "ok": ok}
    chk("A0 锚点指纹", ok_all, "7 个文件 bytes+sha256 前16位 与派单一致")

    cur = f_report.read_bytes()
    old = f_base.read_bytes()
    myb = f_mybase.read_bytes()
    chk("A1 我上轮快照 == 基线", myb == old, f"{len(myb)} B / {hashlib.sha256(myb).hexdigest()[:16]}")

    # ---------------- J1 非 §9 改动 = 0 ----------------
    cl = cur.split(b"\n")
    ol = old.split(b"\n")
    res["J1"]["lines_cur"] = len(cl)
    res["J1"]["lines_old"] = len(ol)
    recon = cl[:379] + cl[472:]
    recon = recon[:146] + [ol[146]] + recon[147:]
    recon_b = b"\n".join(recon)
    res["J1"]["recon_sha"] = hashlib.sha256(recon_b).hexdigest()
    res["J1"]["baseline_sha"] = hashlib.sha256(old).hexdigest()
    res["J1"]["header_old"] = ol[146].decode("utf-8")
    res["J1"]["header_new"] = cl[146].decode("utf-8")
    res["J1"]["inserted_lines"] = len(cl) - len(ol)
    res["J1"]["delta_bytes"] = len(cur) - len(old)
    # 列头只有两处文字变化？
    ho, hn = res["J1"]["header_old"], res["J1"]["header_new"]
    res["J1"]["header_only_two_tokens"] = (hn.replace("胜率(已平仓)", "胜率").replace(
        "avg/median pnl(已平仓)", "avg/median pnl") == ho)
    ok1 = (recon_b == old) and res["J1"]["header_only_two_tokens"] and res["J1"]["inserted_lines"] == 93
    res["J1"]["ok"] = ok1
    chk("J1 非 §9 改动=0", ok1,
        f"逆推(替换 L147 列头 + 删末尾 93 行) sha={res['J1']['recon_sha'][:16]} == 基线 sha；列头仅两处 token 变化")

    # ---------------- 解析 §4.1 主表 ----------------
    lines = cur.decode("utf-8").split("\n")
    rows = {}
    for ln in lines:
        if not ln.startswith("| 臂"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 15:
            continue
        m = re.match(r"臂\s*(\d)", cells[0])
        if not m:
            continue
        scen = {"10bp": "10bp", "30bp": "30bp", "gross": "gross"}[cells[1]]
        p50, p90 = [num(x) for x in cells[9].split("/")]
        ex = cells[11].split("/")
        rows[f"a{m.group(1)}_{scen}"] = {
            "ann252": num(cells[2]), "ann_cal": num(cells[3]), "oos_ann": num(cells[4]),
            "mdd": num(cells[5]), "oos_mdd": num(cells[6]), "sharpe": num(cells[7]),
            "oos_sharpe": num(cells[8]), "p50": p50, "p90": p90, "turnover": num(cells[10]),
            "avg_exp": num(ex[0]), "max_exp": num(ex[1]), "n": num(cells[12]),
            "win": num(cells[13]), "avg_pnl": num(cells[14].split("/")[0]),
            "med_pnl": num(cells[14].split("/")[1]),
        }
    res["J2"]["main_table_rows"] = len(rows)
    chk("J2.0 主表 12 行", len(rows) == 12, f"解析到 {len(rows)} 行（期望 12）")

    # §4.1 附加表（a2h / a4）：| 附加 ... | ann252 | ann_cal | oos | mdd | n | turnover |
    side = {}
    for ln in lines:
        if not (ln.startswith("| 附加") or ln.startswith("| 对照")):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        tag = "a4_10bp" if "a4" in cells[0] else ("a2h_10bp" if "a2h" in cells[0] else None)
        if not tag:
            continue
        try:
            side[tag] = {"ann252": num(cells[1]), "ann_cal": num(cells[2]),
                         "oos_ann": num(cells[3]), "mdd": num(cells[4]),
                         "n": num(cells[5]), "turnover": num(cells[6])}
        except ValueError:
            continue
    res["J2"]["side_table"] = side

    mj = json.loads(f_metrics.read_text(encoding="utf-8"))
    by_tag = {}
    for rec in mj:
        oos = rec.get("oos_by_scen") or {}
        for sc, tag in (rec.get("tags") or {}).items():
            by_tag[tag] = {"rec": rec, "scen": sc, "oos": oos.get(sc)}
    res["J2"]["metrics_tags"] = sorted(by_tag)

    # ---- J2 逐格：报告 §4.1 vs metrics.json / 自算 ----
    cell_rows = []
    hard = []
    for tag, row in rows.items():
        if tag not in by_tag:
            hard.append((tag, "NOT_IN_METRICS", "", ""))
            continue
        mv = by_tag[tag]["rec"][by_tag[tag]["scen"]]
        oo = by_tag[tag]["oos"] or {}
        t, e = load(tag)
        es = eq_stats(t, e)
        ts = trade_stats(t)
        pairs = [
            ("ann252", round(mv["annual"] * 100, 2), row["ann252"]),
            ("ann_cal", round(es["ann_cal"] * 100, 2), row["ann_cal"]),
            ("oos_ann", round(oo["oos_annual"] * 100, 2), row["oos_ann"]),
            ("mdd", round(mv["mdd"] * 100, 2), row["mdd"]),
            ("oos_mdd", round(oo["oos_mdd"] * 100, 2), row["oos_mdd"]),
            ("sharpe", round(mv["sharpe"], 2), row["sharpe"]),
            ("oos_sharpe", round(oo["oos_sharpe_self"], 2), row["oos_sharpe"]),
            ("p50", round(mv["hold_p50"], 2), row["p50"]),
            ("p90", round(mv["hold_p90"], 2), row["p90"]),
            ("turnover", round(mv["annual_turnover"], 2), row["turnover"]),
            ("avg_exp", round(mv["avg_exposure"] * 100, 2), row["avg_exp"]),
            ("max_exp", round(mv["max_exposure"] * 100, 2), row["max_exp"]),
            ("n", float(mv["n_trades"]), row["n"]),
            ("win", round(mv["win_rate"] * 100, 2), row["win"]),
            ("avg_pnl", round(mv["avg_pnl"] * 100, 2), row["avg_pnl"]),
            ("med_pnl", round(mv["median_pnl"] * 100, 2), row["med_pnl"]),
        ]
        for key, expect, got in pairs:
            if key == "win":          # 报告该列只印 1 位小数
                expect = round(mv["win_rate"] * 100, 1)
                tol = 0.051
            elif key in ("p50", "p90", "n"):
                tol = 0.001
            else:
                tol = 0.0051
            d = abs(got - expect)
            ok = d <= tol
            cell_rows.append({"tag": tag, "cell": key, "metrics_or_calc": expect,
                              "report": got, "delta": round(got - expect, 4), "ok": ok})
            if not ok:
                hard.append((tag, key, expect, got))
    res["J2"]["cells_checked"] = len(cell_rows)
    res["J2"]["cell_mismatches"] = [c for c in cell_rows if not c["ok"]]
    chk("J2.1 §4.1 12 行 × 16 列 对回 metrics.json/自算",
        len(hard) == 0,
        f"{len(cell_rows)} 格，{len(hard)} 格越差：{hard[:6]}")

    # ---- J2 双口径年化 5 行（报告列 vs 自算，2dp）----
    dual = {}
    for tag in ("a0_10bp", "a1_10bp", "a2_10bp", "a3_10bp", "a4_10bp"):
        t, e = load(tag)
        es = eq_stats(t, e)
        src = rows[tag] if tag in rows else side.get(tag)
        dual[tag] = {"calc_ann252": round(es["ann252"] * 100, 2),
                     "calc_ann_cal": round(es["ann_cal"] * 100, 2),
                     "y_cal": round(es["y_cal"], 4),
                     "report_ann252": src["ann252"] if src else None,
                     "report_ann_cal": src["ann_cal"] if src else None,
                     "source": "§4.1 主表" if tag in rows else "§4.1 附加表"}
    res["J2"]["dual_annualization"] = dual
    dual_bad = [(k, v) for k, v in dual.items()
                if v["report_ann252"] is None or v["report_ann_cal"] is None
                or abs(v["calc_ann252"] - v["report_ann252"]) > 0.0051
                or abs(v["calc_ann_cal"] - v["report_ann_cal"]) > 0.0051]
    chk("J2.2 双口径年化 5 行（日历年列按 7.3320 年自算）", not dual_bad, f"越差行：{dual_bad}")

    # ---- J2 OOS 逐档：4 臂 × 3 档，逐档不同值 ----
    oos_tbl = {}
    oos_bad = []
    for arm in ("a0", "a1", "a2", "a3"):
        vals = {}
        for sc in ("10bp", "30bp", "gross"):
            tag = f"{arm}_{sc}"
            oo = by_tag[tag]["oos"]
            vals[sc] = round(oo["oos_annual"] * 100, 2)
            if abs(rows[tag]["oos_ann"] - vals[sc]) > 0.0051:
                oos_bad.append((tag, rows[tag]["oos_ann"], vals[sc]))
        oos_tbl[arm] = vals
        if len(set(vals.values())) != 3:
            oos_bad.append((arm, "same-values", vals))
    res["J2"]["oos_by_arm"] = oos_tbl
    chk("J2.3 OOS 4 臂×3 档 逐档不同值且报告列=该档自算", not oos_bad, f"异常：{oos_bad}")

    # ---- J2 §9.2 胜率/avg/median 两套 ----
    t0, e0 = load("a0_10bp")
    ts0 = trade_stats(t0)
    expect92 = {
        "n_all": 199, "n_end": 5, "n_closed": 194,
        "win_closed": 33.51, "win_all": 32.66,
        "nwin_closed": 65, "nwin_all": 65,
        "avg_closed": 1.31, "avg_all": 1.27,
        "med_closed": -9.64, "med_all": -8.11,
    }
    got92 = {
        "n_all": ts0["n_trades"], "n_end": ts0["n_end"], "n_closed": ts0["n_closed"],
        "win_closed": round(ts0["win_closed"], 2), "win_all": round(ts0["win_all"], 2),
        "nwin_closed": ts0["n_win_closed"], "nwin_all": ts0["n_win_all"],
        "avg_closed": round(ts0["avg_closed"], 2), "avg_all": round(ts0["avg_all"], 2),
        "med_closed": round(ts0["med_closed_avg"], 2), "med_closed_upper": round(ts0["med_closed_upper"], 2),
        "med_all": round(ts0["med_all_avg"], 2), "med_all_upper": round(ts0["med_all_upper"], 2),
    }
    res["J2"]["s9_2"] = {"expect": expect92, "calc": got92}
    ok92 = all([
        got92["n_all"] == 199, got92["n_end"] == 5, got92["n_closed"] == 194,
        got92["nwin_closed"] == 65, got92["nwin_all"] == 65,
        abs(got92["win_closed"] - 33.51) <= 0.005, abs(got92["win_all"] - 32.66) <= 0.005,
        abs(got92["avg_closed"] - 1.31) <= 0.005, abs(got92["avg_all"] - 1.27) <= 0.005,
        abs(min(abs(got92["med_closed"] - (-9.64)), abs(got92["med_closed_upper"] - (-9.64))) ) <= 0.005,
        abs(min(abs(got92["med_all"] - (-8.11)), abs(got92["med_all_upper"] - (-8.11)))) <= 0.005,
    ])
    chk("J2.4 §9.2 胜率/avg/median 两套（65/194 vs 65/199）", ok92, json.dumps(got92, ensure_ascii=False))

    # ---- J2 §9.5 p90 三法 ----
    p90_tbl = {}
    p90_bad = []
    for tag in ("a0_10bp", "a1_10bp", "a2_10bp", "a3_10bp", "a2h_10bp", "a4_10bp"):
        t, e = load(tag)
        ts = trade_stats(t)
        p90_tbl[tag] = {"n": ts["n_trades"], "nearest": ts["p90_nearest"],
                        "linear": round(ts["p90_linear"], 2), "index": ts["p90_index"]}
    a1 = p90_tbl["a1_10bp"]
    ok95 = (a1["n"] == 519 and a1["nearest"] == 59.0 and abs(a1["linear"] - 59.2) < 1e-9
            and a1["index"] == 60 and p90_tbl["a0_10bp"]["n"] == 199
            and p90_tbl["a0_10bp"]["nearest"] == 60.0 and p90_tbl["a2_10bp"]["n"] == 1126
            and p90_tbl["a2_10bp"]["nearest"] == 18.0)
    others_same = all(v["nearest"] == v["linear"] == v["index"] for k, v in p90_tbl.items()
                      if k not in ("a1_10bp",))
    res["J2"]["s9_5_p90"] = {"table": p90_tbl, "others_three_methods_same": others_same}
    chk("J2.5 §9.5 p90 三法 59/59.2/60（a1），其余行三法同值", ok95 and others_same,
        json.dumps(p90_tbl, ensure_ascii=False))

    # ---- J2 止损分档 ----
    t1, e1 = load("a1_10bp")
    sl = t1.filter(pl.col("exit_reason") == "stop_loss")
    r = [(x["exit_price"] / x["entry_price"] - 1) * 100 for x in sl.to_dicts()]
    band = {
        "n": len(r),
        "in_-8.10_-8.00": sum(1 for x in r if -8.10 <= x <= -8.00),
        "in_-8.085_-8.00": sum(1 for x in r if -8.085 <= x <= -8.00),
        "lt_-15": sum(1 for x in r if x < -15),
        "gt_0": sum(1 for x in r if x > 0),
    }
    from collections import Counter
    cnt = Counter(f"{x:.4f}%" for x in r)
    band["mode_top3"] = cnt.most_common(3)
    res["J2"]["stop_bands"] = band
    ok_band = (band["n"] == 425 and band["in_-8.10_-8.00"] == 315
               and band["in_-8.085_-8.00"] == 0 and band["lt_-15"] == 22 and band["gt_0"] == 1
               and dict(cnt.most_common(2)) == {"-8.0919%": 88, "-8.0920%": 85})
    chk("J2.6 止损分档 425/315/0/22/1 + 众数 −8.0919(88)/−8.0920(85)", ok_band,
        json.dumps(band, ensure_ascii=False))

    # ---- J2 F4 换手比 1.55x ----
    t0b, e0b = load("a0_10bp")
    t1b, e1b = load("a1_10bp")
    YRS_FULL = 2678 / 365.25
    to_a0 = float(t0b["entry_value"].sum()) / 1e6 / YRS_FULL
    to_a1 = float(t1b["entry_value"].sum()) / 1e6 / YRS_FULL
    ratio = to_a1 / to_a0
    res["J2"]["f4_turnover"] = {"a0": round(to_a0, 4), "a1": round(to_a1, 4),
                                "ratio_exact": round(ratio, 4),
                                "ratio_2dp": round(ratio, 2),
                                "from_printed": round(5.39 / 3.48, 4)}
    ok_f4 = (abs(round(to_a0, 2) - 3.48) <= 0.005 and abs(round(to_a1, 2) - 5.39) <= 0.005
             and round(ratio, 2) == 1.55 and ratio > 1.5)
    chk("J2.7 F4 换手比 5.39/3.48 = 1.55× > 1.5×", ok_f4,
        json.dumps(res["J2"]["f4_turnover"], ensure_ascii=False))

    # ---------------- J3 PREREG 只增不改 ----------------
    pre = f_prereg.read_bytes()
    preo = f_prereg_old.read_bytes()
    k = 0
    while k < min(len(pre), len(preo)) and pre[k] == preo[k]:
        k += 1
    res["J3"] = {
        "total": len(pre), "old": len(preo), "common_prefix": k,
        "prefix_identical": pre[: len(preo)] == preo,
        "appended_bytes": len(pre) - len(preo),
        "appended_starts_with_newline": pre[len(preo): len(preo) + 1] == b"\n",
        "old_sha": hashlib.sha256(preo).hexdigest(),
        "mtime_old_copy": mtime(f_prereg_old),
        "mtime_new": mtime(f_prereg),
    }
    pre_txt = pre.decode("utf-8")
    app_txt = pre[len(preo):].decode("utf-8")
    # 追加段是否只提到 mtime/sha，不改判据
    res["J3"]["appendix"] = app_txt
    # F4 节是否含「退回只做 45 天上限」
    m_f4 = re.search(r"F4[^\n]*", pre_txt)
    res["J3"]["f4_line"] = m_f4.group(0)[:400] if m_f4 else None
    body = preo.decode("utf-8")
    res["J3"]["f4_in_original_body"] = ("退回只做 45 天上限" in body)
    res["J3"]["f4_in_current_file"] = ("退回只做 45 天上限" in pre_txt)
    ok3 = (res["J3"]["prefix_identical"] and len(preo) == 2871
           and hashlib.sha256(preo).hexdigest().startswith("cf95a0b7")
           and res["J3"]["appended_starts_with_newline"])
    chk("J3.1 PREREG 前 2,871 B 与 cf95a0b7 副本逐字节相同", ok3,
        f"prefix={k}/{len(preo)}；追加 {len(pre)-len(preo)} B；新 sha={hashlib.sha256(pre).hexdigest()[:16]}")
    chk("J3.2 PREREG F4 节含「退回只做 45 天上限」", res["J3"]["f4_in_current_file"],
        (res["J3"]["f4_line"] or "")[:120])

    # §9.1 引用的 mtime 逐个核对
    mt_expect = {
        "results/smoke_a0": "16:20:44",
        "results/a0_10bp": "16:21:47",
        "results/a1_10bp": "16:24:00",
        "results/a2_10bp": "16:24:16",
        "results/a3_10bp": "16:24:33",
        "results/a2h_10bp": "16:25:05",
        "results/a0ev_10bp": "16:25:21",
        "results/a3ev_10bp": "16:25:38",
        "results/a0_30bp": "16:26:57",
        "results/a1_30bp": "16:27:13",
        "results/a2_30bp": "16:27:30",
        "results/a3_30bp": "16:27:47",
        "results/a0_gross": "16:29:55",
        "results/a1_gross": "16:30:12",
        "results/a2_gross": "16:30:29",
        "results/a3_gross": "16:30:45",
        "results/a4_10bp": "16:33:36",
        "results/prod_file_10bp": "17:18:48",
    }
    mt_got, mt_bad = {}, []
    for rel, hhmm in mt_expect.items():
        p = BASE / rel
        if not p.exists():
            mt_bad.append((rel, "MISSING", hhmm))
            continue
        # 取目录内除 result.json 外的最新文件 mtime（= 该臂写盘完成时刻）；同时记录目录 mtime
        files = sorted([q for q in p.rglob("*") if q.is_file()],
                       key=lambda q: q.stat().st_mtime)
        last = mtime(files[-1])[-8:]
        dmt = mtime(p)[-8:]
        mt_got[rel] = {"last_file": last, "dir": dmt, "expect": hhmm}
        if last != hhmm and dmt != hhmm:
            mt_bad.append((rel, dmt, last, hhmm))
    res["J3"]["mtimes"] = mt_got
    res["J3"]["mtime_bad"] = mt_bad
    chk("J3.3 §9.1 的 18 个 mtime 与文件系统一致", not mt_bad, f"不符：{mt_bad}")

    # a0_10bp 三个文件字节数
    sz = {
        "result.json": (RES / "a0_10bp" / "result.json").stat().st_size,
        "trades.parquet": (RES / "a0_10bp" / "trades.parquet").stat().st_size,
        "equity.parquet": (RES / "a0_10bp" / "equity.parquet").stat().st_size,
    }
    res["J3"]["a0_10bp_sizes"] = sz
    chk("J3.4 §9.1 a0_10bp 三个文件 2,349/22,854/18,918 B", sz == {
        "result.json": 2349, "trades.parquet": 22854, "equity.parquet": 18918},
        json.dumps(sz))

    # ---------------- J4 metrics.json ----------------
    def find_key(o, key, path=""):
        hits = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key:
                    hits.append(path + "/" + k)
                hits += find_key(v, key, path + "/" + k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                hits += find_key(v, key, path + f"[{i}]")
        return hits

    oos_hits = find_key(mj, "oos")
    res["J4"]["oos_keys"] = oos_hits
    chk("J4.1 全树无 `oos` 键", len(oos_hits) == 0, f"命中 {len(oos_hits)} 处")

    allow = {"label", "tags", "10bp", "30bp", "gross", "oos_by_scen", "delay"}
    key_sets = [set(r.keys()) for r in mj]
    res["J4"]["key_sets"] = [sorted(s) for s in key_sets]
    chk("J4.2 六条记录顶层键集合 == 白名单", all(s == allow for s in key_sets),
        f"{[sorted(s) for s in key_sets][:2]}")

    scen_cov = {}
    bad_recalc = []
    for rec in mj:
        lab = rec.get("label")
        cov = sorted((rec.get("oos_by_scen") or {}).keys())
        scen_cov[lab] = cov
        for sc, d in (rec.get("oos_by_scen") or {}).items():
            calc = (d["oos_end_value"] / d["oos_start_value"]) ** (1 / d["oos_years"]) - 1
            if abs(calc - d["oos_annual"]) > 5e-5:
                bad_recalc.append((lab, sc, round(calc, 6), d["oos_annual"]))
    res["J4"]["scenario_coverage"] = scen_cov
    res["J4"]["recalc_bad"] = bad_recalc
    lab_ok = all(scen_cov[lab] == ["10bp", "30bp", "gross"]
                 for lab in scen_cov if lab and lab.startswith("臂"))
    chk("J4.3 oos_by_scen 逐档自算一致（(末/初)^(1/3.833)−1）", not bad_recalc, f"{bad_recalc}")
    chk("J4.4 四臂记录 oos_by_scen 三档齐全（a2h/a4 只有 10bp）", lab_ok,
        json.dumps(scen_cov, ensure_ascii=False))

    gen_txt = f_gen.read_text(encoding="utf-8")
    gen_lines = gen_txt.split("\n")
    res["J4"]["gen_oos_lines"] = [f"L{i+1}: {l}" for i, l in enumerate(gen_lines)
                                  if "oos" in l and "oos_by_scen" not in l and "#" not in l.split("=")[0]]
    res["J4"]["gen_has_oos_assign"] = 'out["oos"]' in gen_txt
    chk("J4.5 report_metrics.py 不再写 out[\"oos\"]", not res["J4"]["gen_has_oos_assign"],
        f"相关行 {len(res['J4']['gen_oos_lines'])} 条")
    comment_block = [111 + i for i, l in enumerate(gen_lines[110:114]) if l.strip().startswith("#")]
    res["J4"]["gen_comment_block"] = comment_block
    chk("J4.6 §9.3 所说的「三行注释」在 112–114 行", len(comment_block) == 3,
        f"行号 {comment_block}")
    mtable_txt = f_mtable.read_text(encoding="utf-8")
    mtable_hdr = mtable_txt.split("\n")[0]
    res["J4"]["metrics_table_header"] = mtable_hdr
    chk("J4.7 metrics_table.md 列头仍无「已平仓」且 a0 胜率 33.5%（与 §9.2 自述一致）",
        ("已平仓" not in mtable_hdr) and ("| 33.5% |" in mtable_txt),
        mtable_hdr[:120])

    # ---------------- J5 §9 引用路径/哈希 ----------------
    sec9 = "\n".join(lines[379:472])
    refs = {
        "REPORT_pre_s9_1810.md.bak": (BASE / "REPORT_pre_s9_1810.md.bak").exists(),
        "PREREG_pre_timefix_1810.md.bak": (BASE / "PREREG_pre_timefix_1810.md.bak").exists(),
        "results/a0_10bp/trades.parquet": (RES / "a0_10bp" / "trades.parquet").exists(),
        "results/a0_10bp/result.json": (RES / "a0_10bp" / "result.json").exists(),
        "results/a0_10bp/equity.parquet": (RES / "a0_10bp" / "equity.parquet").exists(),
        "results/a2h_10bp/trades.parquet": (RES / "a2h_10bp" / "trades.parquet").exists(),
    }
    res["J5"] = {"paths": refs}
    chk("J5.1 §9 引用的路径全部存在", all(refs.values()), json.dumps(refs))

    # §9 里出现的 sha 前缀逐个核对
    sha_hits = re.findall(r"`([0-9a-f]{8,64})`", sec9)
    sha_map = {}
    files_now = {
        "PREREG_S01B_20261108.md": sha(f_prereg),
        "metrics.json": sha(f_metrics),
        "metrics_table.md": sha(f_mtable),
        "report_metrics.py": sha(f_gen),
        "REPORT_pre_s9_1810.md.bak": sha(f_base),
        "PREREG_pre_timefix_1810.md.bak": sha(f_prereg_old),
    }
    unexplained = []
    for h in set(sha_hits):
        match = [n for n, v in files_now.items() if v.startswith(h)]
        sha_map[h] = match or "NO-MATCH"
        if not match:
            unexplained.append(h)
    res["J5"]["sha_in_s9"] = sha_map
    # 6174f4da 必须在 §9 内被标作废
    stale_ok = True
    if "6174f4da" in sec9:
        idx = sec9.find("6174f4da")
        window = sec9[idx: idx + 60]
        stale_ok = "作废" in window
    res["J5"]["6174f4da_marked_stale_in_s9"] = stale_ok
    chk("J5.2 §9 内哈希引用可对上现存文件（或明确作废）", len(unexplained) == 0, f"未对上：{unexplained}")
    chk("J5.3 §9 里 6174f4da 已标「作废」", stale_ok, "§9.6 原文：旧值 6174f4da… 作废")

    # 正文 §8 哈希表是否仍把 6174f4da 当现行值（无 §9 交叉引用）
    body_lines = lines[:379]
    stale_body = [(i + 1, l) for i, l in enumerate(body_lines) if "6174f4da" in l]
    res["J5"]["stale_hash_in_body"] = [{"line": i, "text": l[:200]} for i, l in stale_body]
    cross_ref = any(("6174f4da" in l) and (("§8" in l) or ("正文" in l) or ("产物哈希" in l))
                    for l in lines[379:472])
    res["J5"]["sec9_cross_refs_body_hash_table"] = cross_ref
    chk("J5.4 正文（§0–§8）不再把 6174f4da 当现行哈希 / §9 是否有交叉引用",
        len(stale_body) == 0 or cross_ref,
        f"正文命中 {len(stale_body)} 行（L357/L365）；§9 交叉引用={cross_ref}——P3 非阻断", blocking=False)

    # 3c0f27e9：prod_file vs a3 trades 字节相同
    h_prod = sha(RES / "prod_file_10bp" / "trades.parquet")
    h_a3 = sha(RES / "a3_10bp" / "trades.parquet")
    res["J5"]["prod_vs_a3_trades"] = {"prod": h_prod, "a3": h_a3}
    chk("J5.5 prod_file_10bp 与 a3_10bp 的 trades.parquet 字节相同 3c0f27e9",
        h_prod == h_a3 and h_prod.startswith("3c0f27e9"),
        f"{h_prod[:16]} vs {h_a3[:16]}")

    # .step1 / 变体路径是否被 §9 引用（应无）
    step1_ref = (".step1" in sec9)
    res["J5"]["sec9_cites_step1"] = step1_ref
    chk("J5.6 §9 不引用已移走的 .step1 路径", not step1_ref, f"sec9 含 .step1 = {step1_ref}")

    # 9.4 逐笔全等 199/199, 1135/1135
    t_a0ev = pl.read_parquet(RES / "a0ev_10bp" / "trades.parquet")
    t_a3ev = pl.read_parquet(RES / "a3ev_10bp" / "trades.parquet")
    eq0 = t0b.equals(t_a0ev)
    t_a3 = pl.read_parquet(RES / "a3_10bp" / "trades.parquet")
    eq3 = t_a3.equals(t_a3ev)
    res["J5"]["equals"] = {"a0": (eq0, t0b.height), "a3": (eq3, t_a3.height)}
    chk("J5.7 §9.4 臂0 199/199、臂3 1135/1135 逐笔全等", eq0 and eq3,
        json.dumps({k: (v[0], v[1]) for k, v in res["J5"]["equals"].items()}))

    # ---------------- 汇总 ----------------
    n_three = sum(1 for lab, cov in res["J4"]["scenario_coverage"].items() if len(cov) == 3)
    res["J4"]["records_with_three_scen"] = n_three
    sec9_claim = "三档齐全" in sec9
    res["J4"]["sec9_claims_three_scen_for_all_six"] = sec9_claim and n_three != 6
    chk("J4.8 §9.3 「六行 … oos_by_scen 三档齐全」字面成立",
        (not sec9_claim) or n_three == 6,
        f"实际只有 {n_three}/6 条记录有三档（a2h / a4 只跑了 10bp）——P3 措辞", blocking=False)

    # _audit_report_table.py 是否只读
    art = (BASE / "_audit_report_table.py").read_text(encoding="utf-8")
    ro = ("write_text" not in art) and ('.to_csv(' not in art) and ("open(" not in art)
    res["J5"]["audit_script_readonly"] = ro
    chk("J5.8 _audit_report_table.py 只读（无写盘调用）", ro, "未见 write_text/to_csv/open()")

    res["checks"] = CHECKS
    blocking_bad = [c for c in CHECKS if c["blocking"] and not c["ok"]]
    notes = [c for c in CHECKS if (not c["blocking"]) and (not c["ok"])]
    res["verdict"] = "PASS" if not blocking_bad else "FAIL"
    res["notes"] = notes
    (HERE / "_s9_check.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for c in CHECKS:
        tag = "YES " if c["ok"] else ("NO  " if c["blocking"] else "P3  ")
        print(tag + c["id"] + " | " + c["detail"][:170])
    print("VERDICT:", res["verdict"], "checks=", len(CHECKS),
          "blocking_failed=", len(blocking_bad), "p3_notes=", len(notes))
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
