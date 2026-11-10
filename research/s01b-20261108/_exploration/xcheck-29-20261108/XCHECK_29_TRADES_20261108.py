# -*- coding: utf-8 -*-
"""S01b / ⑤-a 前置：199 注入臂「29 笔两记法不等」逐笔复核 + 三记法 A/B/C 复算。

只读 parquet，不写任何结果目录。
用法（仓库根）：
  ./backend/.venv/Scripts/python.exe research/s01b-20261108/xcheck-29-20261108/XCHECK_29_TRADES_20261108.py
"""
import os
import pandas as pd
import numpy as np

ROOT = "research/s01b-20261108"
RES = f"{ROOT}/crossdown-event-20261108/results"
ADJ = f"{ROOT}/data_root/adj_factor/all.parquet"
OUT = f"{ROOT}/xcheck-29-20261108"

pd.set_option("display.width", 260)
pd.set_option("display.max_rows", 200)


def load():
    A = pd.read_parquet(f"{RES}/a0_10bp/trades.parquet")   # 208 默认臂
    C = pd.read_parquet(f"{RES}/c0_10bp/trades.parquet")   # 199 注入臂
    for d in (A, C):
        d["spread"] = d.exit_value - d.entry_value
        d["gap"] = d.pnl_amount - d.spread
        d["gap_r"] = d.gap.round(2)
        d["e0"] = pd.to_datetime(d.entry_date).dt.strftime("%Y-%m-%d")
        d["e1"] = pd.to_datetime(d.exit_date).dt.strftime("%Y-%m-%d")
    eq = {k: pd.read_parquet(f"{RES}/{arm}/equity.parquet").value.astype(float)
          for k, arm in (("A208", "a0_10bp"), ("C199", "c0_10bp"))}
    adj = pd.read_parquet(ADJ)
    adj["td"] = pd.to_datetime(adj.trade_date).dt.strftime("%Y-%m-%d")
    return A, C, eq, adj


def blocks(A, C):
    A = A.copy(); C = C.copy()
    A["k"] = list(zip(A.symbol, A.e0)); C["k"] = list(zip(C.symbol, C.e0))
    C["pe"] = C.pnl_amount.where(~C.open_at_end, C.exit_value - C.entry_value)
    cm = set(A.k) & set(C.k)

    def f(av, cv):
        sa = av[A.k.isin(cm)].sum(); sc = cv[C.k.isin(cm)].sum()
        o1 = cv[~C.k.isin(cm)].sum(); o2 = av[~A.k.isin(cm)].sum()
        tot = sc - sa + o1 - o2
        return dict(same=round(sc - sa, 2), only199=round(o1, 2), only208=round(-o2, 2), total=round(tot, 2),
                    share_same=round((sc - sa) / tot * 100, 1))
    return len(cm), f(A.pnl_amount, C.pnl_amount), f(A.spread, C.spread), f(A.pnl_amount, C.pe)


def main():
    A, C, eq, adj = load()
    print("== 0. 规模 / 权益锚点")
    print(f"  208 臂笔数 {len(A)}  open_at_end {int(A.open_at_end.sum())}   "
          f"权益 {eq['A208'].iloc[0]:,.2f} -> {eq['A208'].iloc[-1]:,.2f}  "
          f"({(eq['A208'].iloc[-1]/eq['A208'].iloc[0]-1)*100:+.2f}%)")
    print(f"  199 臂笔数 {len(C)}  open_at_end {int(C.open_at_end.sum())}   "
          f"权益 {eq['C199'].iloc[0]:,.2f} -> {eq['C199'].iloc[-1]:,.2f}  "
          f"({(eq['C199'].iloc[-1]/eq['C199'].iloc[0]-1)*100:+.2f}%)")
    eqd = float(eq["C199"].iloc[-1] - eq["A208"].iloc[-1])
    print(f"  权益差 {eqd:,.2f}")

    print("\n== 1. 两记法差额的分布（判断阈值是否干净）")
    for n, d in (("208", A), ("199", C)):
        z = int((d.gap_r.abs() < 1e-9).sum())
        s = d[(d.gap_r.abs() > 1e-9) & (d.gap_r.abs() < 0.02)]
        big = d[d.gap_r.abs() >= 0.02]
        print(f"  {n}: 恰等 {z} 笔 | |差|=0.01 {len(s)} 笔（+{(s.gap_r>0).sum()} / -{(s.gap_r<0).sum()}，净 {s.gap_r.sum():+.2f}） "
              f"| |差|>=0.02 {len(big)} 笔（最小 {big.gap_r.abs().min() if len(big) else float('nan'):,.2f}，"
              f"最大 {big.gap_r.abs().max() if len(big) else float('nan'):,.2f}）")

    print("\n== 2. 29 笔分块")
    big = C[C.gap_r.abs() >= 0.02].sort_values("e0")
    print(f"  笔数 {len(big)}  合计 {big.gap.sum():,.2f}")
    print(f"  期末未平仓 {int(big.open_at_end.sum())} 笔  合计 {big[big.open_at_end].gap.sum():,.2f}")
    print(f"  已平仓 {(~big.open_at_end).sum()} 笔  合计 {big[~big.open_at_end].gap.sum():,.2f}")
    print(big[["symbol", "e0", "e1", "shares", "entry_price", "exit_price",
               "entry_value", "exit_value", "pnl_amount", "open_at_end", "gap_r"]].to_string(index=False))

    print("\n== 3. 24 笔已平仓 vs 除权台账：gap ?= shares*dividend/(1+bonus)")
    closed = big[~big.open_at_end].copy()
    rows = []
    for _, t in closed.iterrows():
        ev = adj[(adj.symbol == t.symbol) & (adj.td > t.e0) & (adj.td <= t.e1)]
        pred = float((t.shares * ev.dividend / (1 + ev.bonus)).sum())
        rows.append(dict(symbol=t.symbol, e0=t.e0, e1=t.e1, shares=int(t.shares),
                         n_event=len(ev), dates=",".join(ev.td),
                         div=",".join(f"{x:g}" for x in ev.dividend),
                         bonus=",".join(f"{x:g}" for x in ev.bonus),
                         gap=round(t.gap, 2), pred=round(pred, 2),
                         resid=round(t.gap - pred, 2),
                         gross=round(float((t.shares * ev.dividend).sum()), 2)))
    r = pd.DataFrame(rows).sort_values("gap", ascending=False)
    print(r.to_string(index=False))
    print(f"  事件命中 {int((r.n_event == 1).sum())}/{len(r)} 笔恰 1 个窗口内事件；"
          f"最大 |残差| {r.resid.abs().max():.2f} 元；Σgap {r.gap.sum():,.2f} / Σpred {r.pred.sum():,.2f}；"
          f"未除权前口径 Σ {r.gross.sum():,.2f}")

    print("\n== 4. 三记法 A/B/C")
    n_same, A_blocks, B_blocks, C_blocks = blocks(A, C)
    print(f"  同键（symbol+entry_date）{n_same} 笔")
    for name, v in (("A pnl_amount", A_blocks), ("B 价差法", B_blocks), ("C 权益对齐", C_blocks)):
        print(f"  {name:14s} 同键 {v['same']:>12,.2f} ({v['share_same']:>5.1f}%) "
              f"仅199 {v['only199']:>12,.2f} 仅208 {v['only208']:>12,.2f} 合计 {v['total']:>12,.2f}")
    print(f"  A-C {A_blocks['total']-C_blocks['total']:,.2f}  C-B {C_blocks['total']-B_blocks['total']:,.2f}  "
          f"C-权益 {C_blocks['total']-eqd:,.2f}")

    print("\n== 5. 闭合检查")
    print(f"  199: pnl {C.pnl_amount.sum():,.2f} - 浮亏 {-C[C.open_at_end].spread.sum():,.2f} = "
          f"{C.pnl_amount.sum()+C[C.open_at_end].spread.sum():,.2f} vs 权益 Δ {eq['C199'].iloc[-1]-eq['C199'].iloc[0]:,.2f} "
          f"(差 {C.pnl_amount.sum()+C[C.open_at_end].spread.sum()-(eq['C199'].iloc[-1]-eq['C199'].iloc[0]):,.2f})")
    print(f"  208: pnl {A.pnl_amount.sum():,.2f} vs 权益 Δ {eq['A208'].iloc[-1]-eq['A208'].iloc[0]:,.2f} "
          f"(差 {A.pnl_amount.sum()-(eq['A208'].iloc[-1]-eq['A208'].iloc[0]):,.2f})")

    os.makedirs(OUT, exist_ok=True)
    big.to_csv(f"{OUT}/trades29.csv", index=False, encoding="utf-8-sig")
    r.to_csv(f"{OUT}/dividends24_recon.csv", index=False, encoding="utf-8-sig")
    C[(C.gap_r.abs() > 1e-9) & (C.gap_r.abs() < 0.02)].to_csv(
        f"{OUT}/rounding_artifacts_199.csv", index=False, encoding="utf-8-sig")
    print(f"\n  落盘：{OUT}/trades29.csv, dividends24_recon.csv, rounding_artifacts_199.csv")


if __name__ == "__main__":
    main()
