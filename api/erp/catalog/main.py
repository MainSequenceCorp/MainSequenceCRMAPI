"""Catalog-only FastAPI entrypoint; no startup migrations or CRM requirement."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, create_model
from sqlalchemy import select

from mainsequence.server.fastapi import install_request_identity
from src.erp.catalog.metatables import RESOURCES, AuditEvent
from src.erp.catalog.schemas import INPUTS, ConvertInput, VersionInput
from src.erp.catalog.service import CatalogError, Service
from src.erp.catalog.store import Store
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/catalog/v1"
TITLES = {
    "items": "Products and services",
    "categories": "Product categories",
    "units": "Units of measure",
    "unit-groups": "Unit groups",
}


def discovery(resource):
    columns = [("name", "Name", "primary"), ("code", "Code", "secondary")]
    filters = [{"key": "archived", "label": "Archived", "type": "boolean"}]
    if resource == "items":
        columns.append(("kind", "Kind", "secondary"))
        filters.append(
            {
                "key": "kind",
                "label": "Kind",
                "type": "select",
                "options": [{"value": k, "label": k.title()} for k in ("product", "service")],
            }
        )
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": TITLES[resource],
            "item_label": "record",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {"placeholder": "Search by name or code", "fields": ["name", "code"]},
                "filters": filters,
                "ordering": [],
            },
            "columns": [
                {
                    "id": k,
                    "header": label,
                    "value_path": k,
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": k != "name",
                    "importance": importance,
                }
                for k, label, importance in columns
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    modules = resolve_modules(["catalog"] if enabled else [])
    app = FastAPI(title="Catalog API", version="0.1.0")
    app.state.catalog_store = Store(local_only=local)

    def service():
        actor, capabilities = actor_and_capabilities(local=local)
        return Service(app.state.catalog_store, actor, capabilities)

    @app.exception_handler(CatalogError)
    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Catalog request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Catalog storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "catalog", "enabled": bool(modules)}

    if modules:

        @app.get(PREFIX + "/ready/")
        def ready():
            current = service()
            current.require("catalog.read")
            return {
                "status": "ready",
                "module": "catalog",
                "schema_revision": "0002",
                "local": local,
                "data_source_uid": current.store.data_source_uid,
                "capabilities": sorted(current.capabilities),
            }

        @app.get(PREFIX + "/resources/")
        def resources():
            current = service()
            current.require("catalog.read")
            return {
                "resources": [
                    {
                        "key": k,
                        "label": TITLES[k],
                        "input_schema": INPUTS[k].model_json_schema(),
                        "can_write": current.permission(k) in current.capabilities,
                        "can_archive": current.permission(k) in current.capabilities,
                    }
                    for k in RESOURCES
                ]
            }

        @app.post(PREFIX + "/convert/")
        def convert(payload: ConvertInput):
            return service().convert(payload.model_dump())

        @app.get(PREFIX + "/audit/")
        def audit(record_uid: UUID, limit: int = Query(50, ge=1, le=100)):
            current = service()
            current.require("catalog.configure")
            return {
                "items": current.store.read(
                    select(AuditEvent.__table__)
                    .where(AuditEvent.record_uid == record_uid)
                    .order_by(AuditEvent.occurred_at.desc(), AuditEvent.uid)
                    .limit(limit)
                )
            }

        def mount(resource):
            root = PREFIX + "/" + resource
            model = INPUTS[resource]
            edit_model = create_model(
                model.__name__ + "Update",
                __base__=model,
                expected_version=(int, Field(ge=1, strict=True)),
            )

            def validate_query(request, *, discovery_query=False):
                allowed = {"search", "archived"}
                if resource == "items":
                    allowed.add("kind")
                if resource == "units":
                    allowed.add("group_uid")
                if not discovery_query:
                    allowed.update({"page_index", "page_size"})
                if set(request.query_params) - allowed:
                    raise CatalogError(422, "invalid_query", "Unsupported Catalog query field")

            def list_records(
                request: Request,
                page_index: int = Query(0, ge=0, le=100000),
                page_size: int = Query(25, ge=1, le=100),
                search: str = Query("", max_length=200),
                archived: bool = False,
                kind: Literal["product", "service"] | None = None,
                group_uid: UUID | None = None,
            ):
                validate_query(request)
                return service().collection(
                    resource,
                    page_index=page_index,
                    page_size=page_size,
                    search=search,
                    archived=archived,
                    kind=kind,
                    group_uid=group_uid,
                )

            def describe(request: Request):
                service().require("catalog.read")
                validate_query(request, discovery_query=True)
                return discovery(resource)

            def create_record(payload):
                return service().save(resource, payload.model_dump())

            create_record.__annotations__["payload"] = model

            def read_record(uid: UUID):
                return service().get(resource, uid)

            def edit_record(uid: UUID, payload):
                return service().save(
                    resource,
                    payload.model_dump(exclude={"expected_version"}),
                    uid=uid,
                    expected_version=payload.expected_version,
                )

            edit_record.__annotations__["payload"] = edit_model

            def archive(uid: UUID, payload: VersionInput):
                return service().archive(resource, uid, payload.expected_version)

            def restore(uid: UUID, payload: VersionInput):
                return service().archive(resource, uid, payload.expected_version, restore=True)

            for method, path, handler, status in [
                ("GET", "/", list_records, 200),
                ("GET", "/discovery/", describe, 200),
                ("POST", "/", create_record, 201),
                ("GET", "/{uid}/", read_record, 200),
                ("PUT", "/{uid}/", edit_record, 200),
                ("POST", "/{uid}/archive/", archive, 200),
                ("POST", "/{uid}/restore/", restore, 200),
            ]:
                app.add_api_route(
                    root + path,
                    handler,
                    methods=[method],
                    status_code=status,
                    name=f"catalog_{resource}_{handler.__name__}",
                )

        for resource in RESOURCES:
            mount(resource)
    install_request_identity(app)
    return app


app = create_app()
