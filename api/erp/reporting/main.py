"""Independent Reporting API, verified identity and explicitly local worker boundary."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mainsequence.server.fastapi import install_request_identity
from api.erp.collections import PageIndex, PageSize, SearchText, collection_get
from src.erp.module_access.http import install_module_admission
from src.erp.modules import resolve_modules
from src.erp.reporting.errors import ReportingError
from src.erp.reporting.schemas import (
    DefinitionCreate,
    DefinitionUpdate,
    Input,
    RunCreate,
    ScheduleCreate,
    ScheduleUpdate,
    VersionInput,
)
from src.erp.reporting.service import Service, now
from src.erp.reporting.sources import KINDS, configured_sources
from src.erp.reporting.store import Store

from .identity import actor_and_capabilities

PREFIX = "/api/reporting/v1"
Resource = Literal["definitions", "runs", "schedules"]
LABELS = {
    "definitions": "Saved reports",
    "runs": "Report runs",
    "schedules": "Schedules",
    "rows": "Captured source records",
}
STATES = {
    "definitions": ["active", "archived"],
    "runs": ["queued", "running", "failed", "succeeded", "cancelled"],
    "schedules": ["active", "paused"],
}


def discovery(resource):
    columns = {
        "definitions": [
            ("name", "Name", "text"),
            ("kind", "Report kind", "text"),
            ("state", "Status", "text"),
            ("search", "Source search", "text"),
        ],
        "runs": [
            ("name", "Report", "text"),
            ("state", "Status", "text"),
            ("progress", "Completed sources", "number"),
            ("created_at", "Queued", "datetime"),
        ],
        "schedules": [
            ("name", "Name", "text"),
            ("state", "Status", "text"),
            ("interval_minutes", "Interval (minutes)", "number"),
            ("next_run_at", "Next run", "datetime"),
        ],
        "rows": [
            ("name", "Source record", "text"),
            ("source", "Module", "text"),
            ("state", "Captured status", "text"),
            ("version", "Captured version", "number"),
            ("net_total", "Net amount", "text"),
            ("currency_code", "Currency", "text"),
        ],
    }[resource]
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
                "search": {"placeholder": "Search by name", "fields": ["name"]},
                "filters": (
                    []
                    if resource == "rows"
                    else [
                        {
                            "key": "state",
                            "label": "Status",
                            "type": "select",
                            "options": [{"value": v, "label": v.title()} for v in STATES[resource]],
                        }
                    ]
                ),
                "ordering": [],
            },
            "columns": [
                {
                    "id": key.replace("_", "-"),
                    "header": label,
                    "value_path": key,
                    "data_type": kind,
                    "default_visible": True,
                    "hideable": key != "name",
                    "importance": "primary" if key == "name" else "secondary",
                }
                for key, label, kind in columns
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False, install_identity=True):
    resolve_modules(["reporting"] if enabled else [])
    app = FastAPI(title="Reporting and automation API", version="0.1.0")
    app.state.reporting_store = Store(local_only=local)
    app.state.worker_ticks = {}

    def current():
        actor, caps = actor_and_capabilities(local=local)
        return Service(app.state.reporting_store, actor, caps, configured_sources(local=local))

    @app.exception_handler(ReportingError)
    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).error("Reporting request failed: %s", type(error).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Reporting storage or source access is unavailable; inspect readiness and saved state before retrying",
                }
            },
            status_code=503,
        )

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            s = current()
            s.require("reporting.read")
            return {
                "status": "ready",
                "schema_revision": "0001",
                "source_uid": s.store.data_source_uid,
                "local": local,
                "capabilities": sorted(s.capabilities),
                "sources": sorted(s.sources.factories),
                "kinds": KINDS,
                "worker_supported": local,
            }

        @app.get(PREFIX + "/worker/status/")
        def worker_status():
            s = current()
            s.require("reporting.read")
            last = app.state.worker_ticks.get(str(s.actor_uid))
            return {
                "supported": local,
                "available": bool(local and last and (now() - last).total_seconds() < 30),
                "last_tick_at": last,
            }

        if local:

            @app.post(PREFIX + "/worker/tick/")
            def tick(_payload: Input):
                s = current()
                result = s.tick()
                app.state.worker_ticks[str(s.actor_uid)] = now()
                return result

        @app.post(PREFIX + "/definitions/", status_code=201)
        def create_definition(payload: DefinitionCreate):
            return current().save(
                "definitions",
                payload.model_dump(exclude={"request_uid"}),
                request_uid=payload.request_uid,
            )

        @app.put(PREFIX + "/definitions/{uid}/")
        def update_definition(uid: UUID, payload: DefinitionUpdate):
            return current().save(
                "definitions",
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/definitions/{uid}/{action}/")
        def definition_action(
            uid: UUID, action: Literal["archive", "restore"], payload: VersionInput
        ):
            return current().definition_state(uid, action, payload.expected_version)

        @app.post(PREFIX + "/runs/", status_code=201)
        def queue(payload: RunCreate):
            return current().queue(payload.model_dump())

        @app.post(PREFIX + "/runs/{uid}/advance/")
        def advance(uid: UUID, payload: VersionInput):
            return current().advance(uid, payload.expected_version)

        @app.post(PREFIX + "/runs/{uid}/verify/")
        def verify(uid: UUID, _payload: Input):
            return current().verify(uid)

        @app.get(PREFIX + "/runs/{uid}/export/")
        def export(uid: UUID):
            return current().export(uid)

        @app.get(PREFIX + "/runs/{uid}/result/")
        def result(uid: UUID):
            return current().result(uid)

        @app.get(PREFIX + "/runs/{uid}/rows/discovery/")
        def row_discovery(uid: UUID):
            current().result_rows(uid)
            return discovery("rows")

        @app.get(PREFIX + "/runs/{uid}/rows/")
        def rows(
            uid: UUID,
            request: Request,
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
            search: SearchText = "",
        ):
            if set(request.query_params) - {"page_index", "page_size", "search"}:
                raise ReportingError(422, "query", "Unsupported result query")
            return current().rows(uid, page_index=page_index, page_size=page_size, search=search)

        @app.post(PREFIX + "/runs/{uid}/{action}/")
        def run_action(
            uid: UUID, action: Literal["retry", "recover", "cancel"], payload: VersionInput
        ):
            return current().control(uid, action, payload.expected_version)

        @app.post(PREFIX + "/schedules/", status_code=201)
        def create_schedule(payload: ScheduleCreate):
            return current().save(
                "schedules",
                payload.model_dump(exclude={"request_uid"}),
                request_uid=payload.request_uid,
            )

        @app.put(PREFIX + "/schedules/{uid}/")
        def update_schedule(uid: UUID, payload: ScheduleUpdate):
            return current().save(
                "schedules",
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/schedules/{uid}/{action}/")
        def schedule_action(uid: UUID, action: Literal["activate", "pause"], payload: VersionInput):
            return current().schedule_state(uid, action, payload.expected_version)

        @app.get(PREFIX + "/{resource}/discovery/")
        def describe(resource: Resource):
            current().require("reporting.read")
            return discovery(resource)

        @collection_get(app, PREFIX + "/{resource}/")
        def collection(
            resource: Resource,
            request: Request,
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
            search: SearchText = "",
            state: str | None = None,
        ):
            if (
                set(request.query_params) - {"page_index", "page_size", "search", "state"}
                or state
                and state not in STATES[resource]
            ):
                raise ReportingError(422, "query", "Unsupported collection query")
            return current().collection(
                resource, page_index=page_index, page_size=page_size, search=search, state=state
            )

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def history(resource: Resource, uid: UUID):
            return current().history(resource, uid)

        @app.get(PREFIX + "/{resource}/{uid}/")
        def detail(resource: Resource, uid: UUID):
            return current().get(resource, uid)

    install_module_admission(app, "reporting")
    if install_identity:
        install_request_identity(app)
    return app
