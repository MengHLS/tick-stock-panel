"""交易分析扩展：导入券商对账单，按 FIFO 配对并生成逐笔复盘。"""

from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "official.trade-analysis"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from .routes import build_router

    registrar.include_router(build_router())
