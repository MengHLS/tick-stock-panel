"""用户可定义的动态自选分组。"""
from __future__ import annotations

from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar
from app.services import watchlist_group_resolvers

EXTENSION_ID = "official.dynamic-watchlist"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from app.custom.dynamic_watchlist.resolver import resolve, validate

    if not watchlist_group_resolvers.is_registered("conditions"):
        watchlist_group_resolvers.register(
            "conditions",
            resolve,
            validator=validate,
        )
