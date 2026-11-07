"""B0b-1 done_when 1: 真盘 8 组双 id 各出 FS03、8 只 canonical 不出。

口径:
* 事实源 = 生产注册表。先 store.load_into_registry(D:/TSP/data/user_data)(8 只 uf_* 
  canonical 在盘上), 再 ensure_factor_providers()(pack 的 8 条 _ALIAS_OF 由此进入
  FactorSpec.alias_of)。
* 真盘 custom_factors/*.json 里没有 alias_of 键(15 文件全无), 所以 alias 侧只能来自
  pack —— 这正是本批要证明的「载体打通」。
* mode=production 判 FS03。canonical 侧若因 status=draft 得 FS01, 不算 FAIL(本判据只
  要求「不出 FS03」), 但会逐条记在 codes 里。

用法: cd backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe ../research/b0b-20261107/verify_fs03_realdisk.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

DATA_DIR = Path("D:/TSP/data")  # data_dir 根: 定义在 user_data/custom_factors/

# 契约 7.15.1 第 1-8 行: alias -> canonical。表在 pack 里, 这里只用来列判据,
# 不是第二份权威(脚本先断言 pack 表与这份清单一致, 不一致直接 FAIL)。
ALIAS_PAIRS = {
    "vol60": "uf_vol60",
    "ma120": "uf_ma120",
    "ma200": "uf_ma200",
    "prior_high_20": "uf_prior_high_20",
    "prior_high_55": "uf_prior_high_55",
    "prior_high_250": "uf_prior_high_250",
    "prior_low_10": "uf_prior_low_10",
    "prior_vol_20": "uf_prior_vol_20",
}


def main() -> int:
    from app.factors import gate, registry, store
    from app.extensions.factors import ensure_factor_providers, factor_provider_status

    store.load_into_registry(DATA_DIR)
    ensure_factor_providers()
    status = factor_provider_status()

    checks: list[dict] = []

    def check(name, ok, detail):
        checks.append({"id": name, "ok": bool(ok), "detail": detail})

    from app.custom.research_factor_pack.factor_specs import _ALIAS_OF
    check("P0.alias_table_matches", _ALIAS_OF == ALIAS_PAIRS,
          {"pack": _ALIAS_OF, "script": ALIAS_PAIRS})
    check("P1.providers_ready", status["ready"] is True,
          {"state": status["state"], "providers": status["providers"]})
    missing = sorted(cid for cid in ALIAS_PAIRS.values()
                     if not (DATA_DIR / "user_data" / "custom_factors" / (cid + ".json")).is_file())
    check("P2.canonical_on_disk", not missing, missing)

    alias_rows = []
    for alias, canonical in ALIAS_PAIRS.items():
        spec = registry.get_factor(alias)
        facts = gate.RegistryFacts(DATA_DIR).facts(alias)
        source = gate.RegistryFacts(DATA_DIR)
        try:
            gate.assert_factors_usable([alias], "production", facts=source)
            codes, error = [], None
        except gate.GateError as exc:
            codes = [item[2] for item in exc.report.blocked]
            error = exc.code
        row = {
            "alias": alias, "canonical": canonical,
            "registered": spec is not None,
            "spec_alias_of": None if spec is None else spec.alias_of,
            "spec_strategy_usable": None if spec is None else spec.strategy_usable,
            "facts_alias_of": facts.alias_of,
            "error_code": error, "blocked_codes": codes,
        }
        row["ok"] = error == "FS03" and "FS03" in codes
        alias_rows.append(row)
    check("A1.eight_aliases_all_FS03", all(r["ok"] for r in alias_rows),
          {"failing": [r["alias"] for r in alias_rows if not r["ok"]]})

    canonical_rows = []
    for alias, canonical in ALIAS_PAIRS.items():
        try:
            gate.assert_factors_usable([canonical], "production", facts=gate.RegistryFacts(DATA_DIR))
            codes, error = [], None
        except gate.GateError as exc:
            codes = [item[2] for item in exc.report.blocked]
            error = exc.code
        spec = registry.get_factor(canonical)
        row = {
            "canonical": canonical, "registered": spec is not None,
            "spec_alias_of": None if spec is None else spec.alias_of,
            "error_code": error, "blocked_codes": codes,
        }
        row["ok"] = "FS03" not in codes and error != "FS03"
        canonical_rows.append(row)
    check("A2.eight_canonicals_no_FS03", all(r["ok"] for r in canonical_rows),
          {"failing": [r["canonical"] for r in canonical_rows if not r["ok"]]})

    diagnostic_codes = []
    for alias in ALIAS_PAIRS:
        try:
            gate.assert_factors_usable([alias], "diagnostic", facts=gate.RegistryFacts(DATA_DIR))
            diagnostic_codes.append(None)
        except gate.GateError as exc:
            diagnostic_codes.append(exc.code)
    check("A3.diagnostic_does_not_reject_alias", all(c is None for c in diagnostic_codes),
          diagnostic_codes)

    check("A4.spec_carrier",
          all(registry.get_factor(a).alias_of == c for a, c in ALIAS_PAIRS.items())
          and all(registry.get_factor(c).alias_of is None for c in ALIAS_PAIRS.values()),
          {a: registry.get_factor(a).alias_of for a in ALIAS_PAIRS})

    json_keys = {}
    for path in sorted((DATA_DIR / "user_data" / "custom_factors").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        json_keys[path.stem] = "alias_of" in payload
    check("A5.disk_json_has_no_alias_of", not any(json_keys.values()), json_keys)

    # 信息项（ok 恒 True, 不设阈值）: canonical 侧出不出 FS01 完全由这一列决定 ——
    # status=draft 时 §7.16.3 按「非 active」拒并记 FS01, active 时无 FS01。
    # 2026-11-07 23:33:57 外部把这 8 个文件由 draft 改成 active（created_at 未变、
    # updated_at 刷新），证据里的 codes 随之从 ['FS01'] 变 []；判据 A2 两边都成立
    # （只要求「不出 FS03」）。把快照写进证据, 让数字可被后来的读方对上。
    status_snapshot = {}
    for cid in ALIAS_PAIRS.values():
        payload = json.loads((DATA_DIR / "user_data" / "custom_factors" / (cid + ".json"))
                             .read_text(encoding="utf-8"))
        status_snapshot[cid] = payload.get("status")
    check("A6.disk_status_snapshot_info", True, status_snapshot)

    failed = [c for c in checks if not c["ok"]]
    payload = {
        "checks": checks,
        "summary": {"total": len(checks), "passed": len(checks) - len(failed), "failed": len(failed)},
        "alias_rows": alias_rows, "canonical_rows": canonical_rows,
        "provider_status": status,
    }
    out = Path(__file__).with_name("logs") / "fs03_realdisk.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for c in checks:
        print(("PASS " if c["ok"] else "FAIL ") + c["id"])
    print()
    for r in alias_rows:
        print("alias  %-16s -> %-18s alias_of=%-18s usable=%-5s codes=%s" % (
            r["alias"], r["canonical"], r["spec_alias_of"], r["spec_strategy_usable"], r["blocked_codes"]))
    print()
    for r in canonical_rows:
        print("canon  %-18s alias_of=%-6s codes=%s" % (r["canonical"], r["spec_alias_of"], r["blocked_codes"]))
    print()
    print("summary:", payload["summary"], "->", out)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
