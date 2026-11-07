"""B: provider 静默吞异常 —— 受控复现（只 monkeypatch import，不动仓库文件）"""
import importlib
import sys

TARGET = "research_universe_pack.factor_provider"
real_import = importlib.import_module


def hostile_import(name, *a, **k):
    if name.endswith(TARGET):
        raise ImportError("simulated transient import failure")
    return real_import(name, *a, **k)


importlib.import_module = hostile_import

from app.extensions import factors as ext
from app.factors.registry import all_factors

print("== step1: 首次触碰注册表 (导入期该 pack 失败) ==")
ids = {s.id for s in all_factors()}
print("catalog_size =", len(ids))
print("PROVIDERS_READY =", ext._PROVIDERS_READY)
print("in_universe present =", "in_universe" in ids)
print("providers loaded =", sorted(ext._PROVIDERS))

print("\n== step2: 故障消失后再调 ensure_factor_providers() (仍在同进程) ==")
importlib.import_module = real_import  # 故障已恢复
for i in (1, 2, 3):
    ext.ensure_factor_providers()
    ids2 = {s.id for s in all_factors()}
    print(f"  第{i}次重调后 catalog_size={len(ids2)} in_universe={'in_universe' in ids2}")

print("\n== step3: 显式清标志后重调（证明唯一阻塞就是这个标志）==")
ext._PROVIDERS_READY = False
ext.ensure_factor_providers()
ids3 = {s.id for s in all_factors()}
print("  catalog_size =", len(ids3), " in_universe =", "in_universe" in ids3)
print("  providers loaded =", sorted(ext._PROVIDERS))
