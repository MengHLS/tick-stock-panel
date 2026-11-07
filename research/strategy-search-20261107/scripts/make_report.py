"""从 registry.json 生成登记表（CSV/Markdown）与多重检验校正结果。"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

import common  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
N_TRIALS = 12          # 本轮假设数（S01–S12）；成本情景与零成本诊断不计为新假设


def yearly_returns(equity: list[dict]) -> dict[str, float]:
    by_year: dict[str, list[float]] = {}
    for row in equity:
        by_year.setdefault(str(row["date"])[:4], []).append(float(row["value"]))
    out = {}
    prev = None
    for year in sorted(by_year):
        vals = by_year[year]
        start = prev if prev is not None else vals[0]
        out[year] = vals[-1] / start - 1
        prev = vals[-1]
    return out


def main() -> None:
    data = json.loads((RESULTS / "registry.json").read_text(encoding="utf-8"))
    runs = {k: v for k, v in data["runs"].items() if v.get("ok")}

    # 各假设在 10bp 情景下的日收益 -> 试验间 Sharpe 方差
    rets = {}
    for key, rec in runs.items():
        if rec.get("gross") or float(rec["slippage_bps"]) != 10.0:
            continue
        path = RESULTS / f"rets_{rec['strategy']}_10.npy"
        if path.exists():
            rets[rec["strategy"]] = np.load(path)
    daily_sr = {k: float(v.mean() / v.std(ddof=1)) for k, v in rets.items() if len(v) > 30}
    sr_var = float(np.var(list(daily_sr.values()), ddof=1)) if len(daily_sr) > 1 else 0.0

    rows = []
    # 作废信息单独存放，与 rows 逐行对齐：绝不能进 rows，否则会污染 summary.json
    void_meta = []
    for key, rec in sorted(runs.items()):
        if float(rec["slippage_bps"]) not in (10.0, 30.0) and not rec.get("gross"):
            continue
        row = {
            "strategy": rec["strategy"], "title": rec["title"], "family": rec["family"],
            "scenario": "gross" if rec.get("gross") else f"{rec['slippage_bps']:g}bp",
            "signals": rec["signals"], "trades": rec["n_trades"],
            "is_return": rec["IS"]["total_return"], "is_sharpe": rec["IS"]["sharpe"],
            "is_mdd": rec["IS"]["max_drawdown"],
            "oos_return": rec["OOS"]["total_return"], "oos_sharpe": rec["OOS"]["sharpe"],
            "oos_mdd": rec["OOS"]["max_drawdown"],
            "all_return": rec["ALL"]["total_return"], "all_cagr": rec["ALL"]["cagr"],
            "all_mdd": rec["ALL"]["max_drawdown"], "all_sharpe": rec["ALL"]["sharpe"],
            "all_sortino": rec["ALL"]["sortino"],
            "trades_closed": rec["ALL"]["n_closed_trades"],
            "win_rate": rec["ALL"]["win_rate"],
            "profit_factor": rec["ALL"]["profit_factor"],
            "avg_holding_days": rec["ALL"]["avg_holding_days"],
            "turnover_x": rec["ALL"]["gross_traded_over_initial"],
            "avg_exposure": rec["ALL"]["avg_exposure"],
            "final_equity": rec["ALL"]["final_equity"],
        }
        rows.append(row)
        void_meta.append({
            "status": rec.get("status") if rec.get("status") else "\u2014",
            "caliber": rec.get("caliber") if rec.get("caliber") else "\u2014",
            "void_ref": rec.get("void_ref") if rec.get("void_ref") else "\u2014",
        })

    # 年度收益（10bp 情景）
    yearly = {}
    for key, rec in runs.items():
        if rec.get("gross") or float(rec["slippage_bps"]) != 10.0:
            continue
        run = json.loads((RESULTS / f"run_{rec['strategy']}_10.json").read_text(encoding="utf-8"))
        yearly[rec["strategy"]] = yearly_returns(run["equity"])

    # 多重检验校正
    dsr = {}
    for name, series in rets.items():
        dsr[name] = common.dsr_value(series, N_TRIALS, sr_var)

    common.save_json(RESULTS / "summary.json", {
        "n_trials": N_TRIALS, "sharpe_variance_daily": sr_var,
        "daily_sharpe": daily_sr, "deflated_sharpe": dsr, "yearly_returns": yearly,
        "rows": rows,
    })

    # registry.csv（原 24 列不动，行尾追加 status/caliber/void_ref）
    if rows:
        keys = list(rows[0].keys()) + ["status", "caliber", "void_ref"]
        with (RESULTS / "registry.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for row, meta in zip(rows, void_meta):
                writer.writerow({**row, **meta})

    meta_by_run = {(r["strategy"], r["scenario"]): m for r, m in zip(rows, void_meta)}

    # Markdown 片段
    lines = []
    lines.append("| 策略 | 情景 | 样本内收益 | 样本内Sharpe | 样本外收益 | 样本外Sharpe | 全期收益 | 年化 | 最大回撤 | Sharpe | DSR | 已平仓笔数 | 换手倍数 | status | caliber | void_ref |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for row in sorted(rows, key=lambda r: (r["strategy"], r["scenario"])):
        d = dsr.get(row["strategy"], {}) if row["scenario"] == "10bp" else {}
        dsrcell = f"{d.get('dsr', float('nan')):.3f}" if d.get("ok") else "—"
        meta = meta_by_run[(row["strategy"], row["scenario"])]
        lines.append(
            f"| {row['strategy']} | {row['scenario']} | {row['is_return']:.2%} | "
            f"{row['is_sharpe']:.2f} | {row['oos_return']:.2%} | {row['oos_sharpe']:.2f} | "
            f"{row['all_return']:.2%} | {row['all_cagr']:.2%} | {row['all_mdd']:.2%} | "
            f"{row['all_sharpe']:.2f} | {dsrcell} | {row['trades_closed']} | {row['turnover_x']:.1f} |"
            f" {meta['status']} | {meta['caliber']} | {meta['void_ref']} |"
        )
    (RESULTS / "registry_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 年度收益表
    years = sorted({y for v in yearly.values() for y in v})
    ylines = ["| 策略 | " + " | ".join(years) + " |", "| --- | " + " | ".join("---:" for _ in years) + " |"]
    for name in sorted(yearly):
        ylines.append("| " + name + " | " + " | ".join(f"{yearly[name].get(y, float('nan')):.1%}" for y in years) + " |")
    (RESULTS / "yearly_table.md").write_text("\n".join(ylines) + "\n", encoding="utf-8")

    print((RESULTS / "registry_table.md").read_text(encoding="utf-8")[:2000])
    print((RESULTS / "yearly_table.md").read_text(encoding="utf-8"))
    for name, d in dsr.items():
        print(name, {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items() if k != "_parts"})


if __name__ == "__main__":
    main()
