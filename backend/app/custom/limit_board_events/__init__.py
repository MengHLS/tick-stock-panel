"""System-generated limit board event extension."""

from __future__ import annotations

from app.custom.limit_board_events import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.services.ext_pull import pull_scheduler, register_pull_handler

EXTENSION_ID = "local.limit-board-events"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    """Register the daily materializer on the shared pull scheduler."""
    _ = registrar
    register_pull_handler(service.CONFIG_ID, service.run_scheduled_limit_board)


def startup(context: ExtensionContext) -> None:
    service.ensure_limit_board_config(context.data_dir)
    pull_scheduler.refresh(context.data_dir)
