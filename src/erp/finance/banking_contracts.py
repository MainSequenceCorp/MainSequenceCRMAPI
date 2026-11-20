"""Finance's provider-independent intake wire contracts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .schemas import DecimalText, Input, Version

DIGEST = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
TOKEN = Annotated[str, Field(min_length=32, max_length=4096)]
KEY = Annotated[str, Field(min_length=1, max_length=128)]


class Transaction(Input):
    booking_status: Literal["booked", "pending"]
    booking_date: date | None
    value_date: date | None = None
    signed_amount: Annotated[
        str, Field(pattern=r"^-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", strict=True)
    ]
    currency_code: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    structured_reference: str | None = Field(default=None, max_length=140)
    end_to_end_reference: str | None = Field(default=None, max_length=140)
    remittance_text: str | None = Field(default=None, max_length=1024)
    counterparty_name: str | None = Field(default=None, max_length=250)
    counterparty_fingerprint: DIGEST | None = None
    correction: Literal["reversal", "correction"] | None = None

    @model_validator(mode="after")
    def validate_amount(self):
        if not Decimal(self.signed_amount) or (
            self.booking_status == "booked" and self.booking_date is None
        ):
            raise ValueError("Invalid booked bank movement")
        return self


class ProviderTransactionIdentity(Input):
    kind: Literal["provider_transaction"]
    digest: DIGEST


class Evidence(Input):
    connection_uid: UUID
    installation_uid: UUID
    statement_uid: UUID | None = None
    generation: Version
    binding_generation: Version
    actor_uid: UUID
    source_account_uid: UUID
    operating_company_uid: UUID
    adapter_key: KEY
    statement_sha256: DIGEST | None = None
    row_locator: int | None = Field(default=None, ge=1, strict=True)
    source_identity: ProviderTransactionIdentity | None = None
    evidence_sha256: DIGEST
    transaction: Transaction

    @model_validator(mode="after")
    def complete_source_identity(self):
        file_identity = (self.statement_uid, self.statement_sha256, self.row_locator)
        if self.source_identity is None and all(value is not None for value in file_identity):
            return self
        if self.source_identity is not None and all(value is None for value in file_identity):
            return self
        raise ValueError("Require one complete bank movement identity")

    @property
    def identity(self) -> tuple[str, str]:
        if self.source_identity is not None:
            return self.source_identity.kind, self.source_identity.digest
        return "statement_row", f"{self.statement_sha256}:{self.row_locator}"


class SourceAccount(Input):
    uid: UUID
    company_uid: UUID
    adapter_key: KEY
    masked_label: str = Field(max_length=128)
    currency_code: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    account_fingerprint: DIGEST
    requires_existing_account: bool = False


class SourceMapping(Input):
    binding: KEY
    source_account_uid: UUID
    bank_account_uid: UUID | None = None


class FenceChange(Input):
    binding: KEY
    action: Literal["open", "close"]
    actor_uid: UUID
    connection_uid: UUID
    installation_uid: UUID
    source_account_uid: UUID
    generation: Version
    binding_generation: Version
    operation_uid: UUID


class ResolveBankRows(Input):
    binding: KEY
    claim_tokens: list[TOKEN] = Field(min_length=1, max_length=50)
    party_uid: UUID | None = None


class ReviewedAllocation(Input):
    invoice_uid: UUID
    expected_version: Version
    amount: DecimalText


class Decision(Input):
    request_uid: UUID
    review_uid: UUID
    action: Literal[
        "record_evidence", "link_duplicate", "link_existing_payment", "post_customer_receipt"
    ]
    party_uid: UUID | None = None
    target_movement_uid: UUID | None = None
    target_payment_uid: UUID | None = None
    separate_movement_reason: str | None = Field(default=None, min_length=1, max_length=500)
    allocations: list[ReviewedAllocation] = Field(default_factory=list, max_length=25)
    reverses_movement_uid: UUID | None = None

    @model_validator(mode="after")
    def confirm_decision(self):
        if len({item.invoice_uid for item in self.allocations}) != len(self.allocations):
            raise ValueError("Each invoice can be allocated once per receipt")
        if self.action != "post_customer_receipt" and self.allocations:
            raise ValueError("Only a new receipt can create allocations")
        if (self.action == "link_duplicate") != bool(self.target_movement_uid):
            raise ValueError("Choose the reviewed duplicate movement")
        if (self.action == "link_existing_payment") != bool(self.target_payment_uid):
            raise ValueError("Choose the reviewed recorded payment")
        if self.action == "post_customer_receipt" and not self.party_uid:
            raise ValueError("Select a customer before posting a receipt")
        return self


class CommitBankRow(Decision):
    binding: KEY
    commit_claim: TOKEN
    expected_mapping_version: Version


class CommitSavedMovement(Decision):
    expected_movement_version: Version


class SaveCounterpartyAlias(Input):
    party_uid: UUID
    expected_movement_version: Version
    request_uid: UUID
