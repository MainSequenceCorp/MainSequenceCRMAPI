"""Exact strict Inventory inputs; no caller-supplied result or identity fields."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Version = Annotated[int, Field(ge=1, strict=True)]
DecimalText = Annotated[
    str, Field(pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Create(Input):
    request_uid: UUID


class VersionInput(Input):
    expected_version: Version


class LocationInput(Input):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._-]{0,63}$")


class LocationCreate(LocationInput, Create):
    operating_company_uid: UUID
    usage: Literal["internal", "supplier", "customer", "adjustment"]


class LocationUpdate(LocationInput, VersionInput):
    pass


class StockItemCreate(Create):
    item_uid: UUID
    operating_company_uid: UUID
    unit_cost: DecimalText


class MovementCreate(Create):
    name: str = Field(min_length=1, max_length=200)
    stock_item_uid: UUID
    source_uid: UUID
    destination_uid: UUID
    quantity: DecimalText
    reason: str = Field(default="", max_length=2000)

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive")
        return value


class ReturnInput(VersionInput, Create):
    reason: str = Field(min_length=1, max_length=2000)


class FromSales(Create):
    order_uid: UUID
    line_uid: UUID
    expected_order_version: Version
    name: str = Field(min_length=1, max_length=200)
    stock_item_uid: UUID
    source_uid: UUID
    destination_uid: UUID
