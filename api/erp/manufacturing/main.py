"""Independent Manufacturing API; explicit migrations and injected SDK identity."""

import logging
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from api.erp.base.identity import actor_and_capabilities as base_identity
from api.erp.catalog.identity import actor_and_capabilities as catalog_identity
from api.erp.inventory.identity import actor_and_capabilities as inventory_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.catalog.service import CatalogError
from src.erp.catalog.service import Service as CatalogService
from src.erp.catalog.store import Store as CatalogStore
from src.erp.inventory.dependencies import Dependencies as InventoryDependencies
from src.erp.inventory.service import Service as InventoryService
from src.erp.inventory.store import Store as InventoryStore
from src.erp.manufacturing.dependencies import Dependencies, InventoryPort
from src.erp.manufacturing.errors import ManufacturingError
from src.erp.manufacturing.schemas import (
    BomCreate,
    BomUpdate,
    ProductionCreate,
    StepFinish,
    StepStart,
    VersionInput,
)
from src.erp.manufacturing.service import Service
from src.erp.manufacturing.store import Store
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/manufacturing/v1"
Resource = Literal["boms", "orders"]
LABELS = {"boms": "Bills of materials", "orders": "Production orders"}
STATES = {
    "boms": ["draft", "active", "archived"],
    "orders": ["draft", "ready", "progress", "done", "cancelled"],
}


def discovery(resource):
    cols = [
        ("name", "Reference"),
        ("state", "Status"),
        ("quantity", "Output quantity"),
        (
            "snapshot.item_name" if resource == "boms" else "snapshot.output.item_name",
            "Finished product",
        ),
    ]
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
                "search": {"placeholder": "Search by reference", "fields": ["name"]},
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [{"value": x, "label": x.title()} for x in STATES[resource]],
                    }
                ],
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
                for key, label in cols
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    resolve_modules(["base", "catalog", "inventory", "manufacturing"] if enabled else [])
    app = FastAPI(title="Manufacturing API", version="0.1.0")
    app.state.manufacturing_store = Store(local_only=local)
    finance_enabled = os.environ.get("MANUFACTURING_FINANCE_ENABLED", "true") != "false"

    def service():
        actor, caps = actor_and_capabilities(local=local)
        ba, bc = base_identity(local=local)
        ca, cc = catalog_identity(local=local)
        ia, ic = inventory_identity(local=local)
        base = BaseService(BaseStore(local_only=local), ba, bc)
        catalog = CatalogService(CatalogStore(local_only=local), ca, cc)

        def finance():
            from src.erp.inventory.integrations import configured_finance

            return configured_finance(local=local)

        inventory = InventoryService(
            InventoryStore(local_only=local),
            ia,
            ic,
            InventoryDependencies(
                base, catalog, finance_factory=finance if finance_enabled else None
            ),
        )
        return Service(
            app.state.manufacturing_store,
            actor,
            caps,
            Dependencies(base, catalog, InventoryPort(inventory)),
        )

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [ManufacturingError, BaseError, CatalogError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Manufacturing request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Manufacturing is unavailable; inspect saved state before retrying",
                }
            },
            status_code=503,
        )

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            s = service()
            s.require("manufacturing.read")
            return {
                "status": "ready",
                "module": "manufacturing",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": s.store.data_source_uid,
                "dependencies": s.dependencies.ready(),
                "capabilities": sorted(s.capabilities),
                "finance_enabled": finance_enabled,
            }

        @app.get(PREFIX + "/{resource}/discovery/")
        def describe(resource: Resource):
            service().require("manufacturing.read")
            return discovery(resource)

        @app.get(PREFIX + "/{resource}/")
        def collection(
            resource: Resource,
            request: Request,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: str | None = None,
        ):
            if (
                set(request.query_params) - {"page_index", "page_size", "search", "state"}
                or state
                and state not in STATES[resource]
            ):
                raise ManufacturingError(422, "query", "Unsupported collection query")
            return service().collection(
                resource, page_index=page_index, page_size=page_size, search=search, state=state
            )

        @app.post(PREFIX + "/boms/", status_code=201)
        def create_bom(payload: BomCreate):
            return service().bom(
                payload.model_dump(exclude={"request_uid"}), request_uid=payload.request_uid
            )

        @app.put(PREFIX + "/boms/{uid}/")
        def edit_bom(uid: UUID, payload: BomUpdate):
            return service().bom(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/boms/{uid}/{action}/")
        def recipe_action(uid: UUID, action: Literal["activate", "archive"], payload: VersionInput):
            return service().bom_action(uid, action, payload.expected_version)

        @app.post(PREFIX + "/orders/", status_code=201)
        def create_production(payload: ProductionCreate):
            return service().production(payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/{action}/")
        def production_action(
            uid: UUID,
            action: Literal["reserve", "cancel", "complete", "finance"],
            payload: VersionInput,
        ):
            return service().transition(uid, action, payload.expected_version)

        @app.post(PREFIX + "/orders/{uid}/steps/{step_uid}/start/")
        def start(uid: UUID, step_uid: UUID, payload: StepStart):
            return service().step(uid, step_uid, "start", payload.model_dump())

        @app.post(PREFIX + "/orders/{uid}/steps/{step_uid}/finish/")
        def finish(uid: UUID, step_uid: UUID, payload: StepFinish):
            return service().step(uid, step_uid, "finish", payload.model_dump())

        @app.get(PREFIX + "/orders/{uid}/valuation/")
        def valuation(uid: UUID):
            return service().valuation(uid)

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            s = service()
            s.require("manufacturing.read")
            return (
                s.collection(
                    "boms",
                    state="active",
                    page_index=page_index,
                    page_size=page_size,
                    search=search,
                )
                if resource == "boms"
                else s.dependencies.collection(
                    resource, page_index=page_index, page_size=page_size, search=search
                )
            )

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def audit(resource: Resource, uid: UUID):
            return service().history(resource, uid)

        @app.get(PREFIX + "/{resource}/{uid}/")
        def detail(resource: Resource, uid: UUID):
            return service().get(resource, uid)

    install_request_identity(app)
    return app


app = create_app()
