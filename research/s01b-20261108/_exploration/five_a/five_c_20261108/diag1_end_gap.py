"""⑤-c 诊断 1：期末权益 1,722.56 缺口——证成 / 证伪（只读）。

不开引擎、不写任何结果目录、不改引擎代码。全部证据来自：
  (a) D:\\TSP 原始日线（688143.SH 2026-10-30 开/收）；
  (b) ⑤-a 各臂已落盘的 trades.parquet / equity.parquet；
  (c) 上一轮 sys.settrace 抓到的生产引擎调用序列 trace_end_position.json；
  (d) 引擎源码行号（只读引用，未修改）。

恒等式（对 finalize_open_at_end=False 的臂）：
    equity_last.value = equity_last.cash + Σ_{D} shares×close
    D = 循环内没卖掉、由循环后 finalize 分支按开盘价虚拟卖出的持仓集合
    final_cash       = equity_last.cash + Σ_{D} exit_value
    gap              = equity_last.value − final_cash
                     = Σ_{D} [ shares×(close−open) + (shares×open − exit_value) ]
                       └── 价基差（收盘盯市 vs 开盘虚拟成交）└── 卖出费用
D 集合用「候选行的 shares×close 子集和 == value−cash」暴力匹配确定，不用人眼挑。

用法：backend/.venv/Scripts/python.exe diag1_end_gap.py
"""
from __future__ import annotations

import itertools
import json
import os
import ast
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
FIVE_A = HERE.parent
RESEARCH = FIVE_A.parent
KLINES = Path(r"D:\TSP\data\kline_daily")

LAST_DATE = "2026-10-30"
PREV_DATE = "2026-10-29"
FOCUS = ["688143.SH", "301513.SZ", "601858.SH", "301313.SZ", "301428.SZ"]

ARMS = [
    "base_nodefaults_10bp",
    "only_entry_price_basis_raw",
    "only_block_limit_open",
    "only_finalize_open_at_end",
    "only_execution_costs",
    "only_trailing_peak_price_close",
    "only_exit_signal_requires_profit",
    "base_nodefaults_gross",
]
ARM_DIR = {a: FIVE_A / a for a in ARMS}
ARM_DIR["a0_10bp_199"] = RESEARCH / "results" / "a0_10bp"


def read_day(day: str, symbols: list[str]) -> pl.DataFrame:
    p = KLINES / f"date={day}" / "part.parquet"
    df = pl.read_parquet(p)
    return (
        df.filter(pl.col("symbol").is_in(symbols))
        .select(["symbol", "open", "high", "low", "close", "volume", "amount"])
        .with_columns(pl.lit(day).alias("date"))
        .sort("symbol")
    )


def closed_form_final_equity(trades: pl.DataFrame, initial: float) -> dict:
    """1,000,000 − Σentry_value + Σexit_value（不含分红，默认口径无分红）。"""
    e = float(trades["entry_value"].sum())
    x = float(trades["exit_value"].sum())
    return {"sum_entry": round(e, 2), "sum_exit": round(x, 2),
            "cash_if_all_credited": round(initial - e + x, 2)}


def find_deferred(cands: pl.DataFrame, target: float, close_by_sym: dict[str, float]):
    """在候选行里找出 shares×close 子集和 == target 的最小集合（暴力，候选<=12）。"""
    rows = cands.to_dicts()
    if not rows:
        return None, []
    for k in range(1, len(rows) + 1):
        for combo in itertools.combinations(range(len(rows)), k):
            tot = sum(rows[i]["shares"] * close_by_sym.get(rows[i]["symbol"], 0.0)
                      for i in combo)
            if abs(tot - target) <= 0.05:
                return k, [rows[i] for i in combo]
    return None, []


def analyse_arm(name: str, path: Path, close_by_sym: dict[str, float],
                initial: float = 1_000_000.0) -> dict:
    trades = pl.read_parquet(path / "trades.parquet")
    equity = pl.read_parquet(path / "equity.parquet")
    last = equity.row(-1, named=True)
    first = equity.row(0, named=True)
    chk = json.loads((path / "result.json").read_text(encoding="utf-8"))
    stats = chk.get("stats", {})
    cfg_source = "effective_config.json"
    if (path / "effective_config.json").exists():
        ec = json.loads((path / "effective_config.json").read_text(encoding="utf-8"))
        resolved = (ec.get("resolved_matcher_config") or {})
        finalize = bool(resolved.get("finalize_open_at_end", False))
        costs_policy = resolved.get("execution_costs")
    else:
        # 早期臂（a0_*）没有 effective_config.json：退回静止读策略文件 META。
        cfg_source = "strategy META (no effective_config.json)"
        src = RESEARCH / "strategies" / "custom" / "s01b_a0.py"
        text = src.read_text(encoding="utf-8")
        begin = text.index("\"backtest_defaults\":") + len("\"backtest_defaults\":")
        depth = 0
        end = begin
        for i in range(begin, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        meta = ast.literal_eval(text[begin:end])
        finalize = bool(meta.get("finalize_open_at_end", False))
        costs_policy = meta.get("execution_costs")
        resolved = meta

    sum_pnl = round(float(trades["pnl_amount"].sum()), 2)
    eq_delta = round(float(last["value"]) - float(first["value"]), 2)
    market_value = round(float(last["value"]) - float(last["cash"]), 2)

    cands = trades.filter(
        (pl.col("exit_date") == last["date"]) & (pl.col("exit_reason") == "end")
    )
    k, deferred = (None, [])
    if not finalize and int(last["positions"]) > 0:
        k, deferred = find_deferred(cands, market_value, close_by_sym)

    out = {
        "arm": name,
        "config_source": cfg_source,
        "n_trades": trades.height,
        "finalize_open_at_end": finalize,
        "execution_costs_policy_present": costs_policy is not None,
        "equity_first_date": first["date"],
        "equity_last_date": last["date"],
        "equity_first_value": float(first["value"]),
        "equity_last_value": float(last["value"]),
        "equity_last_cash": float(last["cash"]),
        "equity_last_positions": int(last["positions"]),
        "market_value_last_row": market_value,
        "sum_pnl_amount": sum_pnl,
        "equity_delta": eq_delta,
        "gap_pnl_minus_delta": round(sum_pnl - eq_delta, 2),
        "reported_total_return": stats.get("total_return"),
        "reported_final_equity": stats.get("final_equity"),
        "deferred_found": k is not None,
        "deferred": [
            {
                "symbol": r["symbol"],
                "entry_date": r["entry_date"],
                "shares": r["shares"],
                "exit_reason": r["exit_reason"],
                "exit_value": r["exit_value"],
                "open_at_end": r["open_at_end"],
                "close_last": close_by_sym.get(r["symbol"]),
                "mark_value": round(r["shares"] * close_by_sym.get(r["symbol"], 0.0), 2),
            }
            for r in deferred
        ],
    }
    if deferred:
        pb = 0.0
        fee = 0.0
        for r in deferred:
            c = close_by_sym[r["symbol"]]
            x = float(r["exit_value"])
            gross = r["shares"] * c
            # 开盘价由 trades 反解：gross_open = 卖出费用 + exit_value 需开盘价；
            # 这里只用「价基差 = 盯市值 − 毛卖出额」，毛卖出额另行由 open 计算。
            pb += gross
            fee += 0.0
            r["mark_value"] = round(gross, 2)
        out["deferred_mark_total"] = round(pb, 2)
        out["deferred_exit_value_total"] = round(
            sum(float(r["exit_value"]) for r in deferred), 2)
    if not finalize:
        cf = closed_form_final_equity(trades, initial)
        out["cash_if_all_credited"] = cf["cash_if_all_credited"]
        out["final_cash_after_finalize"] = round(
            float(last["cash"]) + out.get("deferred_exit_value_total", 0.0), 2)
        out["final_cash_vs_closed_form"] = round(
            out["final_cash_after_finalize"] - cf["cash_if_all_credited"], 2)
    n_eq = equity.height
    if not finalize and deferred:
        corrected = out["final_cash_after_finalize"]
        r_corr = corrected / initial - 1
        out["corrected_total_return"] = round(r_corr, 6)
        out["corrected_annual_return"] = round((1 + r_corr) ** (252 / n_eq) - 1, 6)
        out["reported_annual_return"] = stats.get("annual_return")
        out["total_return_delta_pp"] = round(
            (out["reported_total_return"] - r_corr) * 100, 4)
    out["n_equity_rows"] = n_eq
    return out


def main() -> int:
    px = pl.concat([read_day(PREV_DATE, FOCUS), read_day(LAST_DATE, FOCUS)])
    px.write_csv(HERE / "price_20261030.csv")
    close_by_sym = {r["symbol"]: float(r["close"])
                    for r in px.filter(pl.col("date") == LAST_DATE).to_dicts()}
    open_by_sym = {r["symbol"]: float(r["open"])
                   for r in px.filter(pl.col("date") == LAST_DATE).to_dicts()}
    prev_close = {r["symbol"]: float(r["close"])
                  for r in px.filter(pl.col("date") == PREV_DATE).to_dicts()}

    # ---- ① 行情核对 ----
    prices = []
    for r in px.filter(pl.col("date") == LAST_DATE).to_dicts():
        s = r["symbol"]
        pc = prev_close.get(s)
        prices.append({
            "symbol": s, "date": LAST_DATE,
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "volume": int(r["volume"]),
            "prev_close": pc,
            "pct_open_vs_prev": round(float(r["open"]) / pc - 1, 6) if pc else None,
            "pct_close_vs_prev": round(float(r["close"]) / pc - 1, 6) if pc else None,
        })

    # ---- ② 逐臂核算 ----
    arms = {}
    for name, path in ARM_DIR.items():
        if not (path / "trades.parquet").exists():
            arms[name] = {"arm": name, "error": "trades.parquet missing"}
            continue
        arms[name] = analyse_arm(name, path, close_by_sym)

    # ---- 基线 688143 专项 ----
    base = arms["base_nodefaults_10bp"]
    bt = pl.read_parquet(FIVE_A / "base_nodefaults_10bp" / "trades.parquet")
    row = bt.filter(pl.col("symbol") == "688143.SH").to_dicts()[0]
    o = open_by_sym["688143.SH"]
    c = close_by_sym["688143.SH"]
    sh = float(row["shares"])
    fee = round(sh * o - float(row["exit_value"]), 2)
    focus = {
        "symbol": "688143.SH",
        "entry_date": row["entry_date"],
        "exit_date": row["exit_date"],
        "exit_reason": row["exit_reason"],
        "open_at_end": row["open_at_end"],
        "shares": sh,
        "exchange_open": o,
        "exchange_close": c,
        "trade_exit_price": float(row["exit_price"]),
        "exit_price_equals_open": abs(float(row["exit_price"]) - o) < 1e-6,
        "exit_value_recorded": float(row["exit_value"]),
        "gross_at_open": round(sh * o, 2),
        "sell_fee_implied": fee,
        "mark_at_close": round(sh * c, 2),
        "gap_total": round(sh * c - float(row["exit_value"]), 2),
        "gap_price_basis": round(sh * (c - o), 2),
        "gap_fee": fee,
        "gap_check": round(sh * (c - o) + fee, 2),
        "market_value_last_row": base["market_value_last_row"],
        "market_value_equals_mark": abs(base["market_value_last_row"] - sh * c) < 0.02,
        "equity_last_cash": base["equity_last_cash"],
        "final_cash_after_finalize": base["final_cash_after_finalize"],
    }
    # 开发经理给的 1,722.56 校验
    focus["dev_manager_1722_56"] = round(
        base["market_value_last_row"] - float(row["exit_value"]), 2)
    focus["dev_manager_delta_vs_gap"] = round(
        abs(focus["dev_manager_1722_56"]) - abs(base["gap_pnl_minus_delta"]), 2)
    focus["corrected_total_return"] = base.get("corrected_total_return")
    focus["corrected_annual_return"] = base.get("corrected_annual_return")
    focus["reported_annual_return"] = base.get("reported_annual_return")

    # ---- ③ 调用序列（上一轮 trace） ----
    trace_file = HERE / "trace_end_position.json"
    trace_seq = []
    if trace_file.exists():
        tr = json.loads(trace_file.read_text(encoding="utf-8"))
        for e in tr:
            if e.get("time_id") == 1778:
                trace_seq.append({
                    "fn": e.get("fn"),
                    "asset_id": e.get("asset_id"),
                    "position_id": e.get("position_id"),
                    "reason": e.get("reason"),
                    "return_value": e.get("value"),
                    "n_positions": e.get("n_positions"),
                })

    out = {
        "generated_from": str(FIVE_A),
        "prices": prices,
        "focus": focus,
        "arms": arms,
        "trace_20261030": trace_seq,
    }
    (HERE / "diag1_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- Markdown ----
    L = []
    L.append("# ⑤-c 诊断 1：期末权益 1,722.56 缺口的成因\n")
    L.append("## ① 行情核对（D:\\TSP\\data\\kline_daily）\n")
    L.append("| symbol | 开 | 高 | 低 | 收 | 前收 | 开/前收 | 收/前收 | 量 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in prices:
        L.append(f"| {p['symbol']} | {p['open']:.2f} | {p['high']:.2f} | {p['low']:.2f} "
                 f"| {p['close']:.2f} | {p['prev_close']:.2f} | {p['pct_open_vs_prev']*100:+.2f}% "
                 f"| {p['pct_close_vs_prev']*100:+.2f}% | {p['volume']:,} |")
    L.append("")
    L.append(f"688143.SH 2026-10-30：**开盘 {o:.2f} / 收盘 {c:.2f}**。"
             f"trades 记的 exit_price={focus['trade_exit_price']:.2f}"
             f"（等于开盘：{focus['exit_price_equals_open']}）；"
             f"末行权益的持仓市值 {focus['market_value_last_row']:.2f} = {sh:.0f}×{c:.2f}"
             f"（等于收盘盯市：{focus['market_value_equals_mark']}）。\n")
    L.append("## ② 1,722.56 的分解\n")
    L.append("| 项 | 值 |")
    L.append("|---|---:|")
    L.append(f"| 收盘盯市值 shares×close | {focus['mark_at_close']:.2f} |")
    L.append(f"| trades 记的 exit_value | {focus['exit_value_recorded']:.2f} |")
    L.append(f"| **合计缺口** | **{focus['gap_total']:.2f}** |")
    L.append(f"| 其中 价基差 shares×(close−open) | {focus['gap_price_basis']:.2f} |")
    L.append(f"| 其中 卖出费用 (shares×open − exit_value) | {focus['gap_fee']:.2f} |")
    L.append(f"| 分解校验（两项相加） | {focus['gap_check']:.2f} |")
    L.append(f"| Σpnl − 权益变动（独立口径） | {base['gap_pnl_minus_delta']:.2f} |")
    L.append(f"| 开发经理的 23,652.00 − 21,929.45 | {focus['dev_manager_1722_56']:.2f} |")
    L.append("")
    L.append(f"末现金 {base['equity_last_cash']:.2f} + 该笔 exit_value "
             f"{focus['exit_value_recorded']:.2f} = finalize 后现金 "
             f"{base['final_cash_after_finalize']:.2f}；闭式 "
             f"(1,000,000 − Σentry + Σexit) = {base['cash_if_all_credited']:.2f}，"
             f"差 {base['final_cash_vs_closed_form']:+.2f}（分位取整）。\n")
    L.append("## ③ 各臂同一恒等式\n")
    L.append("| 臂 | finalize | 成本策略 | 末行持仓 | 末行市值 | Σpnl | 权益变动 | gap | 延后卖出笔数 | gap 含义 |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for name, a in arms.items():
        if a.get("error"):
            L.append(f"| {name} | — | — | — | — | — | — | {a['error']} | — | — |")
            continue
        meaning = ("n/a（finalize 臂：pnl 记 0，gap 不是本缺陷）"
                   if a["finalize_open_at_end"] else "期末延后卖出")
        L.append(f"| {name} | {a['finalize_open_at_end']} | "
                 f"{a['execution_costs_policy_present']} | {a['equity_last_positions']} | "
                 f"{a['market_value_last_row']:.2f} | {a['sum_pnl_amount']:.2f} | "
                 f"{a['equity_delta']:.2f} | {a['gap_pnl_minus_delta']:.2f} | "
                 f"{len(a['deferred'])} | {meaning} |")
    L.append("")
    L.append("## ④ 2026-10-30 引擎调用序列（sys.settrace，只读）\n")
    L.append("| 函数 | asset | pos | reason | 返回 | 当时持仓数 |")
    L.append("|---|---|---:|---|---|---:|")
    for e in trace_seq:
        L.append(f"| {e['fn']} | {e['asset_id']} | {e['position_id']} | {e['reason']} "
                 f"| {e['return_value']} | {e['n_positions']} |")
    L.append("")
    (HERE / "diag1_table.md").write_text("\n".join(L), encoding="utf-8")

    print(json.dumps({"focus": focus,
                      "base_gap": base["gap_pnl_minus_delta"],
                      "arms": {k: (v.get("gap_pnl_minus_delta"),
                                   v.get("equity_last_positions"),
                                   v.get("finalize_open_at_end"))
                               for k, v in arms.items()}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
