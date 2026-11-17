"""Independent workforce API with verified platform identity and strict commands."""

import logging
import os
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from api.erp.base.identity import actor_and_capabilities as base_identity
from mainsequence.server.fastapi import install_request_identity
from src.erp.base.service import BaseError
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.modules import resolve_modules
from src.erp.people.dependencies import Dependencies
from src.erp.people.errors import PeopleError
from src.erp.people.metatables import RESOURCES, AuditEvent
from src.erp.people.schemas import (
    AbsenceAction,
    AbsenceCreate,
    AbsenceUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeUpdate,
    StaffInput,
    VersionInput,
)
from src.erp.people.service import Service
from src.erp.people.store import Store

from .identity import actor_and_capabilities

PREFIX = "/api/people/v1"
LABELS = {"employees": "Employees", "departments": "Departments", "absences": "Absence requests"}
STATES = {
    "employees": ["active", "archived"],
    "departments": ["active", "archived"],
    "absences": ["draft", "submitted", "approved", "rejected", "cancelled"],
}


def discovery(resource):
    fields = [("name", "Name"), ("state", "Status")]
    fields += (
        [("job_title", "Job title"), ("company_name", "Company"), ("department_name", "Department")]
        if resource == "employees"
        else [("company_name", "Company")]
        if resource == "departments"
        else [("employee_name", "Employee"), ("start_date", "Start date"), ("end_date", "End date")]
    )
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
                "search": {"placeholder": "Search People records", "fields": ["name"]},
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [{"value": v, "label": v.title()} for v in STATES[resource]],
                    }
                ],
                "ordering": [],
            },
            "columns": [
                {
                    "id": k.replace("_", "-"),
                    "header": label,
                    "value_path": k,
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": k != "name",
                    "importance": "primary" if k == "name" else "secondary",
                }
                for k, label in fields
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False):
    resolve_modules(["base", "people"] if enabled else [])
    app = FastAPI(title="People API", version="0.1.0")
    app.state.people_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)
        ba, bc = base_identity(local=local)

        def projects():
            from src.erp.people.integrations import configured_projects

            return configured_projects(local=local)

        return Service(
            app.state.people_store,
            actor,
            caps,
            Dependencies(
                BaseService(BaseStore(local_only=local), ba, bc),
                projects if os.environ.get("PEOPLE_PROJECTS_ENABLED", "true") != "false" else None,
            ),
        )

    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    for error in [PeopleError, BaseError]:
        app.add_exception_handler(error, domain_error)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("People request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "People storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "people", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            svc = service()
            svc.require("people.read")
            return {
                "status": "ready",
                "module": "people",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": svc.store.data_source_uid,
                "dependencies": svc.dependencies.ready(),
                "capabilities": sorted(svc.capabilities),
                "actor_uid": str(svc.actor_uid),
                "projects_enabled": svc.dependencies.projects_factory is not None,
            }

        @app.get(PREFIX + "/references/{resource}/")
        def references(
            resource: str,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            operating_company_uid: UUID | None = None,
        ):
            svc = service()
            svc.require("people.read")
            if resource in {"employees", "departments"}:
                return svc.collection(
                    resource,
                    page_index=page_index,
                    page_size=page_size,
                    search=search,
                    state="active",
                    operating_company_uid=operating_company_uid,
                )
            return svc.dependencies.collection(
                resource, page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/project-tasks/{uid}/")
        def project_task(uid: UUID):
            svc = service()
            svc.require("people.read")
            return svc.dependencies.projects().get("tasks", uid)

        @app.post(PREFIX + "/employees/{uid}/staff/")
        def staff(uid: UUID, payload: StaffInput):
            return service().staff(uid, payload.model_dump())

        @app.post(PREFIX + "/departments/", status_code=201)
        def create_department(payload: DepartmentCreate):
            return service().save_department(
                payload.model_dump(exclude={"request_uid"}), request_uid=payload.request_uid
            )

        @app.put(PREFIX + "/departments/{uid}/")
        def update_department(uid: UUID, payload: DepartmentUpdate):
            return service().save_department(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/employees/", status_code=201)
        def create_employee(payload: EmployeeCreate):
            return service().save_employee(
                payload.model_dump(exclude={"request_uid"}), request_uid=payload.request_uid
            )

        @app.put(PREFIX + "/employees/{uid}/")
        def update_employee(uid: UUID, payload: EmployeeUpdate):
            return service().save_employee(
                payload.model_dump(exclude={"expected_version"}),
                uid=uid,
                expected_version=payload.expected_version,
            )

        @app.post(PREFIX + "/absences/", status_code=201)
        def create_absence(payload: AbsenceCreate):
            return service().save_absence(
                payload.model_dump(exclude={"request_uid", "expected_employee_version"}),
                request_uid=payload.request_uid,
                expected_employee_version=payload.expected_employee_version,
            )

        @app.put(PREFIX + "/absences/{uid}/")
        def update_absence(uid: UUID, payload: AbsenceUpdate):
            return service().save_absence(
                payload.model_dump(exclude={"expected_version", "expected_employee_version"}),
                uid=uid,
                expected_version=payload.expected_version,
                expected_employee_version=payload.expected_employee_version,
            )

        @app.post(PREFIX + "/absences/{uid}/actions/{action}/")
        def absence_action(uid: UUID, action: str, payload: AbsenceAction):
            return service().absence_action(uid, action, payload.model_dump())

        @app.post(PREFIX + "/{resource}/{uid}/actions/{action}/")
        def lifecycle(resource: str, uid: UUID, action: str, payload: VersionInput):
            return service().archive(resource, uid, action, payload.expected_version)

        @app.get(PREFIX + "/{resource}/discovery/")
        def discover(resource: str):
            svc = service()
            svc.require("people.read")
            if resource not in RESOURCES:
                raise PeopleError(404, "not_found", "Unknown People resource")
            return discovery(resource)

        @app.get(PREFIX + "/{resource}/{uid}/audit/")
        def audit(
            resource: str,
            uid: UUID,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
        ):
            svc = service()
            svc.row(resource, uid)
            terms = [AuditEvent.resource == resource, AuditEvent.record_uid == uid]
            total = svc.count(AuditEvent, *terms)
            items = svc.store.read(
                select(AuditEvent.__table__)
                .where(*terms)
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.uid)
                .offset(page_index * page_size)
                .limit(page_size),
                max_rows=page_size,
            )
            return {
                "items": items,
                "pageInfo": {
                    "pageIndex": page_index,
                    "pageSize": page_size,
                    "totalItems": total,
                    "hasNextPage": (page_index + 1) * page_size < total,
                    "hasPreviousPage": page_index > 0,
                },
            }

        @app.get(PREFIX + "/{resource}/{uid}/")
        def detail(resource: str, uid: UUID):
            return service().get(resource, uid)

        @app.get(PREFIX + "/{resource}/")
        def collection(
            resource: str,
            page_index: int = Query(0, ge=0, le=100000),
            page_size: int = Query(25, ge=1, le=100),
            search: str = Query("", max_length=200),
            state: str | None = Query(None, max_length=32),
            employee_uid: UUID | None = None,
            operating_company_uid: UUID | None = None,
        ):
            return service().collection(
                resource,
                page_index=page_index,
                page_size=page_size,
                search=search,
                state=state,
                employee_uid=employee_uid,
                operating_company_uid=operating_company_uid,
            )

    install_request_identity(app)
    return app


app = create_app()
