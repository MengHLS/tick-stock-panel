"""Register the platform limit-up extension data table."""
from __future__ import annotations

from app.custom.limit_up_platform import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.services.ext_pull import pull_scheduler

EXTENSION_ID = "local.limit-up-platform"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    """The table uses the shared HTTP pull engine; no custom handler is needed."""
    _ = registrar


def startup(context: ExtensionContext) -> None:
    service.ensure_limit_up_config(context.data_dir)
    pull_scheduler.refresh(context.data_dir)
