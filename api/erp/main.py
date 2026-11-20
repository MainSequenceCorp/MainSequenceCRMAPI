"""Main Sequence ERP's shared authenticated business API."""

from importlib import import_module

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette._utils import get_route_path
from starlette.types import ASGIApp, Receive, Scope, Send

from api.erp.crm.main import install_crm_http
from api.erp.mcp.server import install_erp_mcp
from mainsequence.server.fastapi import install_request_identity
from src.erp.modules import MODULES

SETTINGS_PREFIX = "/api/erp/v1"
DOC_PATHS = ("/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc")


class ModuleDispatch:
    """Send each module's full path to its ASGI surface after SDK authentication."""

    def __init__(self, app: ASGIApp, *, surfaces: dict[str, FastAPI]):
        self.app = app
        self.surfaces = surfaces

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = get_route_path(scope)
            for prefix, surface in self.surfaces.items():
                if path == prefix or path.startswith(prefix + "/"):
                    # The module keeps its exception handlers, middleware and app state.
                    await surface(dict(scope), receive, send)
                    return
        await self.app(scope, receive, send)


def create_app(*, local: bool = False) -> FastAPI:
    application = FastAPI(title="Main Sequence ERP", version="0.1.0")
    application.state.erp_requires_module_policy = True

    @application.get("/healthz")
    def healthz():
        return {"status": "ok"}

    install_crm_http(
        application,
        policy_exempt=tuple(("GET", path) for path in DOC_PATHS),
        policy_exempt_paths=("/mcp",),
    )
    # Populate the dispatch map before the middleware stack starts. The one
    # SDK installation wraps both the dispatcher and CRM's root routes/MCP.
    surfaces = {}
    application.add_middleware(ModuleDispatch, surfaces=surfaces)
    install_request_identity(application)
    identity = application.state.mainsequence_request_identity
    local_mode = identity["mode"] == "local"
    if local and not local_mode:
        raise RuntimeError("The ERP local application requires SDK local caller identity.")

    module_paths = {
        key: module.api_prefix for key, module in MODULES.items() if key != "crm"
    }
    module_paths["user_preferences"] = SETTINGS_PREFIX
    module_apps = {"crm": application}
    for key, prefix in module_paths.items():
        factory = import_module(f"api.erp.{key}.main").create_app
        surface = factory(local=local_mode, install_identity=False)
        surface.state.mainsequence_request_identity = identity
        surface.state.erp_requires_module_policy = True
        surfaces[prefix] = module_apps[key] = surface

    application.state.erp_module_apps = module_apps
    install_erp_mcp(application, module_apps=module_apps)

    def openapi():
        if application.openapi_schema is None:
            module_routes = [
                route
                for surface in surfaces.values()
                for route in surface.routes
                if getattr(route, "path", None) not in (*DOC_PATHS, "/healthz")
            ]
            application.openapi_schema = get_openapi(
                title=application.title,
                version=application.version,
                openapi_version=application.openapi_version,
                servers=application.servers,
                routes=[*application.routes, *module_routes],
            )
        return application.openapi_schema

    application.openapi = openapi
    return application


app = create_app()
