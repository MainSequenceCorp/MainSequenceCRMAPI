"""HTTP transport adapter for the shared CRM operation boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException, Request

from api.erp.crm.query import QueryError
from src.erp.base.service import BaseError
from src.erp.crm.contracts import DomainValidationError
from src.erp.crm.platform.catalog import configured_registry
from src.erp.crm.platform.local_runtime import build_local_services
from src.erp.crm.platform.runtime import authenticated_actor, request_port
from src.erp.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.erp.crm.services.operations import (
    AccessDenied,
    CRMContext,
    CRMOperations,
    ServiceUnavailable,
)
from src.erp.crm.services.transfers import ImportInputError

T = TypeVar("T")


def bind_local_crm_request(request: Request, signed_user) -> None:
    registry = configured_registry()
    policy, directory, bootstrap = build_local_services(signed_user=signed_user, registry=registry)
    request.state.crm_registry = registry
    request.state.crm_policy = policy
    request.state.crm_directory = directory
    request.state.crm_bootstrap = bootstrap


def context_for(request: Request) -> CRMContext:
    actor_uid = authenticated_actor()
    policy = request_port(request, "crm_policy")
    directory = request_port(request, "crm_directory")
    if policy is None or directory is None:
        raise HTTPException(status_code=503, detail="CRM policy or directory is unavailable")
    return CRMContext(actor_uid=actor_uid, policy=policy, directory=directory)


def service_for(request: Request) -> CRMOperations:
    return CRMOperations(
        context_for(request),
        resources=request_port(request, "crm_resources"),
        records=request_port(request, "crm_record_store"),
        bootstrap=request_port(request, "crm_bootstrap"),
        campaign_store=request_port(request, "crm_campaign_store"),
    )


def invoke(call: Callable[[], T], *, value_status: int = 422) -> T:
    try:
        return call()
    except BaseError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DomainValidationError as exc:
        field = exc.fields[0]["path"] if exc.fields else "payload"
        raise HTTPException(status_code=422, detail=f"Invalid {field or 'payload'}") from exc
    except ImportInputError as exc:
        raise HTTPException(status_code=413 if exc.too_large else 422, detail=str(exc)) from exc
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=value_status, detail=str(exc)) from exc
