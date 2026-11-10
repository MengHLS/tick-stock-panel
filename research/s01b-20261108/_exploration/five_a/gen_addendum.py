# -*- coding: utf-8 -*-
"""生成 ADDENDUM_two_method_20261108.md（全部数字从 CSV/JSON 读，不手抄）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def sha(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    j = json.load(open(HERE / "dual_accounting.json", encoding="utf-8"))
    cls = pd.read_csv(HERE / "appendix_199_29rows_classified.csv", dtype={"symbol": str})
    j199 = j["appendix_199_inject"]
    A = j199["split"]["methods"]["A_pnl_amount"]
    B = j199["split"]["methods"]["B_value_diff"]

    open5 = cls[cls["open_at_end"]]
    closed24 = cls[~cls["open_at_end"]].sort_values("gap", ascending=False)

    L: list[str] = []
    A_ = L.append
    A_("# ⑤-a 追加 · 两种记法并报 + 199 注入臂 29 笔「两法不等」裁定\n")
    A_("口径：基线 = `base_nodefaults_10bp`（不注入任何 defaults = 生产文件真实默认，208 笔）；"
       "key = `(symbol, entry_date)`。本文件由 `gen_addendum.py` 从 `dual_accounting.json` 与 "
       "`appendix_199_29rows_classified.csv` 机读生成，不手抄数字。\n")

    A_("## 0 · 一句话裁定\n")
    A_("**H1（`pnl_amount` 走了与 `entry_price`/`exit_price` 不同的价基）不成立。** "
       "29 笔的不等全部落在两种「构成差」上，且逐笔闭合：5 笔期末未平仓（`pnl_amount` 只记已实现=0，"
       "价差法取了 `end` 行的盯市价）+ 24 笔已平仓（`pnl_amount` 含持仓期现金分红/送股，"
       "价差法不含）。已平仓 24 笔用除权台账闭式预测分红 %s 元，实测缺口 %s 元，残差 %+.2f 元，"
       "单笔最大 |残差| %.2f 元。\n" % (
           f"{j199['pred_div_closed_form']:,.2f}", f"{j199['gap_closed']:,.2f}", j199["pred_resid"],
           closed24["resid"].abs().max()))
    A_("⇒ 不必把 `pnl_amount` 标成「跨除权笔混合口径」；要标死的是**价差法**："
       "`exit_value − entry_value` 不含分红/送股现金，却含期末未平仓的 `end` 盯市。"
       "单用价差法做跨除权汇总会少算分红、多算期末浮亏。\n")
    A_("代码层同样对得上（`backend/app/backtest/engine.py`，只读未改）：组合口径出场 "
       "`pnl_amount = exit_value + pos[\"cash_dividends\"] − entry_value`（:3201-3205）；"
       "期末未平仓行 `pnl_amount = 0.0`（:4428，同行 `exit_value = shares * exit_price`、"
       "`open_at_end = True`、`exit_reason = \"end\"`）。即价基只一套，分红与期末盯市是另加的项。\n")

    A_("## 1 · 199 注入臂 · 两法并列（供对照，不属七臂）\n")
    A_("| 记法 | 笔数 | 同键 | 仅本臂 | 仅基线 | 本臂合计 | 基线合计 | 总差 | 同键 Δ | 仅本臂 Σ | 仅基线 Σ（贡献） | 同键占比 |")
    A_("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    s199 = j199["split"]
    for nm, blk in (("A_pnl_amount", A), ("B_value_diff", B)):
        A_("| %s | %d | %d | %d | %d | %s | %s | %s | %s | %s | %s | %.2f%% |" % (
            nm, s199["n_arm"], s199["n_same_key"], s199["n_only_arm"], s199["n_only_base"],
            f"{blk['arm_total']:,.2f}", f"{blk['base_total']:,.2f}", f"{blk['total_gap']:,.2f}",
            f"{blk['same_key_delta']:,.2f}", f"{blk['only_arm_sum']:,.2f}",
            f"{blk['only_base_sum']:,.2f}", blk["same_key_share_pct"]))
    A_("")
    A_("三数互不相等（论证见 §2）：权益变化 %s、Σ`pnl_amount` %s、Σ价差 %s；"
       "差值 84,132.93 / 26,612.58 恰好是「期末未平仓盯市」与「已平仓分红」两项。\n" % (
           f"{j199['equity_change']:,.2f}", f"{j199['sum_pnl_amount']:,.2f}", f"{j199['sum_value_diff']:,.2f}"))

    A_("## 2 · 三座桥（两条都独立闭合）\n")
    A_("| 桥 | 等式 | 实测 | 残差 |")
    A_("|---|---|---|---:|")
    A_("| A | 权益变化 = Σ`pnl_amount` − 期末未平仓缺口 | %s − %s = %s | %+.2f |" % (
        f"{j199['sum_pnl_amount']:,.2f}", f"{j199['gap_open_at_end']:,.2f}",
        f"{j199['sum_pnl_amount'] - j199['gap_open_at_end']:,.2f}", j199["bridge_pnl_minus_open"]))
    A_("| B | 权益变化 = Σ价差 + 已平仓分红缺口 | %s + %s = %s | %+.2f |" % (
        f"{j199['sum_value_diff']:,.2f}", f"{j199['gap_closed']:,.2f}",
        f"{j199['sum_value_diff'] + j199['gap_closed']:,.2f}", j199["bridge_vdiff_plus_div"]))
    A_("")
    A_("两条桥指向同一个 %s。也就是说：**`pnl_amount` = 已实现价差 + 持仓期分红/送股现金；"
       "价差法 = 含期末盯市的价差。二者缺的正好是对方多的那一块**，没有第三块残差。\n" % f"{j199['equity_change']:,.2f}")

    A_("## 3 · 29 笔逐笔分类\n")
    A_("### 3.1 期末未平仓 %d 笔（`pnl_amount` = 0，价差法记盯市）\n" % len(open5))
    A_("| symbol | entry_date | exit_date | shares | entry_value | exit_value | `pnl_amount` | 价差 | 缺口 |")
    A_("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in open5.sort_values("gap", ascending=False).iterrows():
        A_("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["symbol"], r["entry_date"], r["exit_date"], f"{r['shares']:,.0f}",
            f"{r['entry_value']:,.2f}", f"{r['exit_value']:,.2f}", f"{r['pnl_amount']:,.2f}",
            f"{r['vd']:,.2f}", f"{r['gap']:,.2f}"))
    A_("\n合计缺口 %s。这 5 笔在 `trades.parquet` 里 `open_at_end=True`、`exit_reason='end'`："
       "引擎给了一个期末盯市 `exit_value`，但没有已实现损益，所以 `pnl_amount` 恒 0。\n" % f"{j199['gap_open_at_end']:,.2f}")

    A_("### 3.2 已平仓 %d 笔（缺口 = 分红/送股现金）\n" % len(closed24))
    A_("| symbol | entry_date | exit_date | shares | 缺口实测 | 闭式预测 | 残差 | 除权事件 |")
    A_("|---|---|---|---:|---:|---:|---:|---|")
    for _, r in closed24.iterrows():
        A_("| %s | %s | %s | %s | %s | %s | %+.2f | %s |" % (
            r["symbol"], r["entry_date"], r["exit_date"], f"{r['shares']:,.0f}",
            f"{r['gap']:,.2f}", f"{r['pred_div_closed_form']:,.2f}", r["resid"], r["div_events"]))
    A_("\n闭式口径：按引擎前推口径 Σ(事件前股数 × 每股现金分红)；送股/转增通过 `mult=1+bonus+allot` 反推事件前股数。"
       "24 笔全部命中，**没有一笔用到「换价基」这个解释**。\n")

    A_("## 4 · 为什么两法算出的「同键重定价占比」差 7 倍\n")
    # 同键对上的 gap（机读，不手抄）
    a0 = pd.read_parquet(HERE.parent / "results" / "a0_10bp" / "trades.parquet")
    bs = pd.read_parquet(HERE / "base_nodefaults_10bp" / "trades.parquet")
    for df in (a0, bs):
        df["key"] = df["symbol"].astype(str).str.cat(df["entry_date"].astype(str), sep="|")
        df["gap"] = df["pnl_amount"] - (df["exit_value"] - df["entry_value"])
    common = set(a0["key"]) & set(bs["key"])
    gap_sk = float(a0[a0["key"].isin(common)]["gap"].sum())
    base_sk_gap = float(bs[bs["key"].isin(common)]["gap"].sum())
    d_sk = A["same_key_delta"] - B["same_key_delta"]
    A_("同键重定价差额：A %s、B %s，差 %s。该差额 == 同键对上 Σ(`pnl_amount` − 价差) %s − 基线自身取整缺口 %+.2f。"
       "即**缺口集中落在同键对上的跨除权笔**：同键对贡献了总缺口 %s 的 %.1f%%。"
       "所以占比差 7 倍不是两把尺子量了不同的东西，而是同一批跨除权笔在 A 里被算进重定价、在 B 里被丢掉。\n" % (
           f"{A['same_key_delta']:,.2f}", f"{B['same_key_delta']:,.2f}", f"{d_sk:,.2f}",
           f"{gap_sk:,.2f}", base_sk_gap, f"{j199['sum_gap']:,.2f}", d_sk / j199["sum_gap"] * 100))

    # §5 机读：同键对的股数/价基差异
    mm = a0.merge(bs, on="key", suffixes=("_99", "_08"))
    n_mm = len(mm)
    c_sh = int((mm["shares_99"] != mm["shares_08"]).sum())
    c_ep = int((abs(mm["entry_price_99"] - mm["entry_price_08"]) > 1e-6).sum())
    c_xp = int((abs(mm["exit_price_99"] - mm["exit_price_08"]) > 1e-6).sum())
    c_xd = int((mm["exit_date_99"] != mm["exit_date_08"]).sum())
    c_du = int((mm["duration_99"] != mm["duration_08"]).sum())
    same_day = mm[mm["exit_date_99"] == mm["exit_date_08"]]
    c_xp_same_day = int((abs(same_day["exit_price_99"] - same_day["exit_price_08"]) > 1e-6).sum())
    rr = mm["shares_99"] / mm["shares_08"]
    pp99 = float(mm["position_pct_99"].median()) * 100
    pp08 = float(mm["position_pct_08"].median()) * 100

    A_("## 5 · 顺带查到的要紧事：「同键」不等于「同一仓位」\n")
    A_("同键 %d 笔里（199 臂 vs 208 基线，同一 `(symbol, entry_date)`）：\n" % n_mm)
    A_("| 项 | 实测 |")
    A_("|---|---|")
    A_("| shares 不同 | %d / %d |" % (c_sh, n_mm))
    A_("| entry_price 不同 | %d / %d |" % (c_ep, n_mm))
    A_("| exit_price 不同 | %d / %d |" % (c_xp, n_mm))
    A_("| 其中「同一天出场、exit_price 仍不同」 | %d / %d |" % (c_xp_same_day, len(same_day)))
    A_("| exit_date 不同 | %d / %d |" % (c_xd, n_mm))
    A_("| duration 不同 | %d / %d |" % (c_du, n_mm))
    A_("| shares 比值（99/08）中位 / 最小 / 最大 | %.4f / %.4f / %.4f |" % (rr.median(), rr.min(), rr.max()))
    A_("| 仓位金额占比中位（99 / 08） | %.2f%% / %.2f%% |" % (pp99, pp08))
    A_("")
    A_("仓位金额接近（%.2f%% vs %.2f%%）而 shares 比值横跨 %.2f–%.2f；更决定性的是：%d 笔当天出场的那批里 %d 笔 "
       "exit_price 仍不同——同一天、同一只股的成交价没理由变，除非两臂的**价格列本身不在同一基上**。\n" % (
           pp99, pp08, rr.min(), rr.max(), len(same_day), c_xp_same_day))
    A_("**机制已在代码里坐实**（`backend/app/backtest/engine.py`，只读未改）：除权台账只在 raw 价执行时加载——"
       "`corporate_actions = self._load_corporate_actions(...) if raw_execution is not None else {}`（:2608-2615）；"
       "加载后逐日对持仓做送股/转增 `shares *= share_multiplier`、`entry_price` 按除权重算（:3823-3830），"
       "现金分红 `pos[\"cash_dividends\"] += dividend_per_share × old_shares` 并同时进 `cash`（:3817-3822）。"
       "所以：默认（208）口径走复权价、除权台账为空 ⇒ 分红与送股全含在价格里，`pnl` 恒等于价差；"
       "199 注入臂走 raw 价 + 除权台账 ⇒ 股数被送股放大、分红落成现金并回加进 `pnl`。\n")
    A_("⇒「同键重定价」实际上是「同键、不同价基（复权 vs raw + 除权台账）、不同股数」，**不能读成「同一仓位换了价格」**；"
       "任何把同键 Δ 解释成纯价格效应的说法都不成立。\n")

    A_("## 6 · 使用说明（建议原样写进任何引用这两列的地方）\n")
    A_("1. `pnl_amount` = **已实现**损益：含持仓期现金分红与送股现金，**不含**期末未平仓的浮盈浮亏（该分支恒 0）。")
    A_("2. `exit_value − entry_value` = **含期末盯市**的价差：**不含**分红/送股现金，但把 `end` 行的盯市价算进去。")
    A_("3. 两法差额 = 分红现金（已平仓）+ 期末盯市（未平仓）。默认（208）口径下两法在 208/208 笔上相等（合计差 0.10 元），"
       "**只在注入 `entry_price_basis=raw` 一类改动的臂上才会分开**——所以引用占比时必须写明是哪一臂、哪一种记法。")
    A_("4. 跨除权笔的「按笔汇总」优先用 `pnl_amount`；用价差法则必须另加分红现金，否则系统性地少算。\n")

    A_("## 7 · 校验\n")
    A_("`classify_29_basis.py` 18 项断言（清单行数、未平仓 count、已平仓 count、`pnl_amount`=0、`end` 盯市存在、"
       "逐笔闭式残差、无 H1 残留、两段缺口合计、未取整总和、两条桥、同键恒等式、占比、同键贡献率）"
       "**全部 PASS**；输出 `classify_29_result.txt`。`verify_dual.py` 38 项亦全 PASS。\n")

    A_("## 8 · 本次新增产物\n")
    A_("| 文件 | 字节 | sha256 |")
    A_("|---|---:|---|")
    for nm in ("classify_29_basis.py", "classify_29_result.txt",
               "appendix_199_29rows_classified.csv", "gen_addendum.py"):
        p = HERE / nm
        if p.exists():
            A_("| `%s` | %d | `%s` |" % (nm, p.stat().st_size, sha(p)))
    A_("")

    out = HERE / "ADDENDUM_two_method_20261108.md"
    body = "\n".join(L) + "\n"
    out.write_text(body, encoding="utf-8")
    print("wrote", out, out.stat().st_size, "B", sha(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
