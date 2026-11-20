"""Admit module business requests inside Main Sequence request identity."""

import logging
import os
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from src.erp.module_access import admission, admission_for
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.scope import LOCAL_SCOPE_SETTING, MODULES_SETTING, SOURCE_SETTING

logger = logging.getLogger(__name__)


def _response(request, exc, *, module_key):
    body = {"code": exc.code, "message": exc.message}
    if module_key == "crm":
        body["request_uid"] = str(getattr(request.state, "crm_request_uid", uuid4()))
    return JSONResponse({"error": body}, status_code=exc.status)


class ModuleAdmissionMiddleware:
    def __init__(self, app, *, module_key, policy_exempt=(), policy_exempt_paths=()):
        self.app = app
        self.module_key = module_key
        self.policy_exempt = frozenset(policy_exempt)
        self.policy_exempt_paths = frozenset(policy_exempt_paths)

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or scope["path"] == "/healthz"
            or scope["path"] in self.policy_exempt_paths
            or (scope["method"], scope["path"]) in self.policy_exempt
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        identity = request.app.state.mainsequence_request_identity
        local = identity["mode"] == "local"
        if (
            local
            and not getattr(request.app.state, "erp_requires_module_policy", False)
            and not any(
                name in os.environ
                for name in (SOURCE_SETTING, LOCAL_SCOPE_SETTING, MODULES_SETTING)
            )
        ):
            # A standalone local launcher without ERP policy keeps its existing
            # contract. ERP local launch explicitly binds all APIs to one source.
            await self.app(scope, receive, send)
            return

        try:
            current = await run_in_threadpool(self.admit, request, local=local)
        except UserPreferencesError as exc:
            await _response(request, exc, module_key=self.module_key)(scope, receive, send)
            return
        except Exception as exc:
            logger.warning(
                "ERP module admission unavailable for %s (%s)", self.module_key, type(exc).__name__
            )
            error = UserPreferencesError(
                503, "module_policy_unavailable", "ERP module policy is unavailable."
            )
            await _response(request, error, module_key=self.module_key)(scope, receive, send)
            return

        token = admission.set(current)
        try:
            await self.app(scope, receive, send)
        finally:
            admission.reset(token)

    def admit(self, request, *, local):
        from src.erp.user_preferences.admission import require_active
        from src.erp.user_preferences.scope import (
            configured_scope,
            provisioned_module_keys,
            scope_for_request,
        )

        public_ingress = getattr(request.state, "auth_outcome", None) == "public_ingress"
        scope = (
            configured_scope(local=local)
            if public_ingress
            else scope_for_request(request, local=local)
        )
        policy = require_active(scope, (self.module_key,), local=local)
        current = admission_for(
            scope, local=local, policy=policy, provisioned=provisioned_module_keys()
        )
        current.require(self.module_key)
        return current


def install_module_admission(app, module_key: str, *, policy_exempt=(), policy_exempt_paths=()):
    """Call immediately before installing the existing SDK identity middleware."""
    app.add_middleware(
        ModuleAdmissionMiddleware,
        module_key=module_key,
        policy_exempt=policy_exempt,
        policy_exempt_paths=policy_exempt_paths,
    )

    async def access_error(request: Request, exc: UserPreferencesError):
        return _response(request, exc, module_key=module_key)

    app.add_exception_handler(UserPreferencesError, access_error)
