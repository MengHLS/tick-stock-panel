"""S01b 独立复核 · 一条命令跑完全部机器可判定项（只读）。

用法（仓库根目录）:
  backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\run_audit.py

做四件事：
  1. 逐格比对 REPORT.md §4.1/4.2/4.3（compare_report_cells.py）
  2. 臂 1 止损分档（价格口径 + 净口径）（check_stop_bands.py）
  3. 预注册 F1–F4 自算（check_prereg_f.py）
  4. 琐碎但必需的核对：逐笔等价、生产文件是否进 policy、时间序、装载安全
退出码: 0 = 全部通过；1 = 有硬性不一致（打印汇总表）
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BASE = PROJECT / "research" / "s01b-20261108"
RES = BASE / "results"
PY = str(PROJECT / "backend" / ".venv" / "Scripts" / "python.exe")
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

results: list[tuple[str, bool, str]] = []


def run(tag: str, script: str) -> None:
    p = subprocess.run([PY, str(HERE / script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, cwd=str(PROJECT))
    out = (p.stdout or "") + (p.stderr or "")
    print(f"\n{'=' * 78}\n### {tag}  ({script})  exit={p.returncode}\n{'=' * 78}")
    print(out.strip()[-4000:])
    results.append((tag, p.returncode == 0, f"exit={p.returncode}"))


def cross_checks() -> None:
    print(f"\n{'=' * 78}\n### 附加核对：逐笔等价 / 生产文件 / META 五项 / 装载安全 / 时间序\n{'=' * 78}")
    import pandas as pd

    ok_all = True

    # (a) 逐笔等价
    pairs = [("a0_10bp", "a0ev_10bp"), ("a3_10bp", "a3ev_10bp"),
             ("prod_file_10bp", "a3_10bp"), ("prod_file_10bp", "a3ev_10bp")]
    for a, b in pairs:
        ta = pd.read_parquet(RES / a / "trades.parquet")
        tb = pd.read_parquet(RES / b / "trades.parquet")
        ea = pd.read_parquet(RES / a / "equity.parquet")
        eb = pd.read_parquet(RES / b / "equity.parquet")
        eq = bool(ta.equals(tb)) and bool(ea.equals(eb))
        ok_all &= eq
        print(f"  [{'OK' if eq else 'DIFF'}] {a} {ta.shape} == {b} {tb.shape}  "
              f"trades={ta.equals(tb)} equity={ea.equals(eb)}")
    results.append(("逐笔等价 4 对（trades+equity）", ok_all, "DataFrame.equals"))

    # (b) 生产文件 sha 与 META 五项
    prod = Path(r"D:\TSP\data\strategies\custom\custom_mw7fvp17.py")
    sha = hashlib.sha256(prod.read_bytes()).hexdigest()[:16]
    print(f"  生产文件 {prod.name}: {prod.stat().st_size} B sha256={sha}")
    r = subprocess.run([PY, str(HERE / "probe_exec_policy.py")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, cwd=str(PROJECT))
    pol_ok = r.returncode == 0 and "五项全进 policy" in (r.stdout or "")
    print(f"  [{'OK' if pol_ok else 'FAIL'}] META.backtest_defaults 五项 → execution_policy")
    results.append(("META 五项进 execution_policy", pol_ok, "probe_exec_policy.py"))

    # (c) 装载安全（在册策略 + D:\TSP 目录里没有会误加载的残file）
    sys.path.insert(0, str(PROJECT / "backend"))
    os.environ["DATA_DIR"] = r"D:\TSP\data"
    from app.strategy.engine import StrategyEngine

    eng = StrategyEngine(strategy_dirs=[
        PROJECT / "backend" / "app" / "strategy" / "research",
        Path(r"D:\TSP\data\strategies\custom"), Path(r"D:\TSP\data\strategies\ai"),
        Path(r"D:\TSP\data\strategies\composite")])
    items = eng.list_strategies(include_research=True)
    errs = eng.load_errors()
    bad = []
    for it in items:
        s = eng.get(it["id"])
        if s.stop_loss is not None and abs(s.stop_loss) > 0.5:
            bad.append((it["id"], "stop_loss", s.stop_loss))
        if s.max_hold_days is not None and s.max_hold_days < 1:
            bad.append((it["id"], "max_hold_days", s.max_hold_days))
    load_ok = not errs and not bad
    print(f"  [{'OK' if load_ok else 'FAIL'}] 在册策略 {len(items)} 条，load_errors={len(errs)}，"
          f"越界风控={bad}")
    stray = sorted(p.name for p in Path(r"D:\TSP\data\strategies\custom").iterdir()
                   if p.suffix not in (".py", ".pyc", ".bak_20261108") and not p.name.startswith("."))
    print(f"  目录内非 .py 残留: {stray or '无'}（加载器只 glob('*.py')，见 engine.py:316）")
    results.append(("装载安全（在册策略不被误伤）", load_ok, f"{len(items)} 条 / 0 越界"))

    # (d) 时间序
    print("\n  时间序（mtime，Asia/Shanghai）:")
    prereg = BASE / "PREREG_S01B_20261108.md"
    t0 = prereg.stat().st_mtime
    print(f"    PREREG  {prereg.stat().st_size:>6} B  {t0:.0f}  sha256="
          f"{hashlib.sha256(prereg.read_bytes()).hexdigest()[:16]}")
    late = []
    for d in sorted(RES.iterdir()):
        f = d / "trades.parquet"
        if f.exists():
            after = f.stat().st_mtime > t0
            if not after:
                late.append(d.name)
            print(f"    {d.name:<14} {f.stat().st_mtime:.0f}  {'预注册后' if after else '预注册前 (!)'}")
    print(f"    预注册前已产出的臂: {late or '无'}")
    results.append(("预注册时间序（被测臂均在 PREREG 之后）",
                    set(late) <= {"a0_10bp", "smoke_a0"}, f"预注册前: {late}"))

    # (e) 报告指纹
    rep = BASE / "REPORT.md"
    print(f"\n  REPORT.md: {rep.stat().st_size} B  sha256="
          f"{hashlib.sha256(rep.read_bytes()).hexdigest()}  mtime={rep.stat().st_mtime:.0f}")
    print(f"  完整 sha256 = {hashlib.sha256(rep.read_bytes()).hexdigest()}")


def main() -> int:
    run("① §4 逐格比对", "compare_report_cells.py")
    run("② 臂1 止损分档", "check_stop_bands.py")
    run("③ 预注册 F1–F4", "check_prereg_f.py")
    cross_checks()

    print(f"\n{'=' * 78}\n汇总\n{'=' * 78}")
    allok = True
    for tag, ok, note in results:
        allok &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {tag}  ({note})")
    print(f"\n总判定: {'PASS' if allok else 'FAIL'}   exit={0 if allok else 1}")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
