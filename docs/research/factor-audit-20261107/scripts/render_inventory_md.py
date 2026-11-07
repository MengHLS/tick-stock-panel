"""把 factors_inventory.csv 渲染成 docs/factors/ 下的可读清单（只读输入，只写新文件）。

运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\docs\\research\\factor-audit-20261107\\scripts\\render_inventory_md.py
"""
from __future__ import annotations

import csv
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[4]
SRC = HERE.parents[1] / "factors_inventory.csv"
OUT_DIR = PROJECT / "docs" / "factors"
OUT_MD = OUT_DIR / "FACTOR_REGISTRY_CORE_93_20261107.md"
OUT_CSV = OUT_DIR / "evidence" / "factors_inventory_core93_20261107.csv"

ORDER = [
    "动量", "趋势", "均线偏离", "波动率", "价格位置", "超买超卖", "量价", "流动性",
    "规模", "财务", "截面联动", "收益形态", "涨停基因", "首板事件链",
]


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def main() -> None:
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "evidence").mkdir(parents=True, exist_ok=True)
    OUT_CSV.write_bytes(SRC.read_bytes())

    by_group: dict[str, list[dict]] = OrderedDict()
    for g in ORDER:
        by_group[g] = [r for r in rows if r["group"] == g]
    for r in rows:
        if r["group"] not in by_group:
            by_group.setdefault(r["group"], []).append(r)

    kind = Counter(r["kind"] for r in rows)
    def _num(x):
        try:
            return int(float(x))
        except Exception:
            return None
    under = [r for r in rows if (lambda a, b: a is not None and b is not None and a < b)(
        _num(r["warmup_bars_declared"]), _num(r["warmup_bars_derived"]))]
    over = [r for r in rows if (lambda a, b: a is not None and b is not None and a > b)(
        _num(r["warmup_bars_declared"]), _num(r["warmup_bars_derived"]))]
    mism = [r for r in under]
    pit = [r for r in rows if r["is_financial_pit"] == "True"]
    pit_shares = [r for r in rows if "历史时点流通股本" in r["price_basis"]]
    mod = Counter(r["computed_in"].split("#")[0] for r in rows)

    lines: list[str] = []
    A = lines.append
    A("# 系统核心因子台账（93 个）")
    A("")
    A("状态：**只读盘点，v1**。生成日期 2026-11-07。作者：因子工程师。")
    A("本文件是台账，不是规格变更单；任何口径修订见 `docs/factors/FACTOR_GAP_SPEC_20261107.md`。")
    A("")
    A("## 0. 这份清单覆盖什么、不覆盖什么")
    A("")
    A("| 项 | 值 | 依据 |")
    A("| --- | --- | --- |")
    A(f"| 运行中注册表总数 | **178**（base 117 / virtual 61，15 组） | `app.factors.registry.all_factors()` 实测 |")
    A(f"| 本清单覆盖 | **{len(rows)}** = 178 − 85 个 `ext_*` 扩展数据因子 | 见 §5 |")
    A(f"| 其中 base / virtual | {kind.get('base',0)} / {kind.get('virtual',0)} | `kind` 字段 |")
    A(f"| 财务 PIT 因子 | **{len(pit)}** 个（均为 `*_latest`，走 `app/backtest/fundamentals.py`） | `is_financial_pit` |")
    A(f"| 另有 PIT 依赖（非财务） | {len(pit_shares)} 个：{', '.join('`'+r['id']+'`' for r in pit_shares) or '无'} | `price_basis` 含「历史时点流通股本」 |")
    A(f"| warmup 声明值**低于**实需（真治理项） | **{len(under)}** 个 | `warmup_bars_declared` < `warmup_bars_derived` |")
    A(f"| warmup 声明值高于实需（安全冗余） | {len(over)} 个 | 同上，方向相反 |")
    A("")
    A("**与任务书「93 个（含 8 个财务 PIT）」的两处核对结论（确证）：**")
    A("")
    A(f"1. 93 这个数字对得上，但它等于「178 − 85 个扩展数据因子」，不是注册表总数：`ext_*` 全部来自扩展数据包（`app/custom/*`、扩展数据列），未纳入本次盘点。")
    A(f"2. 财务 PIT 严格是 **{len(pit)} 个**，不是 8 个。凑出「8」的可能是 `{'`, `'.join(r['id'] for r in pit_shares)}`——它用历史时点流通股本（PIT），但不是财务科目因子。")
    A("")
    A("## 1. 口径公约（本清单的判定标准）")
    A("")
    A("| 公约 | 内容 | 检查方式 |")
    A("| --- | --- | --- |")
    A("| 价格口径 | base/量价类一律用**前复权** `close`/`high`/`low`；`raw_*`（不复权）只用于涨跌停与股票池价格门槛 | 读 `pipeline.py` 的 `compute_indicators` 表达式 |")
    A("| 含当日 | 除显式 `ts_delay`/`shift(1)` 的「此前」语义外，全部**含当日**（当日收盘可知） | `includes_today` / `shift` 字段 |")
    A("| 窗口 | 窗口按**交易日 bar 数**（非自然日）；`min_samples` 不足即 null（不填充） | `window` 字段 |")
    A("| 空值策略 | 全表统一 `keep`：任一输入为空则输出为空，**不填 0、不前向填充**，策略侧自行 `fill_null(False)` | `null_policy_effective`（逐条读实现确认） |")
    A("| warmup | 声明值 vs 实需值分别记录；实需 = 使首个输出非空所需前置 bar 数（含窗口与嵌套因子） | `warmup_bars_derived` |")
    A("")
    A("两层实现位置不同会导致同名口径分叉，读表时以「实现在」为准：")
    A("")
    A("| 实现位置 | 因子数 | 含义 |")
    A("| --- | --- | --- |")
    for k, v in mod.most_common():
        A(f"| `{k}` | {v} | |")
    A("")
    A("## 2. 逐因子台账")
    A("")
    A("列说明：`口径` = 价格基准 / 含当日 / shift / 窗口；`warmup` = 声明 / 实需（✗ = 不一致）；`空值` 全为 keep。")
    A("")
    for g, rs in by_group.items():
        if not rs:
            continue
        A(f"### 2.{ORDER.index(g)+1 if g in ORDER else ''} {g}（{len(rs)} 个）")
        A("")
        A("| id | 名称 | 类型 | 公式 | 口径 | warmup 声明/实需 | 数据源列 | 空值 | PIT | 实现在 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rs:
            cal = f"{r['price_basis']}；含当日={r['includes_today']}；{r['shift'] or '无shift'}；窗口={r['window'] or '—'}"
            wm = f"{r['warmup_bars_declared']} / {r['warmup_bars_derived']}"
            d, v = _num(r["warmup_bars_declared"]), _num(r["warmup_bars_derived"])
            if d is not None and v is not None and d < v:
                wm += " ✗低估"
            elif d is not None and v is not None and d > v:
                wm += " ↑高估"
            A("| `{}` | {} | {} | `{}` | {} | {} | {} | {} | {} | `{}` |".format(
                r["id"], esc(r["label"]), r["kind"], esc(r["formula_code"]) or esc(r["formula_text_registry"]),
                esc(cal), wm, esc(r["data_source_cols"]) or "—", r["null_policy_declared"],
                "是" if r["is_financial_pit"] == "True" else "—",
                esc(r["computed_in"]),
            ))
        A("")

    A(f"## 3. warmup 声明低于实际需求的 {len(mism)} 个（治理项）")
    A("")
    A("这些因子的 `warmup_bars` 在注册表里声明得比实际所需短，后果是策略在因子尚未产出有效值的区间就认为「已预热」，早期信号可能是 null 或短窗口噪声。另有 {} 个因子声明值偏保守（声明 > 实需），不构成风险，仅在表中标 `↑高估`。".format(len(over)))
    A("")
    A("| id | 声明 | 实需 | 说明 |")
    A("| --- | --- | --- | --- |")
    for r in mism:
        A(f"| `{r['id']}` | {r['warmup_bars_declared']} | {r['warmup_bars_derived']} | {esc(r['warmup_note'])} |")
    A("")
    A("## 4. 财务 PIT 因子（7 个）")
    A("")
    A("| id | 名称 | PIT 来源 | 公式 | 空值 |")
    A("| --- | --- | --- | --- | --- |")
    for r in pit:
        A(f"| `{r['id']}` | {esc(r['label'])} | `{esc(r['pit_source'])}` | `{esc(r['formula_code'])}` | {r['null_policy_declared']} |")
    A("")
    A("## 5. 未纳入本清单的 85 个 `ext_*`（扩展数据）")
    A("")
    A("`all_factors()` 里 85 个 `ext_` 前缀因子由扩展数据包注册（集合竞价、龙虎榜等），其口径由各自 provider 定义、数据源不在本项目行情库内。本清单**不判定**其口径，只在策略引用时要求单独出证据。核验命令：")
    A("")
    A("```bash")
    A("cd C:\\work\\sourcecode\\tick-stock-panel\\backend")
    A(".\\\\.venv\\\\Scripts\\\\python.exe -c \"from app.factors import registry as R; fs=R.all_factors(); print(len(fs)); print([f.id for f in fs if f.id.startswith('ext_')][:5])\"")
    A("```")
    A("")
    A("## 6. 复现")
    A("")
    A("```bash")
    A("cd C:\\work\\sourcecode\\tick-stock-panel\\backend")
    A(".\\\\.venv\\\\Scripts\\\\python.exe ..\\docs\\\\research\\\\factor-audit-20261107\\\\scripts\\\\build_inventory.py   # 生成 csv/json")
    A(".\\\\.venv\\\\Scripts\\\\python.exe ..\\docs\\\\research\\\\factor-audit-20261107\\\\scripts\\\\render_inventory_md.py     # 生成本文件")
    A("```")
    A("")
    A("机器可读证据：`docs/factors/evidence/factors_inventory_core93_20261107.csv`（同 `docs/research/factor-audit-20261107/factors_inventory.csv`）、`factors_inventory.json`（含 dependencies / stability / asset_types）。")
    A("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT_MD, OUT_MD.stat().st_size, "bytes")
    print("copied csv ->", OUT_CSV)


if __name__ == "__main__":
    main()
