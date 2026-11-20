"""Thin HTTP adapters for the Outreach Sequences extension."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel

from src.erp.crm.campaigns.models import (
    AdvanceCommand,
    BlockCommand,
    CampaignCreate,
    CampaignPatch,
    CompleteCommand,
    GraphUpdate,
    GraphValidateRequest,
    ParticipantCreate,
    ParticipantPatch,
    ProgressRef,
    ReconcileCommand,
    ReportCommand,
    StepPromptCreate,
    StepPromptPatch,
    WaitCommand,
)
from src.erp.crm.models.common import VersionCommand

from .service_adapter import invoke, service_for

router = APIRouter(prefix="/extensions/outreach-sequences", tags=["Outreach Sequences"])


def mount_campaign_compatibility(application: FastAPI):
    """Serve the previous site's routes until it moves to Outreach Sequences."""
    for route in router.routes:
        if isinstance(route, APIRoute):
            path = route.path.removeprefix(router.prefix)
            if path.startswith("/sequences/"):
                path = "/campaigns/" + path.removeprefix("/sequences/")
            application.add_api_route(
                "/extensions/campaigns" + path,
                route.endpoint,
                methods=route.methods,
                status_code=route.status_code,
                include_in_schema=False,
            )


LIST_KEYS = {"page_index", "page_size", "search"}


def _filters(request: Request) -> dict[str, str]:
    return {key: value for key, value in request.query_params.items() if key not in LIST_KEYS}


def _list(method: str, request: Request, page_index: int, page_size: int, search: str | None):
    return invoke(
        lambda: getattr(service_for(request).campaigns, method)(
            page_index=page_index, page_size=page_size, search=search, filters=_filters(request)
        )
    )


def _call(method: str, request: Request, *args, **kwargs):
    return invoke(lambda: getattr(service_for(request).campaigns, method)(*args, **kwargs))


@router.get("/sequences/")
def list_sequences(request: Request, page_index: int = Query(0, ge=0), page_size: int = Query(25, ge=1, le=100),
                   search: str | None = Query(None, max_length=255)):
    return _list("list_campaigns", request, page_index, page_size, search)


@router.post("/sequences/", status_code=201)
def create_sequence(request: Request, payload: CampaignCreate):
    return _call("create_campaign", request, payload)


@router.get("/sequences/{uid}/")
def get_sequence(uid: uuid.UUID, request: Request):
    return _call("get_campaign", request, uid)


@router.patch("/sequences/{uid}/")
def update_sequence(uid: uuid.UUID, request: Request, payload: CampaignPatch):
    return _call("update_campaign", request, uid, payload)


@router.post("/sequences/{uid}/archive/")
def archive_sequence(uid: uuid.UUID, request: Request, payload: VersionCommand):
    return _call("archive_campaign", request, uid, payload.expected_version, archived=True)


@router.post("/sequences/{uid}/restore/")
def restore_sequence(uid: uuid.UUID, request: Request, payload: VersionCommand):
    return _call("archive_campaign", request, uid, payload.expected_version, archived=False)


@router.post("/sequences/{uid}/graph/validate/")
def validate_graph(uid: uuid.UUID, request: Request, payload: GraphValidateRequest):
    return _call("validate_candidate_graph", request, uid, payload)


@router.post("/sequences/{uid}/graph/")
def update_graph(uid: uuid.UUID, request: Request, payload: GraphUpdate):
    return _call("update_graph", request, uid, payload)


@router.get("/prompts/")
def list_step_prompts(request: Request, page_index: int = Query(0, ge=0), page_size: int = Query(25, ge=1, le=100),
                      search: str | None = Query(None, max_length=255)):
    return _list("list_step_prompts", request, page_index, page_size, search)


@router.post("/prompts/", status_code=201)
def create_step_prompt(request: Request, payload: StepPromptCreate):
    return _call("create_step_prompt", request, payload)


@router.get("/prompts/{uid}/")
def get_step_prompt(uid: uuid.UUID, request: Request):
    return _call("get_step_prompt", request, uid)


@router.patch("/prompts/{uid}/")
def update_step_prompt(uid: uuid.UUID, request: Request, payload: StepPromptPatch):
    return _call("update_step_prompt", request, uid, payload)


@router.get("/participants/")
def list_participants(request: Request, page_index: int = Query(0, ge=0), page_size: int = Query(25, ge=1, le=100),
                      search: str | None = Query(None, max_length=255)):
    return _list("list_participants", request, page_index, page_size, search)


@router.post("/participants/", status_code=201)
def create_participant(request: Request, payload: ParticipantCreate):
    return _call("create_participant", request, payload)


@router.get("/participants/{uid}/")
def get_participant(uid: uuid.UUID, request: Request):
    return _call("get_participant", request, uid)


@router.patch("/participants/{uid}/")
def update_participant(uid: uuid.UUID, request: Request, payload: ParticipantPatch):
    return _call("update_participant", request, uid, payload)


def _task_command(method: str, request: Request, payload: BaseModel):
    return _call(method, request, payload)


@router.post("/tasks/prepare/")
def prepare_task(request: Request, payload: ProgressRef):
    return _task_command("prepare", request, payload)


@router.post("/tasks/advance/")
def advance_task(request: Request, payload: AdvanceCommand):
    return _task_command("advance", request, payload)


@router.post("/tasks/complete/")
def complete_task(request: Request, payload: CompleteCommand):
    return _task_command("complete", request, payload)


@router.post("/tasks/wait/")
def wait_task(request: Request, payload: WaitCommand):
    return _task_command("wait", request, payload)


@router.post("/tasks/block/")
def block_task(request: Request, payload: BlockCommand):
    return _task_command("block", request, payload)


@router.post("/tasks/report/")
def report_task(request: Request, payload: ReportCommand):
    return _task_command("report", request, payload)


@router.post("/tasks/reconcile/")
def reconcile_task(request: Request, payload: ReconcileCommand):
    return _task_command("reconcile", request, payload)
