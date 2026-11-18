"""Private merchant API. Public local portal routes live in a separate application."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.catalog.service import CatalogError
from src.erp.commerce.errors import CommerceError
from src.erp.commerce.schemas import (
    GrantCreate,
    InvoiceInput,
    OfferCreate,
    OfferInput,
    OfferUpdate,
    SiteCreate,
    SiteInput,
    SiteUpdate,
    VersionInput,
)
from src.erp.commerce.store import Store
from src.erp.module_access import module_available
from src.erp.module_access.http import install_module_admission
from src.erp.modules import resolve_modules

from .services import enabled, service

PREFIX = "/api/commerce/v1"
Resource = Literal["sites", "offers", "grants", "checkouts"]
LABELS = {
    "sites": "Websites",
    "offers": "Service offers",
    "grants": "Portal access",
    "checkouts": "Checkouts",
}
STATES = {
    "sites": ["draft", "published"],
    "offers": ["draft", "published"],
    "grants": ["active", "revoked"],
    "checkouts": ["placed"],
}


def discovery(resource):
    columns = [("name", "Title / reference"), ("state", "Status")]
    if resource == "sites":
        columns += [("slug", "Public address")]
    elif resource == "offers":
        columns += [("unit_price", "Unit price")]
    elif resource == "grants":
        columns += [("expires_at", "Expires")]
    else:
        columns += [("net_total", "Net amount"), ("snapshot.currency_code", "Currency")]
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
                "search": {"placeholder": "Search by title or reference", "fields": ["name"]},
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
                for key, label in columns
            ],
        },
        "bulk_actions": [],
    }


def install_errors(app):
    async def domain(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [CommerceError, BaseError, CatalogError]:
        app.add_exception_handler(error, domain)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Commerce request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Commerce is unavailable; inspect the saved result before retrying",
                }
            },
            status_code=503,
        )


def create_app(*, enabled_module=True, local=False, install_identity=True):
    resolve_modules(["base", "catalog", "commerce"] if enabled_module else [])
    app = FastAPI(title="Website and commerce API", version="0.1.0")
    app.state.commerce_store = Store(local_only=local)
    install_errors(app)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def current():
        return service(local=local, store=app.state.commerce_store)

    if enabled_module:

        @app.get(PREFIX + "/ready/")
        def ready():
            s = current()
            s.require("commerce.read")
            return {
                "status": "ready",
                "module": "commerce",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": s.store.data_source_uid,
                "dependencies": s.dependencies.ready(),
                "capabilities": sorted(s.capabilities),
                "sales_enabled": module_available("sales") and enabled("sales"),
                "finance_enabled": module_available("finance") and enabled("finance"),
            }

        @app.get(PREFIX + "/resources/")
        def resources():
            s = current()
            s.require("commerce.read")
            return {
                "items": [
                    {
                        "key": key,
                        "label": label,
                        "input_schema": (
                            SiteInput
                            if key == "sites"
                            else OfferInput
                            if key == "offers"
                            else GrantCreate
                        ).model_json_schema()
                        if key != "checkouts"
                        else {},
                        "can_write": (
                            "commerce.manage" if key == "grants" else "commerce.configure"
                        )
                        in s.capabilities
                        and key != "checkouts",
                    }
                    for key, label in LABELS.items()
                ]
            }

        @app.get(PREFIX + "/{resource}/discovery/")
        def describe(resource: Resource):
            current().require("commerce.read")
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
                raise CommerceError(422, "query", "Unsupported collection query")
            return current().collection(
                resource, page_index=page_index, page_size=page_size, search=search, state=state
            )

        @app.post(PREFIX + "/sites/", status_code=201)
        def create_site(payload: SiteCreate):
            return current().save(
                "sites",
                payload.model_dump(exclude={"request_uid"}),
                request_uid=payload.request_uid,
            )

        @app.put(PREFIX + "/sites/{uid}/")
        def edit_site(uid: UUID, payload: SiteUpdate):
            return current().save(
                "sites",
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/offers/", status_code=201)
        def create_offer(payload: OfferCreate):
            return current().save(
                "offers",
                payload.model_dump(exclude={"request_uid"}),
                request_uid=payload.request_uid,
            )

        @app.put(PREFIX + "/offers/{uid}/")
        def edit_offer(uid: UUID, payload: OfferUpdate):
            return current().save(
                "offers",
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/grants/", status_code=201)
        def grant(payload: GrantCreate):
            return current().issue_grant(payload.model_dump())

        @app.post(PREFIX + "/grants/{uid}/revoke/")
        def revoke(uid: UUID, payload: VersionInput):
            return current().revoke(uid, payload.expected_version)

        @app.post(PREFIX + "/checkouts/{uid}/invoice/")
        def invoice(uid: UUID, payload: InvoiceInput):
            return current().invoice(uid, payload.model_dump())

        @app.post(PREFIX + "/{resource}/{uid}/{action}/")
        def publication(
            resource: Literal["sites", "offers"],
            uid: UUID,
            action: Literal["publish", "unpublish"],
            payload: VersionInput,
        ):
            return current().publish(resource, uid, action, payload.expected_version)

        @app.get(PREFIX + "/checkouts/{uid}/payment/")
        def payment(uid: UUID):
            s = current()
            s.require("commerce.read")
            return s.payment(s.raw("checkouts", uid))

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            s = current()
            s.require("commerce.read")
            return (
                s.collection("sites", page_index=page_index, page_size=page_size, search=search)
                if resource == "sites"
                else s.dependencies.collection(
                    resource, page_index=page_index, page_size=page_size, search=search
                )
            )

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def history(resource: Resource, uid: UUID):
            return current().history(resource, uid)

        @app.get(PREFIX + "/{resource}/{uid}/")
        def detail(resource: Resource, uid: UUID):
            return current().get(resource, uid)

    install_module_admission(app, "commerce")
    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
