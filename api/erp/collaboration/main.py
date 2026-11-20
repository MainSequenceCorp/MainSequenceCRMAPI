"""Independent internal discussions with an optional record-owner access adapter."""

import logging
import os
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from mainsequence.server.fastapi import install_request_identity
from api.erp.collections import PageIndex, PageSize, SearchText
from src.erp.collaboration.dependencies import Dependencies
from src.erp.collaboration.errors import CollaborationError
from src.erp.collaboration.schemas import (
    DiscussionCreate,
    DiscussionUpdate,
    MessageCreate,
    MessageEdit,
    MessageRetract,
    VersionInput,
)
from src.erp.collaboration.service import Service
from src.erp.collaboration.store import Store
from src.erp.module_access import module_available
from src.erp.module_access.http import install_module_admission
from src.erp.modules import resolve_modules

from .identity import actor_and_capabilities, actor_name

PREFIX = "/api/collaboration/v1"


def discovery():
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": "discussions",
            "label": "Discussions",
            "item_label": "discussion",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {
                    "placeholder": "Search discussion subjects",
                    "fields": ["name", "description"],
                },
                "filters": [
                    {
                        "key": "state",
                        "label": "Status",
                        "type": "select",
                        "options": [
                            {"value": s, "label": s.title()} for s in ["open", "closed", "archived"]
                        ],
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
                for key, label in [
                    ("name", "Subject"),
                    ("state", "Status"),
                    ("description", "Description"),
                ]
            ],
        },
        "bulk_actions": [],
    }


def create_app(*, enabled=True, local=False, install_identity=True):
    resolve_modules(["collaboration"] if enabled else [])
    app = FastAPI(title="Collaboration API", version="0.1.0")
    app.state.collaboration_store = Store(local_only=local)

    def service():
        actor, caps = actor_and_capabilities(local=local)

        def projects():
            from src.erp.collaboration.integrations import configured_projects

            return configured_projects(local=local)

        return Service(
            app.state.collaboration_store,
            actor,
            caps,
            Dependencies(
                projects
                if os.environ.get("COLLABORATION_PROJECTS_ENABLED", "true") != "false"
                else None
            ),
            actor_name=actor_name(),
        )

    @app.exception_handler(CollaborationError)
    async def domain_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        logging.getLogger(__name__).exception("Collaboration request failed", exc_info=error)
        return JSONResponse(
            {
                "error": {
                    "code": "unavailable",
                    "message": "Collaboration storage or identity is unavailable. Check readiness before retrying.",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "running", "module": "collaboration", "enabled": enabled}

    if enabled:

        @app.get(PREFIX + "/ready/")
        def ready():
            svc = service()
            svc.require("collaboration.read")
            return {
                "status": "ready",
                "module": "collaboration",
                "local": local,
                "schema_revision": "0001",
                "data_source_uid": svc.store.data_source_uid,
                "capabilities": sorted(svc.capabilities),
                "actor_uid": str(svc.actor_uid),
                "projects_enabled": module_available("projects") and svc.dependencies.projects_factory is not None,
            }

        @app.get(PREFIX + "/references/projects/")
        def projects(
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
            search: SearchText = "",
        ):
            svc = service()
            svc.require("collaboration.read")
            return svc.dependencies.projects().collection(
                page_index=page_index, page_size=page_size, search=search
            )

        @app.get(PREFIX + "/discussions/discovery/")
        def discover():
            service().require("collaboration.read")
            return discovery()

        @app.get(PREFIX + "/discussions/")
        def collection(
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
            search: SearchText = "",
            state: str | None = Query(None, max_length=32),
            project_uid: UUID | None = None,
        ):
            return service().collection(
                page_index=page_index,
                page_size=page_size,
                search=search,
                state=state,
                project_uid=project_uid,
            )

        @app.post(PREFIX + "/discussions/", status_code=201)
        def create(payload: DiscussionCreate):
            return service().create(payload.model_dump())

        @app.get(PREFIX + "/discussions/{uid}/")
        def get(uid: UUID):
            return service().get(uid)

        @app.put(PREFIX + "/discussions/{uid}/")
        def edit(uid: UUID, payload: DiscussionUpdate):
            return service().edit(
                uid, payload.model_dump(exclude={"expected_version"}), payload.expected_version
            )

        @app.post(PREFIX + "/discussions/{uid}/actions/{action}/")
        def action(uid: UUID, action: str, payload: VersionInput):
            return service().transition(uid, action, payload.expected_version)

        @app.get(PREFIX + "/discussions/{uid}/messages/")
        def messages(
            uid: UUID,
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
        ):
            return service().messages(uid, page_index=page_index, page_size=page_size)

        @app.post(PREFIX + "/discussions/{uid}/messages/", status_code=201)
        def post(uid: UUID, payload: MessageCreate):
            return service().post(uid, payload.model_dump())

        @app.get(PREFIX + "/messages/{uid}/")
        def message(uid: UUID):
            return service().message(uid)

        @app.put(PREFIX + "/messages/{uid}/")
        def edit_message(uid: UUID, payload: MessageEdit):
            return service().edit_message(uid, payload.model_dump())

        @app.post(PREFIX + "/messages/{uid}/retract/")
        def retract(uid: UUID, payload: MessageRetract):
            return service().retract(uid, payload.model_dump())

        @app.get(PREFIX + "/messages/{uid}/revisions/")
        def revisions(
            uid: UUID,
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
        ):
            return service().revisions(uid, page_index=page_index, page_size=page_size)

        @app.get(PREFIX + "/discussions/{uid}/audit/")
        def audit(
            uid: UUID,
            page_index: PageIndex = 0,
            page_size: PageSize = 25,
        ):
            return service().history(uid, page_index=page_index, page_size=page_size)

    install_module_admission(app, "collaboration")
    if install_identity:
        install_request_identity(app)
    return app


app = create_app()
