"""问 1 实验 ②: 进程内首次触碰注册表发生在 isolated_registry() 预览上下文.

两条分支对比:
  A 正常: 先 all_factors() (生产 resource_bundle.py:732 的做法) 再进 preview
  B 异常: 直接进 preview, 在 preview 内第一次触碰注册表
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[3] / "backend"

BODY_A = r"""
import json, sys
sys.path.insert(0, {backend!r})
import app.factors.registry as reg
import app.extensions.factors as ext

out = {}
reg.all_factors()                      # 生产 resource_bundle.py:732 的同款预热
out["ready_before_preview"] = ext._PROVIDERS_READY
with reg.isolated_registry() as snap:
    out["preview_has_in_universe"] = "in_universe" in snap
    out["preview_n"] = len(snap)
out["after_get_factor_in_universe"] = reg.get_factor("in_universe") is not None
out["providers"] = sorted(ext._PROVIDERS)
print("@@JSON@@" + json.dumps(out, default=str))
"""

BODY_B = r"""
import json, sys
sys.path.insert(0, {backend!r})
import app.factors.registry as reg
import app.extensions.factors as ext

out = {}
out["ready_before_preview"] = ext._PROVIDERS_READY
with reg.isolated_registry() as snap:
    ids = [s.id for s in reg.all_factors()]   # 首次触碰发生在 preview 内
    out["preview_n"] = len(ids)
    out["preview_has_in_universe"] = "in_universe" in ids
    out["preview_has_vol60"] = "vol60" in ids
    out["preview_has_prior_high_250"] = "prior_high_250" in ids
out["ready_after_preview"] = ext._PROVIDERS_READY
live = [s.id for s in reg.all_factors()]      # 出了 preview 之后的正式注册表
out["live_n"] = len(live)
out["live_has_in_universe"] = "in_universe" in live
out["live_has_vol60"] = "vol60" in live
out["live_has_prior_high_250"] = "prior_high_250" in live
out["get_factor_in_universe_is_none"] = reg.get_factor("in_universe") is None
out["get_factor_vol60_is_none"] = reg.get_factor("vol60") is None
# 状态自相矛盾: owner 表与 PROVIDERS 都登记了, 正式注册表里却没有 spec
out["owners_in_universe"] = ext._FACTOR_OWNERS.get("in_universe")
out["provider_for_in_universe"] = getattr(ext.factor_provider_for("in_universe"), "provider_id", None)
out["providers"] = sorted(ext._PROVIDERS)
print("@@JSON@@" + json.dumps(out, default=str))
"""


def run(body: str) -> dict:
    p = subprocess.run(
        [sys.executable, "-c", body.replace("{backend!r}", repr(str(BACKEND)))],
        capture_output=True,
        text=True,
    )
    for line in p.stdout.splitlines():
        if line.startswith("@@JSON@@"):
            return json.loads(line[len("@@JSON@@"):])
    return {"error": p.stderr[-3000:], "rc": p.returncode}


result = {
    "A_preview_after_warmup": run(BODY_A),
    "B_preview_as_first_touch": run(BODY_B),
}
pathlib.Path(__file__).with_name("p2_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
