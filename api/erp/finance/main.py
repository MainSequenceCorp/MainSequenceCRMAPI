"""Finance API with independent identity, readiness and module-owned storage."""

import logging
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from api.erp.base.identity import actor_and_capabilities as base_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.finance.dependencies import Dependencies
from src.erp.finance.errors import FinanceError
from src.erp.finance.metatables import AuditEvent
from src.erp.finance.schemas import (
    AllocationInput,
    FromSalesInput,
    InvoiceCreate,
    InvoiceUpdate,
    PaymentCreate,
    PaymentUpdate,
    ReverseAllocation,
    VersionInput,
    VoidInput,
)
from src.erp.finance.service import Service
from src.erp.finance.store import Store
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/finance/v1"


def discovery(resource):
    invoice = resource == "invoices"
    fields = [
        ("name", "Reference", "primary"),
        ("party_name", "Customer / vendor", "secondary"),
        ("state", "Status", "secondary"),
        ("total", "Total", "secondary"),
        ("allocated", "Allocated", "secondary"),
        ("currency_code", "Currency", "secondary"),
    ]
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": "Invoices and bills" if invoice else "Payments",
            "item_label": "invoice" if invoice else "payment",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search by reference or party",
                    "fields": ["name", "party_name"],
                },
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [
                            {"value": s, "label": s.title()} for s in ["draft", "posted", "void"]
                        ],
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
                for key, label, importance in fields
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    resolve_modules(["base", "finance"] if enabled else [])
    app = FastAPI(title="Finance API", version="0.1.0")
    app.state.finance_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)
        base_actor, base_caps = base_identity(local=local)

        def sales():
            from src.erp.finance.sales_integration import configured_sales

            return configured_sales(local=local)

        dependencies = Dependencies(
            BaseService(BaseStore(local_only=local), base_actor, base_caps),
            sales if os.environ.get("FINANCE_SALES_ENABLED", "true") != "false" else None,
        )
        return Service(app.state.finance_store, actor, caps, dependencies)

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [FinanceError, BaseError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Finance request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Finance storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "finance", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            current = service()
            current.require("finance.read")
            return {
                "status": "ready",
                "module": "finance",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": current.store.data_source_uid,
                "dependencies": current.dependencies.ready(),
                "capabilities": sorted(current.capabilities),
                "sales_enabled": current.dependencies.sales_factory is not None,
            }

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            current = service()
            current.require("finance.read")
            return current.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/sales-orders/{uid}/")
        def sales_order(uid: UUID):
            current = service()
            current.require("finance.read")
            return current.dependencies.sales().get(uid)

        @app.post(PREFIX + "/invoices/from-sales/", status_code=201)
        def from_sales(payload: FromSalesInput):
            return service().from_sales(payload.model_dump())

        @app.post(PREFIX + "/allocations/", status_code=201)
        def allocate(payload: AllocationInput):
            return service().allocate(payload.model_dump())

        @app.post(PREFIX + "/allocations/{uid}/reverse/")
        def reverse(uid: UUID, payload: ReverseAllocation):
            return service().reverse_allocation(uid, **payload.model_dump())

        @app.get(PREFIX + "/audit/")
        def audit(resource: Literal["invoices", "payments"], record_uid: UUID):
            current = service()
            current.require("finance.configure")
            return {
                "items": current.store.read(
                    select(AuditEvent.__table__)
                    .where(AuditEvent.resource == resource, AuditEvent.record_uid == record_uid)
                    .order_by(AuditEvent.occurred_at.desc())
                    .limit(100)
                )
            }

        def mount(resource, create_schema, update_schema):
            prefix = PREFIX + "/" + resource

            @app.get(prefix + "/discovery/", name=resource + "-discovery")
            def describe():
                service().require("finance.read")
                return discovery(resource)

            @app.get(prefix + "/", name=resource + "-list")
            def collection(
                request: Request,
                page_index: int = Query(0, ge=0, le=100000),
                page_size: int = Query(25, ge=1, le=100),
                search: str = Query("", max_length=200),
                state: Literal["draft", "posted", "void"] | None = None,
            ):
                if set(request.query_params) - {"page_index", "page_size", "search", "state"}:
                    raise FinanceError(422, "invalid_query", "Unsupported Finance query")
                return service().collection(
                    resource, page_index=page_index, page_size=page_size, search=search, state=state
                )

            @app.post(prefix + "/", status_code=201, name=resource + "-create")
            def create(payload: create_schema):
                return service().save(
                    resource,
                    payload.model_dump(exclude={"request_uid"}),
                    request_uid=payload.request_uid,
                )

            @app.get(prefix + "/{uid}/allocations/", name=resource + "-allocations")
            def allocations(
                uid: UUID,
                page_index: int = Query(0, ge=0, le=100000),
                page_size: int = Query(25, ge=1, le=100),
            ):
                return service().allocation_collection(
                    resource, uid, page_index=page_index, page_size=page_size
                )

            @app.get(prefix + "/{uid}/", name=resource + "-detail")
            def detail(uid: UUID):
                return service().get(resource, uid)

            @app.put(prefix + "/{uid}/", name=resource + "-update")
            def edit(uid: UUID, payload: update_schema):
                return service().save(
                    resource,
                    payload.model_dump(exclude={"expected_version"}),
                    uid=uid,
                    expected_version=payload.expected_version,
                )

            @app.post(prefix + "/{uid}/post/", name=resource + "-post")
            def post(uid: UUID, payload: VersionInput):
                return service().transition(resource, uid, "post", payload.expected_version)

            @app.post(prefix + "/{uid}/void/", name=resource + "-void")
            def void(uid: UUID, payload: VoidInput):
                return service().transition(
                    resource, uid, "void", payload.expected_version, payload.reason
                )

        mount("invoices", InvoiceCreate, InvoiceUpdate)
        mount("payments", PaymentCreate, PaymentUpdate)
    install_request_identity(app)
    return app


app = create_app()
