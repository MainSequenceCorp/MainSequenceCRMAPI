"""Pipeline HTTP routes with concrete Pydantic request bodies."""

from __future__ import annotations

from fastapi import APIRouter, Request


from api.erp.collections import collection_get
from api.erp.crm.route_support import _collection

router = APIRouter(prefix="/api/crm/v1/pipelines")


@collection_get(router, "/", name="list-pipelines")
def collection(request: Request):
    return _collection("pipelines", request)
