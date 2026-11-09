"""威科夫日线研究：只读事件 API 与独立研究页后端扩展。

首版只做“单股、日线、只读研究显示”。规则未由研究规格冻结前不注册可交易策略，
不接监控、通知、模拟跟单或真实交易。
"""

from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "official.wyckoff-research"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from .routes import build_router

    registrar.include_router(build_router())
