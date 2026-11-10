"""独立 A/B：把基线 engine_before.py 冒充 app.backtest.engine，再跑 8 条新用例。
不修改任何被测文件；只在本进程内替换模块对象。"""
from __future__ import annotations
import importlib.util, sys, traceback
from pathlib import Path

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

# 先导入 app.backtest 包，再把包里的 engine 替换成基线
import app.backtest  # noqa: E402
base = load("app.backtest.engine", ROOT / "research/s01b-20261108/postfix_20261108/baseline/engine_before.py")
setattr(app.backtest, "engine", base)
print("engine module in use =", sys.modules["app.backtest.engine"].__file__)

spec = importlib.util.spec_from_file_location("t_eos_ab", BACKEND / "tests/backtest/test_end_settlement.py")
tmod = importlib.util.module_from_spec(spec)
sys.modules["t_eos_ab"] = tmod
spec.loader.exec_module(tmod)

names = [n for n in dir(tmod) if n.startswith("test_")]
names.sort()
fails = []
for n in names:
    fn = getattr(tmod, n)
    try:
        fn()
        print(f"PASS {n}")
    except BaseException as exc:  # noqa: BLE001
        tb = traceback.extract_tb(exc.__traceback__)
        where = f"{Path(tb[-1].filename).name}:{tb[-1].lineno}"
        _msg = (str(exc).splitlines() or [""])[0]
        print(f"FAIL {n} :: {type(exc).__name__} @ {where} :: {_msg[:120]}")
        fails.append(n)
print(f"SUMMARY {len(fails)} failed / {len(names)-len(fails)} passed of {len(names)}")
