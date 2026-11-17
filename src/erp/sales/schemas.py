"""Strict Sales contracts; exact decimal strings, no caller-owned state/audit."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DecimalText = Annotated[
    str, Field(pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LineInput(Input):
    item_uid: UUID
    description: str = Field(default="", max_length=4000)
    quantity: DecimalText = "1"
    unit_price: DecimalText = "0"
    discount: DecimalText = "0"

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive")
        return value

    @field_validator("discount")
    @classmethod
    def percentage(cls, value):
        if Decimal(value) > 100:
            raise ValueError("Discount must be between 0 and 100")
        return value


class OrderInput(Input):
    name: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,63}$")
    customer_uid: UUID
    operating_company_uid: UUID
    currency_uid: UUID
    customer_reference: str = Field(default="", max_length=200)
    valid_until: date | None = None
    notes: str = Field(default="", max_length=4000)
    crm_deal_uid: UUID | None = None
    lines: list[LineInput] = Field(default_factory=list, max_length=100)


class CreateInput(OrderInput):
    request_uid: UUID


class UpdateInput(OrderInput):
    expected_version: int = Field(ge=1, strict=True)


class VersionInput(Input):
    expected_version: int = Field(ge=1, strict=True)
