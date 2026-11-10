"""S01b 阶段2：D 口径 vs C 口径（末日结算修复后）逐臂对照表 + 作废清单底稿。

只读输入：
  D = research/s01b-20261108/results/<arm>/          （旧引擎跑出的既有产物）
  C = research/s01b-20261108/postfix_20261108/results_all/<arm>/  （当前引擎 4243fe97 重跑）
  锚点：five_a/<arm>/ (D) 对 postfix_20261108/<arm>/ (C)，即五-a 单键分解六臂组

输出（全部落在 postfix_20261108/）：
  delta_arms.json                 机器可读逐臂 Δ
  METRICS_D_vs_C_20261108.md      三列对照表 + 作废清单
  metrics_table_C_20261108.md     C 口径的 8 臂指标表（与 metrics_table.md 同结构）

指标算法与 report_metrics.py 逐行一致（OOS: >=2023-01-01，基数日 2022-12-30）。
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib

import polars as pl

HERE = pathlib.Path(__file__).resolve().parent
PARENT = HERE.parent
D_ROOT = PARENT / "results"
C_ROOT = HERE / "results_all"
FIVE_A = PARENT / "five_a"
POSTFIX = HERE

START, END = "2019-07-01", "2026-10-30"
OOS_START = "2023-01-01"
OOS_BASE_DATE = "2022-12-30"
VOLATILE = {"timing_ms", "matrix_data_cache_timing_ms", "matrix_data_cache_hit",
            "matrix_data_cache_status", "matrix_data_cache_bytes"}

ARMS = [
    ("a0_10bp", "臂 0 基线（无风控出场）", "10bp"),
    ("a0_30bp", "臂 0 基线（无风控出场）", "30bp"),
    ("a0_gross", "臂 0 基线（无风控出场）", "gross"),
    ("a1_10bp", "臂 1 + 止损 -8%", "10bp"),
    ("a1_30bp", "臂 1 + 止损 -8%", "30bp"),
    ("a1_gross", "臂 1 + 止损 -8%", "gross"),
    ("a2_10bp", "臂 2 + 止损 + 移动止盈 10/8", "10bp"),
    ("a2_30bp", "臂 2 + 止损 + 移动止盈 10/8", "30bp"),
    ("a2_gross", "臂 2 + 止损 + 移动止盈 10/8", "gross"),
    ("a3_10bp", "臂 3 + 上路 + 最长持有 45", "10bp"),
    ("a3_30bp", "臂 3 + 上路 + 最长持有 45", "30bp"),
    ("a3_gross", "臂 3 + 上路 + 最长持有 45", "gross"),
    ("a2h_10bp", "对照 臂2 peak=high", "10bp"),
    ("a4_10bp", "附加 只改 MAX_HOLD_DAYS=45", "10bp"),
    ("a0ev_10bp", "等价性 臂0 事件式 cross_down", "10bp"),
    ("a3ev_10bp", "等价性 臂3 事件式 cross_down", "10bp"),
    ("prod_file_10bp", "生产文件口径复现（5,510B 变体）", "10bp"),
    ("smoke_a0", "冒烟 臂0 2023Q1（3 个月）", "10bp"),
]

SIX_ARM_ANCHOR = [
    ("base_nodefaults_10bp", -51.47, -51.64),
    ("only_execution_costs", -51.46, -51.63),
    ("only_entry_price_basis_raw", -56.53, -56.70),
    ("base_nodefaults_gross", None, None),
    ("only_block_limit_open", 12.13, 11.78),
    ("only_trailing_peak_price_close", -51.47, -51.64),
    ("only_finalize_open_at_end", -52.18, -52.18),
    ("only_exit_signal_requires_profit", -32.62, -32.62),
]


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def years(a: str, b: str) -> float:
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days / 365.25


def oos_metrics(root: pathlib.Path, tag: str) -> dict | None:
    p = root / tag / "equity.parquet"
    if not p.exists():
        return None
    e = pl.read_parquet(p).sort("date").with_columns(pl.col("value").cast(pl.Float64))
    base_rows = e.filter(pl.col("date") <= OOS_BASE_DATE)
    base = float(base_rows["value"][-1]) if base_rows.height else float(e["value"][0])
    oos = e.filter(pl.col("date") >= OOS_START)
    if not oos.height:
        return None
    v0, v1 = base, float(oos["value"][-1])
    d1 = str(oos["date"][-1])
    yrs = years(OOS_BASE_DATE, d1)
    ann = (v1 / v0) ** (1 / yrs) - 1 if v0 > 0 and v1 > 0 else float("nan")
    peak, mdd = -1e18, 0.0
    for v in oos["value"].to_list():
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    rets = (oos["value"] / oos["value"].shift(1) - 1).drop_nulls()
    mu, sd = float(rets.mean()), float(rets.std())
    sharpe = mu / sd * math.sqrt(252) if sd else float("nan")
    return {"oos_annual": round(ann, 4), "oos_mdd": round(mdd, 4),
            "oos_sharpe": round(sharpe, 3), "oos_days": oos.height}


def arm_metrics(root: pathlib.Path, tag: str) -> dict | None:
    rj = root / tag / "result.json"
    if not rj.exists():
        return None
    r = json.loads(rj.read_text(encoding="utf-8"))
    st = r["stats"]
    t = pl.read_parquet(root / tag / "trades.parquet")
    dur = t["duration"].cast(pl.Float64)
    turnover = float(t["entry_value"].sum()) / 1_000_000.0 / years(START, END)
    er = {d["exit_reason"]: d["len"]
          for d in t.group_by("exit_reason").len().sort("exit_reason").to_dicts()}
    m = {
        "n_trades": st["n_trades"],
        "completed_trade_count": st["completed_trade_count"],
        "open_at_end_count": st["open_at_end_count"],
        "total_return": round(st["total_return"], 6),
        "annual_return": round(st["annual_return"], 6),
        "max_drawdown": round(st["max_drawdown"], 6),
        "sharpe": round(st["sharpe"], 3),
        "win_rate": round(st["win_rate"], 6),
        "avg_pnl": round(st["avg_pnl"], 6),
        "median_pnl": round(st["median_pnl"], 6),
        "avg_holding_days": round(st["avg_holding_days"], 3),
        "hold_p50": round(float(dur.median()), 2),
        "hold_p90": round(float(dur.quantile(0.9)), 2),
        "annual_turnover": round(turnover, 3),
        "avg_exposure": round(st["avg_exposure"], 6),
        "max_exposure": round(st["max_exposure"], 6),
        "final_equity": round(st["final_equity"], 2),
        "exit_reason": er,
    }
    oos = oos_metrics(root, tag)
    if oos:
        m.update(oos)
    return m


def stats_diff(d: dict, c: dict) -> dict:
    out = {}
    keys = (set(d) | set(c)) - VOLATILE
    for k in sorted(keys):
        if isinstance(d.get(k), dict) and isinstance(c.get(k), dict):
            if d[k] != c[k]:
                out[k] = {"D": d[k], "C": c[k]}
            continue
        if d.get(k) != c.get(k):
            out[k] = {"D": d.get(k), "C": c.get(k)}
    return out


def finalize_flag(cfg: pathlib.Path) -> bool | None:
    if not cfg.exists():
        return None
    o = json.loads(cfg.read_text(encoding="utf-8"))
    eo = (o.get("execution_policy_normalized") or {}).get("engine_options") or {}
    return eo.get("finalize_open_at_end")


def collect() -> dict:
    arms = []
    for tag, label, scen in ARMS:
        d_res = D_ROOT / tag
        c_res = C_ROOT / tag
        entry = {"tag": tag, "label": label, "scenario": scen,
                 "has_D": d_res.exists(), "has_C": c_res.exists()}
        if not (d_res.exists() and c_res.exists()):
            entry["status"] = "MISSING"
            arms.append(entry)
            continue
        shas = {}
        for name in ("trades.parquet", "equity.parquet"):
            pd_, pc = d_res / name, c_res / name
            if pd_.exists() and pc.exists():
                sd, sc = sha256_file(pd_), sha256_file(pc)
                shas[name] = {"D": sd, "C": sc, "same": sd == sc}
        pd_, pc = d_res / "drawdown.parquet", c_res / "drawdown.parquet"
        shas["drawdown.parquet"] = {
            "D": sha256_file(pd_) if pd_.exists() else None,
            "C": sha256_file(pc) if pc.exists() else None,
            "same": (sha256_file(pd_) == sha256_file(pc)) if (pd_.exists() and pc.exists()) else None,
        }
        d_res_js = json.loads((d_res / "result.json").read_text(encoding="utf-8"))
        c_res_js = json.loads((c_res / "result.json").read_text(encoding="utf-8"))
        sd_, sc_ = d_res_js.get("stats", {}), c_res_js.get("stats", {})
        diff = stats_diff(sd_, sc_)
        mD, mC = arm_metrics(D_ROOT, tag), arm_metrics(C_ROOT, tag)
        deltas = {}
        if mD and mC:
            for k in mD:
                if k in ("exit_reason",):
                    deltas[k] = {"same": mD[k] == mC.get(k),
                                 "D": mD[k], "C": mC.get(k)}
                    continue
                a, b = mD[k], mC.get(k)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    deltas[k] = {"D": a, "C": b, "delta": round(b - a, 6)}
        unchanged = (not diff
                     and all(v["same"] is True for k, v in shas.items()
                             if k != "drawdown.parquet")
                     and all((deltas.get(k, {}).get("delta") in (0, 0.0, None))
                             for k in deltas if "delta" in deltas[k]))
        entry.update({
            "status": "UNCHANGED" if unchanged else "CHANGED",
            "finalize_open_at_end": finalize_flag(c_res / "effective_config.json"),
            "parquet_sha256": shas,
            "stats_diff": diff,
            "execution_D": sd_.get("execution"),
            "execution_C": sc_.get("execution"),
            "execution_same": sd_.get("execution") == sc_.get("execution"),
            "metrics_D": mD,
            "metrics_C": mC,
            "deltas": deltas,
        })
        arms.append(entry)
    anchor = []
    for tag, pp_D, pp_C in SIX_ARM_ANCHOR:
        a = arm_metrics(FIVE_A, tag)
        b = arm_metrics(POSTFIX, tag)
        if not (a and b):
            anchor.append({"tag": tag, "status": "MISSING"})
            continue
        anchor.append({
            "tag": tag,
            "total_return_D": a["total_return"], "total_return_C": b["total_return"],
            "delta_pp": round((b["total_return"] - a["total_return"]) * 100, 4),
            "final_D": a["final_equity"], "final_C": b["final_equity"],
            "expected_pp_D": pp_D, "expected_pp_C": pp_C,
            "mdd_D": a["max_drawdown"], "mdd_C": b["max_drawdown"],
            "parquet_trades_same": (
                sha256_file(FIVE_A / tag / "trades.parquet")
                == sha256_file(POSTFIX / tag / "trades.parquet")
                if (FIVE_A / tag / "trades.parquet").exists()
                and (POSTFIX / tag / "trades.parquet").exists() else None),
        })
    return {"arms": arms, "anchor_six": anchor,
            "engine_C_sha256": sha256_file(pathlib.Path(
                r"C:\work\sourcecode\tick-stock-panel\backend\app\backtest\engine.py"))}


def fmt_pct(v, digits=2):
    return "—" if v is None else f"{v * 100:+.{digits}f}%"


def render_md(data: dict) -> str:
    arms = data["arms"]
    L: list[str] = []
    L.append("# S01b · D 口径 → C 口径（末日结算修复）逐臂对照 · 2026-11-08")
    L.append("")
    L.append(f"- C 口径引擎：`engine.py` sha256 `{data['engine_C_sha256'][:16]}…`"
             "（修复后，末日不再出现「按收盘盯市写权益行 + 按开盘价卖出入现金」两处口径不一致）")
    L.append("- D 值直接读 `research/s01b-20261108/results/<arm>/result.json`，C 值读 "
             "`postfix_20261108/results_all/<arm>/result.json`，两者都未手抄")
    L.append("- 全部 18 臂在同一口径下重跑：同一策略文件、同一 start/end、同一滑点/成本、"
             "同一 5 仓 60% 敞口。`prod_file_10bp` 从 `prod_file_snapshots/"
             "custom_mw7fvp17.py.variant_5510B_918254f0.py` 还原到 `_inputs/` 再跑（生产文件已回滚，"
             "不读写 `D:\\TSP`）")
    L.append("")
    n_chg = sum(1 for a in arms if a.get("status") == "CHANGED")
    n_unch = sum(1 for a in arms if a.get("status") == "UNCHANGED")
    L.append(f"**结论先行：{n_unch} 臂未变、{n_chg} 臂已变。** 原因不是「修复没生效」，"
             "而是这 18 臂的策略文件全部声明 `finalize_open_at_end=True`（见表末列），"
             "走的是末日强制清算分支——按契约这正是唯一不触发该缺陷的分支。")
    L.append("")

    L.append("## 1 · 臂级：已变 / 未变")
    L.append("")
    L.append("| 臂 | 策略 | 情景 | 状态 | trades sha 同 | equity sha 同 | drawdown(D 有无) | "
             "finalize_open_at_end | 末值 D | 末值 C |")
    L.append("|---|---|---|---|---|---|---|---|---:|---:|")
    for a in arms:
        if a.get("status") == "MISSING":
            L.append(f"| `{a['tag']}` | {a['label']} | {a['scenario']} | 缺产物 | | | | | | |")
            continue
        sh = a["parquet_sha256"]
        L.append(
            f"| `{a['tag']}` | {a['label']} | {a['scenario']} | "
            f"{'**已变**' if a['status'] == 'CHANGED' else '未变'} | "
            f"{'是' if sh['trades.parquet']['same'] else '否'} | "
            f"{'是' if sh['equity.parquet']['same'] else '否'} | "
            f"{'无 / 新增' if sh['drawdown.parquet']['D'] is None else ('是' if sh['drawdown.parquet']['same'] else '否')} | "
            f"{a['finalize_open_at_end']} | "
            f"{a['metrics_D']['final_equity']:,.2f} | {a['metrics_C']['final_equity']:,.2f} |")
    L.append("")

    L.append("## 2 · 逐指标三列对照（D / C / Δ）")
    L.append("")
    metrics = [
        ("n_trades", "笔数", "d"),
        ("completed_trade_count", "闭环笔数", "d"),
        ("open_at_end_count", "期末仍持仓", "d"),
        ("total_return", "总收益", "pct"),
        ("annual_return", "全期年化", "pct"),
        ("max_drawdown", "MDD", "pct"),
        ("sharpe", "Sharpe", "f3"),
        ("win_rate", "胜率", "pct1"),
        ("avg_pnl", "avg pnl", "pct"),
        ("median_pnl", "median pnl", "pct"),
        ("avg_holding_days", "均持仓天数", "f2"),
        ("hold_p50", "持仓 p50", "f1"),
        ("hold_p90", "持仓 p90", "f1"),
        ("annual_turnover", "年换手", "x"),
        ("avg_exposure", "均暴露", "pct"),
        ("max_exposure", "最大暴露", "pct"),
        ("final_equity", "末值", "money"),
        ("oos_annual", "OOS 年化", "pct"),
        ("oos_mdd", "OOS MDD", "pct"),
        ("oos_sharpe", "OOS Sharpe", "f3"),
    ]

    def cell(v, kind):
        if v is None:
            return "—"
        if kind == "pct":
            return f"{v * 100:+.2f}%"
        if kind == "pct1":
            return f"{v * 100:.1f}%"
        if kind == "d":
            return f"{int(v)}"
        if kind == "f3":
            return f"{v:+.3f}"
        if kind == "f2":
            return f"{v:.2f}"
        if kind == "f1":
            return f"{v:.0f}"
        if kind == "x":
            return f"{v:.2f}x"
        if kind == "money":
            return f"{v:,.2f}"
        return str(v)

    for key, name, kind in metrics:
        L.append(f"### {name}（`{key}`）")
        L.append("")
        L.append(f"| 臂 | D | C | Δ |")
        L.append("|---|---:|---:|---:|")
        for a in arms:
            if a.get("status") == "MISSING":
                continue
            d = a["metrics_D"].get(key)
            c = a["metrics_C"].get(key)
            if isinstance(d, (int, float)) and isinstance(c, (int, float)):
                dd = c - d
                if kind == "pct":
                    dcell = f"{dd * 100:+.4f}pp"
                elif kind == "pct1":
                    dcell = f"{dd * 100:+.2f}pp"
                elif kind == "money":
                    dcell = f"{dd:+,.2f}"
                elif kind == "d":
                    dcell = f"{int(dd):+d}"
                elif kind == "x":
                    dcell = f"{dd:+.3f}x"
                elif kind == "f1":
                    dcell = f"{dd:+.2f}"
                else:
                    dcell = f"{dd:+.6f}"
            else:
                dcell = "—"
            L.append(f"| `{a['tag']}` | {cell(d, kind)} | {cell(c, kind)} | {dcell} |")
        L.append("")

    L.append("## 3 · `stats.execution` 的 P6 相关键（D vs C）")
    L.append("")
    keys = ("sell_limit_down", "pending_exit", "sell_suspended", "sell_invalid_price",
            "buy_limit_up", "buy_no_slot")
    L.append("| 臂 | " + " | ".join(keys) + " | 整块相同 |")
    L.append("|---|" + "---|" * len(keys) + "---|")
    for a in arms:
        if a.get("status") == "MISSING":
            continue
        ed, ec = a["execution_D"] or {}, a["execution_C"] or {}
        cs = []
        for k in keys:
            vd, vc = ed.get(k), ec.get(k)
            cs.append(f"{vd}→{vc}" if vd != vc else f"{vd}")
        L.append(f"| `{a['tag']}` | " + " | ".join(cs) + f" | {'是' if a['execution_same'] else '**否**'} |")
    L.append("")

    L.append("## 4 · 六臂锚点自洽（五-a 单键分解组，D 取自 five_a/，C 取自本目录）")
    L.append("")
    L.append("| 臂 | 总收益 D | 总收益 C | Δ | 契约已知 Δ | 末值 D | 末值 C | trades sha 同 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for a in data["anchor_six"]:
        if a.get("status") == "MISSING":
            L.append(f"| `{a['tag']}` | 缺产物 | | | | | | |")
            continue
        if a.get("expected_pp_C") is None:
            exp = "未给"
        else:
            exp = f"{a['expected_pp_C'] - a['expected_pp_D']:+.2f}pp"
        L.append(f"| `{a['tag']}` | {fmt_pct(a['total_return_D'])} | {fmt_pct(a['total_return_C'])} | "
                 f"{a['delta_pp']:+.2f}pp | {exp} | "
                 f"{a['final_D']:,.2f} | {a['final_C']:,.2f} | "
                 f"{'是' if a['parquet_trades_same'] else '否'} |")
    L.append("")
    return "\n".join(L)


def render_metrics_table_c(data: dict) -> str:
    arms = {a["tag"]: a for a in data["arms"]}
    # 与 report_metrics.py 的行序/行数完全一致：6 个 label × 3 个成本档，未跑则写「未跑」
    labels = [
        ("臂 0 基线（无风控出场）", "a0"),
        ("臂 1 + 止损 -8%", "a1"),
        ("臂 2 + 止损 + 移动止盈 10/8", "a2"),
        ("臂 3 + 上路 + 最长持有 45", "a3"),
        ("对照 臂2 peak=high", "a2h"),
        ("附加 只改 MAX_HOLD_DAYS=45", "a4"),
    ]
    hdr = ("| 臂 | 情景 | 全期年化 | OOS 年化 | MDD | OOS MDD | Sharpe | OOS Sharpe* | "
           "持仓 p50/p90 | 年换手 | 均/最大暴露 | 笔数 | 胜率 | avg/median pnl |")
    lines = [hdr, "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, stem in labels:
        for scen, suffix in (("10bp", "_10bp"), ("30bp", "_30bp"), ("gross", "_gross")):
            a = arms.get(stem + suffix) or {}
            m = a.get("metrics_C")
            if not m:
                lines.append(f"| {label} | {scen} | 未跑 | | | | | | | | | | | |")
                continue
            lines.append(
                f"| {label} | {scen} | {m['annual_return']:+.2%} | {m.get('oos_annual', float('nan')):+.2%} | "
                f"{m['max_drawdown']:.2%} | {m.get('oos_mdd', float('nan')):.2%} | {m['sharpe']:+.2f} | "
                f"{m.get('oos_sharpe', float('nan')):+.2f} | {m['hold_p50']:.0f}/{m['hold_p90']:.0f} | "
                f"{m['annual_turnover']:.2f}x | {m['avg_exposure']:.2%}/{m['max_exposure']:.2%} | "
                f"{m['n_trades']} | {m['win_rate']:.1%} | {m['avg_pnl']:+.2%}/{m['median_pnl']:+.2%} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    data = collect()
    (HERE / "delta_arms.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render_md(data)
    (HERE / "METRICS_D_vs_C_20261108.md").write_text(md, encoding="utf-8")
    (HERE / "metrics_table_C_20261108.md").write_text(
        render_metrics_table_c(data), encoding="utf-8")
    n_chg = sum(1 for a in data["arms"] if a.get("status") == "CHANGED")
    n_unch = sum(1 for a in data["arms"] if a.get("status") == "UNCHANGED")
    n_miss = sum(1 for a in data["arms"] if a.get("status") == "MISSING")
    print(f"[delta] arms={len(data['arms'])} unchanged={n_unch} changed={n_chg} missing={n_miss}")
    for a in data["arms"]:
        if a.get("status") == "CHANGED":
            print(f"[changed] {a['tag']} stats_diff={json.dumps(a['stats_diff'], ensure_ascii=False)[:300]}")
    print("[anchor]")
    for a in data["anchor_six"]:
        if a.get("status") != "MISSING":
            print(f"  {a['tag']:<34} Δ={a['delta_pp']:+.4f}pp  末值 {a['final_D']:,.2f} → {a['final_C']:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
