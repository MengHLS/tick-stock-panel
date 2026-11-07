"""T74 strategy research: baseline identity, path diagnostics, and experiment records."""

from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "official.strategy-research"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from .routes import build_router

    registrar.include_router(build_router())
