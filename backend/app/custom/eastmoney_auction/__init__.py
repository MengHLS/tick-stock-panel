"""Live Eastmoney opening-auction extension."""

from __future__ import annotations

from app.custom.eastmoney_auction import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.services.ext_pull import pull_scheduler, register_pull_handler

EXTENSION_ID = "local.eastmoney-auction"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    """Register collectors on the shared extension-data scheduler."""
    _ = registrar
    register_pull_handler(service.PREOPEN_CONFIG, service.run_scheduled_preopen)
    register_pull_handler(service.RESULT_CONFIG, service.run_scheduled_result)


def startup(context: ExtensionContext) -> None:
    service.ensure_auction_configs(context.data_dir)
    pull_scheduler.refresh(context.data_dir)
