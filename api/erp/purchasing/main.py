"""Independently launched Purchasing API; migrations are explicit, never startup work."""

import logging
import os
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
from src.erp.purchasing.dependencies import Dependencies
from src.erp.purchasing.errors import PurchasingError
from src.erp.purchasing.metatables import AuditEvent
from src.erp.purchasing.schemas import (
    AcceptInput,
    BillInput,
    CreateInput,
    ReceiptInput,
    RevokeInput,
    UpdateInput,
    VersionInput,
)
from src.erp.purchasing.service import Service
from src.erp.purchasing.store import Store

from .identity import actor_and_capabilities

PREFIX = "/api/purchasing/v1"
STATES = ("draft", "rfq", "confirmed", "closed", "cancelled")


def discovery():
    columns = [
        ("name", "Reference", "primary"),
        ("supplier_name", "Supplier", "secondary"),
        ("state", "Status", "secondary"),
        ("net_total", "Net amount", "secondary"),
        ("currency_code", "Currency", "secondary"),
    ]
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": "orders",
            "label": "Purchase orders",
            "item_label": "order",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search by reference or supplier",
                    "fields": ["name", "supplier_name"],
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
    resolve_modules(["base", "catalog", "purchasing"] if enabled else [])
    app = FastAPI(title="Purchasing API", version="0.1.0")
    app.state.purchasing_store = Store(local_only=local)

    def service():
        actor, capabilities = actor_and_capabilities(local=local)
        base_actor, base_caps = base_identity(local=local)
        catalog_actor, catalog_caps = catalog_identity(local=local)
        base = BaseService(BaseStore(local_only=local), base_actor, base_caps)
        catalog = CatalogService(CatalogStore(local_only=local), catalog_actor, catalog_caps)

        def inventory():
            from src.erp.purchasing.integrations import configured_inventory

            return configured_inventory(local=local, base=base, catalog=catalog)

        def finance():
            from src.erp.purchasing.integrations import configured_finance

            return configured_finance(local=local, base=base)

        dependencies = Dependencies(
            base,
            catalog,
            inventory
            if os.environ.get("PURCHASING_INVENTORY_ENABLED", "true") != "false"
            else None,
            finance if os.environ.get("PURCHASING_FINANCE_ENABLED", "true") != "false" else None,
        )
        return Service(app.state.purchasing_store, actor, capabilities, dependencies)

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in (PurchasingError, BaseError, CatalogError):
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Purchasing request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Purchasing storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "purchasing", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            current = service()
            current.require("purchasing.read")
            dependencies = current.dependencies.ready()
            return {
                "status": "ready",
                "module": "purchasing",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": current.store.data_source_uid,
                "dependencies": dependencies,
                "capabilities": sorted(current.capabilities),
                "inventory_enabled": current.dependencies.inventory_factory is not None,
                "finance_enabled": current.dependencies.finance_factory is not None,
            }

        @app.get(PREFIX + "/orders/discovery/")
        def describe():
            service().require("purchasing.read")
            return discovery()

        @app.get(PREFIX + "/orders/")
        def collection(
            request: Request,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: Literal["draft", "rfq", "confirmed", "closed", "cancelled"] | None = None,
        ):
            if set(request.query_params) - {"page_index", "page_size", "search", "state"}:
                raise PurchasingError(422, "invalid_query", "Unsupported Purchasing query")
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

        @app.get(PREFIX + "/orders/{uid}/fulfillment/")
        def fulfillment(uid: UUID):
            return service().fulfillment(uid)

        @app.post(PREFIX + "/orders/{uid}/lines/{line_uid}/accept/")
        def accept(uid: UUID, line_uid: UUID, payload: AcceptInput):
            return service().accept(uid, line_uid, payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/lines/{line_uid}/revoke/")
        def revoke(uid: UUID, line_uid: UUID, payload: RevokeInput):
            return service().revoke(uid, line_uid, payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/lines/{line_uid}/receipt/")
        def receipt(uid: UUID, line_uid: UUID, payload: ReceiptInput):
            return service().receipt(uid, line_uid, payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/bill/")
        def bill(uid: UUID, payload: BillInput):
            return service().bill(uid, payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/{action}/")
        def action(
            uid: UUID,
            action: Literal["rfq", "confirm", "cancel", "reopen", "close"],
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
            current.require("purchasing.read")
            return current.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/audit/")
        def audit(record_uid: UUID):
            current = service()
            current.require("purchasing.manage")
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
