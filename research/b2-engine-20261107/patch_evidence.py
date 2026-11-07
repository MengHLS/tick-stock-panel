"""给 evidence_build.py 追加接线判据 (W-A..W-H) 与测试现状块。一次性补丁脚本。"""
from pathlib import Path

p = Path("research/b2-engine-20261107/evidence_build.py")
s = p.read_text(encoding="utf-8")

# 1) 载入接线日志
old_load = 'refs = load("id_refs_20261107.json")'
new_load = 'refs = load("id_refs_20261107.json")\nwiring = load("wiring_verify.json")'
assert s.count(old_load) == 1
s = s.replace(old_load, new_load)

old_cmd = 'CMD_REFS = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "\n            "research/b2-engine-20261107/verify_id_refs.py")'
new_cmd = old_cmd + '\nCMD_WIRE = (f"cd C:/work/sourcecode/tick-stock-panel && {ENV} {PY} "\n            "research/b2-engine-20261107/verify_wiring.py  # 生产 Provider 入口 materialize_factor_columns")'
assert s.count(old_cmd) == 1
s = s.replace(old_cmd, new_cmd)

# 2) 接线断言: 插在 "口径差" 之前
anchor = '    # ---------------- 口径差 (不是判据, 供裁定) ----------------'
wire_block = '''    # ---------------- 接线 (生产 Provider 入口, 不是直调) ----------------
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
'''
assert s.count(anchor) == 1
s = s.replace(anchor, wire_block + anchor)

# 3) CAL 口径注: 注明契约原文
old_note = '''         note="实现取 cum_count(=研究侧, A1 逐日 0 差); brief 要求 listing_date+交易日轴。"
              "40,717 标的日不同(评估窗内 17,499), 全部是 B>=120 而 A<120 的情形"),'''
new_note = '''         note="实现取 cum_count(=研究侧, A1 逐日 0 差)。契约 v0.7:125 原文: observed_bars 在研究中 = "
              "date.cum_count().over(symbol)，即该标的在已加载面板内的 bar 行数，不是上市自然日"
              "（并明确「不要自然日差」）; brief 的 listing_date+交易日轴 表述与契约冲突, 按「口径以契约"
              "与因子研究员定义为准」取契约。40,717 标的日不同(评估窗内 17,499), 全部是 listing 口径"
              ">=120 而 bar 口径 <120 的情形"),'''
assert s.count(old_note) == 1
s = s.replace(old_note, new_note)

p.write_text(s, encoding="utf-8")
print("patched evidence_build")
