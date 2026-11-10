"""交易计划与执行复盘扩展。

只新增独立页面、计划数据与 AI 复盘接口；计划/执行口径由本扩展维护，
不修改核心交易、回测或模拟盘账务。
"""

from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "official.trade-plan"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from .routes import build_router

    registrar.include_router(build_router())
