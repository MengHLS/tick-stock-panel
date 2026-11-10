"""S01b 四臂策略文件生成器。

单一模板 -> 每臂一个策略文件（research/s01b-20261108/strategies/custom/<sid>.py）。
除被替换的常量块 / META id-name-tags / 成本块 / 峰值口径外，逐字节相同；
生成后由 materialize() 返回 (路径, sha256, 行数) 记录到清单。
模板正文与 D:\TSP\data\strategies\custom\custom_mw7fvp17.py 的最终版一致
（交付版用 diff 证明：只差 id/name/tags 与实验口径字段）。
"""
from __future__ import annotations
import hashlib
from pathlib import Path

TEMPLATE = '''"""__DOCSTRING__"""
import numpy as np
from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
    matrix_feature,
    valid_shift,
)
META = {
    "id": "__MID__",
    "name": "__MNAME__",
    "description": "__MDESC__",
    "tags": __MTAGS__,
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "backtest_defaults": {
        "trailing_peak_price": "__PEAK__",
        "entry_price_basis": "raw",
        "block_limit_open": True,
        "finalize_open_at_end": True,
        "exit_signal_requires_profit": False,
        "execution_costs": __COSTS__,
    },
    "basic_filter": {
        "price_min": 2.0,
        "price_max": None,
        "market_cap_min": None,
        "float_cap_min": None,
        "float_cap_max": None,
        "amount_min": None,
        "amount_max": None,
        "turnover_min": None,
        "turnover_max": None,
        "exclude_st": True,
        "exclude_new_days": 30,
        "boards": ["沪主板", "深主板", "创业板", "科创板", "北交所"],
    },
    "params": [
        {"id": "fast_period", "label": "快线周期", "type": "int", "default": 20,
         "min": 5, "max": 60, "step": 1},
        {"id": "slow_period", "label": "慢线周期", "type": "int", "default": 60,
         "min": 20, "max": 250, "step": 1},
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}
EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = __STOP__
TRAILING_TAKE_PROFIT_ACTIVATE = __TTP_ACT__
TRAILING_TAKE_PROFIT_DRAWDOWN = __TTP_DD__
TRAILING_STOP = __TRAIL__
MAX_HOLD_DAYS = __MAXHOLD__
REQUIRED_FEATURES = ["close", "ma20", "ma60"]
def _bounded_int(value, default, low, high):
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))
class MaCross2060MatrixStrategy:
    """20 日与 60 日均线的金叉/死叉策略，按 20 日动量排序择优建仓。"""
    def required_fields(self) -> frozenset:
        return frozenset({"close", "ma20", "ma60"})
    def required_warmup_bars(self, params: dict) -> int:
        slow = _bounded_int(params.get("slow_period"), 60, 20, 250)
        return slow + 2
    def compute_signals(self, market: MarketDataMatrix, params: dict) -> SignalMatrix:
        fast_n = _bounded_int(params.get("fast_period"), 20, 5, 60)
        slow_n = _bounded_int(params.get("slow_period"), 60, 20, 250)
        if fast_n >= slow_n:
            fast_n, slow_n = 20, 60
        fast = np.asarray(matrix_feature(market, "ma%d" % fast_n), dtype=np.float64)
        slow = np.asarray(matrix_feature(market, "ma%d" % slow_n), dtype=np.float64)
        prev_fast = np.asarray(valid_shift(fast, 1), dtype=np.float64)
        prev_slow = np.asarray(valid_shift(slow, 1), dtype=np.float64)
        cross_up = (fast > slow) & (prev_fast <= prev_slow)
        cross_down = __XDOWN__
        momentum = np.asarray(matrix_feature(market, "momentum_20d"), dtype=np.float64)
        momentum = np.where(np.isfinite(momentum), momentum, 0.0)
        return make_signal_matrix(
            market.shape,
            entry=cross_up.astype(np.uint8),
            exit=cross_down.astype(np.uint8),
            ranking_score=momentum,
        )
MATRIX_STRATEGY = MaCross2060MatrixStrategy()
'''

LEVEL_XDOWN = "fast < slow"
EVENT_XDOWN = "(fast < slow) & (prev_fast >= prev_slow)"

# 成本口径（四臂统一）：
#   佣金 3bp（双边，commission_pct 引擎两侧各收一次）+ 印花 10bp（仅卖出）
#   + 过户 0.02bp（2e-6，按派单口径）+ 最低佣金 5 元/笔（沿用 S01 基线 ACCOUNT）
#   + 滑点 10bp / 30bp 双边（由 StrategyBacktestConfig.slippage_bps 传入）
COSTS_PAID = '{"min_commission": 5.0, "transfer_fee_pct": 0.000002}'
COSTS_GROSS = '{"min_commission": 0.0, "transfer_fee_pct": 0.0}'

ARMS = {
    # sid                          stop     ttp_act ttp_dd trail  maxhold peak    成本
    "s01b_a0":  dict(stop=None,  ttp_act=None, ttp_dd=None, trail=None, max_hold=60, peak="close"),
    "s01b_a1":  dict(stop=-0.08, ttp_act=None, ttp_dd=None, trail=None, max_hold=60, peak="close"),
    "s01b_a2":  dict(stop=-0.08, ttp_act=0.10, ttp_dd=0.08, trail=None, max_hold=60, peak="close"),
    "s01b_a3":  dict(stop=-0.08, ttp_act=0.10, ttp_dd=0.08, trail=None, max_hold=45, peak="close"),
    # 峰值口径对照（只把 close 换成 high，其余与臂 2 完全一致）
    "s01b_a2h": dict(stop=-0.08, ttp_act=0.10, ttp_dd=0.08, trail=None, max_hold=60, peak="high"),
    # cross_down 等价性：同一配置（臂 0 + 臂 3）下的事件式/水平式对照
    "s01b_a0ev": dict(stop=None,  ttp_act=None, ttp_dd=None, trail=None, max_hold=60, peak="close", xdown=EVENT_XDOWN),
    "s01b_a3ev": dict(stop=-0.08, ttp_act=0.10, ttp_dd=0.08, trail=None, max_hold=45, peak="close", xdown=EVENT_XDOWN),
}

def _lit(v) -> str:
    return "None" if v is None else repr(v)

def render(sid: str, *, gross: bool = False) -> str:
    spec = ARMS[sid]
    text = TEMPLATE
    text = text.replace("__DOCSTRING__",
        "S01b 风控变体实验臂 %s（模板生成，勿手改）：ma20 上穿 ma60 买入，死叉卖出。" % sid)
    text = text.replace("__MID__", sid)
    text = text.replace("__MNAME__", "S01b 实验臂 %s" % sid)
    text = text.replace("__MDESC__", "S01b 四臂实验；由 arms.py 模板生成，参数见模块常量。")
    text = text.replace("__MTAGS__", '["趋势", "双均线", "S01b", "experiment"]')
    text = text.replace("__PEAK__", spec["peak"])
    text = text.replace("__COSTS__", COSTS_GROSS if gross else COSTS_PAID)
    text = text.replace("__STOP__", _lit(spec["stop"]))
    text = text.replace("__TTP_ACT__", _lit(spec["ttp_act"]))
    text = text.replace("__TTP_DD__", _lit(spec["ttp_dd"]))
    text = text.replace("__TRAIL__", _lit(spec["trail"]))
    text = text.replace("__MAXHOLD__", _lit(spec["max_hold"]))
    text = text.replace("__XDOWN__", spec.get("xdown", LEVEL_XDOWN))
    return text

def materialize(sid: str, *, gross: bool = False, outdir: Path | None = None) -> dict:
    outdir = outdir or Path(__file__).resolve().parent / "strategies" / "custom"
    outdir.mkdir(parents=True, exist_ok=True)
    body = render(sid, gross=gross)
    path = outdir / f"{sid}.py"
    path.write_text(body, encoding="utf-8")
    raw = path.read_bytes()
    return {
        "sid": sid,
        "gross": gross,
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "lines": body.count("\n"),
    }

if __name__ == "__main__":
    import json
    out = [materialize(sid) for sid in ARMS]
    print(json.dumps(out, ensure_ascii=False, indent=1))
