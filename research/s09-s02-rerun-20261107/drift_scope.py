"""漂移范围探查：把另外几条（S01 / S03 / S05 / S08）用同一条 harness 重跑，
与 registry 比，判断 S09 的 732→679 是「S09 独有」还是「全批漂移」。

只读，不写 registry。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import common

market = common.open_market()
panel = common.load_panel(market)
prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
ev = prepared.filter(prepared["date"] >= common.EVAL_START)
registry = json.loads(
    (ROOT / "research" / "strategy-search-20261107" / "results" / "registry.json").read_text(encoding="utf-8")
)["runs"]

by_key = {s.key: s for s in common.STRATEGIES}
want = [
    ("S01_ma_cross_20_60", "S01_ma_cross_20_60@10"),
    ("S03_tsmom_60_m", "S03_tsmom_60_m@10"),
    ("S05_bollinger_20_2", "S05_bollinger_20_2@10"),
    ("S08_high_52w", "S08_high_52w@10"),
]
out = {}
for key, reg in want:
    strat = by_key[key]
    res = common.run_continuous(market, ev, strat, 10.0)
    last = res["equity"][-1] if res["equity"] else {}
    out[key] = {
        "today_n_trades": len(res["trades"]),
        "registry_n_trades": registry[reg]["n_trades"],
        "today_final_value": last.get("value"),
        "registry_final_equity": registry[reg]["ALL"]["final_equity"],
        "today_seg_trades": [(s["start"][:4], (s["stats"] or {}).get("n_trades")) for s in res["segments"]],
        "registry_seg_trades": [(s["start"][:4], s["n_trades"]) for s in registry[reg]["segments"]],
    }
    print(key, out[key]["today_n_trades"], out[key]["registry_n_trades"], flush=True)

(Path(__file__).resolve().parent / "DRIFT_SCOPE.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("DONE", flush=True)
