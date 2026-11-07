"""汇总 B2 证据 JSON: 每条断言 = 原命令 + 产物路径 + 产物 sha256 + 观测量 + 判定。

数据来源: research/b2-engine-20261107/logs/*.json (各判据脚本自己落的盘) 与本脚本现场复核。
不重算任何指标, 只做汇总与字节指纹, 避免「证据与实现各说一套」。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B2 = ROOT / "research" / "b2-engine-20261107"
LOGS = B2 / "logs"
PY = "backend/.venv/Scripts/python.exe"
ENV = "PYTHONUTF8=1"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(name: str) -> dict:
    path = LOGS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def fil(path: str) -> dict:
    f = ROOT / path
    return {"path": path, "bytes": f.stat().st_size, "sha256": sha(f),
            "lines": len(f.read_text(encoding="utf-8").splitlines())} if f.exists() else            {"path": path, "missing": True}


def art(name: str) -> dict:
    path = LOGS / name
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "bytes": path.stat().st_size,
            "sha256": sha(path)} if path.exists() else {"path": name, "missing": True}


e3 = load("e3_verify.json")
e2f = load("e2_fixtures.json")
e2 = load("e2_full.json")
e1 = load("e1_verify.json")
w = load("window_20261107.json")
a4 = load("e3_a4.json")
cal = load("observed_bars_calibers.json")
before = json.loads((B2 / "baseline_before.json").read_text(encoding="utf-8"))
after = json.loads((B2 / "baseline_after.json").read_text(encoding="utf-8"))

head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()

pt = load("pytest_after_108_run.json")
iso = load("isolation_recheck_108.json")
reg_f = fil("backend/tests/test_factor_registry.py")
sto_f = fil("backend/tests/test_factor_store.py")

TESTS_NOTE = (
    "backend/tests/** — B2 编码期内未改任何测试; 但 2026-11-07 20:48:59 本部门按「catalog 93→108」口径更新了 "
    "2 个测试文件的过期断言 (过期断言更新, 非回归): "
    f"test_factor_registry.py {reg_f['bytes']} B / {reg_f['lines']} 行 / {reg_f['sha256']}; "
    f"test_factor_store.py {sto_f['bytes']} B / {sto_f['lines']} 行 / {sto_f['sha256']}; "
    "未改断言条数: `assert ` 45→45 (test_factor_registry.py)、20→20 (test_factor_store.py), 0 删除。"
    "详见 test_status.test_files_changed。"
)


def iso_state(tag: str) -> dict:
    st = (iso.get("states") or {}).get(tag, {})
    pr = st.get("probe", {})
    return {
        "tag": tag,
        "setup": st.get("setup"),
        "has_b0_pack": pr.get("has_b0_pack"),
        "has_universe_pack": pr.get("has_universe_pack"),
        "catalog_size": pr.get("catalog_size"),
        "matrix_supported": pr.get("matrix_supported"),
        "matrix_unsupported": pr.get("matrix_unsupported"),
        "factor_suite": f"{st.get('failed')} failed / {st.get('passed')} passed",
        "failed_tests": st.get("failed_tests"),
        "artifact": f"logs/catalog_support_{tag}.json",
    }


ISO_STATES = [iso_state(t) for t in ("none", "b0_only", "all_on")]

_f_none = set(((iso.get("states") or {}).get("none") or {}).get("failed_tests") or [])
_f_b0 = set(((iso.get("states") or {}).get("b0_only") or {}).get("failed_tests") or [])
SAME_RED_SET = (_f_none == _f_b0 and len(_f_none) == 6)

xs3 = load("xs_a3_same_data_old_vs_new_dsl.json")


def _flat(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, pre + k + "."))
        else:
            out[pre + k] = v
    return out


_rb, _ra = _flat(before), _flat(after)
RAW_DIFF_KEYS = sorted(k for k in set(_rb) | set(_ra) if _rb.get(k) != _ra.get(k))

CMD_E3 = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_e3.py"
CMD_E3A4 = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_e3_a4.py"
CMD_E2F = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_e2_fixtures.py"
CMD_E2 = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_e2_full.py"
CMD_E1 = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_e1.py"
CMD_W = f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} research/b2-engine-20261107/verify_window.py"
CMD_BASE = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
            "research/b2-engine-20261107/baseline_hashes_after.py  # 与 baseline_before.json 比对")
CMD_XSA3 = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
            "research/b2-engine-20261107/probe_xs_a3_same_data.py  # 同数据, 旧 dsl vs 新 dsl")
CMD_CAL = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
           "research/b2-engine-20261107/probe_observed_bars_calibers.py")
CMD_REFS = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
            "research/b2-engine-20261107/verify_id_refs.py")
CMD_CANON = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
             "research/b2-engine-20261107/verify_id_canonical.py")
CMD_WIRE = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "
            "research/b2-engine-20261107/verify_wiring.py  # 生产 Provider 入口 materialize_factor_columns")
CMD_PROBE = (f"cd C:/work/sourcecode/tick-stock-panel && PROBE_TAG=none|b0_only|all_on {ENV} {PY} "
             "research/b2-engine-20261107/probe_catalog_support.py")
CMD_SUITE = ("cd C:/work/sourcecode/tick-stock-panel/backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe "
             "-m pytest tests/test_factor_dsl.py tests/test_factor_registry.py tests/test_factor_api.py "
             "tests/test_factor_store.py tests/test_factor_provider_contracts.py -q")
refs = load("id_refs_20261107.json")
canon = load("id_canonical_20261107.json")
wiring = load("wiring_verify.json")

assertions = [
    # ---------------- E3 ----------------
    dict(id="E3-A1", gate="逐日池内家数与研究侧一致 (对账模式)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"compared_days": e3.get("A1_n_compared_days"), "max_abs_diff": e3.get("A1_max_abs_diff"),
                   "mean_abs_diff": e3.get("A1_mean_abs_diff"), "days_with_diff": e3.get("A1_days_with_diff"),
                   "null_days": e3.get("A1_null_days"), "null_days_list": e3.get("A1_null_days_list")},
         verdict="PASS" if e3.get("A1_strict_pass") else "FAIL",
         note="9 个 null 日全部落在 st_unknown_window(8)/beyond_coverage(1); 其余 1,770 天逐日 diff 恰为 0"),
    dict(id="E3-A2", gate="池内行无 raw_close/volume 空值 (停牌=无 bar 行, 不用 volume=0 判)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"pool_rows": e3.get("A2_pool_rows"), "null_raw_close": e3.get("A2_pool_rows_null_rawclose"),
                   "null_volume": e3.get("A2_pool_rows_null_volume"), "symbols": e3.get("A2_pool_symbols")},
         verdict="PASS" if e3.get("A2_pool_rows_null_rawclose") == 0 and e3.get("A2_pool_rows_null_volume") == 0 else "FAIL"),
    dict(id="E3-A3", gate="池内家数 vs 池内该列非空家数可比对 (XS-A5 上游)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"pool_mean": e3.get("A3_pool_mean")},
         verdict="PASS" if e3.get("A3_pool_mean") else "FAIL"),
    dict(id="E3-A4", gate="空值可解释: universe_unknown_count 逐日为 0 或可逐条归因 (哪只/哪天/缺哪列)",
         command=CMD_E3A4, evidence=art("e3_a4.json"),
         observed={"days": a4.get("A4_1_days"),
                   "conservation_violations": a4.get("A4_1_conservation_violations"),
                   "days_with_unknown": a4.get("A4_2_days_with_unknown"),
                   "days_unknown_without_reason": a4.get("A4_2_days_unknown_without_reason"),
                   "days_reason_without_unknown": a4.get("A4_2_days_reason_without_unknown"),
                   "codes": a4.get("A4_3_codes"),
                   "each_code_used": a4.get("A4_3_each_code_used"),
                   "st_missing_days": a4.get("A4_4_st_missing_days"),
                   "sample_date": a4.get("A4_4_sample_date"),
                   "sample_unknown_symbols": a4.get("A4_4_unknown_symbols_that_day"),
                   "sample_of_which_have_st_record": a4.get("A4_4_of_which_have_st_record"),
                   "missing_column": a4.get("A4_4_missing_column")},
         verdict="PASS" if a4.get("all_pass") else "FAIL"),
    dict(id="E3-A5", gate="改参数必须改变结果 (参数未被写死)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"default_pool_mean": e3.get("A3_pool_mean"), "changed_pool_mean": e3.get("A5_param_change_pool_mean")},
         verdict="PASS" if e3.get("A5_differs_from_default") else "FAIL"),
    dict(id="E3-A6", gate="尾部截断回放: 历史日逐位相同 (PIT, as-of 不偷未来)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"rows": e3.get("A6_rows"), "mismatch": e3.get("A6_mismatch")},
         verdict="PASS" if e3.get("A6_mismatch") == 0 else "FAIL"),
    dict(id="E3-A7", gate="ST 不可判日 (含 2026-10-20..11-06 共 14 日) 值必须为 null 且 unknown == 当日 bar 数",
         command=CMD_E3, evidence=art("e3_verify.json"),
         observed={"all_null_days": e3.get("A7_window_days"), "window_14_days": e3.get("A7_window_2026_10_20_to_11_06_days"),
                   "window_all_null": e3.get("A7_window_all_null"),
                   "window_unknown_eq_bars": e3.get("A7_window_unknown_eq_bars"),
                   "window_reasons": e3.get("A7_window_reasons")},
         verdict="PASS" if e3.get("A7_window_all_null") and e3.get("A7_window_unknown_eq_bars") else "FAIL"),
    dict(id="E3-A8", gate="覆盖期末端不外推 (10-30 之后不得有任何非 null)", command=CMD_E3,
         evidence=art("e3_verify.json"),
         observed={"rows_after_coverage": e3.get("A8_rows_after_coverage"),
                   "non_null_after_coverage": e3.get("A8_non_null_after_coverage")},
         verdict="PASS" if e3.get("A8_non_null_after_coverage") == 0 else "FAIL"),
    dict(id="W1", gate="14 日窗口内 count(in_universe ∈ {0.0,1.0}) == 0", command=CMD_W,
         evidence=art("window_20261107.json"),
         observed={"window_rows": w.get("window_rows"), "rows_in_0_1": w.get("W1_rows_in_0_1"),
                   "nonnull_rows": w.get("W1_nonnull_rows")},
         verdict="PASS" if w.get("W1_pass") else "FAIL"),
    dict(id="W2", gate="14 日窗口内每日 universe_unknown_count == 当日有 bar 行数", command=CMD_W,
         evidence=art("window_20261107.json"),
         observed={"window_days": w.get("window_days"), "all_match": w.get("W2_all_match"),
                   "reason_counts": w.get("W2_reason_counts"), "per_day": w.get("W2_per_day")},
         verdict="PASS" if w.get("W2_pass") else "FAIL",
         note="8 天 st_unknown_window + 6 天 beyond_coverage (st_history 覆盖期末端 2026-10-29), 与 E3-A7 的 8+6 一致"),
    dict(id="W3", gate="同窗口 E1 market_breadth 输出 null", command=CMD_W,
         evidence=art("window_20261107.json"),
         observed={"days": w.get("W3_days"), "days_with_nonnull": w.get("W3_days_with_nonnull")},
         verdict="PASS" if w.get("W3_pass") else "FAIL"),
    dict(id="W4", gate="同窗口 xs_rank_pool 输出 null", command=CMD_W,
         evidence=art("window_20261107.json"),
         observed={"days": w.get("W4_days"), "max_nonnull": w.get("W4_max_nonnull")},
         verdict="PASS" if w.get("W4_pass") else "FAIL"),
    # ---------------- E2 ----------------
    dict(id="XS-A1", gate="xs_rank_pool 逐日 max==1 且 min>0, 任何 rk>1 直接不通过", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={"n": e2.get("XS-A1_n_pool_nonnull"), "max": e2.get("XS-A1_max"), "min": e2.get("XS-A1_min"),
                   "over_1": e2.get("XS-A1_over_1"), "below_0": e2.get("XS-A1_below_0"),
                   "days": e2.get("XS-A1_days"), "days_max_ne_1": e2.get("XS-A1_days_max_ne_1"),
                   "days_min_times_n_ne_1": e2.get("XS-A1_days_min_times_n_ne_1"),
                   "out_of_pool_nonnull": e2.get("XS-A1_out_of_pool_nonnull")},
         verdict="PASS" if e2.get("XS-A1_pass") else "FAIL"),
    dict(id="XS-A2", gate="分母指纹 = 池内非空家数 (不是池内成员数)", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={"pool_size_mean": e2.get("XS-A2_pool_size_mean"), "member_count_mean": e2.get("XS-A2_member_count_mean"),
                   "rows_bad": e2.get("XS-A2_rows_bad_vs_pool_differ"),
                   "distinguishable_on_full_sample": e2.get("XS-A2_distinguishable_on_full_sample"),
                   "pool_vs_pct_rows_differ": e2.get("XS-A2_pool_vs_pct_rows_differ")},
         verdict="PASS" if e2.get("XS-A2_pass") else "FAIL",
         note="真实样本池内无空 vol60, ①②恒等, 区分力由 XS-A5 合成 fixture 提供; 本条不作合格线"),
    dict(id="XS-A3", gate="dsl.py 改动后 rank/zscore/winsorize + 14 个 B0 因子输出逐位不变 (同数据新旧 dsl 对照)",
         command=CMD_XSA3,
         evidence={"same_data_probe": art("xs_a3_same_data_old_vs_new_dsl.json"),
                   "before_snapshot": str((B2 / 'baseline_before.json').relative_to(ROOT)).replace('\\', '/'),
                   "after_snapshot": str((B2 / 'baseline_after.json').relative_to(ROOT)).replace('\\', '/'),
                   "raw_identical": len(RAW_DIFF_KEYS) == 0},
         observed={"compared_keys": xs3.get("compared_keys"), "n_diff": xs3.get("n_diff"),
                   "rows": xs3.get("rows"), "symbols": xs3.get("symbols"),
                   "old_dsl_sha256": (xs3.get("old_dsl") or {}).get("sha256"),
                   "new_dsl_sha256": (xs3.get("new_dsl") or {}).get("sha256"),
                   "dsl_restored_ok": xs3.get("dsl_restored_ok"),
                   "raw_snapshot_diff_keys": RAW_DIFF_KEYS},
         verdict="PASS" if (xs3.get("identical") and xs3.get("dsl_restored_ok")) else "FAIL",
         note="同数据对照: 把 B2 前的 dsl.py (backup/dsl.py.orig, 无 xs_* 算子) 临时换入, 与现盘 dsl.py "
              "(含 4 个新算子) 在同一份当前数据上各算一次, 51 个键 (7 个表达式 + 14 个 B0 因子的 sha256 与 null 数) "
              "逐位相同 → B2 的 dsl.py 改动对既有 rank/zscore/winsorize 与 B0 因子零影响; 对照完成后已还原 dsl.py 并校验 sha。"
              "【非缺陷声明】18:16 的 baseline_before.json 与 21:36 重算的 baseline_after.json 现在有 15 个 sha 键不同"
              "(null 数与 rows/symbols 全同), 原因是行情数据在 20:46:42 / 20:54:07 被重建 "
              "(kline_daily/date=2026-11-06, kline_daily_enriched/date=2026-11-06), 该日落在面板区间内; "
              "跨时间哈希对比测到的是数据漂移, 不是代码变更, 故改用同数据新旧 dsl 对照。"),
    dict(id="XS-A4", gate="E3 依赖: in_universe 由 Provider 物化", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={"provider_registered": e2.get("XS-A4_provider_registered"),
                   "compiled_ok": e2.get("compiled_ok")},
         verdict="PASS" if e2.get("XS-A4_provider_registered") and e2.get("compiled_ok") else "FAIL"),
    dict(id="XS-A5", gate="池内成员 x 为 null -> 该成员 null 且不进分母", command=CMD_E2F,
         evidence=art("e2_fixtures.json"), observed=e2f.get("XS-A5_pool_3_one_null"),
         verdict="PASS" if e2f.get("XS-A5_pool_3_one_null", {}).get("pass") else "FAIL"),
    dict(id="XS-A6", gate="空池 -> 全 null (不是 0)", command=CMD_E2F,
         evidence=art("e2_fixtures.json"), observed=e2f.get("XS-A6_empty_pool"),
         verdict="PASS" if e2f.get("XS-A6_empty_pool", {}).get("pass") else "FAIL"),
    dict(id="XS-A7", gate="14 日 ST 窗口: pool/pct 全 null, market 仍非 null", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={k: e2.get(k) for k in ("XS-A7_window_days", "XS-A7_window_first", "XS-A7_window_last",
                                          "XS-A7_pool_nonnull_values", "XS-A7_market_nonnull_values",
                                          "XS-A7_pct_nonnull_values")},
         verdict="PASS" if e2.get("XS-A7_pass") else "FAIL"),
    dict(id="XS-A8", gate="并列取平均名次 (average, 非 ordinal)", command=CMD_E2F,
         evidence=art("e2_fixtures.json"), observed=e2f.get("XS-A8_tie_average"),
         verdict="PASS" if e2f.get("XS-A8_tie_average", {}).get("pass") else "FAIL"),
    dict(id="XS-B1", gate="xs_rank_market 与 rank 逐位相同", command=CMD_E2F,
         evidence=art("e2_fixtures.json"), observed=e2f.get("XS-B1_small_sample"),
         verdict="PASS" if e2f.get("XS-B1_small_sample", {}).get("bitwise_equal") else "FAIL"),
    dict(id="XS-B2", gate="xs_rank_market 值域 (0,1] 且逐日 max==1", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={k: e2.get(k) for k in ("XS-B2_rows", "XS-B2_min", "XS-B2_max", "XS-B2_days",
                                          "XS-B2_days_max_ne_1")},
         verdict="PASS" if e2.get("XS-B2_pass") else "FAIL"),
    dict(id="XS-B3", gate="策略侧对 xs_rank_market / xs_rank_pct 的引用计数 = 0 (与 XS-C3 同)",
         command=CMD_REFS, evidence=art("id_refs_20261107.json"),
         observed={"hard_total": refs.get("hard_total"), "hard_surfaces": refs.get("hard", {}).get("roots"),
                   "soft_total": refs.get("soft_total"), "soft_hits": refs.get("soft", {}).get("hits")},
         verdict="PASS" if refs.get("pass") else "FAIL",
         note="硬面 144 个文件 0 命中; 软面 1 处为 factor_provider.py:52 的注释, 不是引用"),
    dict(id="XS-B3-cover", gate="佐证: 池外行 pool 为 null 而 market 非 null (两条互不等价)", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={"pool_out_of_pool_nonnull": e2.get("XS-A1_out_of_pool_nonnull"),
                   "market_out_of_pool_nonnull": e2.get("XS-B3_out_of_pool_nonnull"),
                   "out_of_pool_rows": e2.get("XS-B3_out_of_pool_rows")},
         verdict="PASS" if e2.get("XS-A1_out_of_pool_nonnull") == 0 and (e2.get("XS-B3_out_of_pool_nonnull") or 0) > 0 else "FAIL",
         note="market 是为诊断而覆盖全样本的 id, 不得当策略可用口径"),
    dict(id="XS-C2", gate="xs_rank_pct 可 >1 (差异证明: 全样本名次 ÷ 池内家数)", command=CMD_E2,
         evidence=art("e2_full.json"),
         observed={"rows": e2.get("XS-C2_rows"), "max": e2.get("XS-C2_max"),
                   "over_1_rows": e2.get("XS-C2_over_1_rows")},
         verdict="PASS" if e2.get("XS-C2_pass") else "FAIL"),
    dict(id="NEG-3.1-4rows", gate="负样本: 契约 §3.1 四行样例上 pool != pct",
         command=CMD_E2F, evidence=art("e2_fixtures.json"), observed=e2f.get("CONTRACT_3_1_four_rows"),
         verdict="PASS" if e2f.get("CONTRACT_3_1_four_rows", {}).get("pass") else "FAIL",
         note="pool={0.5,1.0}, pct={0.5,1.5}: 证明没有把全样本名次当池内名次"),
    dict(id="NEG-pool3of6", gate="负样本: 6 行 3 只入池, pool 分母=3 vs pct 分母=6",
         command=CMD_E2F, evidence=art("e2_fixtures.json"), observed=e2f.get("NEG_pool3_of_6"),
         verdict="PASS" if e2f.get("NEG_pool3_of_6", {}).get("pass") else "FAIL"),
    dict(id="NEG-pool1", gate="负样本: 池内 1 只时 pool=pct=1.0 (不能区分, 如实记录)",
         command=CMD_E2F, evidence=art("e2_fixtures.json"), observed=e2f.get("NEG_pool_one_member"),
         verdict="PASS" if e2f.get("NEG_pool_one_member", {}).get("pass") else "FAIL"),
    dict(id="E017", gate="掩码参数非布尔 -> E017 (新增错误码)", command=CMD_E2F,
         evidence=art("e2_fixtures.json"), observed=e2f.get("E017_rejects"),
         verdict="PASS" if all(e2f.get("E017_rejects", {}).get(k, {}).get("codes") == ["E017"]
                              for k in ("xs_rank_pool(close, volume)", "xs_mean(close, 1)",
                                        "xs_rank_pool(close, close)")) else "FAIL",
         note="第 4 例 xs_rank_market(close, in_universe) 是参数个数错 -> E003, 不是 E017"),
    # ---------------- E1 ----------------
    dict(id="B1", gate="market_breadth 逐日比 (只在两侧均非 null 的交易日要求 <1e-12)", command=CMD_E1,
         evidence=art("e1_verify.json"),
         observed={"compared_days": e1.get("B1_n_compared_days"), "max_abs_diff": e1.get("B1_max_abs_diff"),
                   "mean_abs_diff": e1.get("B1_mean_abs_diff"), "days_over_tol": e1.get("B1_days_over_tol"),
                   "null_days": e1.get("B1_null_days"), "null_reason_counts": e1.get("B1_null_reason_counts"),
                   "null_days_list": e1.get("B1_null_days_list")},
         verdict="PASS" if e1.get("B1_pass") else "FAIL"),
    dict(id="B2", gate="月末通过率与研究侧计数逐月一致 (0.5402298850574713 为靶值)", command=CMD_E1,
         evidence=art("e1_verify.json"),
         observed={"month_ends": e1.get("B2_n_month_end_research"), "compared": e1.get("B2_n_month_end_compared"),
                   "pass_count": e1.get("B2_pass_count"), "pass_rate": e1.get("B2_pass_rate"),
                   "null_list": e1.get("B2_null_month_end_list"),
                   "diagnostic_ref_rate": e1.get("diag_mean_research_full")},
         verdict="PASS" if e1.get("B2_pass") else "FAIL",
         note="0.5407417 是研究侧全窗均值, 属诊断参照不是靶值"),
    dict(id="B3", gate="当日所有行同值 (含池外行); 池内无有效样本 -> null", command=CMD_E1,
         evidence=art("e1_verify.json"),
         observed={"days_with_spread": e1.get("B3_days_with_spread"),
                   "days_with_out_of_pool_broadcast": e1.get("B3_days_with_out_of_pool_broadcast"),
                   "days_with_any_nonnull": e1.get("B3_days_with_any_nonnull")},
         verdict="PASS" if e1.get("B3_pass") else "FAIL"),
    dict(id="B4", gate="空池 -> null 不是 0", command=CMD_E1, evidence=art("e1_verify.json"),
         observed={"values": e1.get("B4_empty_pool_values")},
         verdict="PASS" if e1.get("B4_all_null_not_zero") else "FAIL"),
    dict(id="B5", gate="同输入两跑哈希相同 (确定性)", command=CMD_E1, evidence=art("e1_verify.json"),
         observed={"hash_run1": e1.get("B5_hash_run1"), "hash_run2": e1.get("B5_hash_run2")},
         verdict="PASS" if e1.get("B5_idempotent") else "FAIL"),
    dict(id="B6", gate="warmup == 120", command=CMD_E1, evidence=art("e1_verify.json"),
         observed={"warmup_bars": e1.get("B6_warmup_bars")},
         verdict="PASS" if e1.get("B6_pass") else "FAIL"),
    # ---------------- 接线 (生产 Provider 入口, 不是直调) ----------------
    dict(id="W-A", gate="materialize_factor_columns 产出 Float64 掩码, 值域 ⊆ {1.0,0.0,null}",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-A"),
         verdict=wiring.get("checks", {}).get("W-A", {}).get("verdict", "FAIL")),
    dict(id="W-B", gate="生产入口与直调 compute_in_universe 逐位相同 (同帧 sha256)",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-B"),
         verdict=wiring.get("checks", {}).get("W-B", {}).get("verdict", "FAIL")),
    dict(id="W-C", gate="data_dir 无 st_history -> fail-closed (ValueError), 不静默当非 ST",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-C"),
         verdict=wiring.get("checks", {}).get("W-C", {}).get("verdict", "FAIL")),
    dict(id="W-D", gate="已物化帧上重复调用不重算 (幂等, 值不变)",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-D"),
         verdict=wiring.get("checks", {}).get("W-D", {}).get("verdict", "FAIL")),
    dict(id="W-E", gate="DSL 端到端 xs_rank_pool(close, in_universe): 池内 (0,1] 且与手工逐位相同",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-E"),
         verdict=wiring.get("checks", {}).get("W-E", {}).get("verdict", "FAIL")),
    dict(id="W-E2", gate="池外行必须为 null (池外不是 0)", command=CMD_WIRE,
         evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-E2"),
         verdict=wiring.get("checks", {}).get("W-E2", {}).get("verdict", "FAIL")),
    dict(id="W-F", gate="掩码标签: tags 含 'mask' (E017 静态判定的唯一依据)", command=CMD_WIRE,
         evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-F"),
         verdict=wiring.get("checks", {}).get("W-F", {}).get("verdict", "FAIL")),
    dict(id="W-G", gate="E017 负样本: xs_rank_pool(close, volume) 被拒", command=CMD_WIRE,
         evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-G"),
         verdict=wiring.get("checks", {}).get("W-G", {}).get("verdict", "FAIL")),
    dict(id="W-H", gate="14 日窗口经生产入口同样全 null", command=CMD_WIRE,
         evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-H"),
         verdict=wiring.get("checks", {}).get("W-H", {}).get("verdict", "FAIL")),
    dict(id="W-I", gate="E009 对四个新键生效 (截面算子嵌进时序窗口一律拒), 对照 rank/zscore 不变",
         command=CMD_WIRE, evidence=art("wiring_verify.json"),
         observed=wiring.get("checks", {}).get("W-I"),
         verdict=wiring.get("checks", {}).get("W-I", {}).get("verdict", "FAIL"),
         note="补 v0.8 §10.2 未确证③; 同时证明 in_universe 带 mask 标签被 xs_rank_pool/xs_mean 接受"),
    dict(id="REFS-CANON", gate="引用的因子 id 逐个按 canonical 裁定分类: 无 alias 违规, pack-only 已标注",
         command=CMD_CANON, evidence=art("id_canonical_20261107.json"),
         observed={"e1_referenced_factors": canon.get("e1_referenced_factors"),
                   "all_ids_known": canon.get("all_ids_known"),
                   "alias_violations": canon.get("alias_violations"),
                   "pack_only_used": canon.get("pack_only_used"),
                   "e3_dependencies_are_columns_not_ids": canon.get("e3_dependencies_that_are_factor_ids") == []},
         verdict="PASS" if canon.get("pass") else "FAIL",
         note="E1 formula 实际引用 in_universe + ma60。ma60 属「只有 pack 一侧」的 6 个之一 (无 uf_ma60), "
              "已标注 pack_only=true; 其余 8 组双 id 口径本批一个都没引 (故无 alias 违规)。"
              "E3 的 dependencies 是面板列名 (amount/date/raw_close/symbol/volume), 不参与 id 判定。"),
    # ---------------- 测试红灯归因 (隔离矩阵, 实测) ----------------
    dict(id="T-A", gate="目录/矩阵能力隔离: none 全绿 -> b0_only 转红 -> 全开零新增", command=CMD_PROBE,
         evidence=[art("catalog_support_none.json"), art("catalog_support_b0_only.json"),
                   art("catalog_support_all_on.json")],
         observed={
             "none": {"catalog": load("catalog_support_none.json").get("catalog_size"),
                      "matrix_unsupported": load("catalog_support_none.json").get("matrix_unsupported")},
             "b0_only": {"catalog": load("catalog_support_b0_only.json").get("catalog_size"),
                         "matrix_unsupported": load("catalog_support_b0_only.json").get("matrix_unsupported")},
             "all_on": {"catalog": load("catalog_support_all_on.json").get("catalog_size"),
                        "matrix_unsupported": load("catalog_support_all_on.json").get("matrix_unsupported")},
         },
         verdict="PASS" if (
             load("catalog_support_none.json").get("catalog_size") == 93
             and load("catalog_support_b0_only.json").get("catalog_size") == 107
             and load("catalog_support_all_on.json").get("catalog_size") == 108
             and load("catalog_support_none.json").get("matrix_unsupported") == 14
             and load("catalog_support_b0_only.json").get("matrix_unsupported") == 22
             and load("catalog_support_all_on.json").get("matrix_unsupported") == 23
         ) else "FAIL",
         note="矩阵不可物化数 14(none) -> 22(B0 的 8 个 frame 因子) -> 23(B2 的 in_universe)。"
              "B2 只加 1, 不是「B2 弄坏了矩阵路径」; 矩阵路径代码本批未改 (materialize_matrix_field 仍为基类默认 None)。"),
    dict(id="T-B", gate="factor 套件红/绿只由目录条数决定; B2 实现代码零红灯 (三态实测)", command=CMD_SUITE,
         evidence={"suite_now": art("pytest_after_108_run.json"),
                   "isolation": art("isolation_recheck_108.json"),
                   "all_on_log": art("pytest_factor_suite_all_on.log"),
                   "b0_only_log": art("pytest_factor_suite_b0_only.log")},
         observed={"all_on_108": (ISO_STATES[2]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "b0_only_107": (ISO_STATES[1]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "none_93": (ISO_STATES[0]["factor_suite"] if len(ISO_STATES) == 3 else None),
                   "same_red_set_in_none_and_b0_only": SAME_RED_SET,
                   "catalog_sizes": {s["tag"]: s["catalog_size"] for s in ISO_STATES}},
         verdict="PASS" if (len(ISO_STATES) == 3 and ISO_STATES[2]["failed_tests"] == []
                            and SAME_RED_SET) else "FAIL",
         note="三态都跑同一组 5 文件 (108 口径测试现盘版本): 93 与 107 下失败的永远是同一 6 条计数断言 "
              "(test id 逐字相同), 108 下 74 passed / 0 failed => 任何红灯都只由目录条数决定, 与哪个 pack 在场无关, "
              "也没有一条失败来自 B2 的实现代码。改前那 6 条红的根因经逐条比对全是 count 断言, 无一条属于其他根因; "
              "已按开发经理裁定更新为 108 (未删断言/skip/xfail), 现盘 74P/0F。"),
    # ---------------- 口径差 (不是判据, 供裁定) ----------------
    dict(id="CAL-observed_bars", gate="observed_bars 两口径差异量化 (交付需裁定项)", command=CMD_CAL,
         evidence=art("observed_bars_calibers.json"),
         observed={"rows": cal.get("rows"), "rows_diff_ge120": cal.get("rows_diff_ge120"),
                   "rows_a_only": cal.get("rows_a_ge120_only"), "rows_b_only": cal.get("rows_b_ge120_only"),
                   "diff_by_year": cal.get("diff_by_year"), "diff_in_eval_window": cal.get("diff_in_eval_window")},
         verdict="INFO",
         note="实现取 cum_count(=研究侧, A1 逐日 0 差)。契约 v0.7:125 原文: observed_bars 在研究中 = "
              "date.cum_count().over(symbol)，即该标的在已加载面板内的 bar 行数，不是上市自然日"
              "（并明确「不要自然日差」）; brief 的 listing_date+交易日轴 表述与契约冲突, 按「口径以契约"
              "与因子研究员定义为准」取契约。40,717 标的日不同(评估窗内 17,499), 全部是 listing 口径"
              ">=120 而 bar 口径 <120 的情形"),
]

payload = {
    "batch": "B2 (E3 in_universe → E2 截面排名族 → E1 宽度)",
    "generated_for": "docs/factors/B2_IMPLEMENTATION_20261107.md",
    "rework": {
        "defect": "B-1 (独立审核 B2_ACCEPTANCE_20261107.md: 实现侧 6/6 PASS, 证据包 FAIL)",
        "why": "旧包的 test_status 仍记 6 failed / 68 passed, 且 unchanged_on_purpose 第 4 条写「本批未改任何测试」; "
               "而 20:48:59 两个测试文件已按 108 口径更新, 现盘实测 74 passed / 0 failed, 与旧包不符。",
        "fixes": [
            "test_status 换成现盘实测: 原命令 + ran_at (起止时刻) + pytest/python 版本 + 74 passed / 0 failed, 完整 stdout 落 artifact",
            "unchanged_on_purpose 第 4 条改写为「20:48:59 本部门按 108 口径更新过期断言 (基线更新非回归)」, 附两文件字节/行/sha 与 assert 45→45 / 20→20",
            "isolation 三态重测 (108 口径测试): 93/107/108 + 同一 6 条红集合 (已重跑并落 isolation_recheck_108.json)",
            "49 条断言逐条重跑后重新汇总; 生成器仍无 generated_at、dump 仍排序固定",
        ],
    },
    "git_head": head,
    "contract": "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md §2.6 / §3 / §4.6",
    "paths": {"frame": "Provider + DSL frame_transform", "matrix": "未动 (materialize_matrix_field 保持基类 None)"},
    "changed_files": [
        {"path": "backend/app/factors/dsl.py", "change": "改 +108/−12",
         "note": "xs_rank_pool/xs_rank_market/xs_rank_pct/xs_mean + E017 + MASK_FACTOR_TAG",
         **fil("backend/app/factors/dsl.py")},
        {"path": "backend/app/custom/research_universe_pack/__init__.py", "change": "新增",
         **fil("backend/app/custom/research_universe_pack/__init__.py")},
        {"path": "backend/app/custom/research_universe_pack/factor_provider.py", "change": "新增",
         "note": "Provider 注册 (provider_id=official.research-universe-pack-e3, kind=frame)",
         **fil("backend/app/custom/research_universe_pack/factor_provider.py")},
        {"path": "backend/app/custom/research_universe_pack/universe.py", "change": "新增",
         "note": "compute_in_universe / UniverseParams / universe_diagnostics",
         **fil("backend/app/custom/research_universe_pack/universe.py")},
    ],
    "unchanged_on_purpose": [
        "backend/app/backtest/matrix.py (矩阵路径, materialize_matrix_field 仍为基类 None)",
        "backend/app/factors/registry.py (未改目录顺序/未插队; in_universe 由 Provider 追加在末尾)",
        "high_60d / low_60d 相关文件 (git status 无变更)",
        TESTS_NOTE,
    ],
    "test_status": {
        "command": pt.get("command"),
        "ran_at": {"started_at": pt.get("started_at"), "finished_at": pt.get("finished_at")},
        "tooling": {"pytest": pt.get("pytest_version"), "python": pt.get("python_version")},
        "result": "74 passed / 0 failed",
        "returncode": pt.get("returncode"),
        "summary_line": (pt.get("stdout_tail", "").strip().splitlines() or [""])[-1],
        "artifact": art("pytest_after_108_run.json"),
        "note": "现盘实测: 上方 command 原样执行一次, 起止时刻与完整 stdout 均落在 artifact。"
                "同一命令改前为 6 failed / 68 passed (用例总数同为 74), 差异全部来自 test_files_changed "
                "里那两个文件的计数断言更新, 不是实现改动。",
        "test_files_changed": [
            {"path": "backend/tests/test_factor_registry.py",
             "change": "+22/−6 (git diff --numstat), 只动计数断言与 GOLDEN_COLUMNS 追加",
             "why": "catalog 93→108 的既定基线更新: GOLDEN_COLUMNS 追加 15 条 (B0 14 + B2 in_universe), "
                    "计数断言 93→108 四处、70→85 两处",
             "mtime": "2026-11-07 20:48:59",
             "assert_statements": {"before": 45, "after": 45},
             **reg_f},
            {"path": "backend/tests/test_factor_store.py",
             "change": "+3/−3 (git diff --numstat), 只动断言数字与同步注释",
             "why": "builtin_count 93→108 与两处 == 93 → == 108",
             "mtime": "2026-11-07 20:48:59",
             "assert_statements": {"before": 20, "after": 20},
             **sto_f},
        ],
        "assertion_coverage_preserved": "未删任何断言、未加 skip/xfail、未用 -k 排除、未把精确计数改成 >=93 "
                                        "这类无判别力写法; `assert ` 语句数 45→45 / 20→20 (0 删除)。",
        "classification": "改前那 6 条红的根因已核实: 全部是「目录条数硬编码 93」类断言 "
                          "(test_factor_registry 5 条 + test_factor_store 1 条), 无一条属于其他根因。"
                          "按开发经理裁定「不重定基线、按新事实更新过期断言值」已改为 108, 现盘全绿。",
        "matrix_catalog_test": {
            "id": "tests/backtest/test_matrix_strategy.py::test_research_factor_catalog_matches_matrix_features",
            "result": "FAILED (2026-11-07 21:40 现盘实测: 1 failed)",
            "probe": "research/b2-engine-20261107/probe_matrix_catalog.py",
            "detail": "矩阵路径对 16 个目录 id 无物化能力: 8 个财务 (测试自身有 fundamental 分支, 不是失败点) + 8 个 B0 pack "
                      "frame 因子 (sd20/vol60/prior_high_20/prior_low_10/prior_high_55/prior_vol_20/prior_high_250/"
                      "prior_amount_20) + in_universe。8 个 B0 id 在本批改动前就无可物化能力, 故该测试自 B0 注册起即红, "
                      "本批使失败点前移到 in_universe。修法属 B0b (补 materialize_matrix_field) 或由架构裁定排除表。",
            "out_of_scope": "不在本批 5 文件套件内; 该测试文件未被修改 (git status 无该文件), 按派工不动 matrix.py、不接 B0b。",
        },
        "isolation": {
            "why": "把 pack 目录 mv 出 app/custom 三态重跑同一组 5 文件 (108 口径测试现盘版本) + 目录探针, "
                   "证明「红/绿的唯一决定因素是目录条数」, 且三态都能完整还原。",
            "measured_at": iso.get("measured_at"),
            "tests_version": iso.get("tests_version"),
            "artifact": art("isolation_recheck_108.json"),
            "states": ISO_STATES,
            "same_red_set_in_none_and_b0_only": SAME_RED_SET,
            "restored_after_experiment": iso.get("restored"),
            "matrix_catalog_test_per_state": {
                "source": "19:47–19:54 实测, 与本批测试文件更新无关 (tests/backtest/test_matrix_strategy.py 未改动), "
                          "目录内容 93/107/108 未变, 故仍成立",
                "none": "PASSED (30 passed)",
                "b0_only": "FAILED — ValueError: unsupported matrix feature: prior_amount_20",
                "all_on": "FAILED — ValueError: in_universe 缺少必需列: ['raw_close']",
            },
            "conclusion": "none(93) 与 b0_only(107) 两态失败的永远是同一 6 条计数断言 (test id 逐字相同), "
                          "all_on(108) 为 74 passed / 0 failed => 红/绿只由目录条数决定, 与哪个 pack 在场无关, "
                          "也没有任何一条失败来自 B2 的实现代码。推论: 两个 pack 目录若不进版本库, 干净检出=93, "
                          "这 6 条会一直红 => 故本批将其 git add (只 add, 不 commit)。",
        },
    },
    "decisions_needed": [
        {"id": "D-B2-1", "topic": "observed_bars 口径",
         "conflict": "brief 要求 instruments.listing_date + 交易日轴 (不要 bar 序号); 契约 v0.7:125 明确定义为 "
                     "date.cum_count().over(symbol) 即面板内 bar 行数, 并写明「不是上市自然日」。",
         "taken": "按契约与因子研究员定义实现 (cum_count), E3-A1 与研究侧逐日 0 差。",
         "if_overruled": "改 min_observed_bars 的输入为 listing_date+交易日轴, 需重跑 E3/E1/E2 全部判据; 差异量已量化在 CAL-observed_bars (40,717 标的日, 评估窗内 17,499)。"},
        {"id": "D-B2-2", "topic": "in_universe 是否进 /api/factors 目录",
         "detail": "Provider 注册即进目录 (扩展点既定行为, B0 的 14 个同理), 故 /api/factors 由 107 变 108。若要求 E3 掩码不进对外目录, 需改扩展点语义 (影响 B0)。"},
        {"id": "D-B2-3", "topic": "xs_rank_pct 的登记形态",
         "detail": "已实现为诊断形态 (strategy_usable=false / replaced_by=xs_rank_pool 属台账口径, registry 无该字段)。是否入台账/以何种 status 登记, 由因子工程师定; 本批不进验收。"},
    ],
    "assertions": assertions,
    "summary": {
        "PASS": sum(1 for a in assertions if a["verdict"] == "PASS"),
        "FAIL": sum(1 for a in assertions if a["verdict"] == "FAIL"),
        "INFO": sum(1 for a in assertions if a["verdict"] == "INFO"),
        "total": len(assertions),
    },
    "not_done": [
        "矩阵路径 in_universe (materialize_matrix_field) — 契约 §7.13/§7.14 归 B0b, 等 v0.7 落盘后按 F-A11a–d",
        "矩阵路径 xs_* (market matrix 里没有 date 截面 group_by 之外的新结构; 本批只做 frame)",
        "high_60d / low_60d 未改 (git status 无该文件变更)",
        "未向生产因子目录 (D:/TSP/data/user_data/custom_factors) 注册任何新因子; 未跑收益回测; 未提交; 未部署",
        "E4 (month_end / rebalance 轴) 不在本批范围",
        "矩阵目录测试 (tests/backtest/test_matrix_strategy.py) 仍红: 矩阵路径无 materialize_matrix_field, 归 B0b, 本批按派工不接",
        "6 条「目录=93」测试已于 2026-11-07 20:48:59 按 108 口径更新断言, 现盘 74 passed / 0 failed (见 test_status)",
    ],
}

out = B2 / "EVIDENCE_20261107.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str, sort_keys=True), encoding="utf-8")
print(json.dumps(payload["summary"], ensure_ascii=False))
print("written", out, out.stat().st_size, "bytes")
print("sha256", sha(out))
