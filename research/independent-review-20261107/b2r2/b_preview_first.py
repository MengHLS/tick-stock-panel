"""B-2: 首次触碰注册表发生在 isolated_registry() 预览上下文内 —— 确定性分支"""
from app.factors import registry
from app.factors.registry import all_factors
from app.extensions import factors as ext

print("== 进程内第一次触碰因子注册表: 在 isolated_registry() 预览上下文里 ==")
with registry.isolated_registry() as snap:
    inside = {s.id for s in all_factors()}
    print("  预览快照内 catalog_size =", len(inside))
    print("  预览快照内 in_universe =", "in_universe" in inside)

after = {s.id for s in all_factors()}
print("\n== 预览退出后 (正式注册表) ==")
print("  catalog_size =", len(after))
print("  in_universe present =", "in_universe" in after)
print("  PROVIDERS_READY =", ext._PROVIDERS_READY)
print("  _PROVIDERS 条数 =", len(ext._PROVIDERS))
print("  _FACTOR_OWNERS 条数 =", len(ext._FACTOR_OWNERS))
missing = sorted(set(ext._FACTOR_OWNERS) - after)
print("  owner 表有、注册表没有的因子数 =", len(missing))
print("  样例:", missing[:6])

print("\n== 后果: 再调 ensure_factor_providers() ==")
ext.ensure_factor_providers()
after2 = {s.id for s in all_factors()}
print("  catalog_size =", len(after2), " in_universe =", "in_universe" in after2)

print("\n== 后果: factor_provider_for('in_universe') 是否仍声称有 provider ==")
p = ext.factor_provider_for("in_universe")
print("  ->", getattr(p, "provider_id", None))

print("\n== 对照: 清标志重调能否修复 ==")
ext._PROVIDERS_READY = False
ext.ensure_factor_providers()
after3 = {s.id for s in all_factors()}
print("  catalog_size =", len(after3), " in_universe =", "in_universe" in after3)
