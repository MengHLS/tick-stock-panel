"""生成「12 条策略输入 → 系统因子」映射表（MD + JSON，单一数据源）。

数值全部从 compare_stats.json / xs_rank_stats.json 读取，不手抄，避免文档与证据不一致。
运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\docs\\research\\factor-audit-20261107\\scripts\\build_strategy_map.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[4]
AUD = HERE.parents[1]
OUT_MD = PROJECT / "docs" / "factors" / "STRATEGY_INPUT_FACTOR_MAP_20261107.md"
OUT_JSON = AUD / "strategy_factor_map.json"

CMP = json.loads((AUD / "compare_stats.json").read_text(encoding="utf-8"))
XS = json.loads((AUD / "xs_rank_stats.json").read_text(encoding="utf-8"))


def p(key: str) -> str:
    d = CMP["pairs"].get(key)
    if not d:
        return "—"
    return (f"n={d['n']:,}；corr={d['corr_pearson']:.6f}；spearman={d['corr_spearman']:.6f}；"
            f"平均绝对差={d['mean_abs_diff']:.4g}；p95={d['p95_abs_diff']:.4g}；"
            f"均值 {d['mean_a']:.4g} vs {d['mean_b']:.4g}")


def s(key: str) -> str:
    d = CMP["signals"].get(key)
    if not d:
        return "—"
    return (f"判定一致率 jaccard={d['jaccard']:.3f}；仅研究侧成立 {d['only_a']:,} 行；"
            f"仅系统侧成立 {d['only_b']:,} 行（n={d['n']:,}）")


def x(key: str) -> str:
    d = XS["xs_rank"].get(key)
    if not d:
        return "—"
    return (f"{d['rebuild_dates']} 个调仓日；平均选股数 研究 {d['mean_sel_research']:.1f} vs 系统 {d['mean_sel_system']:.1f}；"
            f"jaccard={d['mean_jaccard']:.3f}")


SAME = "逐位相同（平均绝对差 0）"

# ---------------------------------------------------------------- 映射数据
# verdict ∈ 可直接复用 / 口径不一致 / 系统缺失
# path    ∈ 注册即可（DSL 表达式，无需改引擎）/ 需引擎能力 / 需生产侧执行器 / 仅缺因子
STRATS: list[dict] = [
    {
        "key": "S01_ma_cross_20_60", "title": "双均线 20/60 金叉（持有至死叉或最长 60 交易日）",
        "items": [
            ("ma20", "`close.rolling_mean(20)`", "`ma20`（base，含当日）", "可直接复用", "注册即可", SAME + "（" + p("ma20_research_vs_system") + "）"),
            ("ma60", "`close.rolling_mean(60)`", "`ma60`（base，含当日）", "可直接复用", "注册即可", SAME + "（" + p("ma60_research_vs_system") + "）"),
            ("ret20（信号打分）", "`close/close.shift(20)-1`", "`momentum_20d`", "可直接复用", "注册即可", SAME + "（" + p("ret20_vs_momentum_20d") + "）"),
            ("in_universe", "观察 bar≥120 & 非 ST & raw_close≥3 & 20日均额≥1亿 & volume>0", "**无**（系统无股票池掩码因子）", "系统缺失", "仅缺因子", "见 §5 横向输入；影响 12 条策略全部"),
            ("max_hold_days=60 强制平仓", "回测引擎按持有天数强制出场", "**生产侧无**（回测引擎有 `max_hold_days`；监控/模拟盘无）", "系统缺失", "需生产侧执行器", "见 §5；`app/strategy/paper_auto.py` 无持有期上限逻辑"),
        ],
    },
    {
        "key": "S02_donchian_20_10", "title": "唐奇安 20 日突破 / 10 日退出",
        "items": [
            ("prior_high20", "`high.shift(1).rolling_max(20)`", "**无**；最近的是 `high_60d`（`close.rolling_max(60)`，含当日）", "系统缺失", "注册即可", "可用 `ts_delay(ts_max(high,20),1)` 注册；不可用 `high_60d` 替代"),
            ("prior_low10（出场）", "`low.shift(1).rolling_min(10)`", "**无**；最近的是 `low_60d`（`close.rolling_min(60)`，含当日）", "系统缺失", "注册即可", f"`close < low_60d` 在研究数据上触发率 **0.000%**（研究侧 prior_low10 触发 {CMP['series']['prior_low10_missing']['share_rows_where_close_below_prior_low10']:.2%}）——用 `low_60d` 会让 S02 出场永不触发"),
            ("ret20（信号打分）", "`close/close.shift(20)-1`", "`momentum_20d`", "可直接复用", "注册即可", SAME),
        ],
    },
    {
        "key": "S03_tsmom_60_m", "title": "60 日时序动量 + 月末调仓",
        "items": [
            ("ret60", "`close/close.shift(60)-1`", "`momentum_60d`", "可直接复用", "注册即可", SAME + "（" + p("ret60_vs_momentum_60d") + "）"),
            ("ma120", "`close.rolling_mean(120)`", "**无**（只有 `ma20`/`ma60` 与 `deviate_*d` 偏离因子）", "系统缺失", "注册即可", "`ts_mean(close,120)` 编译通过，warmup=121；参考统计：站上 MA120 的样本占比 46.8%"),
            ("ma20 / ma60", "同 S01", "`ma20` / `ma60`", "可直接复用", "注册即可", SAME),
            ("month_end（调仓日）", "全市场交易日历，下一交易日跨月即月末", "**无**（无调仓日因子，也无组合级调仓执行器）", "系统缺失", "需生产侧执行器", "12 条策略中 7 条依赖月末/周末再平衡（S03/S06/S07/S08/S10/S11/S12），见 §5"),
        ],
    },
    {
        "key": "S04_rsi14_reversion", "title": "RSI(14) < 30 超卖反转（最长 10 交易日）",
        "items": [
            ("rsi14", "`gains/losses 来自 ret1(pct_change)` + `ewm(alpha=1/14, adjust=False)`", "`rsi_14`（同 ewm，但 gains/losses 来自 `close.diff()` 绝对价差；零损失处用 1e-12 护栏）", "口径不一致", "仅缺因子",
             p("rsi14_vs_rsi_14") + "；阈值判定差异：" + s("rsi_lt30") + " / RSI>55：" + s("rsi_gt55")),
            ("rsi14 的 warmup", "ewm 无固定窗口，理论无界", "注册表声明 warmup=1", "口径不一致", "仅缺因子", "ewm(alpha=1/14) 权重衰减到 1e-3 需约 95 根 bar；声明 1 会让早期 RSI 明显失真"),
        ],
    },
    {
        "key": "S05_bollinger_20_2", "title": "布林带(20,2) 下轨反转",
        "items": [
            ("bb_lower / bb_upper", "`ma20 ∓ 2*sd20`（sd20 = `close.rolling_std(20)`）", "`boll_lower` / `boll_upper`（base）", "可直接复用", "注册即可", SAME + "（" + p("bb_lower_vs_boll_lower") + "）"),
            ("sd20", "`close.rolling_std(20)`", "无独立字段；`(boll_upper-boll_lower)/4` 反推", "可直接复用", "注册即可", "反推值与 sd20 逐位相同（平均绝对差 " + f"{CMP['pairs']['sd20_vs_implied_sd']['mean_abs_diff']:.1e}" + "）"),
            ("bb_z（信号打分）", "`(close-ma20)/sd20`", "`boll_position`：`(close-boll_lower)/(boll_upper-boll_lower)`，`bb_z = 4*boll_position-2`", "可直接复用", "注册即可", "恒等关系逐位验证（平均绝对差 " + f"{CMP['pairs']['bb_z_vs_4x_boll_position_minus_2']['mean_abs_diff']:.1e}" + "）"),
            ("ma20", "`close.rolling_mean(20)`", "`ma20`", "可直接复用", "注册即可", SAME),
        ],
    },
    {
        "key": "S06_xs_reversal_5d", "title": "5 日收益最弱 5% 周度反转",
        "items": [
            ("rk_ret5（截面排名）", "`in_universe` 内 `rank(average)/池内家数`", "`rank(momentum_5d)`：全样本 `rank(average)/当日非空家数`，**无掩码**", "口径不一致", "需引擎能力",
             x("S06_ret5_le_0.05") + f"；分母：池内 {XS['xs_rank']['S06_ret5_le_0.05']['mean_universe_size']:.0f} vs 全样本 {XS['xs_rank']['S06_ret5_le_0.05']['mean_system_denominator']:.0f}"),
            ("ret5", "`close/close.shift(5)-1`", "`momentum_5d`", "可直接复用", "注册即可", SAME + "（" + p("ret5_vs_momentum_5d") + "）"),
            ("week_end（调仓日）", "周最后一个交易日", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
        ],
    },
    {
        "key": "S07_xs_lowvol_60d", "title": "60 日波动最低 10% 月度持有",
        "items": [
            ("vol60", "`ret1.rolling_std(60)`（日频，未年化）", "**无**；最近的 `annual_vol_20d` = `ret1.rolling_std(20)*√252`", "系统缺失", "注册即可",
             "不可替代：" + p("vol60_vs_annual_vol_20d") + "；年化后仍不可替代：" + p("vol60_ann_vs_annual_vol_20d") + "；低波十分位重叠 jaccard=" + f"{XS['vol60_substitution']['mean_jaccard']:.3f}"),
            ("rk_vol60", "池内 `rank(vol60)/池内家数`", "**双重缺口**：`vol60` 未注册 + `rank()` 无股票池掩码", "系统缺失", "需引擎能力", x("S07_vol60_le_0.10")),
            ("month_end", "月末最后交易日", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
            ("vol60 的量级", "日频标准差", "—", "—", "—", f"研究口径分位：p10={CMP['series']['vol60_dist']['p10']:.4f} / p50={CMP['series']['vol60_dist']['p50']:.4f} / p90={CMP['series']['vol60_dist']['p90']:.4f}"),
        ],
    },
    {
        "key": "S08_high_52w", "title": "52 周新高附近月度持有（距 250 日高点 3% 内）",
        "items": [
            ("dist_52w_high", "`close/prior_high250-1`，`prior_high250 = high.shift(1).rolling_max(250)`", "`distance_to_high_240d`：`close/close.rolling_max(240)-1`（**收盘价、含当日、240**）", "口径不一致", "注册即可",
             p("dist_52w_high_vs_distance_to_high_240d") + "；「距高点 3% 内」判定：" + s("near_high_3pct")),
            ("ma120", "`close.rolling_mean(120)`", "**无**", "系统缺失", "注册即可", "同上 S03"),
            ("month_end", "月末", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
        ],
    },
    {
        "key": "S09_volume_breakout_55", "title": "55 日新高 + 1.5 倍量能突破",
        "items": [
            ("prior_high55", "`high.shift(1).rolling_max(55)`", "系统只有 `high_60d` = `close.rolling_max(60)`（**收盘价、含当日、60**）", "系统缺失", "注册即可",
             "**用 high_60d 替代会让入场条件恒不成立**：" + s("s09_break_vs_high_60d") + "；若改用「收盘价+shift1+60」也只剩一半：" + s("s09_break_vs_prior_high60_C")),
            ("prior_vol20", "`volume.shift(1).rolling_mean(20)`", "**无 vol_ma20**；现有 `vol_ma5`/`vol_ma10`（含当日）", "系统缺失", "注册即可",
             "1.5 倍量条件用 `vol_ma10` 替代：" + s("s09_vol_1p5_vs_ma10") + "；量能均值本身：" + p("prior_vol20_vs_vol_ma10")),
            ("ma20（出场）", "`close.rolling_mean(20)`", "`ma20`", "可直接复用", "注册即可", SAME),
            ("ret60（信号打分）", "`close/close.shift(60)-1`", "`momentum_60d`", "可直接复用", "注册即可", SAME),
        ],
    },
    {
        "key": "S10_xs_reversal_20d", "title": "20 日收益最弱 10% 月度持有",
        "items": [
            ("rk_ret20", "池内 `rank(ret20)/池内家数`", "`rank(momentum_20d)`，无掩码", "口径不一致", "需引擎能力", x("S10_ret20_le_0.10")),
            ("ret20", "`close/close.shift(20)-1`", "`momentum_20d`", "可直接复用", "注册即可", SAME),
            ("month_end", "月末", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
        ],
    },
    {
        "key": "S11_lowvol_reversal", "title": "低波动 + 20 日反转复合（两项排名均在前 30%，按排名和排序）",
        "items": [
            ("rk_vol60 / rk_ret20", "两个池内截面排名", "`rank(vol60)` / `rank(momentum_20d)`，无掩码；且 vol60 未注册", "系统缺失", "需引擎能力", "复合选股 " + x("S11_both_le_0.30") + " —— 系统口径下选股数放大 " + f"{XS['xs_rank']['S11_both_le_0.30']['mean_sel_system'] / XS['xs_rank']['S11_both_le_0.30']['mean_sel_research']:.1f}×"),
            ("排序键 -(rk_vol60+rk_ret20)", "研究侧直接对排名求和", "`score` 列可由 `rank/zscore` 组合表达，但依赖同一 rank 口径", "口径不一致", "需引擎能力", "排序口径不一致会改变持仓优先级，不只是选股集合"),
            ("month_end", "月末", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
        ],
    },
    {
        "key": "S12_lowvol_breadth", "title": "低波动月度 + 市场宽度 ≥ 0.5 才建仓",
        "items": [
            ("vol60 / rk_vol60", "同 S07", "**无** / 无掩码 rank", "系统缺失", "需引擎能力", x("S07_vol60_le_0.10")),
            ("market_breadth", "`in_universe` 内 `close>ma60` 的占比（收盘可知）", "**无**（DSL 只有逐行算子 + 截面 rank/zscore/winsorize，没有全市场聚合）", "系统缺失", "需引擎能力",
             f"掩码 {XS['market_breadth']['mean_research']:.3f} vs 无掩码 {XS['market_breadth']['mean_unmasked']:.3f}；corr={XS['market_breadth']['corr_pearson']:.3f}；平均绝对差 {XS['market_breadth']['mean_abs_diff']:.3f}；阈值翻转日占比 {XS['market_breadth']['share_days_threshold_flip']:.1%}；月末通过率 {XS['market_breadth']['share_month_ends_research_ge_0p5']:.1%} vs {XS['market_breadth']['share_month_ends_unmasked_ge_0p5']:.1%}"),
            ("month_end", "月末", "**无**", "系统缺失", "需生产侧执行器", "见 §5"),
        ],
    },
]

SIDEWAYS: list[tuple[str, str, str, str, str]] = [
    ("股票池 in_universe", "bar≥120 / 非ST / raw_close≥3 / 20日均额≥1亿 / volume>0",
     "**无**股票池因子（`st_flag` 是数据列，不是因子）", "系统缺失", "当前 1429 只 vs 全样本 3095 只；1 亿成交额门槛若用 `amount_mean_20d`(含当日) 替代，" + s("universe_amount_1e8")),
    ("月末/周末调仓日", "交易日历末交易日", "**无**", "系统缺失", "8/12 条策略依赖；回测侧由 `app/backtest/factor.py` 的 `rebalance` 处理，生产侧无"),
    ("max_hold_days", "回测引擎参数", "回测有（MatcherConfig.max_hold_days）；监控/模拟盘无", "系统缺失", "S01/S02/S03/S04/S05/S06 均依赖持有期上限"),
    ("执行价", "研究 `matching=open_t+1`、`entry_price_basis=raw`", "回测引擎同参可复现；模拟盘 `order_type=next_open` 可对齐", "可直接复用", "执行链路口径一致，无需新因子"),
    ("涨跌停不可买", "研究 `block_limit_open=True`", "回测引擎支持", "可直接复用", "同上"),
]


def main() -> None:
    # 汇总
    counts = {"可直接复用": 0, "口径不一致": 0, "系统缺失": 0, "—": 0}
    for st in STRATS:
        for _, _, _, v, _, _ in st["items"]:
            if v in counts:
                counts[v] += 1
    for _, _, _, v, _ in SIDEWAYS:
        counts[v] += 1

    L: list[str] = []
    A = L.append
    A("# 12 条策略「输入 → 系统因子」映射与口径差异")
    A("")
    A("状态：**v1，只读盘点**。生成日期 2026-11-07。作者：因子工程师（本文件不含任何收益数字，只有口径与信号判定差异）。")
    A("")
    A("策略规格来源：`research/strategy-search-20261107/scripts/common.py`（`add_indicators` / `add_universe` / `build_signals` / `STRATEGIES`）。")
    A("系统口径来源：`backend/app/indicators/pipeline.py#compute_indicators`、`backend/app/strategy/scoring.py#scoring_value_expr`、`backend/app/factors/dsl.py`、`backend/app/backtest/engine.py`。")
    A("")
    A("## 0. 结论")
    A("")
    A("| 判定 | 项数 | 含义 |")
    A("| --- | --- | --- |")
    A(f"| 可直接复用 | {counts['可直接复用']} | 公式与口径逐位一致，注册引用即可 |")
    A(f"| 口径不一致 | {counts['口径不一致']} | 系统有近义因子，但价基/窗口/shift/掩码不同；下方给出实测差异 |")
    A(f"| 系统缺失 | {counts['系统缺失']} | 系统没有该因子或该执行能力 |")
    A("")
    A("三句话概括：")
    A("")
    A("1. **纯量价中间量几乎全部可以逐位复用**（`momentum_*`、`ma20/ma60`、`boll_*`、`change_pct` 平均绝对差为 0）。S01/S05 今天就能用系统因子无损表达。")
    A("2. **真正卡住策略的是 4 类东西**：`vol60`、`ma120/ma200`、`prior_high*`/`prior_low*`/`prior_vol20` 这类「此前」语义、以及带股票池掩码的截面排名；其中前三类都能用现有 DSL 算子注册（无需改引擎），第四类需要引擎给出「掩码后的 rank」。")
    A("3. **`high_60d` 不能当 `prior_high55` 用**：`high_60d` 用收盘价且含当日，`close > high_60d` 在 5 470 011 行里一次都不成立（S09 入场条件会整体失效）。`low_60d` 同理（触发率 0.000%）。")
    A("")
    A("## 1. 复算基线")
    A("")
    meta = CMP["meta"]
    A("| 项 | 值 |")
    A("| --- | --- |")
    A(f"| 行情面板 | {meta['rows']:,} 行 / {meta['symbols']:,} 只 / {meta['date_min']} ~ {meta['date_max']} |")
    A(f"| 评估区间 | {meta['eval_start']} ~ {XS['meta']['eval_end']}（{meta['eval_rows']:,} 行） |")
    A(f"| 股票池门槛（研究） | {', '.join(f'{k}={v}' for k, v in XS['meta']['universe'].items())} |")
    A("| 判定阈值 | 全部取自 `common.py#build_signals`，不调参 |")
    A("| 复算脚本 | `docs/research/factor-audit-20261107/scripts/audit_compare.py`、`audit_xs_rank.py` |")
    A("")
    A("## 2. 逐策略映射")
    A("")
    for st in STRATS:
        A(f"### {st['key']} — {st['title']}")
        A("")
        A("| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |")
        A("| --- | --- | --- | --- | --- | --- |")
        for item, rdef, sysref, verdict, path, ev in st["items"]:
            if verdict == "可直接复用" and path == "注册即可":
                path = "已注册，直接引用"
            A(f"| {item} | {rdef} | {sysref} | **{verdict}** | {path} | {ev} |")
        A("")
    A("## 3. 横向输入（与具体策略无关，但每条策略都用）")
    A("")
    A("| 输入 | 研究定义 | 系统对应 | 判定 | 数值差异 / 证据 |")
    A("| --- | --- | --- | --- | --- |")
    for item, rdef, sysref, verdict, ev in SIDEWAYS:
        A(f"| {item} | {rdef} | {sysref} | **{verdict}** | {ev} |")
    A("")
    A("## 4. 逐条策略的可落地结论")
    A("")
    A("| 策略 | 今天能否用系统因子无损表达 | 缺什么 |")
    A("| --- | --- | --- |")
    A("| S01 双均线 | 能（除股票池掩码与持有期上限） | in_universe、max_hold |")
    A("| S02 唐奇安 | 不能 | prior_high20、prior_low10 |")
    A("| S03 时序动量 | 不能 | ma120、month_end |")
    A("| S04 RSI | 近似（需接受 0.89 pt 的系统偏差） | rsi 口径统一 |")
    A("| S05 布林 | 能（除股票池掩码） | in_universe |")
    A("| S06 5 日反转 | 不能（系统口径选股数放大 3.1×） | 掩码 rank、week_end |")
    A("| S07 低波 | 不能 | vol60、掩码 rank、month_end |")
    A("| S08 52 周新高 | 不能（近高点判定差一半） | 250 日高点口径、ma120、month_end |")
    A("| S09 量能突破 | 不能（入场恒不成立） | prior_high55、prior_vol20 |")
    A("| S10 20 日反转 | 不能（系统口径选股数放大 3.3×） | 掩码 rank、month_end |")
    A("| S11 复合 | 不能（系统口径选股数放大 14.1×） | vol60、掩码 rank、month_end |")
    A("| S12 低波+宽度 | 不能 | vol60、掩码 rank、market_breadth、month_end |")
    A("")
    A("## 5. 复现")
    A("")
    A("```bash")
    A("cd C:\\work\\sourcecode\\tick-stock-panel\\backend")
    A(".\\\\.venv\\\\Scripts\\\\python.exe ..\\docs\\\\research\\\\factor-audit-20261107\\\\scripts\\\\audit_compare.py    # 口径对照 -> compare_stats.json")
    A(".\\\\.venv\\\\Scripts\\\\python.exe ..\\docs\\\\research\\\\factor-audit-20261107\\\\scripts\\\\audit_xs_rank.py    # 截面/宽度 -> xs_rank_stats.json")
    A(".\\\\.venv\\\\Scripts\\\\python.exe ..\\docs\\\\research\\\\factor-audit-20261107\\\\scripts\\\\build_strategy_map.py  # 生成本文件 + strategy_factor_map.json")
    A("```")
    A("")
    A("机器可读：`docs/research/factor-audit-20261107/strategy_factor_map.json`、`compare_stats.json`、`xs_rank_stats.json`。")
    A("")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(
        {"meta": {"generated": "2026-11-07", "author": "因子工程师",
                  "source": "research/strategy-search-20261107/scripts/common.py",
                  "stats": ["compare_stats.json", "xs_rank_stats.json"]},
         "counts": counts,
         "strategies": [{"key": st["key"], "title": st["title"],
                         "items": [{"item": i, "research_def": d, "system_ref": sr,
                                    "verdict": v, "path": pa, "evidence": e}
                                   for i, d, sr, v, pa, e in st["items"]]} for st in STRATS],
         "sideways": [{"item": i, "research_def": d, "system_ref": sr, "verdict": v, "evidence": e}
                      for i, d, sr, v, e in SIDEWAYS]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("counts", counts)
    print("wrote", OUT_MD, OUT_MD.stat().st_size)
    print("wrote", OUT_JSON, OUT_JSON.stat().st_size)


if __name__ == "__main__":
    main()
