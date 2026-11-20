"""One authenticated SDK MCP transport for the ERP."""

import json
import logging
from contextvars import ContextVar
from time import monotonic
from uuid import uuid4

import anyio
from fastapi import HTTPException, Request
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR, CallToolResult, TextContent, Tool
from pydantic import ValidationError

from api.erp.crm.mcp_server import _active_tool_name
from api.erp.crm.mcp_tools import MAX_RESULT_CHARS
from api.erp.crm.mcp_tools import tool_result as crm_result
from mainsequence.server.fastapi import install_mcp
from src.erp.base.service import BaseError
from src.erp.catalog.service import CatalogError
from src.erp.crm.platform.diagnostics import request_diagnostics
from src.erp.crm.services.operations import AccessDenied, ServiceUnavailable
from src.erp.module_access import admission
from src.erp.user_preferences.errors import UserPreferencesError

from .admission import Scope, active_scope
from .compatibility import CRM_TOOL_ALIASES, ERPSkills
from .contracts import Failure
from .owner_routes import OwnerOperationError
from .registry import SKILLS_ROOT, CRMTool, Registry
from .tools import (
    base,
    catalog,
    collaboration,
    commerce,
    crm,
    erp,
    finance,
    inventory,
    manufacturing,
    marketing,
    people,
    projects,
    purchasing,
    reporting,
    sales,
    settings,
)

logger = logging.getLogger(__name__)
_active_request: ContextVar[Request] = ContextVar("erp_mcp_request")


def build_registry(module_apps):
    registry = Registry(module_apps)
    for module in (
        erp,
        base,
        catalog,
        crm,
        sales,
        finance,
        projects,
        people,
        collaboration,
        marketing,
        settings,
        inventory,
        purchasing,
        manufacturing,
        commerce,
        reporting,
    ):
        module.register_tools(registry)
    return registry


def _result(details) -> CallToolResult:
    encoded = json.dumps(details, ensure_ascii=False)
    if len(encoded) > MAX_RESULT_CHARS:
        details = {"code": "result_too_large", "message": "Narrow the query or read one record."}
        encoded = json.dumps(details)
    return CallToolResult(
        content=[TextContent(type="text", text=encoded)],
        structuredContent=details,
        isError=details["code"] != "ok",
    )


def _failure(code, message, *, data=None):
    return _result(Failure(code=code, message=message, data=data).model_dump(exclude_none=True))


def _error(error, *, legacy=False):
    status = getattr(error, "status", getattr(error, "status_code", None))
    domain_code = getattr(error, "code", None)
    if domain_code == "module_disabled":
        code, message = "module_disabled", "A required ERP module is inactive."
    elif status in {401, 403} or isinstance(error, AccessDenied):
        code, message = "forbidden", "ERP access denied."
    elif status == 404:
        code, message = "not_found", "ERP record not found."
    elif status == 409:
        code, message = "conflict", "ERP state changed. Read it again before retrying."
    elif status in {400, 422}:
        return _failure(
            "validation_error", "ERP domain validation failed.", data={"code": domain_code}
        )
    else:
        code, message = "unavailable", "ERP policy or owner service is unavailable."
    if legacy:
        return crm_result("forbidden" if code == "module_disabled" else code, message=message)
    return _failure(code, message)


_EXPECTED = (
    AccessDenied,
    ServiceUnavailable,
    UserPreferencesError,
    HTTPException,
    BaseError,
    CatalogError,
    OwnerOperationError,
)


def _visible(scope, entries):
    visible = []
    for entry in entries:
        try:
            scope.admit(entry)
        except Exception as error:
            logger.debug(
                "ERP MCP discovery excluded %s (%s)", entry.definition.name, type(error).__name__
            )
        else:
            visible.append(entry.definition)
    return visible


def install_erp_mcp(application, *, module_apps):
    registry = build_registry(module_apps)
    application.state.erp_mcp_registry = registry

    class ERPServer(MCPServer):
        async def list_tools(self) -> list[Tool]:
            request = _active_request.get()
            try:
                scope = await anyio.to_thread.run_sync(Scope.prepare, request, module_apps)
            except Exception as error:
                result = _error(error)
                raise MCPError(
                    code=INTERNAL_ERROR, message=result.structuredContent["message"]
                ) from None
            return await anyio.to_thread.run_sync(_visible, scope, registry.entries.values())

        async def call_tool(
            self, name: str, arguments: dict, context: Context | None = None
        ) -> CallToolResult:
            request = _active_request.get()
            entry = registry.entries.get(CRM_TOOL_ALIASES.get(name, name))
            legacy = isinstance(entry, CRMTool)
            started = monotonic()
            tool_token = _active_tool_name.set(name if entry else None)
            try:
                scope = await anyio.to_thread.run_sync(Scope.prepare, request, module_apps)
                if entry is None:
                    return _failure("not_found", "ERP tool not found.")
                if not legacy:
                    try:
                        parsed = entry.input_model.model_validate(arguments)
                    except ValidationError:
                        return _failure("invalid_arguments", "Invalid tool arguments.")
                admitted = await anyio.to_thread.run_sync(scope.admit, entry)
                token = admission.set(admitted)
                scope_token = active_scope.set(scope)
                try:
                    if legacy:
                        return await entry.invoke(arguments)
                    data = await anyio.to_thread.run_sync(
                        entry.handler, scope, parsed, abandon_on_cancel=False
                    )
                    result = entry.result_model.model_validate(data).model_dump(mode="json")
                    return _result({"code": "ok", "data": result})
                finally:
                    active_scope.reset(scope_token)
                    admission.reset(token)
            except _EXPECTED as error:
                return _error(error, legacy=legacy)
            except Exception as error:
                logger.warning(
                    "ERP MCP operation failed tool=%s owner=%s request_uid=%s error_type=%s",
                    entry.definition.name if entry else None,
                    entry.owner_module if entry else None,
                    request.state.crm_request_uid,
                    type(error).__name__,
                )
                if legacy:
                    return crm_result("internal_error", message="CRM operation failed")
                return _failure("internal_error", "ERP operation failed.")
            finally:
                _active_tool_name.reset(tool_token)
                logger.debug(
                    "ERP MCP invocation tool=%s request_uid=%s elapsed_ms=%d",
                    entry.definition.name if entry else None,
                    request.state.crm_request_uid,
                    (monotonic() - started) * 1000,
                )

    server = ERPServer("erp", version="1", extensions=[ERPSkills(SKILLS_ROOT)])
    transport = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def erp_transport(scope, receive, send):
        request = Request(dict(scope), receive)
        if not getattr(request.state, "crm_request_uid", None):
            request.state.crm_request_uid = uuid4()
        token = _active_request.set(request)
        try:
            with request_diagnostics(request.state.crm_request_uid):
                await transport(scope, receive, send)
        finally:
            _active_request.reset(token)

    install_mcp(application, erp_transport, lifespan=server.session_manager.run)
