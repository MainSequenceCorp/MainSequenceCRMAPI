"""Strict internal and customer contracts; no caller price/customer override."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Version = Annotated[int, Field(ge=1, strict=True)]
DecimalText = Annotated[
    str, Field(pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteInput(Input):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    body: str = Field(default="", max_length=5000)
    operating_company_uid: UUID
    currency_uid: UUID


class SiteCreate(SiteInput):
    request_uid: UUID


class SiteUpdate(SiteInput):
    expected_version: Version


class OfferInput(Input):
    site_uid: UUID
    item_uid: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit_price: DecimalText

    @field_validator("unit_price")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Price must be positive")
        return value


class OfferCreate(OfferInput):
    request_uid: UUID


class OfferUpdate(OfferInput):
    expected_version: Version


class VersionInput(Input):
    expected_version: Version


class GrantCreate(Input):
    request_uid: UUID
    site_uid: UUID
    customer_uid: UUID


class CheckoutLine(Input):
    offer_uid: UUID
    expected_version: Version
    quantity: DecimalText

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive")
        return value


class CheckoutCreate(Input):
    request_uid: UUID
    expected_site_version: Version
    lines: list[CheckoutLine] = Field(min_length=1, max_length=20)


class InvoiceInput(VersionInput):
    request_uid: UUID
    name: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,63}$")
    document_date: date
    due_date: date
    tax_rate: DecimalText = "0"

    @model_validator(mode="after")
    def valid(self):
        if self.due_date < self.document_date or Decimal(self.tax_rate) > 100:
            raise ValueError("Invalid dates or tax percentage")
        return self
