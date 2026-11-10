"""D-EOS 修复的测试侧改动（与 apply_patch.py 同一改动集，可复审/可回滚）。

两步：
  1. 把本目录的 `test_end_settlement.py` 复制成
     `backend/tests/backtest/test_end_settlement.py`（T-EOS-1~5 + 六条逃逸路径
     + carry_out 反例，共 8 个用例）。
  2. 修订 `backend/tests/backtest/test_limit_down_close_exit.py` 里的
     `test_stuck_position_at_window_end_is_recorded_portfolio_mode`：它原先断言
     "期末不可成交的持仓以封板价成交、exit_reason 保留递延原因"，正是契约
     §1.3 P6 / §7.1 A-R5 描述的缺陷行为；按 I3/S-3 改为 MARKED 口径，并把
     legacy 路径 (X-1，本次不修) 的旧行为显式登记为"两路径分道"。

用法：backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\apply_test_changes.py
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
TESTS = PROJECT / "backend" / "tests" / "backtest"
NEW_TEST_SRC = HERE / "test_end_settlement.py"
NEW_TEST_DST = TESTS / "test_end_settlement.py"
LEGACY_TEST = TESTS / "test_limit_down_close_exit.py"

OLD_FN = '''def test_stuck_position_at_window_end_is_recorded_portfolio_mode():
    """组合模式: 期末仍被封板递延的持仓同样强制落账 (与独立路径同口径),
    不再只进 pending_exit_positions 而在交易记录里消失。"""
    days = _normal_panel(8, sealed={7: {"o": 10.30, "h": 10.32, "l": 9.27, "c": 9.27}})
    panel = _panel(days)
    dates = [r["date"] for r in panel.select(["symbol", "date"]).iter_rows(named=True)]
    entry_mask = pl.Series([(dt - START).days in {0} for dt in dates], dtype=pl.Boolean)
    exit_mask = pl.Series([(dt - START).days in {7} for dt in dates], dtype=pl.Boolean)
    cfg = MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0)
    engine = BacktestEngine(repo=None)  # type: ignore[arg-type]

    matrix_result = engine.simulate_portfolio(panel, entry_mask, exit_mask, cfg)
    assert matrix_result.stats.get("n_trades") == 1
    trade = matrix_result.trades[0]
    assert trade.exit_date == "2024-01-08"  # 末日强制落账
    assert trade.exit_reason == "signal"    # 递延原因保留
    assert trade.blocked_exit_days >= 1
    assert trade.exit_price == 9.27
    assert matrix_result.stats.get("pending_exit_positions") == 1  # 观测信号保留

    # legacy 组合路径 parity
    legacy_result = engine.simulate_portfolio_legacy(panel, entry_mask, exit_mask, cfg)
    assert [asdict(t) for t in legacy_result.trades] == [asdict(t) for t in matrix_result.trades]
    assert legacy_result.stats["pending_exit_positions"] == 1
'''

NEW_FN = '''def test_stuck_position_at_window_end_is_recorded_portfolio_mode():
    """组合模式: 期末仍被封板递延的持仓按 MARKED 落账 (契约 D-EOS I3 / S-3)。

    口径变更 (2026-11-08 D-EOS，随引擎"末日终结结算步"同批):
      * 改前: 期末不可成交 (契约 §1.3 P6) 的持仓在 post-loop 以**封板价**"成交"、
        并保留递延原因 —— 该价现实中排不出去 (§7.1 A-R5)，且末行现金/市值两处
        口径不一致 (§1.2)。
      * 改后: MARKED —— open_at_end=True、pnl_amount=0.0、exit_reason="end"，
        市值留在末行权益、现金不含它 (I1/I2/I3)。
    """
    days = _normal_panel(8, sealed={7: {"o": 10.30, "h": 10.32, "l": 9.27, "c": 9.27}})
    panel = _panel(days)
    dates = [r["date"] for r in panel.select(["symbol", "date"]).iter_rows(named=True)]
    entry_mask = pl.Series([(dt - START).days in {0} for dt in dates], dtype=pl.Boolean)
    exit_mask = pl.Series([(dt - START).days in {7} for dt in dates], dtype=pl.Boolean)
    cfg = MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0)
    engine = BacktestEngine(repo=None)  # type: ignore[arg-type]

    matrix_result = engine.simulate_portfolio(panel, entry_mask, exit_mask, cfg)
    assert matrix_result.stats.get("n_trades") == 1
    trade = matrix_result.trades[0]
    assert trade.exit_date == "2024-01-08"      # 末日
    assert trade.exit_reason == "end"           # MARKED 固定 end (不再保留递延原因)
    assert trade.open_at_end is True            # 盯市, 不是伪造成交
    assert trade.pnl_amount == 0.0
    assert trade.blocked_exit_days >= 1         # "曾受阻"痕迹保留
    assert trade.exit_price == 9.27             # 末日收盘 = 盯市价
    assert matrix_result.stats.get("pending_exit_positions") == 1
    row = matrix_result.equity_curve[-1]
    assert row["positions"] == 1
    assert abs(row["value"] - (row["cash"] + trade.shares * 9.27)) < 0.01

    # legacy 组合路径 (契约 §1.4 / §10 X-1): 同型缺陷本次不修，仍按旧口径
    # "以封板价成交 + 保留递延原因" 落账 ⇒ 两路径在此分道，属登记在案的差异，
    # 不是回归。
    legacy_result = engine.simulate_portfolio_legacy(panel, entry_mask, exit_mask, cfg)
    assert legacy_result.stats["pending_exit_positions"] == 1
    assert [asdict(t)["exit_reason"] for t in legacy_result.trades] == ["signal"]
    assert [t.open_at_end for t in legacy_result.trades] == [False]
'''


def main() -> int:
    if not NEW_TEST_SRC.exists():
        print(f"[FATAL] missing {NEW_TEST_SRC}")
        return 2
    raw = LEGACY_TEST.read_bytes()
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    norm = text.replace("\r\n", "\n")

    if norm.count(OLD_FN) == 1:
        norm = norm.replace(OLD_FN, NEW_FN, 1)
        out = norm.replace("\n", "\r\n") if crlf else norm
        LEGACY_TEST.write_bytes(out.encode("utf-8"))
        print(f"[amend] {LEGACY_TEST.name}: 1 处用例改为 MARKED 口径")
    elif norm.count(NEW_FN) == 1:
        print(f"[skip ] {LEGACY_TEST.name}: 已改过")
    else:
        print("[FATAL] 未找到待修订用例（定位串 0 次命中），停下不改")
        return 3

    shutil.copyfile(NEW_TEST_SRC, NEW_TEST_DST)
    h = hashlib.sha256(NEW_TEST_DST.read_bytes()).hexdigest()
    print(f"[copy ] {NEW_TEST_DST.name} <- {NEW_TEST_SRC.name} sha256={h}")
    print(f"[legacy] sha256={hashlib.sha256(LEGACY_TEST.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
