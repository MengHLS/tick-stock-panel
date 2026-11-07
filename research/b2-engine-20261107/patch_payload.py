"""给 evidence_build.py 的 payload 补 changed_files 指纹 / test_status / decisions。"""
from pathlib import Path

p = Path("research/b2-engine-20261107/evidence_build.py")
s = p.read_text(encoding="utf-8")

helper_anchor = 'def art(name: str) -> dict:'
helper = '''def fil(path: str) -> dict:
    f = ROOT / path
    return {"path": path, "bytes": f.stat().st_size, "sha256": sha(f),
            "lines": len(f.read_text(encoding="utf-8").splitlines())} if f.exists() else \
           {"path": path, "missing": True}


'''
assert s.count(helper_anchor) == 1
s = s.replace(helper_anchor, helper + helper_anchor)

old_cf = '''    "changed_files": [
        {"path": "backend/app/factors/dsl.py", "change": "+108/−12", "note": "xs_rank_pool/xs_rank_market/xs_rank_pct/xs_mean + E017"},
        {"path": "backend/app/custom/research_universe_pack/__init__.py", "change": "新增"},
        {"path": "backend/app/custom/research_universe_pack/factor_provider.py", "change": "新增"},
        {"path": "backend/app/custom/research_universe_pack/universe.py", "change": "新增"},
    ],'''
new_cf = '''    "changed_files": [
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
        "backend/tests/** (本批未改任何测试; 见 test_status)",
    ],
    "test_status": {
        "command": "cd C:/work/sourcecode/tick-stock-panel/backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe "
                   "-m pytest tests/test_factor_dsl.py tests/test_factor_registry.py tests/test_factor_api.py "
                   "tests/test_factor_store.py tests/test_factor_provider_contracts.py -q",
        "result": "6 failed / 68 passed",
        "classification": "全部为「目录条数硬编码 93」类断言: 6 条失败 (test_factor_registry 5 条 + "
                          "test_factor_store 1 条)。B0 批把 14 个 pack 因子注册进目录后已是 107 (5+1 条自那时起即红), "
                          "本批 in_universe 使其变 108。非本批引入, 也非本批可单独修复 (要么重定基线, 要么让 in_universe "
                          "不进目录, 而后者会让 DSL 无法解析掩码)。",
        "matrix_catalog_test": {
            "id": "tests/backtest/test_matrix_strategy.py::test_research_factor_catalog_matches_matrix_features",
            "result": "FAILED",
            "probe": "research/b2-engine-20261107/probe_matrix_catalog.py",
            "detail": "矩阵路径对 16 个目录 id 无物化能力: 8 个财务 (测试自身有 fundamental 分支, 不是失败点) + 8 个 B0 pack "
                      "frame 因子 (sd20/vol60/prior_high_20/prior_low_10/prior_high_55/prior_vol_20/prior_high_250/"
                      "prior_amount_20) + in_universe。8 个 B0 id 在本批改动前就无可物化能力, 故该测试自 B0 注册起即红, "
                      "本批使失败点前移到 in_universe。修法属 B0b (补 materialize_matrix_field) 或由架构裁定排除表。",
        },
        "note": "本批未修改该测试 (一度加过 FRAME_ONLY_FACTOR_IDS 排除+失效断言, 因 8 个 B0 id 仍红、无法变绿且会掩盖 B0b 缺口, 已 git checkout 还原)。",
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
    ],'''
assert s.count(old_cf) == 1
s = s.replace(old_cf, new_cf)

old_nd = '''    "not_done": [
        "矩阵路径 in_universe (materialize_matrix_field) — 契约 §7.13/§7.14 归 B0b, 等 v0.7 落盘后按 F-A11a–d",
        "high_60d / low_60d 未改 (git status 无该文件变更)",
        "未注册任何新因子到生产目录; 未跑收益回测; 未提交; 未部署",
        "E4 (month_end / rebalance 轴) 不在本批范围",
    ],'''
new_nd = '''    "not_done": [
        "矩阵路径 in_universe (materialize_matrix_field) — 契约 §7.13/§7.14 归 B0b, 等 v0.7 落盘后按 F-A11a–d",
        "矩阵路径 xs_* (market matrix 里没有 date 截面 group_by 之外的新结构; 本批只做 frame)",
        "high_60d / low_60d 未改 (git status 无该文件变更)",
        "未向生产因子目录 (D:/TSP/data/user_data/custom_factors) 注册任何新因子; 未跑收益回测; 未提交; 未部署",
        "E4 (month_end / rebalance 轴) 不在本批范围",
        "6 条「目录=93」测试仍红 + 矩阵目录测试仍红, 见 test_status (需裁定, 本批未改测试)",
    ],'''
assert s.count(old_nd) == 1
s = s.replace(old_nd, new_nd)

p.write_text(s, encoding="utf-8")
print("patched payload")
