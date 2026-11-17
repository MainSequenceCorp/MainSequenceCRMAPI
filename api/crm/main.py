"""Compatibility entrypoint for existing CRM launchers."""

from api.erp.crm.main import app, create_app

__all__ = ["app", "create_app"]
