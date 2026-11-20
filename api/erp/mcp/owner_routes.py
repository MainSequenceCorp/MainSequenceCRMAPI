"""Bind selected ERP tools to their typed owner endpoints in-process.

The catalogue supplies fixed route templates and resource values at startup.
The owner function is called once inside MCP's verified actor and admission
context. Client arguments cannot select a route, HTTP method, or handler.
"""

from copy import copy
from inspect import iscoroutinefunction
from urllib.parse import urlencode

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from pydantic import BaseModel, JsonValue, RootModel, TypeAdapter, create_model

from src.erp.base.service import BaseError
from src.erp.catalog.service import CatalogError
from src.erp.collaboration.errors import CollaborationError
from src.erp.commerce.errors import CommerceError
from src.erp.finance.errors import FinanceError
from src.erp.inventory.errors import InventoryError
from src.erp.manufacturing.errors import ManufacturingError
from src.erp.marketing.errors import MarketingError
from src.erp.modules import MODULES
from src.erp.people.errors import PeopleError
from src.erp.projects.errors import ProjectsError
from src.erp.purchasing.errors import PurchasingError
from src.erp.reporting.errors import ReportingError
from src.erp.sales.errors import SalesError

from .contracts import EmptyInput

_DOMAIN_ERRORS = (
    BaseError,
    CatalogError,
    CollaborationError,
    CommerceError,
    FinanceError,
    InventoryError,
    ManufacturingError,
    MarketingError,
    PeopleError,
    ProjectsError,
    PurchasingError,
    ReportingError,
    SalesError,
)


class OwnerOperationError(Exception):
    def __init__(self, error):
        super().__init__("ERP owner operation failed")
        self.status = error.status
        self.code = error.code


class OwnerResult(RootModel[dict[str, JsonValue] | list[JsonValue]]):
    """JSON projection from the owner when the route has no response DTO."""


class OwnerRoutes:
    def __init__(self, registry, owner, skill):
        self.registry = registry
        self.owner = owner
        self.skill = skill
        self.app = registry.module_apps[owner]
        self.prefix = "/api/erp/v1" if owner == "user_preferences" else MODULES[owner].api_prefix
        routes = [*self.app.routes, *getattr(self.app.state, "erp_mcp_banking_routes", ())]
        self.routes = {
            (method, route.path): route
            for route in routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }

    def read(self, name, path, description, **options):
        self.bind(name, "GET", path, description, kind="read", **options)

    def write(self, name, method, path, description, **options):
        self.bind(name, method, path, description, kind="write", **options)

    def preview(self, name, path, description, **options):
        self.bind(name, "POST", path, description, kind="preview", **options)

    def bind(
        self,
        name,
        method,
        path,
        description,
        *,
        kind,
        permission=None,
        fixed=None,
        required_modules=(),
        local_only=False,
        organization_admin=False,
        available=None,
    ):
        route = self.routes[(method, self.prefix + path)]
        dep = route.dependant
        if (
            iscoroutinefunction(route.endpoint)
            or dep.dependencies
            or dep.header_params
            or dep.cookie_params
            or dep.response_param_name
            or dep.background_tasks_param_name
            or dep.security_scopes_param_name
            or len(dep.body_params) > 1
        ):
            raise TypeError(f"Unsupported ERP owner endpoint for {name}")
        args = {field.name: field.field_info for field in (*dep.path_params, *dep.query_params)}
        fixed_values = {
            key: TypeAdapter(args.pop(key).annotation).validate_python(value)
            for key, value in (fixed or {}).items()
        }
        body = dep.body_params[0] if dep.body_params else None
        body_type = body.field_info.annotation if body else EmptyInput
        if not issubclass(body_type, BaseModel) or args.keys() & body_type.model_fields.keys():
            raise TypeError(f"Ambiguous ERP owner schema for {name}")

        arguments = create_model(
            "".join(part.title() for part in name.split("_")) + "Arguments",
            __base__=body_type,
            **{key: (info.annotation, copy(info)) for key, info in args.items()},
        )

        def invoke(scope, data):
            params = {**fixed_values, **{key: getattr(data, key) for key in args}}
            if body is not None:
                original = {
                    key: getattr(data, key)
                    for key in body_type.model_fields
                    if key in data.model_fields_set
                }
                params[body.name] = body_type.model_validate(original)
            if dep.request_param_name:
                query = {
                    field.alias: params[field.name]
                    for field in dep.query_params
                    if field.name in data.model_fields_set and params[field.name] is not None
                }
                params[dep.request_param_name] = Request(
                    {
                        **scope.request.scope,
                        "app": self.app,
                        "query_string": urlencode(query, doseq=True).encode(),
                    }
                )
            try:
                output = route.endpoint(**params)
            except _DOMAIN_ERRORS as error:
                raise OwnerOperationError(error) from error
            return jsonable_encoder(output)

        capabilities = (f"{self.owner}.{permission}",) if permission else ()
        self.registry.operation(
            name,
            description=description,
            owner=self.owner,
            capabilities=capabilities,
            skill=self.skill,
            inputs=arguments,
            output=OwnerResult,
            handler=invoke,
            kind=kind,
            required_modules=required_modules,
            local_only=local_only,
            organization_admin=organization_admin,
            available=available,
        )
