"""Base-only entrypoint. Identity is installed after every business route."""

import logging
from dataclasses import asdict
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, create_model
from sqlalchemy import select

from mainsequence.server.fastapi import install_request_identity
from api.erp.collections import PageIndex, PageSize, SearchText
from src.erp.base.metatables import RESOURCES, AuditEvent
from src.erp.base.schemas import INPUTS, AllocationInput, RoundInput, VersionInput
from src.erp.base.service import BaseError, Service
from src.erp.base.store import Store
from src.erp.identity_composition import identity_consumers
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/base/v1"
TITLES = {
    "parties": "People and organizations",
    "affiliations": "Affiliations",
    "addresses": "Addresses",
    "operating-companies": "Operating companies",
    "countries": "Countries",
    "subdivisions": "Subdivisions",
    "languages": "Languages",
    "currencies": "Currencies",
    "number-sequences": "Number sequences",
    "settings": "Shared defaults",
    "preferences": "My preferences",
}


def discovery(resource):
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
                "search": {"placeholder": "Search by name", "fields": ["name"]},
                "filters": [{"key": "archived", "label": "Archived", "type": "boolean"}],
                "ordering": [],
            },
            "columns": [
                {
                    "id": "name",
                    "header": "Name",
                    "value_path": "name",
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": False,
                    "importance": "primary",
                },
                {
                    "id": "version",
                    "header": "Version",
                    "value_path": "version",
                    "data_type": "number",
                    "default_visible": True,
                    "hideable": True,
                    "importance": "tertiary",
                },
            ],
        },
        "bulk_actions": [],
    }


def service_for(app: FastAPI, *, local: bool) -> Service:
    actor, capabilities = actor_and_capabilities(local=local)
    store = app.state.base_store
    return Service(store, actor, capabilities, consumers=identity_consumers(store))


def create_app(*, enabled=True, local=False, install_identity=True):
    modules = resolve_modules(["base"] if enabled else [])
    app = FastAPI(title="ERP Base API", version="0.1.0")
    app.state.base_store = Store(local_only=local)
    app.state.base_local = local

    def service():
        return service_for(app, local=local)

    @app.exception_handler(BaseError)
    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Base request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Base storage or identity is unavailable. Retry after checking local readiness.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "base", "enabled": bool(modules)}

    if modules:

        @app.get(PREFIX + "/ready/")
        def ready():
            current = service()
            current.require("base.read")
            source = current.store.data_source_uid
            settings = current.collection("settings")["items"]
            if len(settings) != 1:
                raise BaseError(
                    503, "not_initialized", "Apply Base migrations and seed shared defaults locally"
                )
            return {
                "status": "ready",
                "module": "base",
                "schema_revision": "0002",
                "local": local,
                "capabilities": sorted(current.capabilities),
                "data_source_uid": source,
                "modules": [asdict(module) for module in modules],
            }

        @app.get(PREFIX + "/catalog/")
        def catalog():
            current = service()
            current.require("base.read")
            return {
                "resources": [
                    {
                        "key": key,
                        "label": TITLES[key],
                        "input_schema": INPUTS[key].model_json_schema(),
                        "can_write": current.permission(key) in current.capabilities,
                        "can_allocate": key == "number-sequences"
                        and "base.write" in current.capabilities,
                        "can_archive": key not in {"settings", "preferences"}
                        and current.permission(key) in current.capabilities,
                    }
                    for key in RESOURCES
                ]
            }

        def mount(resource):
            root = PREFIX + "/" + resource
            model = INPUTS[resource]
            edit_model = create_model(
                model.__name__ + "Update",
                __base__=model,
                expected_version=(int, Field(ge=1, strict=True)),
            )

            def list_records(
                page_index: PageIndex = 0,
                page_size: PageSize = 25,
                search: SearchText = "",
                archived: bool = False,
                kind: str | None = None,
            ):
                return service().collection(
                    resource,
                    page_index=page_index,
                    page_size=page_size,
                    search=search,
                    archived=archived,
                    kind=kind,
                )

            def describe(request: Request):
                service().require("base.read")
                if set(request.query_params) - {"search", "archived"}:
                    raise BaseError(
                        422,
                        "invalid_discovery_query",
                        "Discovery accepts only semantic search and archived filters",
                    )
                return discovery(resource)

            def create_record(payload):
                return service().save(resource, payload.model_dump())

            create_record.__annotations__["payload"] = model

            def read_record(uid: UUID):
                return service().get(resource, uid)

            def edit_record(uid: UUID, payload):
                return service().save(
                    resource,
                    payload.model_dump(exclude={"expected_version"}, exclude_unset=True),
                    uid=uid,
                    expected_version=payload.expected_version,
                )

            edit_record.__annotations__["payload"] = edit_model

            def archive_record(uid: UUID, payload: VersionInput):
                return service().archive(resource, uid, payload.expected_version)

            def restore_record(uid: UUID, payload: VersionInput):
                return service().archive(resource, uid, payload.expected_version, restore=True)

            for method, path, handler, code in [
                ("GET", "/", list_records, 200),
                ("GET", "/discovery/", describe, 200),
                ("POST", "/", create_record, 201),
                ("GET", "/{uid}/", read_record, 200),
                ("PUT", "/{uid}/", edit_record, 200),
            ]:
                app.add_api_route(
                    root + path,
                    handler,
                    methods=[method],
                    status_code=code,
                    name=f"base_{resource}_{handler.__name__}",
                )
            if resource not in {"settings", "preferences"}:
                app.add_api_route(
                    root + "/{uid}/archive/",
                    archive_record,
                    methods=["POST"],
                    name=f"base_{resource}_archive",
                )
                app.add_api_route(
                    root + "/{uid}/restore/",
                    restore_record,
                    methods=["POST"],
                    name=f"base_{resource}_restore",
                )

        for resource in RESOURCES:
            mount(resource)

        @app.post(PREFIX + "/number-sequences/{uid}/allocate/")
        def allocate(uid: UUID, payload: AllocationInput):
            return service().allocate(uid, payload.request_uid, payload.expected_version)

        @app.post(PREFIX + "/currencies/{uid}/round/")
        def round_amount(uid: UUID, payload: RoundInput):
            return service().round_amount(uid, payload.amount)

        @app.get(PREFIX + "/audit/")
        def audit(record_uid: UUID, limit: int = Query(50, ge=1, le=100)):
            current = service()
            current.require("base.configure")
            table = AuditEvent.__table__
            return {
                "items": current.store.read(
                    select(table)
                    .where(table.c.record_uid == record_uid)
                    .order_by(table.c.occurred_at.desc(), table.c.uid)
                    .limit(limit)
                )
            }

    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
