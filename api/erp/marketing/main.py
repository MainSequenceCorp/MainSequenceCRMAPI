"""Independent mailing audience and local capture API; no external send transport."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from api.erp.base.identity import actor_and_capabilities as base_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.marketing.dependencies import Dependencies
from src.erp.marketing.errors import MarketingError
from src.erp.marketing.schemas import (
    FollowupInput,
    MailingCreate,
    MailingUpdate,
    QueueInput,
    RecipientChange,
    RecipientCreate,
    SimulationInput,
    SubscriberCreate,
    SubscriptionChange,
    VersionInput,
)
from src.erp.marketing.service import Service
from src.erp.marketing.store import Store
from src.erp.module_access.http import install_module_admission
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities

PREFIX = "/api/marketing/v1"
Resource = Literal["subscribers", "mailings"]


def discovery(resource):
    states = (
        ["subscribed", "unsubscribed"]
        if resource == "subscribers"
        else ["draft", "queued", "completed", "cancelled"]
    )
    fields = (
        [("name", "Name"), ("email", "Email"), ("state", "Subscription")]
        if resource == "subscribers"
        else [
            ("name", "Mailing"),
            ("subject", "Subject"),
            ("state", "Status"),
            ("mode", "Delivery mode"),
        ]
    )
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": "Subscribers" if resource == "subscribers" else "Mailings",
            "item_label": "subscriber" if resource == "subscribers" else "mailing",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search mailings"
                    if resource == "mailings"
                    else "Search subscribers",
                    "fields": ["name", "subject" if resource == "mailings" else "email"],
                },
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [{"value": state, "label": state.title()} for state in states],
                    }
                ],
                "ordering": [],
            },
            "columns": [
                {
                    "id": key,
                    "header": label,
                    "value_path": key,
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": key != "name",
                    "importance": "primary" if key == "name" else "secondary",
                }
                for key, label in fields
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False, install_identity=True):
    resolve_modules(["base", "marketing"] if enabled else [])
    app = FastAPI(title="Marketing API", version="0.1.0")
    app.state.marketing_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)
        ba, bc = base_identity(local=local)
        return Service(
            app.state.marketing_store,
            actor,
            caps,
            Dependencies(BaseService(BaseStore(local_only=local), ba, bc), local=local),
        )

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [MarketingError, BaseError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Marketing request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Marketing storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "marketing", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            svc = service()
            svc.require("marketing.read")
            return {
                "status": "ready",
                "module": "marketing",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": svc.store.data_source_uid,
                "dependencies": svc.dependencies.ready(),
                "capabilities": sorted(svc.capabilities),
                "mode": "local_capture",
                "capture_available": local,
                "crm_enabled": svc.dependencies.crm_enabled,
            }

        @app.get(PREFIX + "/references/people/")
        def people(
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            svc = service()
            svc.require("marketing.read")
            return svc.dependencies.people(
                page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/references/people/{uid}/")
        def person(uid: UUID):
            svc = service()
            svc.require("marketing.read")
            return svc.dependencies.person(uid)

        @app.get(PREFIX + "/references/tasks/")
        def tasks(
            party_uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            svc = service()
            svc.require("marketing.read")
            return svc.dependencies.tasks(
                party_uid, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/{resource}/discovery/")
        def discover(resource: Resource):
            service().require("marketing.read")
            return discovery(resource)

        @app.get(PREFIX + "/{resource}/")
        def collection(
            resource: Resource,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: str | None = Query(None, max_length=32),
        ):
            return service().collection(
                resource, page_index=page_index, page_size=page_size, search=search, state=state
            )

        @app.post(PREFIX + "/subscribers/", status_code=201)
        def subscribe(payload: SubscriberCreate):
            return service().subscriber(payload.model_dump())

        @app.post(PREFIX + "/subscribers/{uid}/subscription/")
        def subscription(uid: UUID, payload: SubscriptionChange):
            return service().subscription(uid, payload.model_dump())

        @app.post(PREFIX + "/mailings/", status_code=201)
        def create_mailing(payload: MailingCreate):
            return service().mailing(payload.model_dump())

        @app.put(PREFIX + "/mailings/{uid}/")
        def edit_mailing(uid: UUID, payload: MailingUpdate):
            return service().mailing(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.get(PREFIX + "/mailings/{uid}/recipients/")
        def recipients(
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: str | None = Query(None, max_length=32),
        ):
            return service().collection(
                "recipients",
                mailing_uid=uid,
                page_index=page_index,
                page_size=page_size,
                search=search,
                state=state,
            )

        @app.post(PREFIX + "/mailings/{uid}/recipients/", status_code=201)
        def add_recipient(uid: UUID, payload: RecipientCreate):
            return service().add_recipient(uid, payload.model_dump())

        @app.post(PREFIX + "/mailings/{uid}/queue/")
        def queue(uid: UUID, payload: QueueInput):
            return service().queue(uid, payload.model_dump())

        @app.post(PREFIX + "/mailings/{uid}/capture/")
        def capture(uid: UUID, payload: VersionInput):
            return service().capture(uid, payload.expected_version)

        @app.post(PREFIX + "/mailings/{uid}/cancel/")
        def cancel(uid: UUID, payload: VersionInput):
            return service().cancel(uid, payload.expected_version)

        @app.get(PREFIX + "/recipients/{uid}/")
        def recipient(uid: UUID):
            return service().get("recipients", uid)

        @app.post(PREFIX + "/recipients/{uid}/remove/")
        def remove(uid: UUID, payload: RecipientChange):
            return service().remove_recipient(
                uid, payload.expected_version, payload.expected_mailing_version
            )

        @app.post(PREFIX + "/recipients/{uid}/simulate/")
        def simulate(uid: UUID, payload: SimulationInput):
            return service().simulate(uid, payload.model_dump())

        @app.post(PREFIX + "/recipients/{uid}/followup/")
        def followup(uid: UUID, payload: FollowupInput):
            return service().link_followup(uid, payload.model_dump())

        @app.get(PREFIX + "/recipients/{uid}/events/")
        def events(
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
        ):
            return service().events(uid, page_index=page_index, page_size=page_size)

        @app.get(PREFIX + "/{resource}/{uid}/")
        def get(resource: Resource, uid: UUID):
            return service().get(resource, uid)

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def audit(
            resource: Literal["subscribers", "mailings", "recipients"],
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
        ):
            return service().history(resource, uid, page_index=page_index, page_size=page_size)

    install_module_admission(app, "marketing")
    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
