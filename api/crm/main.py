"""Stable Production source entrypoint for the shared ERP API."""

from api.erp.main import app, create_app
from src.erp.user_preferences.scope import (
    configured_scope,
    configured_source,
    provisioned_module_keys,
)

if app.state.mainsequence_request_identity["mode"] != "local":
    configured_scope()
    configured_source()
    provisioned_module_keys()

__all__ = ["app", "create_app"]
