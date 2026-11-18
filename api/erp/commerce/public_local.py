"""Local-only customer API. No internal routes, customer platform identity or hosted ingress."""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mainsequence.client.utils import get_authorization_headers
from mainsequence.server.fastapi import install_request_identity
from metatables import configure_local_client
from src.erp.commerce.errors import CommerceError
from src.erp.commerce.schemas import CheckoutCreate
from src.erp.commerce.store import Store, require_local_runtime
from src.erp.module_access.http import install_module_admission

from .local import FORBIDDEN, loopback_host
from .main import install_errors
from .services import service

PREFIX = "/api/commerce-public/v1"


def create_app():
    configure_local_client()
    expected = os.environ.get("COMMERCE_LOCAL_SOURCE_UID")
    if not expected or str(require_local_runtime()) != expected:
        raise RuntimeError("Commerce public local access requires the exact verified SQLite source")
    # This local boundary resolves the merchant from the SDK, never from customer input.
    if str(Store(local_only=True).data_source_uid) != expected:
        raise RuntimeError("Commerce source mismatch")
    app = FastAPI(
        title="Local customer storefront", docs_url=None, redoc_url=None, openapi_url=None
    )
    install_errors(app)
    install_module_admission(app, "commerce")
    install_request_identity(app)
    if app.state.mainsequence_request_identity["mode"] != "local":
        raise RuntimeError("The public local launcher cannot run in a platform deployment")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        host = request.url.hostname
        if (
            not request.client
            or not loopback_host(request.client.host)
            or not host
            or not loopback_host(host)
            or origin
            and not loopback_host(urlsplit(origin).hostname or "")
            or any(name.lower() in FORBIDDEN for name, _ in request.scope["headers"])
        ):
            response = JSONResponse(
                {
                    "error": {
                        "code": "local_only",
                        "message": "This local customer endpoint requires loopback access without platform identity headers",
                    }
                },
                status_code=403,
            )
        else:
            try:
                headers = await asyncio.wait_for(
                    asyncio.to_thread(get_authorization_headers), timeout=20
                )
                value = headers.get("Authorization", "")
                if not value.startswith("Bearer "):
                    raise RuntimeError("SDK sign-in required")
            except Exception:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "merchant_unavailable",
                            "message": "The local merchant service is unavailable",
                        }
                    },
                    status_code=503,
                )
            else:
                request.scope["headers"] = [
                    *request.scope["headers"],
                    (b"authorization", value.encode("latin-1")),
                ]
                response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def current():
        if str(require_local_runtime()) != expected:
            raise CommerceError(
                503, "local_source", "Local storage changed; restart before continuing"
            )
        return service(local=True)

    @app.get(PREFIX + "/sites/{slug}/")
    def site(
        slug: str,
        request: Request,
        page_index: int = Query(0, ge=0, le=100000),
        page_size: int = Query(25, ge=1, le=100),
    ):
        if set(request.query_params) - {"page_index", "page_size"}:
            raise CommerceError(422, "query", "Unsupported public query")
        return current().public_site(slug, page_index=page_index, page_size=page_size)

    @app.get(PREFIX + "/checkouts/")
    def orders(
        request: Request,
        x_portal_token: str = Header(""),
        page_index: int = Query(0, ge=0, le=100000),
        page_size: int = Query(25, ge=1, le=100),
    ):
        if set(request.query_params) - {"page_index", "page_size"}:
            raise CommerceError(422, "query", "Unsupported portal query")
        return current().portal_orders(x_portal_token, page_index=page_index, page_size=page_size)

    @app.post(PREFIX + "/checkouts/", status_code=201)
    def checkout(payload: CheckoutCreate, x_portal_token: str = Header("")):
        return current().checkout(x_portal_token, payload.model_dump())

    @app.get(PREFIX + "/checkouts/{uid}/")
    def detail(uid: UUID, x_portal_token: str = Header("")):
        return current().portal_checkout(x_portal_token, uid)

    frontend_dist = os.environ.get("COMMERCE_PUBLIC_FRONTEND_DIST")
    if frontend_dist:
        root = Path(frontend_dist).resolve()
        if not root.is_dir() or not (root / "index.html").is_file():
            raise RuntimeError(
                "Build the shared ERP frontend before serving the local customer preview"
            )

        @app.get("/shop/{slug}", include_in_schema=False)
        @app.get("/shop/{slug}/", include_in_schema=False)
        def storefront(slug: str):
            return FileResponse(root / "index.html")

        app.mount("/", StaticFiles(directory=root, html=True), name="shared-erp-artifact")
    return app
