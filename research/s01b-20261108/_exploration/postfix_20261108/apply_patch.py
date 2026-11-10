"""D-EOS 末日结算修复：唯一改动集落点（可复审、可回滚）。

只改 `backend/app/backtest/engine.py`，四个 hunk，全部按契约
`docs/architecture/CONTRACT_END_SETTLEMENT_20261108.md`（v1.0 / 37,195 B /
sha256 c3c6501f...）的 S-1 / S-2 / S-3 / S-7 落地：

  H1 (S-1/S-7) 在末根 K 线的持仓体顶部、`:4104` 之后 `:4105` 之前插入一次性
     终结结算步 `end_settlement` 守卫 + `_try_sell(..., "end", ...)`。
  H2 (S-2)     把链底 `end` 分支（原 `:4245-4250`）改成 `elif end_settlement:`
     并加"防御性重复"计数器（守卫下不可达，不用 assert）。
  H3 (S-3/S-8) 把 post-loop 的 `elif config.finalize_open_at_end:` 改成单一
     MARKED 记账号 `else:`（只为仍在 positions 的持仓追加 open_at_end 记录）。
  H4 (S-3)     删除原 post-loop `else:` 里的 `_sell`（那正是缺陷主路径：
     结算发生在末行权益写入之后）。

不触碰：`_calc_portfolio_stats_from_values`（I4/S-9）、`exit_prices` 价基
（S-5，`:2617-2621`）、`MatcherConfig.finalize_open_at_end` 默认值（S-10，
`:261`）、`carry_out` 分支（S-7）、`simulate_portfolio_legacy`（X-1）、
`dsl.py` / 信号链 / `store.py` / 策略文件。

用法：
    backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\apply_patch.py [--check]

`--check` 只校验四个 hunk 的定位串各出现 1 次，不写文件。
幂等：已打过的文件会被识别（定位串不再匹配 + 新串已存在）并直接返回 0。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ENGINE = PROJECT / "backend" / "app" / "backtest" / "engine.py"
BASELINE = HERE / "baseline" / "engine_before.py"
DIFF_OUT = HERE / "engine_diff.patch"

EXPECT_BEFORE_SHA = "ecc3d8261c5605edd877f5a48863cb239700486a9167de610ea0db82ec184cbe"
EXPECT_BEFORE_BYTES = 268_800

# ---------------------------------------------------------------- hunk 定义
H4_OLD = """        else:
            for position_id in list(positions):
                pos = positions[position_id]
                asset_id = int(pos["asset_id"])
                last_time = None
                for t in range(time_count - 1, -1, -1):
                    if _valid_price(exit_prices[t, asset_id]):
                        last_time = t
                        break
                if last_time is None:
                    continue
                _sell(
                    last_time,
                    position_id,
                    str(pos.get("pending_exit_reason") or "end"),
                    matrix.timestamp_labels[last_time][:10],
                    set(),
                )
"""
H4_NEW = ""

H3_OLD = """        elif config.finalize_open_at_end:
            for position_id in list(positions):
                pos = positions.pop(position_id)
"""
H3_NEW = """        else:
            # MARKED 记账号 (契约 S-3/S-8): 只为仍留在 positions 的持仓追加
            # open_at_end 记录 —— 现金与持仓市值已在末行权益写入之前定稿, 这里不再
            # 调用 _sell, 也不改动末行任何数字。两条终态由此收敛:
            #   * finalize_open_at_end=True: 全部持仓走此分支 (= 改前行为, 逐字节不变);
            #   * 默认臂: 只剩末日不可成交 (P6: 停牌/一字跌停) 的持仓走此分支。
            for position_id in list(positions):
                pos = positions.pop(position_id)
"""

H1_OLD = """            cash_for_plan = cash
            for position_id in list(positions):
                pos = positions.get(position_id)
                if pos is None:
                    continue
                asset_id = int(pos["asset_id"])
                if pos["entry_date"] == date_text:
"""
H1_NEW = """            cash_for_plan = cash
            # 末日终结结算窗口 (契约 D-EOS S-1/S-7): 只在末根 K 线、非跨段结转、且
            # 未要求期末盯市时开启。判定在循环外算一次; 循环内在每个持仓体顶部调用
            # 结算步 —— 该位置在建仓日 / pending / risk / 信号闩锁 / 延展策略五条
            # 早退分支之前, 所以 P1~P6 没有任何一条能绕过它 (契约 §1.3)。
            end_settlement = (
                time_id == time_count - 1
                and not options.carry_out
                and not config.finalize_open_at_end
            )
            for position_id in list(positions):
                pos = positions.get(position_id)
                if pos is None:
                    continue
                asset_id = int(pos["asset_id"])
                if end_settlement and _try_sell(
                    time_id, position_id, "end", date_text, sold_today
                ):
                    # SETTLED: 已按该臂 exit_fill 的末根价成交、现金已入账、trade 已
                    # 闭环; 本 bar 余下步骤不再触碰该持仓 (契约 I3)。
                    continue
                if pos["entry_date"] == date_text:
"""

H2_OLD = """                elif (
                    time_id == time_count - 1
                    and not config.finalize_open_at_end
                    and not options.carry_out
                ):
                    reason = "end"
"""
H2_NEW = """                elif end_settlement:
                    # 防御性重复 (契约 S-2): 终结结算步已在持仓体顶部跑过, 能走到
                    # 这里只剩"末日不可成交"(P6) 的遗留 —— 它已被登记 pending 并在
                    # 上面的 pending 守卫里 continue 掉, 故本分支在守卫下不可达。
                    # 保留而不用 assert: 回测引擎不应在生产路径抛断言; 计数器让
                    # "不该发生"在 stats["execution"] 里可见。
                    _count("end_branch_reached_after_settlement")
                    reason = "end"
"""

# 顺序有意义：先删旧 else 块，再把 elif 改名成 else（否则 H3 的定位串会歧义）。
HUNKS = [("H4", H4_OLD, H4_NEW), ("H3", H3_OLD, H3_NEW), ("H1", H1_OLD, H1_NEW), ("H2", H2_OLD, H2_NEW)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    raw = ENGINE.read_bytes()
    sha_before = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    norm = text.replace("\r\n", "\n")

    if sha_before != EXPECT_BEFORE_SHA:
        # 允许"已打过补丁"的幂等重放，但必须是本脚本产出的样子。
        if all(n in norm for n in (H1_NEW, H2_NEW, H3_NEW)) and not any(
            old in norm for _, old, _ in HUNKS
        ):
            print(f"[skip] already patched: bytes={len(raw)} sha256={sha_before}")
            return 0
        print(
            f"[FATAL] engine.py 基线不符: bytes={len(raw)} sha256={sha_before} "
            f"(expect {EXPECT_BEFORE_BYTES} / {EXPECT_BEFORE_SHA})"
        )
        return 2

    for name, old, _ in HUNKS:
        n = norm.count(old)
        if n != 1:
            print(f"[FATAL] {name} 定位串命中 {n} 次 (必须恰好 1 次)")
            return 3

    patched = norm
    for name, old, new in HUNKS:
        patched = patched.replace(old, new, 1)
        print(f"[hunk] {name} applied")

    if args.check:
        print("[check] 四个 hunk 定位成功，未写文件")
        return 0

    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    if not BASELINE.exists():
        BASELINE.write_bytes(raw)

    out = patched.replace("\n", "\r\n") if crlf else patched
    ENGINE.write_bytes(out.encode("utf-8"))

    added = removed = -1
    try:
        diff = list(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                out.decode("utf-8").splitlines(keepends=True),
                fromfile="a/backend/app/backtest/engine.py",
                tofile="b/backend/app/backtest/engine.py",
                n=3,
            )
        )
        DIFF_OUT.write_text("".join(diff), encoding="utf-8")
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    except Exception as exc:  # noqa: BLE001 - 差异文件只是证据，失败不应回滚代码
        print(f"[warn] diff artifact failed: {exc!r}")

    new_raw = ENGINE.read_bytes()
    print(f"[before] bytes={len(raw)} sha256={sha_before}")
    print(f"[after ] bytes={len(new_raw)} sha256={hashlib.sha256(new_raw).hexdigest()}")
    print(f"[diff  ] +{added} / -{removed} lines -> {DIFF_OUT}")
    print(f"[lines ] {len(norm.splitlines())} -> {len(patched.splitlines())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
