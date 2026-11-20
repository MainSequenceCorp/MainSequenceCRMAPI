"""Finance documents, allocations, valuation reads, and saved bank evidence."""

from os import getenv
from typing import Literal
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from pydantic import Field

from api.erp.finance.main import service_for
from src.erp.finance.errors import FinanceError

from ..contracts import GetInput
from ..owner_routes import OwnerOperationError, OwnerResult, OwnerRoutes


class AllocationList(GetInput):
    resource: Literal["invoices", "payments"]
    page_index: int = Field(0, ge=0, le=100_000, strict=True)
    page_size: int = Field(25, ge=1, le=100, strict=True)


def _allocations(scope, args):
    current = service_for(scope.apps["finance"], local=scope.local)
    try:
        allocations = current.allocation_collection(
            args.resource, args.uid, page_index=args.page_index, page_size=args.page_size
        )
    except FinanceError as error:
        raise OwnerOperationError(error) from error
    return jsonable_encoder(allocations)


def _banking_configured(_scope):
    try:
        UUID(getenv("ERP_FINANCE_BANKING_COMPANY_UID", ""))
    except ValueError:
        return False
    return True


def register_tools(registry):
    finance = OwnerRoutes(registry, "finance", "finance/finance-documents")
    for resource, label in (
        ("invoices", "invoices and vendor bills"),
        ("payments", "recorded payments"),
    ):
        stem, path = f"finance_{resource}", f"/{resource}/"
        finance.read(f"{stem}_list", path, f"Find Finance {label}.", permission="read")
        finance.read(
            f"{stem}_get", path + "{uid}/", f"Read one of the {label} by UID.", permission="read"
        )
        finance.write(
            f"{stem}_create", "POST", path, f"Create a draft in {label}.", permission="write"
        )
        finance.write(
            f"{stem}_update",
            "PUT",
            path + "{uid}/",
            f"Edit a draft in {label}.",
            permission="write",
        )
    finance.write(
        "finance_invoices_create_from_sales",
        "POST",
        "/invoices/from-sales/",
        "Create one draft invoice from a confirmed Sales order and link both records atomically.",
        permission="write",
        required_modules=("sales",),
    )
    registry.read(
        "finance_allocations_list",
        description="List allocations for one invoice or payment UID.",
        owner="finance",
        capabilities=("finance.read",),
        skill="finance/finance-documents",
        inputs=AllocationList,
        output=OwnerResult,
        handler=_allocations,
    )
    finance.write(
        "finance_allocations_create",
        "POST",
        "/allocations/",
        "Allocate an amount between two posted documents using both expected versions.",
        permission="post",
    )
    finance.read(
        "finance_inventory_valuations_list",
        "/inventory-valuations/",
        "List Finance entries for inventory valuations.",
        permission="read",
    )
    finance.read(
        "finance_inventory_valuations_get",
        "/inventory-valuations/{uid}/",
        "Read the two posting legs for a valued stock movement.",
        permission="read",
    )

    bank = OwnerRoutes(registry, "finance", "finance/finance-bank-reconciliation")
    for name, path, description in (
        ("bank_accounts_list", "/bank-accounts/", "List masked Finance bank accounts."),
        (
            "bank_movements_list",
            "/bank-movements/",
            "List saved movements for one Finance bank account.",
        ),
        (
            "bank_reconciliation_operation_get",
            "/intake/operations/{request_uid}/",
            "Read the saved outcome for a Finance reconciliation operation.",
        ),
    ):
        bank.read(
            f"finance_{name}", path, description, permission="read", available=_banking_configured
        )
    bank.preview(
        "finance_bank_reconciliation_review",
        "/bank-movements/{movement_uid}/reconciliation/reviews/",
        "Prepare a review of a saved movement and possible invoice allocations for human confirmation.",
        permission="read",
        available=_banking_configured,
    )
