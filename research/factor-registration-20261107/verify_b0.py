"""B0 注册验收脚本 — 14 个研究基线因子。

判据 (逐条对应 @开发经理 的验收清单):
  1. 注册后 compile_formula("<id> > 0").ok == True, 14/14。
  2. 数值保真: 2019-07-01~2026-10-30 全样本, 与研究侧/指标层同名列比对,
     max_abs_diff == 0 且 n > 5.4e6。
  3. prior_* 与 high_60d 的 jaccard < 1 (证明不是改名)。
  4. warmup: 每标的第一个非空位置 = 理论窗口位置, 其前一根为 null, warmup_bars >= 位置+1。
  5. 幂等: 连续注册两次不产生重复 id / 不抬版本 / 不报错。

只读: 不改任何既有因子、不动 app/factors/dsl.py 与注册表内核。
输出: docs/factors/evidence/registration_b0_20261107.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
for extra in (PROJECT / "backend", PROJECT / "research" / "strategy-search-20261107" / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import common  # research/strategy-search-20261107/scripts/common.py
import numpy as np
import polars as pl

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)

# 因子 id -> 研究侧 (common.add_indicators) 同名列
FACTORS: tuple[tuple[str, str], ...] = (
    ("ma20", "ma20"),
    ("ma60", "ma60"),
    ("boll_lower", "bb_lower"),
    ("boll_upper", "bb_upper"),
    ("sd20", "sd20"),
    ("prior_high_20", "prior_high20"),
    ("prior_low_10", "prior_low10"),
    ("prior_high_55", "prior_high55"),
    ("prior_vol_20", "prior_vol20"),
    ("ma120", "ma120"),
    ("vol60", "vol60"),
    ("prior_high_250", "prior_high250"),
    ("prior_amount_20", "prior_amount20"),
    ("ma200", "ma200"),
)
FACTOR_IDS = tuple(fid for fid, _ in FACTORS)

# 指标层同名列 (compute_indicators) 可直接比对的 4 个
INDICATOR_PAIRS = {
    "ma20": "ma20",
    "ma60": "ma60",
    "boll_lower": "boll_lower",
    "boll_upper": "boll_upper",
}

BASE_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
CHUNK_SYMBOLS = 300

EXPECTED_FIRST_VALID = {
    "ma20": 19, "ma60": 59, "ma120": 119, "ma200": 199, "sd20": 19,
    "boll_lower": 19, "boll_upper": 19,
    "prior_high_20": 20, "prior_low_10": 10, "prior_high_55": 55,
    "prior_high_250": 250, "prior_vol_20": 20, "prior_amount_20": 20,
    "vol60": 60,
}


def _clean(series: pl.Series) -> pl.Series:
    """NaN 视为缺失 (与 null 同处理), 保证 diff 不被 NaN 污染。"""
    return series.cast(pl.Float64).fill_nan(None)


def step1_compile() -> dict:
    from app.factors.dsl import compile_formula
    from app.factors.registry import get_factor

    rows = []
    for fid in FACTOR_IDS:
        compiled = compile_formula(f"{fid} > 0")
        spec = get_factor(fid)
        rows.append(
            {
                "id": fid,
                "compile_ok": bool(compiled.ok),
                "errors": [e.code for e in compiled.errors],
                "registered": spec is not None,
                "kind": getattr(spec, "kind", None),
                "group": getattr(spec, "group", None),
                "warmup_bars": getattr(spec, "warmup_bars", None),
                "dependencies": sorted(getattr(spec, "dependencies", ())),
                "formula": getattr(spec, "formula_text", None),
                "version": getattr(spec, "version", None),
            }
        )
    ok = all(r["compile_ok"] and r["registered"] for r in rows)
    return {"ok": ok, "n_ok": sum(1 for r in rows if r["compile_ok"]), "rows": rows}


def step5_idempotent() -> dict:
    from app.custom.research_factor_pack.factor_provider import FACTOR_PROVIDERS
    from app.extensions.factors import ensure_factor_providers, register_factor_provider
    from app.factors.registry import all_factors, get_factor

    ensure_factor_providers()
    before = {fid: get_factor(fid).version for fid in FACTOR_IDS}
    total_before = len(all_factors())
    error = None
    try:
        # (1) 再走一次自动发现 (启动期重复调用)
        ensure_factor_providers()
        # (2) 再直接注册同一个 provider 实例 (同内容重复注册)
        register_factor_provider(FACTOR_PROVIDERS[0])
    except Exception as exc:  # noqa: BLE001 - 失败要落进证据
        error = f"{type(exc).__name__}: {exc}"
    after = {fid: get_factor(fid).version for fid in FACTOR_IDS}
    total_after = len(all_factors())
    counts = {fid: sum(1 for s in all_factors() if s.id == fid) for fid in FACTOR_IDS}
    return {
        "ok": error is None
        and before == after
        and total_before == total_after
        and all(v == 1 for v in counts.values()),
        "error": error,
        "versions_before": before,
        "versions_after": after,
        "total_factors_before": total_before,
        "total_factors_after": total_after,
        "duplicate_counts": counts,
    }


def step2_3_4() -> dict:
    from app.indicators.pipeline import compute_indicators
    from app.strategy.scoring import materialize_scoring_columns

    started = time.perf_counter()
    market = common.open_market()
    frame = common.load_panel(market)
    print(
        f"[data] rows={frame.height} symbols={frame['symbol'].n_unique()} "
        f"({time.perf_counter() - started:.1f}s)",
        flush=True,
    )

    symbols = frame["symbol"].unique().sort().to_list()
    acc = {
        fid: {
            "max_abs_diff": 0.0,
            "n_both": 0,
            "ref_notnull_platform_null": 0,
            "ref_null_platform_notnull": 0,
            "indicator_max_abs_diff": None,
            "indicator_n": 0,
            "ref_null_rows": 0,
        }
        for fid in FACTOR_IDS
    }
    jaccard = {
        "prior_high_20_vs_high_60d": {"both_true": 0, "union_true": 0},
        "prior_high_55_vs_high_60d": {"both_true": 0, "union_true": 0},
        "prior_high_250_vs_high_60d": {"both_true": 0, "union_true": 0},
    }
    # 值级判重 (jaccard 之外的第二道): 与 high_60d 逐位相等且两边都非空的行数。
    # jaccard 在 high_60d 含当日 high 时是单边的, 只能证明"不是别名"的方向,
    # 逐位相等计数才能排除 prior_* 就是 high_60d 改名。
    value_identity = {
        "prior_high_20_vs_high_60d": {"n_both": 0, "n_exact_equal": 0},
        "prior_high_55_vs_high_60d": {"n_both": 0, "n_exact_equal": 0},
        "prior_high_250_vs_high_60d": {"n_both": 0, "n_exact_equal": 0},
    }
    rows_eval_total = 0

    chunks = [symbols[i:i + CHUNK_SYMBOLS] for i in range(0, len(symbols), CHUNK_SYMBOLS)]
    for idx, chunk in enumerate(chunks, 1):
        part = frame.filter(pl.col("symbol").is_in(chunk)).sort(["symbol", "date"])
        if part.is_empty():
            continue

        # 研究侧参考列 (common.add_indicators, 口径冻结来源)
        reference = common.add_indicators(part)
        # 指标层同名列 (正式系统 compute_indicators)
        indicators = compute_indicators(
            part,
            needed=set(INDICATOR_PAIRS.values()) | {"high_60d"},
            assume_sorted=True,
        )

        base = part.select(BASE_COLUMNS)
        platform = materialize_scoring_columns(base, FACTOR_IDS)

        keep = (
            (reference["date"] >= EVAL_START) & (reference["date"] <= EVAL_END)
        ).alias("_keep")
        n_eval = int(reference.select(keep)["_keep"].sum())
        if n_eval == 0:
            continue
        rows_eval_total += n_eval

        for fid, ref_col in FACTORS:
            a = _clean(platform[fid]).filter(keep)
            b = _clean(reference[ref_col]).filter(keep)
            both = a.is_not_null() & b.is_not_null()
            diff = (a - b).abs().filter(both)
            block = acc[fid]
            block["max_abs_diff"] = max(block["max_abs_diff"], float(diff.max() or 0.0))
            block["n_both"] += int(both.sum())
            block["ref_notnull_platform_null"] += int((b.is_not_null() & a.is_null()).sum())
            block["ref_null_platform_notnull"] += int((b.is_null() & a.is_not_null()).sum())
            block["ref_null_rows"] += int(b.is_null().sum())
            if fid in INDICATOR_PAIRS:
                c = _clean(indicators[INDICATOR_PAIRS[fid]]).filter(keep)
                both_i = a.is_not_null() & c.is_not_null()
                d_i = (a - c).abs().filter(both_i)
                m = float(d_i.max() or 0.0)
                block["indicator_max_abs_diff"] = max(
                    block["indicator_max_abs_diff"] or 0.0, m
                )
                block["indicator_n"] += int(both_i.sum())

        # jaccard: close > prior_* vs close > high_60d
        close = _clean(part["close"])
        h60 = _clean(indicators["high_60d"])
        for fid, key in (
            ("prior_high_20", "prior_high_20_vs_high_60d"),
            ("prior_high_55", "prior_high_55_vs_high_60d"),
            ("prior_high_250", "prior_high_250_vs_high_60d"),
        ):
            pv = _clean(platform[fid])
            valid = close.is_not_null() & pv.is_not_null() & h60.is_not_null() & keep
            cond_a = (close > pv).fill_null(False)
            cond_b = (close > h60).fill_null(False)
            both_true = int((cond_a & cond_b & valid).sum())
            union_true = int(((cond_a | cond_b) & valid).sum())
            jaccard[key]["both_true"] += both_true
            jaccard[key]["union_true"] += union_true
            both_nonnull = pv.is_not_null() & h60.is_not_null() & keep
            value_identity[key]["n_both"] += int(both_nonnull.sum())
            value_identity[key]["n_exact_equal"] += int(
                ((pv == h60) & both_nonnull).sum()
            )

        print(
            f"[chunk {idx}/{len(chunks)}] rows={part.height} eval={n_eval} "
            f"({time.perf_counter() - started:.1f}s)",
            flush=True,
        )

    for block in jaccard.values():
        block["jaccard"] = (
            block["both_true"] / block["union_true"] if block["union_true"] else None
        )
        block["n"] = block["union_true"]

    # ---- warmup 抽查: 取行数最多的标的, 逐因子定位第一个非空位置 ----
    from app.factors.registry import get_factor

    longest = (
        frame.group_by("symbol")
        .len()
        .sort(["len", "symbol"], descending=[True, False])
        .head(1)["symbol"][0]
    )
    one = frame.filter(pl.col("symbol") == longest).sort("date")
    plat_one = materialize_scoring_columns(one.select(BASE_COLUMNS), FACTOR_IDS)
    warmup_rows = []
    for fid in FACTOR_IDS:
        values = _clean(plat_one[fid]).to_numpy()
        first_valid = int(np.argmax(np.isfinite(values)))
        prev_ok = first_valid == 0 or not np.isfinite(values[first_valid - 1])
        spec = get_factor(fid)
        warmup_rows.append(
            {
                "id": fid,
                "symbol": longest,
                "bars": int(plat_one.height),
                "first_valid_index_0based": first_valid,
                "expected_index": EXPECTED_FIRST_VALID[fid],
                "index_matches": first_valid == EXPECTED_FIRST_VALID[fid],
                "index_minus_1_is_null": bool(prev_ok),
                "value_at_first_valid": float(values[first_valid]),
                "warmup_bars": spec.warmup_bars,
                "warmup_bars_ge_index_plus_1": spec.warmup_bars >= first_valid + 1,
            }
        )

    # 窗口值手算对照 (独立于参考列, 3 个代表因子)
    close = one["close"].to_numpy()
    high = one["high"].to_numpy()
    manual = {
        "ma20": float(np.mean(close[:20])),
        "prior_high_55": float(np.max(high[:55])),
        "vol60": float(np.std(np.diff(close[:61]) / close[:60], ddof=1)),
    }
    ids = [r["id"] for r in warmup_rows]
    manual_rows = []
    for fid, value in manual.items():
        got = warmup_rows[ids.index(fid)]["value_at_first_valid"]
        manual_rows.append(
            {
                "id": fid,
                "manual_value": value,
                "platform_value": got,
                "abs_diff": abs(float(got) - value),
            }
        )

    for block in value_identity.values():
        block["exact_equal_share"] = (
            block["n_exact_equal"] / block["n_both"] if block["n_both"] else None
        )

    # 逐条判据 (验收清单 2/3/4), 不做人工目测
    checks = []
    for fid, _ in FACTORS:
        b = acc[fid]
        b["n_reachable"] = b["n_both"] + b["ref_null_rows"]
        b["n_floor_5_4e6_ok"] = b["n_both"] > 5_400_000
        checks.append(
            {
                "id": fid,
                "max_abs_diff_zero": b["max_abs_diff"] == 0.0,
                "no_missing_on_platform": b["ref_notnull_platform_null"] == 0,
                "no_extra_on_platform": b["ref_null_platform_notnull"] == 0,
                "n_gt_5.4e6": b["n_floor_5_4e6_ok"],
                "n_reachable": b["n_reachable"],
            }
        )

    return {
        "rows_total": frame.height,
        "rows_eval": rows_eval_total,
        "per_factor": acc,
        "jaccard": jaccard,
        "value_identity_vs_high_60d": value_identity,
        "warmup": warmup_rows,
        "warmup_manual": manual_rows,
        "checks": checks,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


def main() -> int:
    from app.config import settings

    print(f"[config] data_dir={settings.data_dir}", flush=True)
    compiled = step1_compile()
    print(f"[step1] compile_ok {compiled['n_ok']}/{len(FACTOR_IDS)}", flush=True)
    idem = step5_idempotent()
    print(f"[step5] idempotent={idem['ok']} error={idem['error']}", flush=True)
    fidelity = step2_3_4()

    import hashlib

    kernel = {}
    for rel in (
        "backend/app/factors/dsl.py",
        "backend/app/factors/registry.py",
        "backend/app/factors/store.py",
        "backend/app/extensions/factors.py",
        "backend/app/strategy/scoring.py",
    ):
        data = (PROJECT / rel).read_bytes()
        kernel[rel] = hashlib.sha256(data).hexdigest()
    git_status = __import__("subprocess").run(
        ["git", "status", "--porcelain", "--", "backend"],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kernel_files_sha256": kernel,
        "git_status_backend": git_status,
        "data_dir": str(settings.data_dir),
        "window": {"start": str(EVAL_START), "end": str(EVAL_END)},
        "registration_path": (
            "app/custom/research_factor_pack/factor_provider.py "
            "(FactorProvider 注册入口), 计算走既有 DSL"
        ),
        "step1_compile": compiled,
        "step5_idempotent": idem,
        "fidelity": fidelity,
    }

    print("\n== step1 compile ==")
    print(f"{compiled['n_ok']}/{len(FACTOR_IDS)} ids compile OK")
    print("\n== fidelity ==")
    print(f"{'id':18s} {'max_abs_diff':>14s} {'n':>12s} {'ref!null&plat_null':>19s} "
          f"{'ind.max_abs_diff':>18s}")
    for fid, _ in FACTORS:
        b = fidelity["per_factor"][fid]
        ind = b["indicator_max_abs_diff"]
        print(
            f"{fid:18s} {b['max_abs_diff']:14.6g} {b['n_both']:12d} "
            f"{b['ref_notnull_platform_null']:19d} "
            f"{('nan' if ind is None else format(ind, '.6g')):>18s}"
        )
    print("\n== jaccard vs high_60d ==")
    for key, block in fidelity["jaccard"].items():
        print(
            f"{key}: jaccard={block['jaccard']} both_true={block['both_true']} "
            f"union={block['union_true']}"
        )
    print("\n== value identity vs high_60d (逐位相等) ==")
    for key, block in fidelity["value_identity_vs_high_60d"].items():
        print(
            f"{key}: n_both={block['n_both']} n_exact_equal={block['n_exact_equal']} "
            f"share={block['exact_equal_share']}"
        )
    print("\n== reachable rows / 判据 ==")
    print(f"{'id':18s} {'n':>10s} {'n_reachable':>12s} {'diff0':>6s} {'no_miss':>8s} "
          f"{'no_extra':>9s} {'n>5.4e6':>8s}")
    for row in fidelity["checks"]:
        b = fidelity["per_factor"][row["id"]]
        print(
            f"{row['id']:18s} {b['n_both']:10d} {row['n_reachable']:12d} "
            f"{row['max_abs_diff_zero']!s:>6s} {row['no_missing_on_platform']!s:>8s} "
            f"{row['no_extra_on_platform']!s:>9s} {row['n_gt_5.4e6']!s:>8s}"
        )
    print("\n== warmup ==")
    for row in fidelity["warmup"]:
        print(
            f"{row['id']:18s} first_valid={row['first_valid_index_0based']:4d} "
            f"expected={row['expected_index']:4d} match={row['index_matches']} "
            f"prev_null={row['index_minus_1_is_null']} warmup={row['warmup_bars']} "
            f"ok={row['warmup_bars_ge_index_plus_1']}"
        )
    print("\n== warmup manual ==")
    for row in fidelity["warmup_manual"]:
        print(
            f"{row['id']:18s} manual={row['manual_value']!r} "
            f"platform={row['platform_value']!r} diff={row['abs_diff']}"
        )
    print(
        f"\n[step5] idempotent={idem['ok']} total_factors={idem['total_factors_after']} "
        f"duplicates={set(idem['duplicate_counts'].values())}"
    )

    out = Path(
        r"C:\work\sourcecode\tick-stock-panel\docs\factors\evidence\registration_b0_20261107.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[evidence] {out} ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
