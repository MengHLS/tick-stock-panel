"""System-generated limit board event extension."""

from __future__ import annotations

from app.custom.limit_board_events import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.services import preferences

EXTENSION_ID = "local.limit-board-events"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    """Register no routes; this extension only materializes extension data."""
    _ = registrar


def startup(context: ExtensionContext) -> None:
    service.ensure_limit_board_config(context.data_dir)
    enabled = preferences.get_data_sync_prefs()["data_sync_ext_pull_enabled"]
    service.limit_board_scheduler.start(
        context.data_dir,
        enabled=enabled,
        repository=context.repository,
    )
