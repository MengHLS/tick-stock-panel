
import sys
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import registry
print("len(_CATALOG)", len(registry._CATALOG))
for fn in ["list_factors","factor_columns_view","all_specs","specs"]:
    print(fn, hasattr(registry,fn))
try:
    print("factor_columns_view n", len(registry.factor_columns_view()))
except Exception as e:
    print("fcv err",e)
print("_REGISTRY n", len(registry._REGISTRY))
from app.extensions import factors as extf
extf.ensure_factor_providers()
print("after providers _REGISTRY", len(registry._REGISTRY))
import collections
pref=collections.Counter(i.split("_")[0] if "_" in i else "other" for i in registry._REGISTRY)
print(dict(list(pref.items())[:12]))
