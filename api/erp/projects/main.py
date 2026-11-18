"""Independent delivery API and verified platform identity."""

import logging
import os
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from api.erp.base.identity import actor_and_capabilities as base_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.module_access import module_available
from src.erp.module_access.http import install_module_admission
from src.erp.modules import resolve_modules
from src.erp.projects.dependencies import Dependencies
from src.erp.projects.errors import ProjectsError
from src.erp.projects.metatables import AuditEvent
from src.erp.projects.schemas import (
    BillInput,
    FromSales,
    ProjectCreate,
    ProjectUpdate,
    TaskCreate,
    TaskState,
    TaskUpdate,
    TimeInput,
    VersionInput,
    VoidTime,
)
from src.erp.projects.service import Service
from src.erp.projects.store import Store

from .identity import actor_and_capabilities

PREFIX = "/api/projects/v1"
STATES = {
    "projects": ["planned", "active", "delivered", "closed", "cancelled"],
    "tasks": ["todo", "in_progress", "blocked", "done", "cancelled"],
}


def discovery(resource):
    label = "Projects" if resource == "projects" else "Delivery tasks"
    fields = (
        [
            ("name", "Name", "primary"),
            ("state", "Status", "secondary"),
            ("customer_name", "Customer", "secondary"),
        ]
        if resource == "projects"
        else [
            ("name", "Title", "primary"),
            ("state", "Status", "secondary"),
            ("assignee_name", "Assignee", "secondary"),
            ("estimate_minutes", "Estimate (minutes)", "secondary"),
        ]
    )
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": resource,
            "label": label,
            "item_label": "record",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search delivery records",
                    "fields": ["name", "description"],
                },
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [
                            {"value": s, "label": s.replace("_", " ").title()}
                            for s in STATES[resource]
                        ],
                    }
                ],
                "ordering": [],
            },
            "columns": [
                {
                    "id": key.replace("_", "-"),
                    "header": name,
                    "value_path": key,
                    "data_type": "number" if key == "estimate_minutes" else "text",
                    "default_visible": True,
                    "hideable": key != "name",
                    "importance": importance,
                }
                for key, name, importance in fields
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False, install_identity=True):
    resolve_modules(["base", "projects"] if enabled else [])
    app = FastAPI(title="Projects and services API", version="0.1.0")
    app.state.projects_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)
        ba, bc = base_identity(local=local)

        def sales():
            from src.erp.projects.integrations import configured_sales

            return configured_sales(local=local)

        def finance():
            from src.erp.projects.integrations import configured_finance

            return configured_finance(local=local)

        return Service(
            app.state.projects_store,
            actor,
            caps,
            Dependencies(
                BaseService(BaseStore(local_only=local), ba, bc),
                sales if os.environ.get("PROJECTS_SALES_ENABLED", "true") != "false" else None,
                finance if os.environ.get("PROJECTS_FINANCE_ENABLED", "true") != "false" else None,
            ),
        )

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [ProjectsError, BaseError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Projects request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Projects storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "projects", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            svc = service()
            svc.require("projects.read")
            return {
                "status": "ready",
                "module": "projects",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": svc.store.data_source_uid,
                "dependencies": svc.dependencies.ready(),
                "capabilities": sorted(svc.capabilities),
                "sales_enabled": module_available("sales") and svc.dependencies.sales_factory is not None,
                "finance_enabled": module_available("finance") and svc.dependencies.finance_factory is not None,
            }

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
        ):
            svc = service()
            svc.require("projects.read")
            return svc.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/sales-orders/{uid}/")
        def sales_order(uid: UUID):
            svc = service()
            svc.require("projects.read")
            return svc.dependencies.sales().service_order(uid)

        @app.post(PREFIX + "/projects/from-sales/", status_code=201)
        def from_sales(payload: FromSales):
            return service().from_sales(payload.model_dump())

        @app.post(PREFIX + "/projects/", status_code=201)
        def project_create(payload: ProjectCreate):
            return service().save_project(
                payload.model_dump(exclude={"request_uid"}), request_uid=payload.request_uid
            )

        @app.put(PREFIX + "/projects/{uid}/")
        def project_update(uid: UUID, payload: ProjectUpdate):
            return service().save_project(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/projects/{uid}/bill/")
        def bill(uid: UUID, payload: BillInput):
            return service().bill(uid, payload.model_dump())

        @app.post(PREFIX + "/projects/{uid}/actions/{action}/")
        def project_action(uid: UUID, action: str, payload: VersionInput):
            return service().transition(uid, action, payload.expected_version)

        @app.post(PREFIX + "/tasks/", status_code=201)
        def task_create(payload: TaskCreate):
            return service().save_task(
                payload.model_dump(exclude={"request_uid", "expected_project_version"}),
                request_uid=payload.request_uid,
                expected_project_version=payload.expected_project_version,
            )

        @app.put(PREFIX + "/tasks/{uid}/")
        def task_update(uid: UUID, payload: TaskUpdate):
            return service().save_task(
                payload.model_dump(exclude={"expected_version", "expected_project_version"}),
                uid=uid,
                expected_version=payload.expected_version,
                expected_project_version=payload.expected_project_version,
            )

        @app.post(PREFIX + "/tasks/{uid}/state/")
        def task_state(uid: UUID, payload: TaskState):
            return service().task_state(uid, **payload.model_dump())

        @app.get(PREFIX + "/tasks/{uid}/time/")
        def history(
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
        ):
            return service().history(uid, page_index=page_index, page_size=page_size)

        @app.post(PREFIX + "/tasks/{uid}/time/", status_code=201)
        def log_time(uid: UUID, payload: TimeInput):
            return service().log_time(uid, payload.model_dump())

        @app.get(PREFIX + "/time-entries/{uid}/")
        def time_detail(uid: UUID):
            return service().row("time-entries", uid)

        @app.post(PREFIX + "/time-entries/{uid}/void/")
        def void_time(uid: UUID, payload: VoidTime):
            return service().void_time(uid, payload.model_dump())

        @app.get(PREFIX + "/audit/")
        def audit(resource: str, record_uid: UUID):
            svc = service()
            svc.require("projects.configure")
            return {
                "items": svc.store.read(
                    select(AuditEvent.__table__)
                    .where(AuditEvent.resource == resource, AuditEvent.record_uid == record_uid)
                    .order_by(AuditEvent.occurred_at.desc())
                    .limit(100)
                )
            }

        def mount(resource):
            prefix = PREFIX + "/" + resource

            @app.get(prefix + "/discovery/", name=resource + "-discovery")
            def describe():
                service().require("projects.read")
                return discovery(resource)

            @app.get(prefix + "/", name=resource + "-list")
            def collection(
                request: Request,
                page_index: int = Query(0, ge=0, le=100000),
                page_size: int = Query(25, ge=1, le=100),
                search: str = Query("", max_length=200),
                state: str | None = None,
                project_uid: UUID | None = None,
            ):
                if (
                    set(request.query_params)
                    - {"page_index", "page_size", "search", "state", "project_uid"}
                    or state
                    and state not in STATES[resource]
                ):
                    raise ProjectsError(422, "invalid_query", "Unsupported delivery query")
                return service().collection(
                    resource,
                    page_index=page_index,
                    page_size=page_size,
                    search=search,
                    state=state,
                    project_uid=project_uid,
                )

            @app.get(prefix + "/{uid}/", name=resource + "-detail")
            def detail(uid: UUID):
                return service().get(resource, uid)

        for resource in ["projects", "tasks"]:
            mount(resource)
    install_module_admission(app, "projects")
    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
