"""Loopback-only SDK-authenticated Finance launcher using confirmed local MetaTables."""

import asyncio
import ipaddress
import os
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from mainsequence.client.utils import get_authorization_headers
from metatables import configure_local_client
from src.erp.finance.store import require_local_runtime

from .main import create_app as create_finance_app

FORBIDDEN = {
    b"authorization",
    b"x-mainsequence-caller-assertion",
    b"x-public-ingress",
    b"x-user-id",
    b"x-user-uid",
    b"x-username",
}


def loopback_host(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def create_app():
    configure_local_client()
    expected = os.environ.get("FINANCE_LOCAL_SOURCE_UID")
    if not expected or str(require_local_runtime()) != expected:
        raise RuntimeError("Finance requires the explicitly verified local DataSource UID")
    app = create_finance_app(local=True)
    if app.state.mainsequence_request_identity["mode"] != "local":
        raise RuntimeError("The Finance local launcher cannot run inside a platform deployment")

    @app.middleware("http")
    async def local_identity(request: Request, call_next):
        origin = request.headers.get("origin")
        host = request.url.hostname
        if (
            not request.client
            or not loopback_host(request.client.host)
            or not host
            or not loopback_host(host)
            or (origin and not loopback_host(urlsplit(origin).hostname or ""))
        ):
            return JSONResponse(
                {
                    "error": {
                        "code": "local_only",
                        "message": "Finance local access requires loopback origin and host",
                    }
                },
                status_code=403,
            )
        if any(name.lower() in FORBIDDEN for name, _ in request.scope["headers"]):
            return JSONResponse(
                {
                    "error": {
                        "code": "caller_headers",
                        "message": "Local Finance does not accept caller identity headers",
                    }
                },
                status_code=401,
            )
        try:
            headers = await asyncio.wait_for(
                asyncio.to_thread(get_authorization_headers), timeout=20
            )
            value = headers.get("Authorization", "")
            if not value.startswith("Bearer "):
                raise RuntimeError("SDK sign-in required")
        except Exception:
            return JSONResponse(
                {
                    "error": {
                        "code": "sign_in_unavailable",
                        "message": "Existing SDK sign-in is unavailable",
                    }
                },
                status_code=503,
            )
        request.scope["headers"] = [
            *request.scope["headers"],
            (b"authorization", value.encode("latin-1")),
        ]
        return await call_next(request)

    return app
