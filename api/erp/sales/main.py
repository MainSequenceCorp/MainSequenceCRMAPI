"""Independently launched Sales API; migrations are explicit, never startup work."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from api.erp.base.identity import actor_and_capabilities as base_identity
from api.erp.catalog.identity import actor_and_capabilities as catalog_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.catalog.service import CatalogError
from src.erp.catalog.service import Service as CatalogService
from src.erp.catalog.store import Store as CatalogStore
from src.erp.modules import resolve_modules
from src.erp.sales.dependencies import Dependencies
from src.erp.sales.errors import SalesError
from src.erp.sales.metatables import AuditEvent
from src.erp.sales.schemas import CreateInput, UpdateInput, VersionInput
from src.erp.sales.service import Service
from src.erp.sales.store import Store

from .identity import actor_and_capabilities

PREFIX = "/api/sales/v1"
STATES = ("draft", "quoted", "confirmed", "cancelled")


def discovery():
    columns = [
        ("name", "Reference", "primary"),
        ("customer_name", "Customer", "secondary"),
        ("state", "Status", "secondary"),
        ("net_total", "Net amount", "secondary"),
        ("currency_code", "Currency", "secondary"),
    ]
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": "orders",
            "label": "Quotations and orders",
            "item_label": "order",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search by reference or customer",
                    "fields": ["name", "customer_name"],
                },
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [{"value": s, "label": s.title()} for s in STATES],
                    }
                ],
                "ordering": [],
            },
            "columns": [
                {
                    "id": key.replace("_", "-"),
                    "header": label,
                    "value_path": key,
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": key != "name",
                    "importance": importance,
                }
                for key, label, importance in columns
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    resolve_modules(["base", "catalog", "sales"] if enabled else [])
    app = FastAPI(title="Sales API", version="0.1.0")
    app.state.sales_store = Store(local_only=local)

    def service():
        actor, capabilities = actor_and_capabilities(local=local)
        base_actor, base_caps = base_identity(local=local)
        catalog_actor, catalog_caps = catalog_identity(local=local)
        dependencies = Dependencies(
            BaseService(BaseStore(local_only=local), base_actor, base_caps),
            CatalogService(CatalogStore(local_only=local), catalog_actor, catalog_caps),
            local=local,
        )
        return Service(app.state.sales_store, actor, capabilities, dependencies)

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in (SalesError, BaseError, CatalogError):
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Sales request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Sales storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "sales", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            current = service()
            current.require("sales.read")
            dependencies = current.dependencies.ready()
            return {
                "status": "ready",
                "module": "sales",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": current.store.data_source_uid,
                "dependencies": dependencies,
                "capabilities": sorted(current.capabilities),
            }

        @app.get(PREFIX + "/orders/discovery/")
        def describe():
            service().require("sales.read")
            return discovery()

        @app.get(PREFIX + "/orders/")
        def collection(
            request: Request,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: Literal["draft", "quoted", "confirmed", "cancelled"] | None = None,
        ):
            if set(request.query_params) - {"page_index", "page_size", "search", "state"}:
                raise SalesError(422, "invalid_query", "Unsupported Sales query")
            return service().collection(
                page_index=page_index, page_size=page_size, search=search, state=state
            )

        @app.post(PREFIX + "/orders/", status_code=201)
        def create(payload: CreateInput):
            return service().save(
                payload.model_dump(exclude={"request_uid"}), request_uid=payload.request_uid
            )

        @app.get(PREFIX + "/orders/{uid}/")
        def detail(uid: UUID):
            return service().get(uid)

        @app.put(PREFIX + "/orders/{uid}/")
        def edit(uid: UUID, payload: UpdateInput):
            return service().save(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/orders/{uid}/{action}/")
        def action(
            uid: UUID,
            action: Literal["quoted", "confirm", "cancel", "reopen"],
            payload: VersionInput,
        ):
            return service().transition(uid, action, payload.expected_version)

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            current = service()
            current.require("sales.read")
            return current.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/audit/")
        def audit(record_uid: UUID):
            current = service()
            current.require("sales.configure")
            return {
                "items": current.store.read(
                    select(AuditEvent.__table__)
                    .where(AuditEvent.record_uid == record_uid)
                    .order_by(AuditEvent.occurred_at.desc())
                    .limit(100)
                )
            }

    install_request_identity(app)
    return app


app = create_app()
