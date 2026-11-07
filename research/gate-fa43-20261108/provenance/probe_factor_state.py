from app.factors import registry
from app.extensions import factors as ext


def pytest_runtest_teardown(item, nextitem):
    n = len(registry._REGISTRY)
    preview = registry._PREVIEW_REGISTRY.get() is not None
    print(f"STATE n={n} ready={ext._PROVIDERS_READY} preview={preview} :: {item.nodeid}", flush=True)
