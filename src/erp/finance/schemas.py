"""Strict Finance API inputs; decimal strings and explicit version fences."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DecimalText = Annotated[
    str, Field(pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]
Version = Annotated[int, Field(ge=1, strict=True)]
Reference = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,63}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LineInput(Input):
    description: str = Field(min_length=1, max_length=4000)
    quantity: DecimalText = "1"
    unit_price: DecimalText = "0"
    discount: DecimalText = "0"
    tax_rate: DecimalText = "0"

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive")
        return value

    @field_validator("discount", "tax_rate")
    @classmethod
    def percentage(cls, value):
        if Decimal(value) > 100:
            raise ValueError("Percentage must be between 0 and 100")
        return value


class DocumentInput(Input):
    name: Reference
    kind: Literal["customer", "vendor"] = "customer"
    party_uid: UUID
    operating_company_uid: UUID
    currency_uid: UUID
    document_date: date
    notes: str = Field(default="", max_length=4000)


class InvoiceInput(DocumentInput):
    due_date: date
    lines: list[LineInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def dates(self):
        if self.due_date < self.document_date:
            raise ValueError("Due date cannot precede invoice date")
        return self


class PaymentInput(DocumentInput):
    amount: DecimalText
    external_reference: str = Field(default="", max_length=200)

    @field_validator("amount")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Payment amount must be positive")
        return value


class InvoiceCreate(InvoiceInput):
    request_uid: UUID


class InvoiceUpdate(InvoiceInput):
    expected_version: Version


class PaymentCreate(PaymentInput):
    request_uid: UUID


class PaymentUpdate(PaymentInput):
    expected_version: Version


class VersionInput(Input):
    expected_version: Version


class VoidInput(VersionInput):
    reason: str = Field(min_length=1, max_length=1000)


class AllocationInput(Input):
    request_uid: UUID
    invoice_uid: UUID
    payment_uid: UUID
    amount: DecimalText
    expected_invoice_version: Version
    expected_payment_version: Version

    @field_validator("amount")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Allocation amount must be positive")
        return value


class ReverseAllocation(Input):
    expected_invoice_version: Version
    expected_payment_version: Version


class FromSalesInput(Input):
    request_uid: UUID
    order_uid: UUID
    expected_order_version: Version
    name: Reference
    document_date: date
    due_date: date
    tax_rate: DecimalText = "0"

    @field_validator("tax_rate")
    @classmethod
    def percentage(cls, value):
        if Decimal(value) > 100:
            raise ValueError("Tax percentage must be between 0 and 100")
        return value

    @model_validator(mode="after")
    def dates(self):
        if self.due_date < self.document_date:
            raise ValueError("Due date cannot precede invoice date")
        return self


class PurchaseBillInput(Input):
    request_uid: UUID
    name: Reference
    document_date: date
    due_date: date
    tax_rate: DecimalText = "0"
