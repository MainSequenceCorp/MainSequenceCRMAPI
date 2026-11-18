"""Loopback-only User Preferences launcher using real CLI sign-in."""

import asyncio
import ipaddress
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from mainsequence.client.utils import get_authorization_headers
from metatables import configure_local_client
from src.erp.user_preferences.scope import configured_scope, configured_source

from .main import create_app as create_preferences_app

IDENTITY_HEADERS = {
    b"authorization",
    b"x-mainsequence-caller-assertion",
    b"x-public-ingress",
    b"x-user-id",
    b"x-user-uid",
    b"x-username",
    b"x-organization-environment-uid",
}


def loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def deny(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app():
    configure_local_client()
    configured_scope(local=True)
    configured_source(local=True)
    app = create_preferences_app(local=True)
    if app.state.mainsequence_request_identity["mode"] != "local":
        raise RuntimeError("The User Preferences local launcher cannot run on a platform release")

    @app.middleware("http")
    async def local_identity(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            not request.client
            or not loopback(request.client.host)
            or not loopback(request.url.hostname or "")
            or (origin and not loopback(urlsplit(origin).hostname or ""))
        ):
            return deny(403, "local_only", "Local User Preferences requires a loopback origin")
        if any(name.lower() in IDENTITY_HEADERS for name, _ in request.scope["headers"]):
            return deny(401, "caller_headers", "Local User Preferences rejects identity headers")
        try:
            headers = await asyncio.wait_for(
                asyncio.to_thread(get_authorization_headers), timeout=20
            )
            authorization = headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                raise RuntimeError("SDK sign-in required")
        except Exception:
            return deny(503, "sign_in_unavailable", "Existing SDK sign-in is unavailable")
        request.scope["headers"] = [
            *request.scope["headers"],
            (b"authorization", authorization.encode("latin-1")),
        ]
        return await call_next(request)

    return app
