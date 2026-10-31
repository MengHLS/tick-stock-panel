"""Live Eastmoney opening-auction extension."""

from __future__ import annotations

from app.custom.eastmoney_auction import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.services import preferences

EXTENSION_ID = "local.eastmoney-auction"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    """Register no routes; the extension owns two generated data tables."""
    _ = registrar


def startup(context: ExtensionContext) -> None:
    service.ensure_auction_configs(context.data_dir)
    enabled = preferences.get_data_sync_prefs()["data_sync_ext_pull_enabled"]
    service.auction_scheduler.start(
        context.data_dir,
        enabled=enabled,
        repository=context.repository,
    )
