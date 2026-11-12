"""Thin email HTTP adapters; Google source operations stay under /extensions/google/."""

import json
import uuid

from fastapi import APIRouter, Request
from pydantic import ValidationError

from api.crm.google_routes import router as google_router
from api.crm.query import QueryError
from api.crm.query_models import CollectionQuery, DiscoveryQuery
from api.crm.service_adapter import invoke, service_for
from src.crm.emails.models import (
    EmailFilters,
    EmailQuery,
    FollowUp,
    GmailConversationImport,
    GmailConversationPreview,
    GmailImport,
    GmailMessagePreview,
    GmailSearch,
    ManualEmailCreate,
    StrictModel,
    SyncChoice,
)
from src.crm.emails.service import EmailOperations
from src.crm.platform.runtime import request_port

router = APIRouter(prefix="/api/crm/v1/email-messages")


def operations(request):
    service = service_for(request)
    return EmailOperations(service.context, resources=service.resources,
                           store=request_port(request, "crm_email_store"), google=getattr(request.app.state, "crm_google_service", None))


def parse_email_query(params, discovery=False):
    try:
        query = (DiscoveryQuery if discovery else CollectionQuery).model_validate(dict(params))
        filters = EmailFilters.model_validate(json.loads(query.filters))
        return EmailQuery(search=query.search, filters=filters, **({} if discovery else {
            "page_index": query.page_index, "page_size": query.page_size, "ordering": query.ordering or "-sent_at"}))
    except (ValidationError, ValueError, TypeError) as exc:
        raise QueryError("email query", "Unsupported query or filter") from exc


@router.get("/discovery/")
def discovery(request: Request):
    ops = operations(request)
    invoke(lambda: ops.context.require("crm.read"))
    invoke(lambda: parse_email_query(request.query_params, True))
    return {"contract": "command-center.resource_discovery@v1",
            "resource": {"id": "email-messages", "label": "Emails", "item_label": "Email", "identity": {"fields": ["uid"]}},
            "list": {"controls": {"search": {"placeholder": "Search email subject, people and body", "fields": ["subject", "sender", "body_text"]},
                                  "filters": [], "ordering": ["sent_at", "subject"]},
                     "columns": [{"id": key.replace("_", "-"), "header": label, "value_path": key, "data_type": kind,
                                  "importance": importance, "default_visible": True, "hideable": importance != "primary", **extra}
                                 for key, label, kind, importance, extra in [
                                     ("subject", "Email", "text", "primary", {"sortable_key": "subject"}),
                                     ("sender", "From", "json", "secondary", {}),
                                     ("sent_at", "Sent", "datetime", "secondary", {"sortable_key": "sent_at"}),
                                     ("source", "Source", "text", "tertiary", {})]]}, "bulk_actions": []}


@router.get("/")
def list_emails(request: Request):
    return invoke(lambda: operations(request).list(parse_email_query(request.query_params)))


@router.post("/", status_code=201)
def create_email(request: Request, payload: ManualEmailCreate):
    return invoke(lambda: operations(request).create(payload))


@router.get("/{uid}/")
def get_email(uid: uuid.UUID, request: Request):
    return invoke(lambda: operations(request).get(uid))


@router.post("/{uid}/follow-up/", status_code=201)
def follow_up(uid: uuid.UUID, request: Request, payload: FollowUp):
    return invoke(lambda: operations(request).follow_up(uid, payload))


@google_router.post("/email-search/")
def gmail_search(request: Request, payload: GmailSearch):
    return invoke(lambda: operations(request).search(payload))


@google_router.post("/email-previews/")
def gmail_preview(request: Request, payload: GmailMessagePreview):
    return invoke(lambda: operations(request).preview(payload))


@google_router.post("/email-imports/", status_code=201)
def gmail_import(request: Request, payload: GmailImport):
    return invoke(lambda: operations(request).import_message(payload))


@google_router.post("/email-conversation-previews/")
def conversation_preview(request: Request, payload: GmailConversationPreview):
    return invoke(lambda: operations(request).preview_conversation(payload))


@google_router.post("/email-conversation-imports/", status_code=201)
def conversation_import(request: Request, payload: GmailConversationImport):
    return invoke(lambda: operations(request).import_conversation(payload))


@google_router.post("/email-threads/{uid}/selection/")
def choose_sync(uid: uuid.UUID, request: Request, payload: SyncChoice):
    return invoke(lambda: operations(request).choose_sync(uid, payload))


@google_router.post("/email-threads/{uid}/sync/")
def sync_thread(uid: uuid.UUID, request: Request, payload: StrictModel):
    return invoke(lambda: operations(request).sync(uid))


@google_router.post("/email-sync/")
def sync_selected(request: Request, payload: StrictModel):
    return invoke(lambda: operations(request).sync_selected())
