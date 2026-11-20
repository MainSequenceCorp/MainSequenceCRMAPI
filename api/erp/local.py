"""Run the shared ERP API on loopback with the existing SDK sign-in."""

from fastapi import FastAPI

from metatables import configure_local_client
from src.erp.user_preferences.scope import (
    configured_scope,
    configured_source,
    provisioned_module_keys,
)


def create_app() -> FastAPI:
    configure_local_client()
    configured_scope(local=True)
    configured_source(local=True)
    provisioned_module_keys()

    from api.erp.crm.local import _anonymous_routes, _public_ingress, install_local_identity
    from api.erp.main import create_app as create_erp_app

    with _public_ingress(_anonymous_routes()):
        application = create_erp_app(local=True)
    install_local_identity(application, shared_erp=True)
    application.state.erp_module_apps["user_preferences"].state.crm_local_tau_origin = (
        application.state.crm_local_tau_origin
    )
    return application
