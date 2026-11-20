"""Finance HTTP surface for source mapping, review, reconciliation and close-only recovery."""

from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Query, Request

from mainsequence.client import User
from src.erp.finance.banking import FENCE_PATH, WORKFLOW, Banking, change_fence
from src.erp.finance.banking_contracts import (
    CommitBankRow,
    CommitSavedMovement,
    FenceChange,
    ResolveBankRows,
    SaveCounterpartyAlias,
    SourceMapping,
)
from src.erp.finance.errors import FinanceError
from src.erp.user_preferences.admission import guard_active, lock_admission, require_integration
from src.erp.user_preferences.connector_registry import cleanup_registrations, local_target
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.identity import connector_request_person, require_workflow_admin
from src.erp.user_preferences.integrations import LOCAL_TOKEN_HEADER
from src.erp.user_preferences.scope import scope_for_request
from src.erp.user_preferences.store import configured_store

ROOT = "/api/finance/v1"


def authorize_peer(request, binding, actor, *, local):
    caller = UUID(str(User.get_logged_user().uid))
    if not local:
        return binding.workload_uid == caller
    if caller != actor:
        return False
    try:
        token = local_target(binding.release_uid).token
    except UserPreferencesError:
        return False
    return bool(
        token
        and compare_digest(request.headers.get(LOCAL_TOKEN_HEADER, "").encode(), token.encode())
    )


def banking_routes(service, store, *, local):
    router = APIRouter()

    def bank(request):
        return Banking(service(), scope_for_request(request, local=local), local=local)

    @router.get(ROOT + "/intake/")
    def discovery(request: Request):
        current = bank(request)
        current.finance.require("finance.read")
        company = current.finance.dependencies.get("operating-companies", current.company)
        currency = current.finance.dependencies.get("currencies", company["currency_uid"])
        return {
            "contract_version": "erp.intake@v1",
            "workflow": WORKFLOW,
            "currency_code": currency["code"],
            "operating_company_uid": current.company,
            "actions": [
                "record_evidence",
                "link_duplicate",
                "link_existing_payment",
                "post_customer_receipt",
            ],
        }

    @router.get(ROOT + "/bank-accounts/")
    def accounts(request: Request):
        return {"items": bank(request).accounts()}

    @router.post(ROOT + "/bank-accounts/source-mappings/", status_code=201)
    def save_mapping(request: Request, payload: SourceMapping):
        return bank(request).save_mapping(payload)

    @router.post(ROOT + "/intake/resolve/")
    def resolve(request: Request, payload: ResolveBankRows):
        return bank(request).resolve(payload)

    @router.post(ROOT + "/intake/commit/")
    def commit(request: Request, payload: CommitBankRow):
        return bank(request).commit(payload)

    @router.get(ROOT + "/intake/operations/{request_uid}/")
    def operation(request: Request, request_uid: UUID):
        return bank(request).operation_result(request_uid)

    @router.get(ROOT + "/bank-movements/")
    def movements(
        request: Request, bank_account_uid: UUID, page_index: int = Query(0, ge=0, le=100000)
    ):
        return {"items": bank(request).movements(bank_account_uid, page_index)}

    @router.post(ROOT + "/bank-movements/{movement_uid}/reconciliation/reviews/")
    def review_saved(request: Request, movement_uid: UUID, party_uid: UUID | None = None):
        return bank(request).review_movement(movement_uid, party_uid)

    @router.post(ROOT + "/bank-movements/{movement_uid}/reconciliation/")
    def commit_saved(request: Request, movement_uid: UUID, payload: CommitSavedMovement):
        return bank(request).commit_movement(movement_uid, payload)

    @router.post(ROOT + "/bank-movements/{movement_uid}/counterparty-alias/")
    def alias(request: Request, movement_uid: UUID, payload: SaveCounterpartyAlias):
        return bank(request).alias(movement_uid, payload)

    @router.post(FENCE_PATH)
    def grant_fence(request: Request, payload: FenceChange):
        scope = scope_for_request(request, local=local)
        connector, separator, workflow = payload.binding.partition(".")
        if not connector or not separator or workflow != WORKFLOW:
            raise FinanceError(403, "wrong_workflow", "Unsupported banking grant workflow")
        if payload.action == "open":
            policy = require_integration(scope, payload.binding, local=local)
            binding = policy["connector_binding"]
            allowed = (
                binding.workflow_key == WORKFLOW
                and binding.installation_uid == payload.installation_uid
                and binding.generation == payload.binding_generation
                and authorize_peer(request, binding, payload.actor_uid, local=local)
            )
            if not allowed:
                raise FinanceError(
                    403, "forbidden", "Only the approved Banking connector may open this grant"
                )
            require_workflow_admin(
                binding, lambda: connector_request_person(payload.actor_uid, scope, local=local)
            )
            Banking(service(), scope, local=local).mapping(
                payload.installation_uid, payload.source_account_uid
            )
            guards = guard_active(
                scope,
                ("finance",),
                store.data_source_uid,
                local=local,
                policy_version=policy["version"],
            )
        else:
            caller = UUID(str(User.get_logged_user().uid))
            previous = cleanup_registrations(
                configured_store(local=local, policy_only=True),
                scope,
                connector,
                payload.installation_uid,
                workload_uid=None if local else caller,
            )
            if not any(
                authorize_peer(request, binding, payload.actor_uid, local=local)
                for binding in previous
            ):
                raise FinanceError(
                    403, "forbidden", "No approved Banking connector can close this grant"
                )
            guards = [lock_admission(scope)]
        return change_fence(store, scope, payload, guards=guards, local=local)

    return router
