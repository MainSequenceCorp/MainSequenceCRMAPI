"""Independent Inventory API; authentication comes from the installed SDK."""

import logging
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from api.erp.base.identity import actor_and_capabilities as base_identity
from api.erp.catalog.identity import actor_and_capabilities as catalog_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.catalog.service import CatalogError
from src.erp.catalog.service import Service as CatalogService
from src.erp.catalog.store import Store as CatalogStore
from src.erp.inventory.dependencies import Dependencies
from src.erp.inventory.errors import InventoryError
from src.erp.inventory.schemas import (
    FromSales,
    LocationCreate,
    LocationUpdate,
    MovementCreate,
    ReturnInput,
    StockItemCreate,
    VersionInput,
)
from src.erp.inventory.service import Service
from src.erp.inventory.store import Store
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/inventory/v1"
Resource = Literal["locations", "stock-items", "balances", "movements"]
FIELDS = {
    "locations": [("name", "Location"), ("code", "Code"), ("usage", "Usage")],
    "stock-items": [
        ("name", "Product"),
        ("snapshot.company_name", "Company"),
        ("unit_cost", "Standard cost"),
        ("snapshot.currency_code", "Currency"),
    ],
    "balances": [
        ("name", "Product"),
        ("location_name", "Location"),
        ("on_hand", "On hand"),
        ("reserved", "Reserved"),
        ("available", "Available"),
        ("unit_name", "Unit"),
    ],
    "movements": [
        ("name", "Reference"),
        ("snapshot.item_name", "Product"),
        ("kind", "Kind"),
        ("state", "Status"),
        ("quantity", "Quantity"),
        ("snapshot.unit_name", "Unit"),
    ],
}
LABELS = {
    "locations": "Locations",
    "stock-items": "Stock items",
    "balances": "Stock balances",
    "movements": "Movements",
}


def discovery(resource):
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": LABELS[resource],
            "item_label": "record",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {"placeholder": "Search " + LABELS[resource].lower(), "fields": ["name"]},
                "filters": (
                    [
                        {
                            "key": "state",
                            "label": "Status",
                            "type": "select",
                            "options": [
                                {"value": s, "label": s.title()}
                                for s in ["draft", "ready", "done", "cancelled"]
                            ],
                        }
                    ]
                    if resource == "movements"
                    else []
                ),
                "ordering": [],
            },
            "columns": [
                {
                    "id": key.replace(".", "-").replace("_", "-"),
                    "header": label,
                    "value_path": key,
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": key != "name",
                    "importance": "primary" if key == "name" else "secondary",
                }
                for key, label in FIELDS[resource]
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    resolve_modules(["base", "catalog", "inventory"] if enabled else [])
    app = FastAPI(title="Inventory API", version="0.1.0")
    app.state.inventory_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)
        ba, bc = base_identity(local=local)
        ca, cc = catalog_identity(local=local)

        def sales():
            from src.erp.inventory.integrations import configured_sales

            return configured_sales(local=local)

        def finance():
            from src.erp.inventory.integrations import configured_finance

            return configured_finance(local=local)

        return Service(
            app.state.inventory_store,
            actor,
            caps,
            Dependencies(
                BaseService(BaseStore(local_only=local), ba, bc),
                CatalogService(CatalogStore(local_only=local), ca, cc),
                sales if os.environ.get("INVENTORY_SALES_ENABLED", "true") != "false" else None,
                finance if os.environ.get("INVENTORY_FINANCE_ENABLED", "true") != "false" else None,
            ),
        )

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [InventoryError, BaseError, CatalogError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Inventory request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Inventory request failed; inspect saved state before retrying",
                }
            },
            status_code=503,
        )

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            svc = service()
            svc.require("inventory.read")
            source = svc.store.data_source_uid
            return {
                "ready": True,
                "capabilities": sorted(svc.capabilities),
                "data_source_uid": source,
                "prerequisites": svc.dependencies.ready(),
                "sales_enabled": svc.dependencies.sales_factory is not None,
                "finance_enabled": svc.dependencies.finance_factory is not None,
            }

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: Literal["companies", "items", "orders"],
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            svc = service()
            svc.require("inventory.read")
            return svc.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/references/orders/{uid}/")
        def order(uid: UUID):
            svc = service()
            svc.require("inventory.read")
            return svc.dependencies.sales().get(uid)

        @app.post(PREFIX + "/from-sales/", status_code=201)
        def from_sales(payload: FromSales):
            return service().from_sales(payload.model_dump())

        @app.post(PREFIX + "/locations/", status_code=201)
        def location(payload: LocationCreate):
            return service().location(payload.model_dump())

        @app.put(PREFIX + "/locations/{uid}/")
        def rename(uid: UUID, payload: LocationUpdate):
            return service().location(payload.model_dump(), uid)

        @app.post(PREFIX + "/stock-items/", status_code=201)
        def stock_item(payload: StockItemCreate):
            return service().stock_item(payload.model_dump())

        @app.post(PREFIX + "/movements/", status_code=201)
        def movement(payload: MovementCreate):
            return service().movement(payload.model_dump())

        @app.post(PREFIX + "/movements/{uid}/reverse/", status_code=201)
        def reverse(uid: UUID, payload: ReturnInput):
            return service().reverse(uid, payload.model_dump())

        @app.post(PREFIX + "/movements/{uid}/finance/")
        def finance_post(uid: UUID, payload: VersionInput):
            return service().post_finance(uid, payload.expected_version)

        @app.get(PREFIX + "/movements/{uid}/finance/")
        def finance_entries(uid: UUID):
            return service().finance_entries(uid)

        @app.post(PREFIX + "/movements/{uid}/{action}/")
        def transition(
            uid: UUID, action: Literal["prepare", "complete", "cancel"], payload: VersionInput
        ):
            return service().transition(uid, action, payload.expected_version)

        @app.post(PREFIX + "/{resource}/{uid}/archive/")
        def archive(
            resource: Literal["locations", "stock-items"], uid: UUID, payload: VersionInput
        ):
            return service().archive(resource, uid, payload.expected_version)

        @app.post(PREFIX + "/{resource}/{uid}/restore/")
        def restore(
            resource: Literal["locations", "stock-items"], uid: UUID, payload: VersionInput
        ):
            return service().archive(resource, uid, payload.expected_version, restore=True)

        @app.get(PREFIX + "/{resource}/discovery/")
        def discover(resource: Resource):
            service().require("inventory.read")
            return discovery(resource)

        @app.get(PREFIX + "/{resource}/")
        def collection(
            resource: Resource,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: str | None = Query(None, max_length=24),
            include_archived: bool = False,
            operating_company_uid: UUID | None = None,
            stock_item_uid: UUID | None = None,
        ):
            return service().collection(
                resource,
                page_index=page_index,
                page_size=page_size,
                search=search,
                state=state,
                include_archived=include_archived,
                operating_company_uid=operating_company_uid,
                stock_item_uid=stock_item_uid,
            )

        @app.get(PREFIX + "/{resource}/{uid}/")
        def get(resource: Resource, uid: UUID):
            return service().get(resource, uid)

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def history(
            resource: Resource,
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
        ):
            return service().history(resource, uid, page_index=page_index, page_size=page_size)

    install_request_identity(app)
    return app


app = create_app()
