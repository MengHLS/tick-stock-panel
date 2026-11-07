"""问 1 实验 ①: provider 发现吞异常且不可重试 —— 受控复现.

不改仓库任何文件。每一步用**独立临时目录**, 避免标记文件被互相消费。

四种形态:
  A pvbroken   导入期抛 ImportError (仅首次), 之后可导入        -> :209 分支
  B pvregfail  模块可导入, params() 首调抛 RuntimeError (仅首次) -> :217 分支
  C pvnospec   包目录存在但没有 factor_provider.py               -> :200-202 continue
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[3] / "backend"

IMPORT_FAIL_CODE = '''
import pathlib

marker = pathlib.Path(__file__).with_name("FAIL_ONCE")
if marker.exists():
    marker.unlink()
    raise ImportError("simulated transient import failure (file mid-write)")

from app.extensions.factors import FactorProvider
from app.factors.registry import FactorSpec

FID = "pv_sim_alpha"


class _P(FactorProvider):
    provider_id = "pvbroken"
    version = 1
    kind = "frame"
    factor_ids = frozenset({FID})
    factor_specs = (FactorSpec(id=FID, label="sim", group="sim", formula_text="close"),)

    def dependencies(self, factor_id):
        return frozenset({"close"})

    def warmup_bars(self, factor_id):
        return 1


FACTOR_PROVIDERS = (_P(),)
'''

REG_FAIL_CODE = '''
import pathlib

from app.extensions.factors import FactorProvider
from app.factors.registry import FactorSpec

FID = "pv_reg_alpha"
CALLS = pathlib.Path(__file__).with_name("CALLS")


def _tick():
    n = int(CALLS.read_text()) if CALLS.exists() else 0
    CALLS.write_text(str(n + 1))
    return n


class _P(FactorProvider):
    provider_id = "pvregfail"
    version = 1
    kind = "frame"
    factor_ids = frozenset({FID})
    factor_specs = (FactorSpec(id=FID, label="sim2", group="sim", formula_text="close"),)

    def dependencies(self, factor_id):
        return frozenset({"close"})

    def warmup_bars(self, factor_id):
        return 1

    def params(self, factor_id):
        if _tick() == 0:
            raise RuntimeError("simulated transient params() failure")
        return {}


FACTOR_PROVIDERS = (_P(),)
'''


def fresh_tmp(*, arm_failures: bool) -> pathlib.Path:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="pv1_"))
    for name, code in (("pvbroken", IMPORT_FAIL_CODE), ("pvregfail", REG_FAIL_CODE)):
        d = tmp / name
        d.mkdir()
        (d / "__init__.py").write_text("", encoding="utf-8")
        (d / "factor_provider.py").write_text(code, encoding="utf-8")
        if arm_failures:
            (d / "FAIL_ONCE").write_text("1", encoding="utf-8")
        else:
            # 未装故障: 预先记一次调用, 使首调就是第 2 次 -> params() 不抛
            (d / "CALLS").write_text("1", encoding="utf-8")
    d = tmp / "pvnospec"
    d.mkdir()
    (d / "__init__.py").write_text("", encoding="utf-8")
    return tmp


PROBE = r"""
import json, logging, sys
LOG = []
class H(logging.Handler):
    def emit(self, r):
        LOG.append(r.levelname + "|" + r.name + "|" + r.getMessage())
logging.getLogger().addHandler(H())
logging.getLogger().setLevel(logging.DEBUG)
sys.path.insert(0, {backend!r})
{body}
print("@@JSON@@" + json.dumps(out))
"""

BODY_SIMPLE = r"""
import app.custom
if {tmp!r}:
    app.custom.__path__.append({tmp!r})
import app.extensions.factors as ext
import app.factors.registry as reg
ids = sorted(s.id for s in reg.all_factors())
out = {"ready": ext._PROVIDERS_READY, "n": len(ids), "ids": ids,
       "providers": sorted(ext._PROVIDERS), "log": LOG}
"""

BODY_RETRY = r"""
import app.custom
app.custom.__path__.append({tmp!r})
import app.extensions.factors as ext
import app.factors.registry as reg

def snap(tag):
    ids = sorted(s.id for s in reg.all_factors())
    return {"tag": tag, "ready": ext._PROVIDERS_READY, "n": len(ids), "ids": ids,
             "pv_sim": "pv_sim_alpha" in ids, "pv_reg": "pv_reg_alpha" in ids,
             "providers": sorted(ext._PROVIDERS)}

steps = [snap("first_touch")]
for i in range(3):
    ext.ensure_factor_providers()
    reg.all_factors()
    reg.get_factor("pv_sim_alpha")
    steps.append(snap("recall_" + str(i + 1)))
out = {"steps": steps, "log": LOG, "n_log_entries": len(LOG)}
"""


def run(body: str, tmp: str) -> dict:
    code = PROBE.format(backend=str(BACKEND), body=body.replace("{tmp!r}", repr(tmp)))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("@@JSON@@"):
            return json.loads(line[len("@@JSON@@"):])
    return {"error": p.stderr[-3000:], "rc": p.returncode}


result: dict[str, object] = {}

# 0) 对照: 不加任何临时包
ctrl = run(BODY_SIMPLE, "")
result["0_control"] = {"n": ctrl["n"], "providers": ctrl["providers"], "log": ctrl["log"]}
ctrl_ids = set(ctrl["ids"])

# 1) 单进程内: 首次发现失败 -> 再重试 3 次, 条件此时已恢复
tmp_fail = fresh_tmp(arm_failures=True)
retry = run(BODY_RETRY, str(tmp_fail))
result["1_fail_then_retry_same_process"] = retry
result["1_added_vs_control"] = sorted(set(retry["steps"][0]["ids"]) - ctrl_ids)
result["1_pvnospec_silent"] = {
    "dir_present": (tmp_fail / "pvnospec").is_dir(),
    "any_log_mention": any("pvnospec" in w for w in retry["log"]),
    "id_present": any("pvnospec" in i for i in retry["steps"][0]["ids"]),
}
result["1_steps_pv_flags"] = [
    {"tag": s["tag"], "ready": s["ready"], "n": s["n"], "pv_sim": s["pv_sim"], "pv_reg": s["pv_reg"]}
    for s in retry["steps"]
]
result["1_markers_after"] = sorted(
    p.name for p in tmp_fail.iterdir() if (p / "FAIL_ONCE").exists() or (p / "CALLS").exists()
)

# 2) 另起进程 (标记已消费): 证明条件恢复后新进程即正常
after = run(BODY_SIMPLE, str(tmp_fail))
result["2_new_process_after_condition_fixed"] = {
    "n": after["n"],
    "added_vs_control": sorted(set(after["ids"]) - ctrl_ids),
    "log": [w for w in after["log"] if "pv" in w],
}

# 3) 条件本来就正常 (不装故障): 同一代码路径应全部装载
tmp_ok = fresh_tmp(arm_failures=False)
ok = run(BODY_SIMPLE, str(tmp_ok))
result["3_condition_ok_same_code_path"] = {
    "n": ok["n"],
    "added_vs_control": sorted(set(ok["ids"]) - ctrl_ids),
    "log": [w for w in ok["log"] if "pv" in w],
}

pathlib.Path(__file__).with_name("p1_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
