"""B-2b: 进程内首次触碰注册表 = resource_bundle 预览 (_analyze) —— 端到端可达性"""
import sys

from app.services import resource_bundle
from app.factors.registry import all_factors
from app.extensions import factors as ext

print("调用前 registry 是否已热:", ext._PROVIDERS_READY)
try:
    resource_bundle._analyze({})
    print("_analyze({}) 返回 ok")
except Exception as e:
    print("_analyze 抛:", type(e).__name__, e)

ids = {s.id for s in all_factors()}
print("catalog_size =", len(ids))
print("PROVIDERS_READY =", ext._PROVIDERS_READY)
print("_PROVIDERS =", len(ext._PROVIDERS), "_FACTOR_OWNERS =", len(ext._FACTOR_OWNERS))
print("in_universe present =", "in_universe" in ids)
print("owner 有/注册表无 =", len(set(ext._FACTOR_OWNERS) - ids))
